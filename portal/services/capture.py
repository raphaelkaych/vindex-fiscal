"""Captura durável por CNPJ, com consentimento, limites e entregas por cliente.

Somente o worker importa o transporte de rede. Nenhuma autorização de leitura
permite emitir eventos fiscais; manifestação tem autorização própria.
"""
import uuid
from datetime import timedelta
from .capture_policy import idle_interval

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, DateTimeField, Exists, F, OuterRef, Q, Value, When
from django.utils import timezone

from portal.models import AuditEntry, Company, DigitalCertificate
from portal.sefaz_models import (
    SefazCaptureConfig, SefazConsultation, SefazDistributionStream,
    SefazDocument, SefazStreamDocument, SefazSyncState,
)
from portal.services.invoices import InvoiceImportError, import_invoice, parse_nfe
from portal.services.sefaz import (
    HOUR, LEASE_SECONDS, MAX_RESPONSE_BYTES, SefazBusy, SefazError, SefazNotConfigured,
    SefazRejected, distribution_metadata, parse_distribution,
)

UF_CODES = {'11', '12', '13', '14', '15', '16', '17', '21', '22', '23',
            '24', '25', '26', '27', '28', '29', '31', '32', '33', '35',
            '41', '42', '43', '50', '51', '52', '53'}


def _company(workspace, company_id):
    company = Company.objects.select_related('workspace').filter(
        workspace=workspace, pk=company_id).first()
    if company is None:
        raise SefazError('A empresa não está disponível para este acesso.')
    return company


def _requirements(company, config):
    from .company_status import capture_block_reason
    reason=capture_block_reason(company)
    if reason:raise SefazNotConfigured(reason)
    if not config.enabled:
        raise SefazNotConfigured('A captura está desativada. Habilite a leitura na página de captura SEFAZ.')
    if not config.read_authorized_at:
        raise SefazNotConfigured('Autorize a consulta de leitura desta empresa na aplicação.')
    if config.environment not in {'1', '2'}:
        raise SefazNotConfigured('Selecione um ambiente SEFAZ válido.')
    if config.uf_author and config.uf_author not in UF_CODES:
        raise SefazNotConfigured('A UF do autor da consulta é inválida. Corrija a configuração de captura.')
    certificate = DigitalCertificate.objects.filter(company=company).first()
    if certificate is None:
        raise SefazNotConfigured('Vincule um certificado A1 válido desta raiz de CNPJ.')
    if certificate.is_demo:
        raise SefazNotConfigured('O certificado de demonstração não permite consultar o serviço oficial.')
    if certificate.valid_until <= timezone.now():
        raise SefazNotConfigured('O certificado A1 venceu. Renove-o para retomar a captura.')
    if certificate.valid_from > timezone.now():
        raise SefazNotConfigured('A validade do certificado A1 ainda não começou.')
    if certificate.holder_cnpj[:8] != company.cnpj[:8]:
        raise SefazNotConfigured('O certificado A1 pertence a outra raiz de CNPJ.')
    return certificate


def _config_error(config, message, code='requirements'):
    config.last_checked_at = timezone.now()
    config.last_error = message[:500]
    config.last_error_code = code[:40]
    config.save(update_fields=['last_checked_at', 'last_error', 'last_error_code', 'updated_at'])


