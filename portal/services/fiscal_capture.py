"""Fila adicional; os NSUs de NF-e existentes não são alterados."""
import hashlib,uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q,F
from django.utils import timezone
from portal.models import FiscalConnector,FiscalStream,FiscalConsultation,FiscalEnvelope,FiscalDelivery,AuditEntry
from .sefaz import SefazError,SefazBusy
from .sefaz_transport import load_identity
from .fiscal_transport import CteTransport,NfseTransport
from .fiscal_import import classify,import_fiscal
from .nfse_compat import REVISION,identify
from .fiscal_transport import xml_read
from .capture_policy import idle_interval, page_interval


def _save_documents(stream,batch):
    for nsu,name,payload in batch.documents:
        if not nsu or not nsu.isdecimal():raise SefazError('NSU do documento inválido.')
        digest=hashlib.sha256(payload).hexdigest()
        doc,created=FiscalEnvelope.objects.get_or_create(stream=stream,nsu=nsu,defaults={'schema_name':name,'xml_content':payload.decode('utf-8'),'content_hash':digest,'kind':classify(payload,stream.service)})
        if not created and doc.content_hash!=digest:raise SefazError('NSU repetido com conteúdo divergente. Cursor preservado.')


@transaction.atomic
def recover_fiscal_response(config,stream):
    current=FiscalStream.objects.select_for_update().get(pk=stream.pk)
    if current.lease_until and current.lease_until>timezone.now():return False
    attempt=current.consultations.first()
    if not attempt or not attempt.response_content or attempt.http_status!=200 or attempt.cursor_sent!=current.cursor or (attempt.completed_at and not attempt.error):return False
    transport=CteTransport() if config.service=='cte' else NfseTransport()
    batch=transport.parse(attempt.response_content.encode('utf-8'),config.environment,current.cursor)
    if not batch.accepted or int(batch.cursor)<=int(current.cursor):return False
    _save_documents(current,batch)
    current.cursor=batch.cursor;current.max_cursor=batch.maximum;current.last_status=batch.status;current.last_reason=batch.reason;current.last_accepted_at=timezone.now()
    current.lease_token=None;current.lease_until=None
    current.next_attempt_at=max(current.next_attempt_at or timezone.now(),timezone.now()+idle_interval())
    current.save()
    attempt.status=batch.status;attempt.reason=batch.reason;attempt.cursor_received=batch.cursor;attempt.error='';attempt.completed_at=timezone.now();attempt.counts={'received':len(batch.documents),'recovered_local':True};attempt.save()
    AuditEntry.objects.create(workspace=config.company.workspace,description=f'Resposta {config.service} preservada recuperada localmente, sem repetir HTTP ou reduzir espera.')
    stream.refresh_from_db();return True


def requirements(config):
    from .company_status import capture_block_reason
    reason=capture_block_reason(config.company)
    if reason:raise SefazError(reason)
    if not config.enabled or not config.authorized_at:raise SefazError('Autorize e habilite este conector na aplicação.')
    if config.company.workspace.capture_paused:raise SefazError('Captura pausada pela administração.')
    if config.service not in {'nfse','cte'} or config.environment not in {'1','2'}:raise SefazError('Conector ou ambiente inválido.')
    if config.service=='cte' and not config.uf_author:raise SefazError('Informe a UF do autor para CT-e.')
    load_identity(config.company)


