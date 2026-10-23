"""Agenda chaves comprovadas em CT-e privado; nunca consulta na requisição."""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from portal.models import Company, FiscalDocument, Invoice
from portal.services.capture import _requirements
from portal.services.sefaz import SefazError
from portal.services.sefaz_key_recovery import queue_from_cte, referenced_keys, validate_key


class Command(BaseCommand):
    help = 'Localiza NF-e referenciadas em CT-e do cliente e agenda recuperação oficial por chave, sem enviar eventos.'

    def add_arguments(self, parser):
        parser.add_argument('--company', type=int, required=True)
        parser.add_argument('--desde', required=True, help='Data inicial YYYY-MM-DD, dentro dos últimos 90 dias.')
        parser.add_argument('--limit', type=int, default=10)
        parser.add_argument('--executar', action='store_true', help='Persiste a fila; o worker consulta somente após o bloqueio e a quota.')

    def handle(self, *args, **options):
        try:
            start = parse_date(options['desde'])
        except ValueError:
            start = None
        today = timezone.localdate()
        if not start or not today - timedelta(days=90) <= start <= today or not 1 <= options['limit'] <= 20:
            raise CommandError('Informe data válida nos últimos 90 dias e --limit entre 1 e 20.')
        company = Company.objects.select_related('workspace', 'capture_config').filter(pk=options['company']).first()
        if company is None or not hasattr(company, 'capture_config'):
            raise CommandError('Empresa/configuração não encontrada.')
        config = company.capture_config
        try:
            _requirements(company, config)
            candidates = {}
            known = set(Invoice.objects.filter(company=company, is_demo=False).values_list('access_key', flat=True))
            documents = FiscalDocument.objects.filter(company=company, service='cte', environment=config.environment,
                validation_status='schema', issued_at__gte=timezone.make_aware(datetime.combine(start, time.min))).order_by('-issued_at')
            for evidence in documents.iterator(chunk_size=100):
                try:
                    keys = referenced_keys(company, evidence, config.environment)
                except SefazError:
                    continue
                for key in sorted(keys):
                    try:
                        validate_key(key)
                    except SefazError:
                        continue
                    if key[6:20] != company.cnpj and key not in known and start.strftime('%y%m') <= key[2:6] <= today.strftime('%y%m'):
                        candidates.setdefault(key, evidence.pk)
            selected = list(candidates.items())[:options['limit']]
            created = 0
            if options['executar']:
                for key, evidence_id in selected:
                    _, new = queue_from_cte(company.workspace, company.pk, evidence_id, key)
                    created += int(new)
            self.stdout.write(f'Empresa {company.pk}: {len(candidates)} chave(s) referenciada(s) sem XML importado; {len(selected)} selecionada(s); {created} nova(s) agendada(s).')
            self.stdout.write('A referência não comprova disponibilidade nem destinatário da NF-e. Somente XML recebido será importado; bloqueio, intervalo e quota são preservados.')
            if not options['executar']:
                self.stdout.write('Diagnóstico sem alterações. Para agendar, repita com --executar.')
        except SefazError as error:
            raise CommandError(str(error)) from None