@transaction.atomic
def configure_capture(workspace, company_id, enabled=True, environment='1',
                      actor=None, authorize_read=False, uf_author=''):
    """Salva consentimento e agenda; nunca faz HTTP durante a requisição web."""
    company = _company(workspace, company_id)
    if actor is not None and actor.pk != workspace.owner_id:
        raise SefazError('Somente o titular deste espaço pode autorizar a captura.')
    if environment not in {'1', '2'}:
        raise SefazError('Ambiente SEFAZ inválido.')
    if uf_author and uf_author not in UF_CODES:
        raise SefazError('Selecione uma UF válida para o autor da consulta.')
    config, _ = SefazCaptureConfig.objects.get_or_create(company=company)
    # Consentimento de homologação não autoriza produção implicitamente.
    if enabled and (not config.read_authorized_at or config.environment != environment) and not authorize_read:
        raise SefazError('Confirme a autorização de leitura no ambiente selecionado.')
    if authorize_read:
        config.read_authorized_at = timezone.now()
        config.authorized_by = actor
    config.enabled = bool(enabled)
    config.environment = environment
    config.uf_author = uf_author
    config.last_error = ''
    config.last_error_code = ''
    config.save()
    AuditEntry.objects.create(workspace=workspace, description=(
        f'Captura SEFAZ {"habilitada" if enabled else "desativada"}: '
        f'{company.display_name}; ambiente {environment}; somente leitura')[:250])
    if enabled:
        schedule_company(company)
    return config


def schedule_company(company):
    """Upload/renovação retoma a fila persistente sem reiniciar NSU ou cooldown."""
    config = SefazCaptureConfig.objects.filter(company=company).first()
    if config is None:
        return None
    if not config.enabled:
        return config
    try:
        _requirements(company, config)
    except SefazError as error:
        _config_error(config, str(error))
        return config
    SefazSyncState.objects.get_or_create(company=company, environment=config.environment, source='sefaz')
    _config_error(config, '', '')
    return config


@transaction.atomic
def _stream(company, environment, source):
    # Migra o cursor de uma eventual execução anterior da mesma pessoa jurídica.
    # Novas renovações/cadastros nunca reiniciam o progresso do consumidor.
    previous = SefazSyncState.objects.filter(
        company__cnpj=company.cnpj, environment=environment, source=source)
    last = previous.order_by('-last_nsu').first()
    cooldown = previous.exclude(next_attempt_at=None).order_by('-next_attempt_at').first()
    defaults = {}
    if last is not None:
        defaults.update(last_nsu=last.last_nsu, max_nsu=last.max_nsu)
    if cooldown is not None:
        defaults['next_attempt_at'] = cooldown.next_attempt_at
    stream, created = SefazDistributionStream.objects.get_or_create(
        cnpj=company.cnpj, environment=environment, source=source, defaults=defaults)
    if created:
        for doc in SefazDocument.objects.filter(state__in=previous).iterator():
            stream_doc, _ = SefazStreamDocument.objects.get_or_create(
                stream=stream, content_hash=doc.content_hash,
                defaults={field: getattr(doc, field) for field in (
                    'kind', 'nsu', 'schema_name', 'access_key', 'event_type', 'xml_content')})
            SefazDocument.objects.filter(pk=doc.pk).update(stream_document=stream_doc)
    return stream


@transaction.atomic
def _recover_orphan(stream, now=None):
    """Processo morto durante HTTP tem resultado incerto, mesmo após o lease.

    O CAS pelo token impede que um processo atrasado limpe uma reserva nova.
    Não acrescenta outra hora se a espera da tentativa original já terminou.
    """
    now = now or timezone.now()
    if (stream.source != 'sefaz' or stream.lease_token is None
            or stream.lease_until is None or stream.lease_until > now):
        return False
    attempt_at = stream.last_attempt_at or stream.lease_until
    safe_at = attempt_at + HOUR
    message = ('A execução anterior foi interrompida antes de registrar um resultado completo. '
        'O resultado oficial é incerto. O progresso foi preservado; aguarde a próxima consulta permitida.')
    recovered = SefazDistributionStream.objects.filter(pk=stream.pk, source='sefaz',
        lease_token=stream.lease_token, lease_until__lte=now).update(
            lease_token=None, lease_until=None, next_attempt_at=Case(
                When(next_attempt_at__gt=safe_at, then=F('next_attempt_at')),
                default=Value(safe_at), output_field=DateTimeField()),
            failure_count=F('failure_count') + 1, last_error=message)
    stream.refresh_from_db()
    if not recovered:
        return False
    # Uma consulta interrompida não se transforma numa resposta oficial. Apenas
    # evidências já gravadas no XML privado permitem preencher cStat/xMotivo.
    interrupted = SefazConsultation.objects.filter(state__company__cnpj=stream.cnpj,
        state__environment=stream.environment, state__source='sefaz',
        completed_at__isnull=True, requested_at__gte=attempt_at,
        requested_at__lte=attempt_at + timedelta(seconds=LEASE_SECONDS))
    for consultation in interrupted:
        if consultation.response_xml:
            try:
                metadata = distribution_metadata(consultation.response_xml.encode('utf-8'), stream.environment)
                consultation.status = metadata['status']
                consultation.reason = metadata['reason']
                consultation.official_response_at = metadata['responded_at']
                consultation.reported_nsu = metadata['last_nsu']
                consultation.max_nsu = metadata['max_nsu']
            except SefazError:
                pass
        consultation.completed_at = now
        consultation.error_code = 'interrupted'
        consultation.error = message
        consultation.save(update_fields=['completed_at', 'error_code', 'error',
            'status', 'reason', 'official_response_at', 'reported_nsu', 'max_nsu'])
    SefazSyncState.objects.filter(company__cnpj=stream.cnpj, environment=stream.environment,
        source='sefaz').update(last_error=message, next_attempt_at=stream.next_attempt_at,
            failure_count=stream.failure_count, updated_at=now)
    return True


