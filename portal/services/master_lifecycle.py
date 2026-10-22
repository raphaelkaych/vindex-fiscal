"""Operações administrativas locais. Não transmite consultas ou eventos fiscais."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from portal.models import Company,Workspace,MasterAudit,DigitalCertificate,SefazCaptureConfig,FiscalConnector

LABELS={'Company':'Empresas','DigitalCertificate':'Certificados A1','Invoice':'NF-e completas','Installment':'Parcelas','Boleto':'Boletos','FiscalDocument':'Documentos NFS-e/CT-e','FiscalConnector':'Configurações NFS-e/CT-e','SefazCaptureConfig':'Configurações NF-e','SefazSyncState':'Histórico e estado NF-e','SefazScienceRequest':'Autorizações/eventos fiscais','AuditEntry':'Atividades do cliente','MasterAudit':'Auditorias administrativas','ApiCredential':'Credenciais de API','CredentialCompany':'Empresas autorizadas na API'}


def references(obj):
    """Exclusão física somente sem vínculos; nunca cascata de histórico."""
    rows=[]
    for relation in obj._meta.related_objects:
        if relation.many_to_many:continue
        count=relation.related_model.objects.filter(**{relation.field.name:obj}).count()
        if count:rows.append({'model':LABELS.get(relation.related_model.__name__,str(relation.related_model._meta.verbose_name)),'count':count})
    return rows


def account_blockers(workspace):
    rows=references(workspace)
    owner=workspace.owner
    if owner.has_perm('portal.admin_master') or owner.is_superuser or owner.is_staff:rows.append({'model':'Conta administrativa — exclusão bloqueada','count':1})
    for relation in owner._meta.related_objects:
        if relation.related_model is Workspace or relation.many_to_many:continue
        count=relation.related_model.objects.filter(**{relation.field.name:owner}).count()
        if count:rows.append({'model':'Referências do login em '+str(relation.related_model._meta.verbose_name),'count':count})
    return rows


def audit(actor,workspace,action,details):
    MasterAudit.objects.create(actor=actor,workspace=workspace,action=action,details=details[:200])


@transaction.atomic
def account_action(actor,workspace_id,action):
    workspace=Workspace.objects.select_for_update().select_related('owner').get(pk=workspace_id)
    if not actor.has_perm('portal.admin_master') or not actor.has_perm('portal.operate_clients'):raise ValidationError('Permissão administrativa insuficiente.')
    if workspace.owner_id==actor.pk and action in {'deactivate','delete'}:raise ValidationError('Não é permitido desativar ou excluir a própria conta administrativa.')
    if action=='deactivate' and (workspace.owner.is_staff or workspace.owner.is_superuser or workspace.owner.has_perm('portal.admin_master')):raise ValidationError('Contas administrativas não são desativadas pelo gerenciamento de clientes.')
    if action=='delete':
        if account_blockers(workspace):raise ValidationError('Exclusão bloqueada: existem vínculos ou histórico. Use desativação para preservar os dados.')
        identifier=workspace.pk;owner_id=workspace.owner_id
        # Auditoria sem FK ao cadastro que será removido, com ID preservado.
        audit(actor,None,'client_deleted',f'Cliente vazio id {identifier}; login id {owner_id}; nenhum documento ou histórico fiscal excluído.')
        workspace.delete();get_user_model().objects.get(pk=owner_id).delete()
    elif action in {'deactivate','activate'}:
        workspace.access_status='suspended' if action=='deactivate' else 'active'
        workspace.save(update_fields=['access_status'])
        audit(actor,workspace,'client_'+action,'Acesso e participação fiscal bloqueados pela conta; autorizações, histórico e intervalos preservados.' if action=='deactivate' else 'Conta reativada; serviços previamente habilitados podem retomar conforme a agenda.')
    else:raise ValidationError('Ação administrativa inválida.')


@transaction.atomic
def company_action(actor,workspace_id,company_id,action,environment='1'):
    if not actor.has_perm('portal.admin_master') or not actor.has_perm('portal.operate_clients'):raise ValidationError('Permissão administrativa insuficiente.')
    company=Company.objects.select_for_update().select_related('workspace').get(pk=company_id,workspace_id=workspace_id)
    workspace=company.workspace
    if action=='delete':
        if references(company):raise ValidationError('Exclusão bloqueada: a empresa tem vínculos, certificado, configurações ou histórico. Use desativação.')
        audit(actor,workspace,'company_deleted',f'Empresa vazia id {company.pk}; CNPJ {company.cnpj}. Filas compartilhadas preservadas.')
        company.delete();return
    if action in {'deactivate','activate'}:
        company.deactivated_at=timezone.now() if action=='deactivate' else None
        company.save(update_fields=['deactivated_at'])
    elif action=='remove_certificate':
        # Somente o vínculo local. A chave de cifra e outros A1 permanecem intactos.
        DigitalCertificate.objects.filter(company=company).delete()
        SefazCaptureConfig.objects.filter(company=company).update(enabled=False)
        FiscalConnector.objects.filter(company=company).update(enabled=False)
    elif action.startswith(('pause_','resume_')):
        if environment not in {'1','2'}:raise ValidationError('Ambiente inválido.')
        verb,service=action.split('_',1)
        if service not in {'nfe','nfse','cte'}:raise ValidationError('Serviço inválido.')
        enabled=verb=='resume'
        if service=='nfe':
            config=SefazCaptureConfig.objects.select_for_update().filter(company=company,environment=environment).first()
            if config is None or (enabled and not config.read_authorized_at):raise ValidationError('Não há autorização/configuração NF-e nesse ambiente. Autorize na aplicação antes de retomar.')
            config.enabled=enabled
            if enabled:
                from .capture import _requirements
                from .sefaz_transport import load_identity
                _requirements(company,config);load_identity(company)
        else:
            config=FiscalConnector.objects.select_for_update().filter(company=company,service=service,environment=environment).first()
            if config is None or (enabled and not config.authorized_at):raise ValidationError('Não há autorização/configuração desse serviço no ambiente. Autorize na aplicação antes de retomar.')
            config.enabled=enabled
            if enabled:
                from .fiscal_capture import requirements
                requirements(config)
        config.save(update_fields=['enabled'])
    else:raise ValidationError('Ação administrativa inválida.')
    audit(actor,workspace,'company_'+action,f'Empresa id {company.pk}; CNPJ {company.cnpj}; ambiente {environment}. Sem HTTP fiscal; NSU e documentos preservados.')