def deliver(stream,only_connector=None):
    configs=FiscalConnector.objects.select_related('company__workspace').filter(company__cnpj=stream.cnpj,service=stream.service,environment=stream.environment,enabled=True,authorized_at__isnull=False,company__workspace__capture_paused=False,company__deactivated_at__isnull=True,company__workspace__access_status='active',company__workspace__owner__is_active=True)
    if only_connector is not None:configs=configs.filter(pk=only_connector.pk)
    for config in configs:
        try:requirements(config)
        except SefazError as e:
            FiscalConnector.objects.filter(pk=config.pk).update(last_error=str(e)[:500]);continue
        new=stream.envelopes.exclude(deliveries__connector=config).values('pk')
        retry=config.deliveries.exclude(error='').filter(Q(next_retry_at__isnull=True)|Q(next_retry_at__lte=timezone.now())|~Q(processor_revision=REVISION)).values('envelope_id')
        pending=stream.envelopes.filter(Q(pk__in=new)|Q(pk__in=retry))
        for envelope in pending.iterator():
            try:
                with transaction.atomic():
                    if envelope.kind=='unknown':raise SefazError('Padrão ainda sem importador. Documento capturado e preservado; interpretação pendente.')
                    document=import_fiscal(config,envelope)
                    partial=document is not None and document.validation_status=='partial'
                    FiscalDelivery.objects.update_or_create(connector=config,envelope=envelope,defaults={'document':document,'error':'Importação parcial: revisar estrutura e assinatura. Não incluída nos totais fiscais validados.' if partial else '',
                        'next_retry_at':timezone.now()+timedelta(hours=24) if partial else None,'processing_status':'partial' if partial else 'validated' if document else 'event',
                        'diagnostics':document.validation_details if partial else {},'processor_revision':REVISION,'last_processed_at':timezone.now()})
                if document and document.service=='nfse':
                    # Fora da transação de importação e sem afetar a entrega.
                    try:
                        from .nfse_official_pdf import retrieve_if_configured
                        retrieve_if_configured(document)
                    except Exception:pass
            except SefazError as e:
                try:diagnostics=identify(xml_read(envelope.xml_content.encode()))
                except SefazError:diagnostics={'pattern':'xml_invalido'}
                FiscalDelivery.objects.update_or_create(connector=config,envelope=envelope,defaults={'error':str(e)[:500],'next_retry_at':timezone.now()+timedelta(hours=1),
                    'processing_status':'unsupported' if envelope.kind=='unknown' else 'pending','diagnostics':diagnostics,'processor_revision':REVISION,'last_processed_at':timezone.now()})
            except Exception:
                FiscalDelivery.objects.update_or_create(connector=config,envelope=envelope,defaults={'error':'Falha local de importação. Original preservado; requer revisão.','next_retry_at':timezone.now()+timedelta(hours=1)})
        # Reaplicar eventos também após importar nota que chegou em lote posterior.
        for envelope in stream.envelopes.filter(kind='event').iterator():
            try:import_fiscal(config,envelope)
            except SefazError:pass