def _claim(stream):
    stream.refresh_from_db()
    _recover_orphan(stream)
    now = timezone.now()
    token = uuid.uuid4()
    claimed = SefazDistributionStream.objects.filter(pk=stream.pk).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lte=now)).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).update(
            lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS),
            last_attempt_at=now)
    if not claimed:
        raise SefazBusy('A consulta deste CNPJ está em andamento ou aguardando o intervalo permitido pela SEFAZ.')
    stream.refresh_from_db()
    return token


def _counts(documents):
    result = {kind: 0 for kind in ('summary', 'invoice', 'event', 'event_summary', 'unknown')}
    result['imported'] = 0
    for doc in documents:
        result[doc.kind] += 1
    return result


@transaction.atomic
def _store_response(stream, token, response):
    now = timezone.now()
    current = SefazDistributionStream.objects.select_for_update().get(pk=stream.pk)
    if current.lease_token != token or not current.lease_until or current.lease_until <= now:
        raise SefazBusy('A execução perdeu sua reserva. O cursor não foi alterado.')
    accepted = response.status in {'137', '138'}
    if accepted and int(response.last_nsu) < int(current.last_nsu):
        raise SefazError('O retorno retrocede o NSU. O progresso foi preservado e exige revisão.')
    for doc in response.documents:
        existing = current.documents.filter(nsu=doc.nsu).first() if doc.nsu else None
        if existing is not None and existing.content_hash != doc.content_hash:
            raise SefazError('A SEFAZ devolveu conteúdo diferente para um NSU já armazenado. Revise a distribuição.')
        stored, created = SefazStreamDocument.objects.get_or_create(
            stream=current, content_hash=doc.content_hash,
            defaults={field: getattr(doc, field) for field in (
                'kind', 'nsu', 'schema_name', 'access_key', 'event_type', 'xml_content')})
        if not created and doc.nsu and stored.nsu and doc.nsu != stored.nsu:
            raise SefazError('A SEFAZ devolveu o mesmo conteúdo com NSU divergente. Revise a distribuição.')
        if not stored.nsu and doc.nsu:
            stored.nsu = doc.nsu
            stored.save(update_fields=['nsu'])
    current.reported_nsu = response.last_nsu
    current.last_status = response.status
    current.last_reason = response.reason
    current.last_response_at = now
    current.official_response_at = response.responded_at
    current.last_error = ''
    if response.max_nsu and accepted:
        current.max_nsu = response.max_nsu
    if accepted:
        current.last_nsu = response.last_nsu
        current.failure_count = 0
    else:
        current.failure_count += 1
    if response.status in {'137', '656'} or (accepted and response.last_nsu and response.last_nsu == response.max_nsu):
        # O relógio oficial pode estar alguns segundos à frente do Windows.
        # Esperar pela referência mais tardia, com margem, evita antecipar a
        # hora mínima e prolongar um bloqueio 656 por diferença de relógios.
        reference = max(now, response.responded_at) if response.responded_at else now
        current.next_attempt_at = reference + idle_interval()
    elif not accepted:
        current.next_attempt_at = now + timedelta(seconds=min(3600, 60 * 2 ** min(current.failure_count - 1, 6)))
    else:
        # O histórico continua sem uma espera de horas entre cada página.
        current.next_attempt_at = None
    current.lease_token = None
    current.lease_until = None
    current.save()
    return current


