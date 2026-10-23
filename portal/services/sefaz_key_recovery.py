"""Recuperação pontual de NF-e referenciada em CT-e privado, sem eventos fiscais."""
import re
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from portal.models import AuditEntry, FiscalDocument, Invoice
from portal.sefaz_models import SefazDistributionStream, SefazKeyRecovery
from .capture_policy import consumption_interval
from .sefaz import LEASE_SECONDS, SefazBusy, SefazError
from .sefaz_recovery import RECOVERY_SPACING, blocked_until, point_query_allowed_at, consultations_for_stream


def validate_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[0-9]{6}[A-Z0-9]{12}[0-9]{26}', key):
        raise SefazError('A chave de acesso deve conter 44 posições válidas.')
    total = sum((ord(char) - 48) * (2 + index % 8) for index, char in enumerate(reversed(key[:43])))
    digit = 11 - total % 11
    if digit >= 10:
        digit = 0
    if key[-1] != str(digit) or key[20:22] != '55' or not 1 <= int(key[4:6]) <= 12:
        raise SefazError('A chave de acesso da NF-e contém modelo, mês ou dígito inválido.')
    return key


def referenced_keys(company, evidence, environment):
    from .fiscal_transport import CTE, xml_read
    if (evidence is None or evidence.company_id != company.pk or evidence.service != 'cte'
            or evidence.environment != environment or evidence.validation_status != 'schema'):
        raise SefazError('A referência deve pertencer a um CT-e validado desta empresa e ambiente.')
    root = xml_read(evidence.xml_content.encode('utf-8'))
    ns = {'c': CTE}
    if root.findtext('.//c:infCte/c:dest/c:CNPJ', '', ns) != company.cnpj:
        raise SefazError('A recuperação exige CT-e com esta empresa como destinatária da carga.')
    return {(node.text or '').strip() for node in root.findall('.//c:infDoc/c:infNFe/c:chave', ns)}


@transaction.atomic
def queue_from_cte(workspace, company_id, evidence_id, key):
    from .capture import _company, _requirements, _stream
    company = _company(workspace, company_id)
    config = getattr(company, 'capture_config', None)
    if config is None:
        raise SefazError('Habilite a captura e autorize a leitura desta empresa.')
    _requirements(company, config)
    validate_key(key)
    evidence = FiscalDocument.objects.filter(pk=evidence_id, company=company).first()
    if evidence is None or key not in referenced_keys(company, evidence, config.environment):
        raise SefazError('A chave não possui referência no CT-e deste acesso.')
    if key[6:20] == company.cnpj:
        raise SefazError('NF-e de emissão própria não entra na captura de notas recebidas.')
    if Invoice.objects.filter(company=company, access_key=key, is_demo=False).exists():
        return None, False
    stream = _stream(company, config.environment, 'sefaz')
    existing = stream.key_recoveries.filter(access_key=key).first()
    if existing:
        if existing.company_id is None:
            if stream.key_recoveries.filter(completed_at__isnull=True).count() >= 20:
                raise SefazError('Há 20 recuperações por chave pendentes. Aguarde a conclusão antes de reagendar outras.')
            # Novo titular prova a referência no seu próprio CT-e e consente
            # novamente. O registro antigo não concede acesso nem faz HTTP.
            existing.company=company
            existing.evidence=evidence
            existing.completed_at=None
            existing.result='pending'
            existing.last_error=''
            existing.last_status=''
            existing.next_attempt_at=max(filter(None,[existing.next_attempt_at,stream.blocked_until]),default=None)
            existing.save()
            AuditEntry.objects.create(workspace=workspace,description=f'Recuperação por chave reagendada com referência própria; empresa {company.pk}; histórico global preservado.')
            return existing, True
        return existing, False
    # Consulta excepcional, limitada a chaves comprovadas, sem varredura do CNPJ.
    if stream.key_recoveries.filter(completed_at__isnull=True).count() >= 20:
        raise SefazError('Há 20 recuperações por chave pendentes. Aguarde a conclusão antes de agendar outras.')
    job = SefazKeyRecovery.objects.create(stream=stream, company=company, evidence=evidence, access_key=key)
    AuditEntry.objects.create(workspace=workspace, description=(
        f'Recuperação NF-e por chave agendada a partir do CT-e {evidence.pk}; '
        f'empresa {company.pk}; somente leitura, sem manifestação.'))
    return job, True


