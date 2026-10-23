"""Retomada documentada após 656 e recuperação durável dos NSUs intermediários.

Somente consultas de leitura. O cursor informado em uma rejeição nunca vira
prova de documentos recebidos. A retomada precisa de resposta oficial íntegra;
o intervalo anterior fica em fila própria, com limite conservador de 18/h.
"""
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from portal.sefaz_models import SefazConsultation, SefazDistributionStream, SefazNsuRecovery
from .capture_policy import consumption_interval
from .sefaz import LEASE_SECONDS, SefazBusy, SefazError, parse_distribution

RECOVERY_SPACING = timedelta(seconds=210)
RECOVERY_HOURLY_LIMIT = 18


def consultations_for_stream(stream):
    # Evidência governamental da fila não pertence ao certificado nem é apagada
    # ao excluir um cliente. O segundo ramo mantém compatibilidade com testes
    # e registros legados ainda sem FK ao consumidor.
    return SefazConsultation.objects.filter(Q(stream=stream) | Q(stream__isnull=True,
        state__company__cnpj=stream.cnpj, state__environment=stream.environment, state__source=stream.source))


def blocked_until(stream):
    # Migrações não antecipam a espera de rejeições anteriores à nova coluna.
    dates = [stream.blocked_until]
    if stream.last_status == '656':
        dates.append(stream.next_attempt_at)
    return max((date for date in dates if date), default=None)


def resume_cursor(stream, *, exclude_consultation_id=None):
    """Obtém um ponto de retomada exclusivamente da última resposta distNSU."""
    if stream.source != 'sefaz':
        return stream.last_nsu
    attempts = consultations_for_stream(stream).filter(query_kind='distNSU')
    if exclude_consultation_id is not None:
        attempts = attempts.exclude(pk=exclude_consultation_id)
    latest = attempts.order_by('-requested_at', '-pk').first()
    if not latest or latest.status != '656' or not latest.response_xml:
        return stream.last_nsu
    if latest.requested_nsu != stream.last_nsu and latest.resume_from_nsu != stream.last_nsu:
        return stream.last_nsu
    from .sefaz_transport import SefazTransport
    payload = latest.response_xml.encode('utf-8')
    SefazTransport().validate_response(payload)
    response = parse_distribution(payload, stream.environment)
    if response.status != '656' or 'ultnsu' not in response.reason.lower():
        return stream.last_nsu
    if response.last_nsu and response.last_nsu > stream.last_nsu:
        return response.last_nsu
    return stream.last_nsu


def record_resume_gap(stream, requested_nsu, resume_from_nsu):
    """Chamado na transação que armazena o novo lote aceito."""
    if not resume_from_nsu:
        return
    if stream.last_nsu != resume_from_nsu or requested_nsu <= resume_from_nsu:
        raise SefazError('O ponto de retomada mudou durante a consulta. Exige revisão.')
    first = str(int(resume_from_nsu) + 1).zfill(15)
    SefazNsuRecovery.objects.get_or_create(stream=stream, first_nsu=first,
        last_nsu=requested_nsu, defaults={'next_nsu': first})


def due_recovery(stream, now=None):
    now = now or timezone.now()
    wait = blocked_until(stream)
    if wait and wait > now:
        return None
    return stream.recoveries.filter(completed_at__isnull=True).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).order_by('first_nsu', 'pk').first()