def _sync_state(state, stream):
    state.last_nsu = stream.last_nsu
    state.max_nsu = stream.max_nsu
    state.reported_nsu = stream.reported_nsu
    state.last_status = stream.last_status
    state.last_reason = stream.last_reason
    state.last_response_at = stream.last_response_at
    state.official_response_at = stream.official_response_at
    state.next_attempt_at = stream.next_attempt_at
    state.failure_count = stream.failure_count
    state.last_error = stream.last_error
    if stream.source == 'sefaz' and stream.last_status in {'137', '138'}:
        state.last_real_success_at = stream.last_response_at
    state.save()
    return state


def _pending_documents(stream, state):
    new = stream.documents.exclude(deliveries__state=state).values('pk')
    retries = state.documents.filter(kind='invoice', invoice__isnull=True).filter(
        Q(next_processing_attempt_at__isnull=True)
        | Q(next_processing_attempt_at__lte=timezone.now())).values('stream_document_id')
    return stream.documents.filter(Q(pk__in=new) | Q(pk__in=retries)).order_by('pk')


def _deliver(company, config, stream, identity_validated=False):
    """Copia apenas após consentimento e prova local do CNPJ deste cliente."""
    _requirements(company, config)
    state, _ = SefazSyncState.objects.get_or_create(
        company=company, environment=stream.environment, source=stream.source)
    pending = _pending_documents(stream, state)
    if stream.source == 'sefaz' and not identity_validated and pending.exists():
        # Um cadastro com metadados antigos ou cifra corrompida não é prova de
        # identidade. Reabrir/revalidar o A1 deste cliente antes de cada entrega
        # pendente protege também os replays sem nova consulta HTTP.
        from portal.services.sefaz_transport import load_identity
        load_identity(company)
    imported = 0
    for incoming in pending.iterator():
        with transaction.atomic():
            stored, _ = SefazDocument.objects.get_or_create(
                state=state, content_hash=incoming.content_hash,
                defaults={**{field: getattr(incoming, field) for field in (
                    'kind', 'nsu', 'schema_name', 'access_key', 'event_type', 'xml_content')},
                    'stream_document': incoming})
            if stored.stream_document_id is None:
                stored.stream_document = incoming
            if incoming.kind == 'invoice' and stored.invoice_id is None:
                stored.last_processing_attempt_at = timezone.now()
                try:
                    data = parse_nfe(incoming.xml_content.encode('utf-8'))
                    if data['owner'] != company.cnpj:
                        # O serviço pode distribuir documentos de outros papéis.
                        # Guardar a evidência não transforma emissão em NF-e recebida.
                        raise InvoiceImportError('XML disponibilizado em outro papel fiscal: o CNPJ destinatário difere desta empresa. Não foi importado como nota recebida.')
                    # Savepoint: um XML inválido não apaga o lote recebido nem o NSU.
                    with transaction.atomic():
                        invoice, new = import_invoice(company.workspace,
                            incoming.xml_content.encode('utf-8'),
                            allowed_companies=[company.pk], is_demo=stream.source == 'test',
                            source='sefaz' if stream.source == 'sefaz' else 'xml')
                    stored.invoice = invoice
                    stored.processing_error = ''
                    stored.next_processing_attempt_at = None
                    imported += int(new)
                except (InvoiceImportError, ValidationError) as error:
                    stored.processing_error = str(error)[:500]
                    # Revalidar localmente permite retomar após corrigir parser,
                    # cadastro ou falha transitória, sem repetir a consulta DF-e.
                    stored.next_processing_attempt_at = timezone.now() + HOUR
            stored.save()
    return _sync_state(state, stream), imported


