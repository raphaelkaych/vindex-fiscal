"""Reinterpretação local; nunca consulta a origem nem altera NSU."""
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from portal.models import Company,FiscalConnector,FiscalStream,FiscalDelivery,AuditEntry
from portal.services.fiscal_capture import deliver,requirements
from portal.services.sefaz import SefazError
import hashlib


class Command(BaseCommand):
    help='Confere/reprocessa documentos preservados de uma empresa, sem HTTP fiscal.'
    def add_arguments(self,parser):
        parser.add_argument('--empresa',type=int,required=True)
        parser.add_argument('--servico',choices=['nfse','cte'],default='nfse')
        parser.add_argument('--executar',action='store_true')
    def handle(self,*args,**options):
        company=Company.objects.filter(pk=options['empresa']).first()
        if company is None:raise CommandError('Empresa não encontrada.')
        for config in FiscalConnector.objects.filter(company=company,service=options['servico']):
            pending=FiscalDelivery.objects.filter(connector=config).exclude(error='').select_related('envelope')
            evidence={d.pk:(d.envelope_id,hashlib.sha256(d.envelope.xml_content.encode()).hexdigest()) for d in pending}
            self.stdout.write(f'Empresa {company.pk}, {config.service}, ambiente {config.environment}: {len(evidence)} pendências.')
            if not options['executar']:continue
            try:requirements(config)
            except SefazError as error:raise CommandError(str(error)) from None
            stream=FiscalStream.objects.filter(cnpj=company.cnpj,service=config.service,environment=config.environment).first()
            if not stream:continue
            # Força apenas tentativa LOCAL, respeitando o cursor/espera remotos.
            pending.update(next_retry_at=timezone.now())
            deliver(stream,only_connector=config)
            for row in FiscalDelivery.objects.filter(pk__in=evidence).select_related('envelope','document'):
                if evidence[row.pk]!=(row.envelope_id,hashlib.sha256(row.envelope.xml_content.encode()).hexdigest()):raise CommandError('Falha de integridade do original; interrompa e revise o armazenamento.')
                signature=(row.document.validation_details.get('signature','not_checked') if row.document else 'not_checked')
                self.stdout.write(f'Entrega {row.pk} / NSU {row.envelope.nsu}: {row.processing_status}; assinatura {signature}; original inalterado.')
            AuditEntry.objects.create(workspace=company.workspace,description=f'Reprocessamento local {config.service}: {len(evidence)} pendências; XMLs originais conferidos; sem consulta externa.')