@transaction.atomic
def claim_recovery(stream, recovery):
    current = SefazDistributionStream.objects.select_for_update().get(pk=stream.pk)
    now = timezone.now()
    wait = blocked_until(current)
    if (wait and wait > now) or (current.lease_until and current.lease_until > now):
        raise SefazBusy('A recuperação aguarda a reserva ou o bloqueio deste CNPJ.')
    job = SefazNsuRecovery.objects.select_for_update().get(pk=recovery.pk, stream=current)
    if job.completed_at or (job.next_attempt_at and job.next_attempt_at > now):
        raise SefazBusy('A recuperação aguarda a próxima consulta pontual permitida.')
    # Pode haver NSUs já preservados localmente por um retorno recuperado.
    position = int(job.next_nsu)
    for known in current.documents.filter(nsu__gte=job.next_nsu, nsu__lte=job.last_nsu).order_by('nsu').values_list('nsu', flat=True).iterator():
        if int(known) != position:
            break
        position += 1
    if position > int(job.last_nsu):
        job.next_nsu = job.last_nsu
        job.completed_at = now
        job.save(update_fields=['next_nsu', 'completed_at'])
        return None, None
    job.next_nsu = str(position).zfill(15)
    allowed = point_query_allowed_at(current, now)
    if allowed > now:
        job.next_attempt_at = allowed
        job.save(update_fields=['next_nsu', 'next_attempt_at'])
        return None, None
    token = uuid.uuid4()
    claimed = SefazDistributionStream.objects.filter(pk=current.pk).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lte=now)).update(
        lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS), last_attempt_at=now)
    if not claimed:
        raise SefazBusy('Outra consulta deste CNPJ já possui a reserva.')
    job.next_attempt_at = now + RECOVERY_SPACING
    job.save(update_fields=['next_nsu', 'next_attempt_at'])
    stream.refresh_from_db()
    return token, job


def point_query_allowed_at(current, now):
    """Uma única quota móvel para consNSU e consChNFe do CNPJ/ambiente."""
    recent = consultations_for_stream(current).filter(
        query_kind__in=['consNSU', 'consChNFe'], requested_at__gt=now - timedelta(hours=1)).order_by('requested_at')
    stamps = list(recent.values_list('requested_at', flat=True))
    allowed = max(now, stamps[-1] + RECOVERY_SPACING) if stamps else now
    if len(stamps) >= RECOVERY_HOURLY_LIMIT:
        allowed = max(allowed, stamps[-RECOVERY_HOURLY_LIMIT] + timedelta(hours=1, seconds=10))
    return allowed


@transaction.atomic
def store_recovery_response(stream, token, response, consultation):
    from .capture import _store_documents
    now = timezone.now()
    current = SefazDistributionStream.objects.select_for_update().get(pk=stream.pk)
    if current.lease_token != token or not current.lease_until or current.lease_until <= now:
        raise SefazBusy('A recuperação perdeu sua reserva. O progresso foi preservado.')
    job = SefazNsuRecovery.objects.select_for_update().get(pk=consultation.recovery_id, stream=current)
    if job.completed_at or job.next_nsu != consultation.requested_nsu:
        raise SefazError('O NSU da recuperação mudou durante a consulta.')
    accepted = response.status in {'137', '138'}
    _store_documents(current, response)
    current.last_status = response.status
    current.last_reason = response.reason
    current.reported_nsu = response.last_nsu
    current.last_response_at = now
    current.official_response_at = response.responded_at
    current.last_error = ''
    if accepted:
        position = int(job.next_nsu) + 1
        job.next_nsu = str(min(position, int(job.last_nsu))).zfill(15)
        job.recovered_count += int(response.status == '138')
        job.unavailable_count += int(response.status == '137')
        job.last_error = ''
        current.failure_count = 0
        if position > int(job.last_nsu):
            job.completed_at = now
    else:
        job.last_error = f'SEFAZ {response.status}: {response.reason}'[:500]
        current.failure_count += 1
    if response.status == '656':
        reference = max(now, response.responded_at) if response.responded_at else now
        current.blocked_until = reference + consumption_interval(current.failure_count)
        current.next_attempt_at = max(current.next_attempt_at or now, current.blocked_until)
        job.next_attempt_at = current.blocked_until
    else:
        job.next_attempt_at = max(job.next_attempt_at or now, now + RECOVERY_SPACING)
    job.save()
    # ultNSU/maxNSU da consulta pontual não alteram a distribuição sequencial.
    current.lease_token = None
    current.lease_until = None
    current.save()
    return current