def _fanout(stream, first_company, first_config, first_identity_validated=False):
    """Um cursor global, caixas de entrada isoladas por empresa autorizada."""
    state, imported = _deliver(first_company, first_config, stream, first_identity_validated)
    configs = SefazCaptureConfig.objects.select_related('company__workspace').filter(
        company__cnpj=stream.cnpj, environment=stream.environment,
        enabled=True, read_authorized_at__isnull=False,company__deactivated_at__isnull=True,
        company__workspace__access_status='active',company__workspace__owner__is_active=True,
        company__workspace__capture_paused=False).exclude(pk=first_config.pk)
    for config in configs:
        try:
            _deliver(config.company, config, stream)
            _config_error(config, '', '')
        except SefazError as error:
            _config_error(config, str(error))
        except Exception:
            # Uma caixa de entrada não deve interromper as demais. O próximo
            # ciclo reentrega por hash antes de qualquer nova chamada à SEFAZ.
            _config_error(config, 'Não foi possível processar os documentos locais. A entrega será retomada.', 'processing')
    return state, imported


def _fail(stream, token, state, consultation, config, error, phase='processing'):
    # Somente erros públicos do domínio podem ser exibidos. Nunca serializar
    # exceções de bibliotecas TLS/PKCS12 que possam conter material sensível.
    safe = str(error)[:500] if isinstance(error, (SefazError, ValidationError)) else (
        f'Falha local na etapa {phase} ({type(error).__name__}). Resposta preservada quando recebida; haverá nova tentativa.')
    metadata = {}
    if consultation.response_xml:
        try:
            metadata = distribution_metadata(consultation.response_xml.encode('utf-8'), config.environment)
        except SefazError:
            pass
    if metadata:
        consultation.status = metadata['status']
        consultation.reason = metadata['reason']
        consultation.official_response_at = metadata['responded_at']
        consultation.reported_nsu = metadata['last_nsu']
        consultation.max_nsu = metadata['max_nsu']
    fresh = SefazDistributionStream.objects.filter(pk=stream.pk, lease_token=token).first()
    if fresh:
        # Após iniciar uma consulta real, timeout/XML inválido deixam o resultado
        # remoto desconhecido. Não arriscar consumo indevido repetindo em 60s.
        delay = 3600 if stream.source == 'sefaz' or metadata.get('status') in {'137', '656'} else min(3600, 60 * 2 ** min(fresh.failure_count, 6))
        evidence = {}
        if metadata:
            evidence = {'last_status': metadata['status'], 'last_reason': metadata['reason'],
                'last_response_at': timezone.now(), 'official_response_at': metadata['responded_at'],
                'reported_nsu': metadata['last_nsu']}
        SefazDistributionStream.objects.filter(pk=stream.pk, lease_token=token).update(**evidence,
            lease_token=None, lease_until=None, failure_count=F('failure_count') + 1,
            next_attempt_at=timezone.now() + timedelta(seconds=delay), last_error=safe)
    stream.refresh_from_db()
    SefazSyncState.objects.filter(pk=state.pk).update(last_error=safe,
        next_attempt_at=stream.next_attempt_at, failure_count=stream.failure_count,
        last_status=stream.last_status, last_reason=stream.last_reason,
        last_response_at=stream.last_response_at, official_response_at=stream.official_response_at,
        reported_nsu=stream.reported_nsu)
    consultation.completed_at = timezone.now()
    consultation.error_code = 'capture_failed'
    consultation.error = safe
    # Se a primeira gravação do corpo falhou transitoriamente, o retorno ainda
    # está em memória. Preservá-lo neste fallback permite recuperação LOCAL,
    # sem repetir HTTP nem avançar cursor só por metadados.
    consultation.save(update_fields=['response_xml','completed_at', 'error_code', 'error', 'status', 'reason',
        'official_response_at', 'reported_nsu', 'max_nsu'])
    _config_error(config, safe, 'capture_failed')
    return safe