def run_connector(config,transport=None):
    requirements(config)
    stream,_=FiscalStream.objects.get_or_create(cnpj=config.company.cnpj,service=config.service,environment=config.environment)
    recover_fiscal_response(config,stream)
    deliver(stream)
    now=timezone.now()
    # Resultado de processo interrompido é incerto: nunca repetir imediatamente.
    if stream.lease_token and stream.lease_until and stream.lease_until<=now:
        safe=max(now,stream.lease_until)+idle_interval()
        FiscalStream.objects.filter(pk=stream.pk,lease_token=stream.lease_token,lease_until__lte=now).update(lease_token=None,lease_until=None,next_attempt_at=safe,last_reason='Execução anterior interrompida; resultado remoto incerto.')
        stream.refresh_from_db()
    token=uuid.uuid4()
    claimed=FiscalStream.objects.filter(pk=stream.pk).filter(Q(next_attempt_at__isnull=True)|Q(next_attempt_at__lte=now)).filter(Q(lease_until__isnull=True)|Q(lease_until__lte=now)).update(lease_token=token,lease_until=now+timedelta(minutes=5),last_attempt_at=now)
    if not claimed:raise SefazBusy('Aguardando intervalo ou consulta em andamento neste serviço.')
    stream.refresh_from_db()
    attempt=FiscalConsultation.objects.create(stream=stream,cursor_sent=stream.cursor)
    transport=transport or (CteTransport() if config.service=='cte' else NfseTransport())
    try:
        http,payload=transport.fetch(config,stream.cursor)
        attempt.http_status=http;attempt.response_content=payload.decode('utf-8-sig',errors='replace');attempt.save(update_fields=['http_status','response_content'])
        batch=transport.parse(payload,config.environment,stream.cursor)
        # O contrato ADN usa HTTP 404 + E2220/status explícito para fim da fila.
        # Essa combinação sem documentos é espera normal, não falha de acesso.
        accepted=batch.accepted and (http==200 or (config.service=='nfse' and http==404 and batch.status=='NENHUM_DOCUMENTO_LOCALIZADO' and not batch.documents))
        attempt.status=batch.status;attempt.reason=batch.reason;attempt.cursor_received=batch.cursor
        with transaction.atomic():
            current=FiscalStream.objects.select_for_update().get(pk=stream.pk)
            if current.lease_token!=token or current.lease_until<=timezone.now():raise SefazBusy('Reserva expirada. Resposta preservada; cursor não alterado.')
            if accepted:
                _save_documents(current,batch)
                if int(batch.cursor)<int(current.cursor):raise SefazError('Cursor retornado retrocede. Progresso preservado.')
                current.cursor=batch.cursor;current.max_cursor=batch.maximum;current.last_accepted_at=timezone.now()
            current.last_status=batch.status;current.last_reason=batch.reason
            reference=max(timezone.now(),batch.official_at) if batch.official_at and timezone.is_aware(batch.official_at) else timezone.now()
            current.next_attempt_at=reference+idle_interval() if batch.end or not accepted else reference+page_interval()
            current.lease_token=None;current.lease_until=None;current.save()
        attempt.counts={'received':len(batch.documents)};attempt.completed_at=timezone.now();attempt.save()
        FiscalConnector.objects.filter(pk=config.pk).update(last_error='' if accepted else batch.reason)
        deliver(current)
        return batch
    except Exception as error:
        message=str(error)[:500] if isinstance(error,SefazError) else 'Falha local no processamento do conector; resposta preservada quando recebida.'
        FiscalStream.objects.filter(pk=stream.pk,lease_token=token).update(lease_token=None,lease_until=None,next_attempt_at=timezone.now()+idle_interval(),last_reason=message)
        attempt.completed_at=timezone.now();attempt.error=message;attempt.save()
        FiscalConnector.objects.filter(pk=config.pk).update(last_error=message)
        raise SefazError(message) from None


def run_due_connectors(company_id=None,limit=20):
    configs=FiscalConnector.objects.select_related('company__workspace').filter(enabled=True,authorized_at__isnull=False,company__workspace__capture_paused=False,company__deactivated_at__isnull=True,company__workspace__access_status='active',company__workspace__owner__is_active=True).order_by(F('last_checked_at').asc(nulls_first=True),'pk')
    if company_id:configs=configs.filter(company_id=company_id)
    seen=set();cycle_started=timezone.now()
    for config in configs[:limit]:
        FiscalConnector.objects.filter(pk=config.pk).update(last_checked_at=timezone.now())
        stream=FiscalStream.objects.filter(cnpj=config.company.cnpj,service=config.service,environment=config.environment).first()
        identity=(config.company.cnpj,config.service,config.environment)
        if identity in seen:
            if stream and stream.envelopes.exclude(deliveries__connector=config).exists():deliver(stream,only_connector=config)
            continue
        latest=stream.consultations.only('completed_at','error').first() if stream else None
        if stream and latest and (not latest.completed_at or latest.error):
            try:
                requirements(config)
                recover_fiscal_response(config,stream)
            except SefazError as error:
                FiscalConnector.objects.filter(pk=config.pk).update(last_error=str(error)[:500]);continue
        if stream and ((stream.next_attempt_at and stream.next_attempt_at>timezone.now()) or (stream.lease_until and stream.lease_until>timezone.now())):
            if stream.envelopes.exclude(deliveries__connector=config).exists() or config.deliveries.exclude(error='').filter(Q(next_retry_at__isnull=True)|Q(next_retry_at__lte=timezone.now())|~Q(processor_revision=REVISION)).exists():deliver(stream)
            continue
        try:
            run_connector(config);seen.add(identity)
        except SefazError:
            if FiscalStream.objects.filter(cnpj=config.company.cnpj,service=config.service,environment=config.environment,last_attempt_at__gte=cycle_started).exists():seen.add(identity)
        except Exception:
            FiscalConnector.objects.filter(pk=config.pk).update(last_error='Falha local neste conector. Outros serviços continuam independentes; confira os documentos preservados.')
