"""Exclusão explícita do cliente, preservando filas e evidências fiscais globais.

Fluxo distinto da remoção administrativa de cadastro vazio. Nunca reutiliza
uma sessão de supervisão nem amplia o escopo de uma credencial de API.
"""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from portal.models import (
    Workspace, Company, MasterAudit, FiscalStream, FiscalDelivery,
    SefazDistributionStream, SefazConsultation, SefazScienceRequest, SefazDocument, FiscalDocument, SefazKeyRecovery,
)


def _delete_in_batches(queryset):
    # O coletor do Django pode combinar milhares de SET_NULL em uma única
    # expressão OR/IN e exceder as variáveis do SQLite, mesmo sem filhos.
    # Lotes limitam também memória e SQL, mantendo uma só transação externa.
    while True:
        identifiers = list(queryset.order_by('pk').values_list('pk', flat=True)[:500])
        if not identifiers:
            return
        queryset.model.objects.filter(pk__in=identifiers).delete()


@transaction.atomic
def delete_account(*, actor, workspace_id, confirmation):
    workspace = Workspace.objects.select_for_update().select_related('owner').get(pk=workspace_id)
    owner = workspace.owner
    if confirmation != workspace.name:
        raise ValidationError('Digite o nome exato do cliente para confirmar a exclusão.')
    if actor.pk != owner.pk and not (actor.has_perm('portal.admin_master') and actor.has_perm('portal.operate_clients')):
        raise ValidationError('Não há permissão para excluir esta conta.')
    if owner.is_superuser or owner.is_staff or owner.has_perm('portal.admin_master'):
        raise ValidationError('Transfira a administração para outro login antes de excluir uma conta administrativa.')
    companies = Company.objects.filter(workspace=workspace)
    cnpjs = list(companies.values_list('cnpj', flat=True))
    now = timezone.now()
    # Reservas impedem apagar o vínculo enquanto uma consulta está em andamento.
    nfe = list(SefazDistributionStream.objects.select_for_update().filter(cnpj__in=cnpjs))
    typed = list(FiscalStream.objects.select_for_update().filter(cnpj__in=cnpjs))
    if any(row.lease_until and row.lease_until > now for row in nfe + typed):
        raise ValidationError('Há uma consulta fiscal em andamento. Aguarde sua conclusão e tente novamente.')
    if SefazScienceRequest.objects.filter(company__workspace=workspace,status__in=['pending','sent'],
            authorized_at__gt=now-timedelta(minutes=5)).exists():
        raise ValidationError('Há uma manifestação fiscal em andamento. Aguarde sua conclusão antes de excluir a conta.')
    from .sefaz_recovery import consultations_for_stream
    # Migração defensiva de evidência legada antes de tornar state nulo.
    for stream in nfe:
        consultations_for_stream(stream).filter(stream__isnull=True).update(stream=stream)
    from .master_lifecycle import references
    counts = {row['model']: row['count'] for row in references(workspace)}
    workspace.access_status = 'suspended'
    workspace.capture_paused = True
    workspace.save(update_fields=['access_status', 'capture_paused'])
    # Estes registros comprovam eventos e consumo do CNPJ, inclusive para evitar
    # envio duplicado de Ciência depois de eventual recadastro. Não são apagados.
    SefazScienceRequest.objects.filter(company__workspace=workspace).update(company=None, document=None)
    SefazConsultation.objects.filter(state__company__workspace=workspace).update(state=None)
    SefazKeyRecovery.objects.filter(company__workspace=workspace,completed_at__isnull=True).update(
        completed_at=now,result='rejected',last_error='Solicitação encerrada com a exclusão do acesso de origem.')
    MasterAudit.objects.filter(workspace=workspace).update(workspace=None)
    # A entrega é privada; o envelope e o cursor do conector são compartilhados.
    FiscalDelivery.objects.filter(connector__company__workspace=workspace).delete()
    _delete_in_batches(SefazDocument.objects.filter(state__company__workspace=workspace))
    _delete_in_batches(FiscalDocument.objects.filter(company__workspace=workspace))
    MasterAudit.objects.create(actor=actor if actor.pk != owner.pk else None, action='account_erased',
        details=f'Cliente id {workspace.pk}, login id {owner.pk}: exclusão solicitada e confirmada; arquivos privados/A1 removidos; filas e evidências fiscais globais preservadas.')
    owner_id = owner.pk
    workspace.delete()
    get_user_model().objects.get(pk=owner_id).delete()
    return counts