@transaction.atomic
def recover_received_response(company,config,stream):
    """Reprocessa a última resposta aceita preservada, sem nova consulta HTTP.

    O cursor só avança após armazenar todos os documentos daquele retorno.
    Uma rejeição mais recente ou cursor diferente impede a recuperação automática.
    O prazo conservador já salvo não é antecipado pela recuperação local.
    """
    current=SefazDistributionStream.objects.select_for_update().get(pk=stream.pk)
    if current.source!='sefaz':return False
    now=timezone.now()
    if current.lease_until and current.lease_until>now:return False
    latest=SefazConsultation.objects.filter(state__company__cnpj=current.cnpj,
        state__environment=current.environment,state__source=current.source).order_by('-requested_at','-pk').first()
    if not latest or not latest.error or latest.status not in {'137','138'} or not latest.response_xml or latest.requested_nsu!=current.last_nsu:return False
    from .sefaz_transport import SefazTransport
    payload=latest.response_xml.encode('utf-8')
    SefazTransport().validate_response(payload)
    response=parse_distribution(payload,current.environment)
    if response.last_nsu<=current.last_nsu:return False
    previous_wait=current.next_attempt_at
    token=uuid.uuid4();current.lease_token=token;current.lease_until=now+timedelta(seconds=LEASE_SECONDS)
    current.save(update_fields=['lease_token','lease_until'])
    current=_store_response(current,token,response)
    if previous_wait and (not current.next_attempt_at or current.next_attempt_at<previous_wait):
        current.next_attempt_at=previous_wait;current.save(update_fields=['next_attempt_at'])
    counts=_counts(response.documents)
    latest.error_code='recovered_local';latest.error='';latest.counts=counts
    latest.save(update_fields=['error_code','error','counts'])
    AuditEntry.objects.create(workspace=company.workspace,description='Resposta oficial já recebida recuperada localmente, sem nova consulta nem redução do intervalo.')
    stream.refresh_from_db()
    return True