def due_key_recovery(stream, company, now=None):
    now = now or timezone.now()
    wait = blocked_until(stream)
    if wait and wait > now:
        return None
    if stream.last_status == '656':
        latest = consultations_for_stream(stream).order_by('-requested_at','-pk').values('query_kind','status').first()
        if latest and latest['query_kind'] == 'consChNFe' and latest['status'] == '656':
            # Depois de uma rejeição pontual, a próxima janela precisa testar
            # novamente a distribuição. A fila excepcional não pode tomar
            # indefinidamente o lugar da captura periódica principal.
            return None
    return stream.key_recoveries.filter(company=company, completed_at__isnull=True).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).order_by('created_at', 'pk').first()


@transaction.atomic
def claim_key_recovery(stream, job, company):
    current = SefazDistributionStream.objects.select_for_update().get(pk=stream.pk)
    now = timezone.now()
    wait = blocked_until(current)
    if (wait and wait > now) or (current.lease_until and current.lease_until > now):
        raise SefazBusy('A recuperação por chave aguarda o bloqueio ou a reserva do CNPJ.')
    job = SefazKeyRecovery.objects.select_for_update().get(pk=job.pk, stream=current, company=company)
    if job.completed_at or (job.next_attempt_at and job.next_attempt_at > now):
        raise SefazBusy('A recuperação por chave aguarda seu agendamento.')
    # Revalida a evidência antes do HTTP, sem ampliar escopo entre clientes.
    if job.access_key not in referenced_keys(company, job.evidence, current.environment):
        raise SefazError('A referência fiscal da recuperação não está mais disponível.')
    allowed = point_query_allowed_at(current, now)
    if allowed > now:
        job.next_attempt_at = allowed
        job.save(update_fields=['next_attempt_at'])
        return None, None
    token = uuid.uuid4()
    claimed = SefazDistributionStream.objects.filter(pk=current.pk).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lte=now)).update(
            lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS), last_attempt_at=now)
    if not claimed:
        raise SefazBusy('Outra consulta deste CNPJ já possui a reserva.')
    job.next_attempt_at = now + RECOVERY_SPACING
    job.save(update_fields=['next_attempt_at'])
    stream.refresh_from_db()
    return token, job


@transaction.atomic
def store_key_response(stream, token, response, consultation):
    from .capture import _store_documents
    now = timezone.now()
    current = SefazDistributionStream.objects.select_for_update().get(pk=stream.pk)
    if current.lease_token != token or not current.lease_until or current.lease_until <= now:
        raise SefazBusy('A recuperação por chave perdeu sua reserva.')
    job = SefazKeyRecovery.objects.select_for_update().get(pk=consultation.key_recovery_id, stream=current)
    if job.completed_at or job.access_key != consultation.requested_key:
        raise SefazError('A chave da recuperação mudou durante a consulta.')
    _store_documents(current, response)
    job.last_status = response.status
    job.last_error = ''
    job.next_attempt_at = now + RECOVERY_SPACING
    accepted = response.status in {'137', '138'}
    if accepted:
        current.failure_count = 0
        job.result = 'unavailable' if response.status == '137' else ('xml' if response.documents[0].kind == 'invoice' else 'summary')
        job.completed_at = now
        # Uma consulta pontual aceita não prova que a sequência distNSU voltou.
    elif response.status == '656':
        current.failure_count += 1
        reference = max(now, response.responded_at) if response.responded_at else now
        current.blocked_until = reference + consumption_interval(current.failure_count)
        current.next_attempt_at = max(current.next_attempt_at or now, current.blocked_until)
        job.next_attempt_at = current.blocked_until
        job.last_error = f'SEFAZ 656: {response.reason}'[:500]
    elif response.status in {'108', '109', '999'} and job.consultations.count() < 8:
        job.last_error = f'SEFAZ {response.status}: {response.reason}'[:500]
    else:
        job.result = 'rejected'
        job.completed_at = now
        job.last_error = f'SEFAZ {response.status}: {response.reason}'[:500]
    job.save()
    current.last_status = response.status
    current.last_reason = response.reason
    current.last_response_at = now
    current.official_response_at = response.responded_at
    current.last_error = ''
    current.lease_token = None
    current.lease_until = None
    # last_nsu/max_nsu/reported_nsu sequenciais ficam intactos. Adiar somente
    # a distribuição evita chamadas consecutivas depois da consulta pontual.
    current.next_attempt_at = max(current.next_attempt_at or now, now + RECOVERY_SPACING)
    current.save()
    return current
