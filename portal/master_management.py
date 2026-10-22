"""Gerenciamento explícito fora da supervisão em leitura do painel cliente."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied,ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.debug import sensitive_post_parameters
from django.db import transaction
from django.utils import timezone
from .master_views import master_required
from .models import Workspace,Company,SefazCaptureConfig,FiscalConnector,DigitalCertificate,MasterAudit
from .forms import CertificateForm
from .services.master_lifecycle import references,account_blockers,account_action,company_action

COMPANY_ACTIONS={'deactivate':'Desativar empresa','activate':'Reativar empresa','delete':'Excluir empresa vazia definitivamente','remove_certificate':'Remover A1 e pausar serviços',
    'pause_nfe':'Pausar NF-e','resume_nfe':'Retomar NF-e','pause_nfse':'Pausar NFS-e','resume_nfse':'Retomar NFS-e','pause_cte':'Pausar CT-e','resume_cte':'Retomar CT-e'}
ACCOUNT_ACTIONS={'deactivate':'Desativar conta','activate':'Reativar conta','delete':'Excluir conta vazia definitivamente'}


def operator(request):
    if not request.user.has_perm('portal.operate_clients'):raise PermissionDenied


@master_required
@require_http_methods(['GET','POST'])
def account_manage(request,workspace_id):
    operator(request)
    client=get_object_or_404(Workspace.objects.select_related('owner'),pk=workspace_id)
    action=request.POST.get('action') if request.method=='POST' else request.GET.get('action','')
    if action and action not in ACCOUNT_ACTIONS:raise Http404
    blockers=account_blockers(client);error=''
    if request.method=='POST':
        if request.POST.get('confirmed')!='on':error='Confirme que leu os efeitos desta ação.'
        elif action=='delete' and request.POST.get('confirmation')!=f'EXCLUIR CLIENTE {client.pk}':error='Digite a confirmação exatamente como indicada.'
        else:
            try:account_action(request.user,client.pk,action)
            except ValidationError as e:error=' '.join(e.messages)
            else:
                messages.success(request,'Ação aplicada. Nenhum documento fiscal ou fila compartilhada foi excluído.')
                return redirect('master_home' if action=='delete' else 'master_account_manage',**({} if action=='delete' else {'workspace_id':client.pk}))
    companies=client.companies.select_related('certificate').defer('certificate__encrypted_file','certificate__encrypted_password')
    repeated=Company.objects.filter(cnpj__in=companies.values('cnpj')).exclude(workspace=client).select_related('workspace').order_by('cnpj','workspace_id')
    return render(request,'portal/master_account_manage.html',{'managed_workspace':client,'companies':companies,'duplicates':repeated,'blockers':blockers,'error':error,'action':action,'action_label':ACCOUNT_ACTIONS.get(action,'')})


@master_required
@require_http_methods(['GET','POST'])
@sensitive_post_parameters('password','file')
def company_manage(request,workspace_id,company_id):
    operator(request)
    company=get_object_or_404(Company.objects.select_related('workspace','certificate').defer('certificate__encrypted_file','certificate__encrypted_password'),pk=company_id,workspace_id=workspace_id)
    action=request.POST.get('action','') if request.method=='POST' else request.GET.get('action','')
    if action not in {'','certificate',*COMPANY_ACTIONS}:raise Http404
    environment=request.POST.get('environment',request.GET.get('environment','1'))
    if environment not in {'1','2'}:raise Http404
    form=CertificateForm(request.POST if request.method=='POST' and action=='certificate' else None,request.FILES if request.method=='POST' and action=='certificate' else None)
    error=''
    if request.method=='POST':
        if action=='certificate':
            if form.is_valid():
                from .services.certificates import save_certificate,CertificateError
                try:
                    with transaction.atomic():
                        locked=Company.objects.select_for_update().get(pk=company.pk,workspace_id=workspace_id)
                        save_certificate(locked,form.cleaned_data['file'].read(),form.cleaned_data['password'])
                        MasterAudit.objects.create(actor=request.user,workspace=company.workspace,action='certificate_replaced',details=f'Empresa id {company.pk}; A1 validado e cifrado. Histórico/filas preservados.')
                except CertificateError as e:form.add_error(None,str(e))
                else:
                    messages.success(request,'A1 validado e protegido. Autorizações existentes e progresso preservados; nenhum serviço novo foi autorizado.')
                    return redirect('master_company_manage',workspace_id=workspace_id,company_id=company.pk)
        elif request.POST.get('confirmed')!='on':error='Confirme que leu os efeitos desta ação.'
        elif action=='delete' and request.POST.get('confirmation')!=f'EXCLUIR EMPRESA {company.pk}':error='Digite a confirmação exatamente como indicada.'
        else:
            try:company_action(request.user,workspace_id,company.pk,action,environment)
            except ValidationError as e:error=' '.join(e.messages)
            else:
                messages.success(request,'Ação aplicada somente a este vínculo. Documentos e fila compartilhada preservados.')
                return redirect('master_account_manage',workspace_id=workspace_id)
    from .models import SefazDistributionStream,FiscalStream
    rows=[]
    configs=list(company.fiscal_connectors.all());nfe=SefazCaptureConfig.objects.filter(company=company).first()
    if nfe:configs.insert(0,nfe)
    for config in configs:
        service=getattr(config,'service','nfe')
        stream=(SefazDistributionStream.objects.filter(cnpj=company.cnpj,environment=config.environment,source='sefaz').first() if service=='nfe' else FiscalStream.objects.filter(cnpj=company.cnpj,environment=config.environment,service=service).first())
        blocked=not company.is_active or company.workspace.access_status!='active' or company.workspace.capture_paused
        now=timezone.now();certificate=getattr(company,'certificate',None)
        authorized=getattr(config,'read_authorized_at',getattr(config,'authorized_at',None))
        waiting=stream and stream.next_attempt_at and stream.next_attempt_at>now
        if blocked:status='Bloqueada pela conta/empresa'
        elif not config.enabled:status='Pausada'
        elif not authorized:status='Depende de autorização'
        elif certificate is None or certificate.is_demo or not certificate.valid_from<=now<certificate.valid_until:status='Requer A1 válido'
        elif stream and stream.lease_until and stream.lease_until>now:status='Em processamento'
        elif waiting and stream.last_status=='656':status='Aguardando intervalo · SEFAZ 656'
        elif config.last_error:status='Requer atenção'
        elif waiting:status='Aguardando intervalo'
        else:status='Habilitada · conforme fila'
        rows.append({'service':service,'config':config,'stream':stream,'status':status})
    duplicates=Company.objects.filter(cnpj=company.cnpj).exclude(pk=company.pk).select_related('workspace')
    return render(request,'portal/master_company_manage.html',{'company':company,'managed_workspace':company.workspace,'duplicates':duplicates,'rows':rows,'form':form,'blockers':references(company),'error':error,'action':action,'action_label':COMPANY_ACTIONS.get(action,''),'environment':environment})