def run_company(workspace, company_id, transport=None):
    """Executa no máximo uma consulta real. Cooldown/lease nunca são ignorados."""
    company = _company(workspace, company_id)
    config = SefazCaptureConfig.objects.filter(company=company).first()
    if config is None:
        raise SefazNotConfigured('Habilite e autorize a captura desta empresa na aplicação.')
    try:
        _requirements(company, config)
        if transport is None:
            from portal.services.sefaz_transport import SefazTransport
            transport = SefazTransport()
        source = getattr(transport, 'source', 'test')
        real = getattr(transport, 'is_real', False) is True
        if source not in {'test', 'manual', 'sefaz'} or real != (source == 'sefaz'):
            raise SefazError('A origem do transporte não corresponde à evidência de consulta real.')
    except SefazError as error:
        _config_error(config, str(error))
        raise
    except Exception:
        message = 'Não foi possível validar o transporte e o certificado. Nenhuma consulta foi iniciada.'
        _config_error(config, message, 'configuration')
        raise SefazNotConfigured(message) from None
    stream = _stream(company, config.environment, source)
    _recover_orphan(stream)
    recover_received_response(company,config,stream)
    # Retomar entregas já recebidas antes de consumir nova página ou aguardar.
    try:
        state, _ = _fanout(stream, company, config)
    except SefazError as error:
        _config_error(config, str(error))
        raise
    if stream.last_status in {'137', '138'} and not stream.last_error:
        _config_error(config, '', '')
    now = timezone.now()
    if ((stream.next_attempt_at and stream.next_attempt_at > now)
            or (stream.lease_until and stream.lease_until > now)):
        raise SefazBusy('A consulta deste CNPJ está em andamento ou aguardando o intervalo permitido pela SEFAZ.')
    try:
        transport.ensure_configured(company, config.environment)
    except SefazError as error:
        _config_error(config, str(error))
        raise
    except Exception:
        message = 'Não foi possível validar o transporte e o certificado. Nenhuma consulta foi iniciada.'
        _config_error(config, message, 'configuration')
        raise SefazNotConfigured(message) from None
    token = _claim(stream)
    now = timezone.now()
    state.last_attempt_at = now
    state.save(update_fields=['last_attempt_at', 'updated_at'])
    consultation = SefazConsultation.objects.create(state=state,
        requested_at=now, requested_nsu=stream.last_nsu)
    phase='transport'
    try:
        payload = transport.fetch(company, config.environment, stream.last_nsu)
        if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
            raise SefazError('O retorno excede o limite local ou não contém bytes XML.')
        # Evidência privada gravada antes de qualquer parser/processamento. Não
        # vai para logs, respostas de API ou templates públicos.
        consultation.response_xml = payload.decode('utf-8-sig', errors='replace')
        consultation.save(update_fields=['response_xml'])
        validate_response = getattr(transport, 'validate_response', None)
        phase='schema'
        if validate_response is not None:
            validate_response(payload)
        phase='parse'
        response = parse_distribution(payload, config.environment)
        phase='storage'
        stream = _store_response(stream, token, response)
        # Resposta/cursor são duráveis antes da importação. Reiniciar o processo
        # entre estes pontos reentrega a caixa de entrada sem pedir novamente.
        counts = _counts(response.documents)
        consultation.completed_at = timezone.now()
        consultation.official_response_at = response.responded_at
        consultation.status = response.status
        consultation.reason = response.reason
        consultation.reported_nsu = response.last_nsu
        consultation.max_nsu = response.max_nsu
        consultation.counts = counts
        consultation.save(update_fields=['completed_at', 'official_response_at', 'status',
            'reason', 'reported_nsu', 'max_nsu', 'counts'])
        phase='delivery'
        state, imported = _fanout(stream, company, config, first_identity_validated=real)
        counts['imported'] = imported
        state.last_counts = counts
        state.save(update_fields=['last_counts', 'updated_at'])
        consultation.counts = counts
        consultation.save(update_fields=['counts'])
        _config_error(config, '', '')
        if response.status not in {'137', '138'}:
            message = f'SEFAZ {response.status}: {response.reason}'[:500]
            _config_error(config, message, 'sefaz_' + response.status)
            raise SefazRejected(message)
        AuditEntry.objects.create(workspace=workspace, description=(
            f'{"Distribuição oficial SEFAZ" if real else "Teste de distribuição"}: '
            f'{len(response.documents)} documento(s), {imported} NF-e nova(s), '
            f'empresa {company.display_name}')[:250])
        return state
    except SefazRejected:
        raise
    except Exception as error:
        message = _fail(stream, token, state, consultation, config, error,phase=phase)
        if isinstance(error, SefazError):
            raise
        raise SefazError(message) from None


def run_due(limit=20, company_id=None):
    """Uma volta justa da fila persistente; falha de um cliente não para outros."""
    configs = SefazCaptureConfig.objects.select_related('company__workspace').filter(
        enabled=True, read_authorized_at__isnull=False,company__workspace__capture_paused=False,
        company__deactivated_at__isnull=True,company__workspace__access_status='active',
        company__workspace__owner__is_active=True).order_by(F('last_checked_at').asc(nulls_first=True), 'pk')
    if company_id is not None:
        configs = configs.filter(company_id=company_id)
    results = [];seen=set();cycle_started=timezone.now()
    for config in configs[:limit]:
        identity=(config.company.cnpj,config.environment)
        try:
            _requirements(config.company, config)
            stream = SefazDistributionStream.objects.filter(cnpj=config.company.cnpj,
                environment=config.environment, source='sefaz').first()
            if identity in seen:
                if stream:_deliver(config.company,config,stream)
                if stream and stream.last_status in {'137','138'} and not stream.last_error:_config_error(config,'','')
                elif stream and stream.last_status=='656' and not stream.last_error:_config_error(config,f'SEFAZ 656: {stream.last_reason}','sefaz_656')
                else:SefazCaptureConfig.objects.filter(pk=config.pk).update(last_checked_at=timezone.now())
                results.append((config.company_id,'waiting'))
                continue
            if stream:
                _recover_orphan(stream)
                if stream.last_error:
                    recover_received_response(config.company,config,stream)
            now = timezone.now()
            waiting = stream and ((stream.next_attempt_at and stream.next_attempt_at > now)
                or (stream.lease_until and stream.lease_until > now))
            if waiting:
                state, _ = SefazSyncState.objects.get_or_create(company=config.company,
                    environment=config.environment, source='sefaz')
                if not _pending_documents(stream, state).exists():
                    # Sem pendência de entrega, aguardar não precisa abrir PKCS12
                    # nem refazer fanout de todos os clientes do mesmo CNPJ.
                    _sync_state(state, stream)
                    if stream.last_status in {'137', '138'} and not stream.last_error:
                        _config_error(config, '', '')
                    elif stream.last_status == '656' and not stream.last_error:
                        # Uma falha antiga do worker não deve encobrir o estado
                        # oficial já conhecido durante todo o cooldown.
                        _config_error(config, f'SEFAZ 656: {stream.last_reason}', 'sefaz_656')
                    else:
                        SefazCaptureConfig.objects.filter(pk=config.pk).update(last_checked_at=now)
                    results.append((config.company_id, 'waiting'))
                    seen.add(identity)
                    continue
            run_company(config.company.workspace, config.company_id)
            seen.add(identity)
            results.append((config.company_id, 'completed'))
        except SefazBusy:
            seen.add(identity)
            # Atualiza justiça da fila, sem alterar cooldown ou marcar como erro.
            SefazCaptureConfig.objects.filter(pk=config.pk).update(last_checked_at=timezone.now())
            results.append((config.company_id, 'waiting'))
        except SefazRejected:
            seen.add(identity)
            # run_company já gravou o código/motivo oficial específico.
            results.append((config.company_id, 'error'))
        except SefazError as error:
            # A1/configuração inválida antes de reservar não impede que outro
            # vínculo autorizado do mesmo CNPJ seja o consumidor desta volta.
            if SefazDistributionStream.objects.filter(cnpj=config.company.cnpj,environment=config.environment,source='sefaz',last_attempt_at__gte=cycle_started).exists():seen.add(identity)
            _config_error(config, str(error))
            results.append((config.company_id, 'error'))
        except Exception as error:
            _config_error(config, 'Falha interna no processamento. A captura será retomada no próximo ciclo.', 'worker')
            AuditEntry.objects.create(workspace=config.company.workspace,
                description=f'Falha do worker NF-e: {type(error).__name__}; empresa {config.company_id}. Mensagem e dados fiscais omitidos.')
            results.append((config.company_id, 'error'))
    return results


def has_due_backlog(company_id=None):
    """Há paginação autorizada imediata? Consulta apenas metadados da fila."""
    authorized = SefazCaptureConfig.objects.filter(enabled=True,
        read_authorized_at__isnull=False, company__cnpj=OuterRef('cnpj'),
        environment=OuterRef('environment'),company__deactivated_at__isnull=True,
        company__workspace__access_status='active',company__workspace__capture_paused=False,
        company__workspace__owner__is_active=True)
    if company_id is not None:
        authorized = authorized.filter(company_id=company_id)
    now = timezone.now()
    return SefazDistributionStream.objects.filter(source='sefaz',
        last_status='138', last_nsu__lt=F('max_nsu')).annotate(
            has_authorization=Exists(authorized)).filter(has_authorization=True).filter(
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).filter(
            Q(lease_until__isnull=True) | Q(lease_until__lte=now)).exists()
