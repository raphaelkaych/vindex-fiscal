from .pagination import paginate
import csv
import hashlib
from datetime import date,timedelta
from decimal import Decimal
from django.contrib import messages
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView,PasswordChangeView
from django.core.cache import cache
from django.core.exceptions import BadRequest,ValidationError
from django.core.paginator import Paginator
from django.db import transaction,IntegrityError
from django.db.models import Sum,Q,Count
from django.http import HttpResponse,Http404
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from .forms import RegisterForm,LoginForm,CompanyForm,CertificateForm,ImportForm,ProfileForm
from .capture_forms import CaptureCertificateForm
from .models import Workspace,Company,Invoice,Installment,DigitalCertificate,AuditEntry
from .services.invoices import import_invoice,InvoiceImportError
from .services.certificates import save_certificate,CertificateError
from .services.demo import load_demo,sample_xml,DEMO_COMPANIES
from .validators import format_cnpj
from .services.operational import operational_companies


def health(request):
    from django.db import connection
    from django.http import JsonResponse
    try:
        with connection.cursor() as cursor:cursor.execute('SELECT 1');cursor.fetchone()
    except Exception:return JsonResponse({'ready':False},status=503)
    return JsonResponse({'ready':True})


def rate_limited(request,prefix,maximum=25):
    if request.method!='POST': return False
    key='vindex-limit:'+hashlib.sha256((prefix+request.META.get('REMOTE_ADDR','unknown')).encode()).hexdigest()
    cache.add(key,0,900)
    try: count=cache.incr(key)
    except ValueError: count=1;cache.set(key,count,900)
    return count>maximum

class PortalLoginView(LoginView):
    template_name='portal/auth.html'
    authentication_form=LoginForm
    redirect_authenticated_user=True
    def get_success_url(self):
        return self.get_redirect_url() or ('/gestao/' if self.request.user.has_perm('portal.admin_master') else '/')
    def dispatch(self,request,*args,**kwargs):
        if rate_limited(request,'login'):
            return render(request,'portal/limit.html',status=429)
        return super().dispatch(request,*args,**kwargs)

@sensitive_post_parameters('password1','password2')
def register(request):
    if settings.REGISTRATION_MODE=='closed':return HttpResponse('Cadastro por convite: solicite seu acesso à Vindex.',status=403)
    if request.user.is_authenticated: return redirect('dashboard')
    if rate_limited(request,'register',15): return render(request,'portal/limit.html',status=429)
    form=RegisterForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic(): user=form.save()
        except IntegrityError:
            form.add_error('email','Já existe uma conta com este e-mail.')
        else:
            if settings.REGISTRATION_MODE=='approval':
                Workspace.objects.filter(owner=user).update(access_status='pending')
            login(request,user)
            messages.success(request,'Sua conta foi criada. Cadastre a primeira empresa para começar.')
            return redirect('dashboard')
    return render(request,'portal/auth.html',{'form':form,'registering':True})

def workspace_for(request):
    if getattr(request,'supervised_workspace',None) is not None:
        return request.supervised_workspace
    workspace,_=Workspace.objects.get_or_create(owner=request.user,defaults={'name':request.user.first_name or 'Meu painel'})
    return workspace

def scoped_invoices(request,workspace):
    qs=Invoice.objects.filter(company__workspace=workspace,is_demo=False).select_related('company')
    selected=None
    if request.GET.get('company'):
        value=request.GET['company']
        if not value.isdecimal(): raise Http404
        selected=get_object_or_404(Company,workspace=workspace,pk=value)
        qs=qs.filter(company=selected)
    q=request.GET.get('q','').strip()[:150]
    if q: qs=qs.filter(Q(issuer_name__icontains=q)|Q(number__icontains=q)|Q(access_key__icontains=q)|Q(company__cnpj__icontains=q)|Q(company__legal_name__icontains=q))
    return qs,selected

def date_filters(request,qs,field):
    for param,lookup in [('from','gte'),('to','lte')]:
        value=request.GET.get(param,'')
        if value:
            try: parsed=date.fromisoformat(value)
            except ValueError: raise BadRequest('Use datas válidas nos filtros.') from None
            qs=qs.filter(**{f'{field}__{lookup}':parsed})
    return qs

@login_required
def dashboard(request):
    workspace=workspace_for(request)
    invoices,selected=scoped_invoices(request,workspace)
    installments=Installment.objects.filter(invoice__in=invoices).select_related('invoice__company').defer('invoice__xml_content','invoice__payment_details','invoice__billing_details')
    today=timezone.localdate()
    end=today+timedelta(days=30)
    invoice_stats=invoices.aggregate(value=Sum('total'),count=Count('pk'))
    total=invoice_stats['value'] or Decimal(0)
    companies=workspace.companies.select_related('certificate').defer('certificate__encrypted_file','certificate__encrypted_password').annotate(note_count=Count('invoices'))
    certs=DigitalCertificate.objects.filter(company__workspace=workspace,is_demo=False)
    if selected: certs=certs.filter(company=selected)
    cert_warnings=certs.filter(valid_until__lte=timezone.now()+timedelta(days=30)).count()
    chart=[];projections={}
    for offset,label in [(0,'Próximos 7 dias'),(7,'De 8 a 14 dias'),(14,'De 15 a 21 dias'),(21,'De 22 a 30 dias')]:
        upper=30 if offset==21 else offset+6
        projections['period_'+str(offset)]=Sum('amount',filter=Q(due_on__gte=today+timedelta(days=offset),due_on__lte=today+timedelta(days=upper)))
        chart.append({'label':label,'key':'period_'+str(offset)})
    projections.update(upcoming=Sum('amount',filter=Q(due_on__gte=today,due_on__lte=end)),overdue=Sum('amount',filter=Q(due_on__lt=today)),overdue_count=Count('pk',filter=Q(due_on__lt=today)))
    amounts=installments.aggregate(**projections)
    for bar in chart:bar['amount']=amounts[bar['key']] or Decimal(0)
    max_amount=max((v['amount'] for v in chart),default=Decimal(0))
    for bar in chart: bar['width']=round(bar['amount']/max_amount*100) if max_amount else 0
    context={'workspace':workspace,'companies':companies,'selected_company':selected,'invoice_count':invoice_stats['count'],'invoice_total':total,'upcoming_total':amounts['upcoming'] or Decimal(0),'overdue_total':amounts['overdue'] or Decimal(0),'overdue_count':amounts['overdue_count'],'certificate_count':certs.count(),'certificate_warnings':cert_warnings,'recent_invoices':invoices.defer('xml_content','payment_details','billing_details')[:5],'upcoming_installments':installments.filter(due_on__gte=today).order_by('due_on')[:5],'events':workspace.events.all()[:4],'chart':chart,'has_demo':False}
    from .models import Boleto
    boletos=Boleto.objects.filter(company__workspace=workspace)
    if selected: boletos=boletos.filter(company=selected)
    context['unlinked_boleto_count']=boletos.filter(installment__isnull=True).count()
    context['boleto_count']=boletos.count()
    return render(request,'portal/dashboard.html',context)

@login_required
def companies(request):
    workspace=workspace_for(request)
    companies=operational_companies(workspace).select_related('certificate').annotate(note_count=Count('invoices',filter=Q(invoices__is_demo=False)),note_total=Sum('invoices__total',filter=Q(invoices__is_demo=False)))
    return render(request,'portal/companies.html',{'companies':companies})

@login_required
def company_form(request,pk=None):
    workspace=workspace_for(request)
    company=get_object_or_404(Company,pk=pk,workspace=workspace) if pk else None
    form=CompanyForm(request.POST or None,instance=company,workspace=workspace)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                company=form.save(commit=False);company.workspace=workspace;company.save()
                AuditEntry.objects.create(workspace=workspace,description=f'Empresa {company.display_name} cadastrada ou atualizada'[:250])
        except IntegrityError: form.add_error('cnpj','Este CNPJ já está cadastrado.')
        else:
            messages.success(request,'Empresa salva. Você já pode importar os XMLs deste CNPJ.')
            return redirect('companies')
    return render(request,'portal/form.html',{'form':form,'page_title':'Editar empresa' if pk else 'Nova empresa','page_subtitle':'Organize cada CNPJ em um painel próprio e acompanhe o grupo na visão unificada.','submit_label':'Salvar empresa','back_url':'companies'})

@login_required
def certificates(request):
    workspace=workspace_for(request)
    return render(request,'portal/certificates.html',{'companies':operational_companies(workspace).select_related('certificate')})

@login_required
@sensitive_post_parameters('password')
def certificate_upload(request,pk):
    company=get_object_or_404(Company,pk=pk,workspace=workspace_for(request))
    capture_config=getattr(company,'capture_config',None)
    extra_configs={c.service:c for c in company.fiscal_connectors.filter(environment='1')}
    form=CaptureCertificateForm(request.POST or None,request.FILES or None,
        initial={'uf_author':(capture_config.uf_author if capture_config else '') or (extra_configs['cte'].uf_author if 'cte' in extra_configs else ''),
                 'enable_nfse':bool(extra_configs.get('nfse') and extra_configs['nfse'].enabled),
                 'enable_cte':bool(extra_configs.get('cte') and extra_configs['cte'].enabled),
                 'enable_capture':bool(capture_config and capture_config.enabled)})
    if request.method=='POST' and form.is_valid():
        try: save_certificate(company,form.cleaned_data['file'].read(),form.cleaned_data['password'])
        except CertificateError as exc: form.add_error(None,str(exc))
        else:
            from .models import FiscalConnector
            for service in ['nfse','cte']:
                enabled=form.cleaned_data['enable_'+service]
                if enabled or service in extra_configs:
                    extra,_=FiscalConnector.objects.get_or_create(company=company,service=service,environment='1')
                    extra.enabled=enabled
                    if enabled:
                        extra.authorized_at=timezone.now();extra.authorized_by=request.user
                        extra.uf_author=form.cleaned_data['uf_author'] if service=='cte' else ''
                    extra.save()
                    AuditEntry.objects.create(workspace=company.workspace,description=f'Leitura {service} {"habilitada" if enabled else "pausada"} no vínculo/renovação do A1; progresso preservado.')
            if form.cleaned_data['enable_capture']:
                from .services.capture import configure_capture
                from .services.sefaz import SefazError
                try:
                    configured=configure_capture(company.workspace,company.pk,enabled=True,environment='1',actor=request.user,
                        authorize_read=True,uf_author=form.cleaned_data['uf_author'])
                except (SefazError,ValidationError) as exc:
                    messages.warning(request,f'Certificado salvo com proteção. A captura precisa de atenção: {exc}')
                else:
                    if configured.last_error:
                        messages.warning(request,'Certificado protegido e autorização de leitura salva. Resolva o impedimento indicado no painel da captura.')
                    else:
                        messages.success(request,'Certificado protegido e captura de leitura habilitada. A consulta foi agendada; acompanhe o resultado oficial no painel da empresa.')
                return redirect('capture_detail',pk=company.pk)
            if capture_config and capture_config.enabled:
                from .services.capture import configure_capture
                configure_capture(company.workspace,company.pk,enabled=False,actor=request.user,
                    environment=capture_config.environment,uf_author=capture_config.uf_author)
                messages.success(request,'Certificado protegido e captura pausada conforme a opção escolhida. O histórico e o NSU foram preservados.')
                return redirect('capture_detail',pk=company.pk)
            messages.success(request,'Certificado protegido e associado à empresa. Autorize a captura de leitura para agendar consultas automáticas.')
            return redirect('certificates')
    return render(request,'portal/certificate_form.html',{'company':company,'form':form})

@login_required
@require_POST
def certificate_delete(request,pk):
    workspace=workspace_for(request)
    certificate=get_object_or_404(DigitalCertificate,company_id=pk,company__workspace=workspace)
    name=certificate.company.display_name
    certificate.delete()
    AuditEntry.objects.create(workspace=workspace,description=f'Certificado removido: {name}'[:250])
    messages.success(request,'Certificado removido. O histórico de notas foi preservado.')
    return redirect('certificates')

@login_required
def invoices(request):
    workspace=workspace_for(request)
    qs,selected=scoped_invoices(request,workspace)
    qs=date_filters(request,qs,'issued_on')
    if request.GET.get('review')=='pending': qs=qs.exclude(review_notes='')
    page=paginate(request,qs,15)
    query=request.GET.copy();query.pop('page',None)
    return render(request,'portal/invoices.html',{'page':page,'companies':operational_companies(workspace),'selected_company':selected,'query_string':query.urlencode(),'filtered_count':page.paginator.count,'filtered_total':qs.aggregate(value=Sum('total'))['value'] or Decimal(0)})

@login_required
def invoice_detail(request,pk):
    invoice=get_object_or_404(Invoice.objects.select_related('company').prefetch_related('installments__revisions','installments__boleto'),pk=pk,company__workspace=workspace_for(request),is_demo=False)
    return render(request,'portal/invoice.html',{'invoice':invoice})

@login_required
def xml_download(request,pk):
    invoice=get_object_or_404(Invoice,pk=pk,company__workspace=workspace_for(request),is_demo=False)
    response=HttpResponse(invoice.xml_content,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="nfe-{invoice.access_key}.xml"'
    response['X-Content-Type-Options']='nosniff'
    response['Cache-Control']='no-store, private'
    return response

@login_required
def import_xml(request):
    workspace=workspace_for(request)
    form=ImportForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        created=0;existing=0;errors=[]
        for file in form.cleaned_data['files']:
            try:
                _,new=import_invoice(workspace,file.read())
                created+=int(new);existing+=int(not new)
            except InvoiceImportError as exc: errors.append(str(exc))
        if created: messages.success(request,f'{created} nota(s) importada(s). As parcelas são previsões, sujeitas à conferência.')
        if existing: messages.info(request,f'{existing} nota(s) já estavam cadastradas; nenhuma duplicidade foi criada.')
        for error in errors: messages.error(request,error)
        if not errors: return redirect('invoices')
    return render(request,'portal/import.html',{'form':form,'company_count':workspace.companies.count()})

@login_required
def agenda(request):
    workspace=workspace_for(request)
    notes,selected=scoped_invoices(request,workspace)
    qs=Installment.objects.filter(invoice__in=notes).select_related('invoice__company')
    qs=date_filters(request,qs,'due_on')
    state=request.GET.get('state','')
    today=timezone.localdate()
    if state=='overdue': qs=qs.filter(due_on__lt=today)
    elif state=='upcoming': qs=qs.filter(due_on__gte=today)
    elif state=='undated': qs=qs.filter(due_on__isnull=True)
    query=request.GET.copy();query.pop('page',None)
    return render(request,'portal/agenda.html',{'page':paginate(request,qs,20),'companies':operational_companies(workspace),'selected_company':selected,'filtered_total':qs.aggregate(value=Sum('amount'))['value'] or Decimal(0),'filtered_count':qs.count(),'query_string':query.urlencode()})

@login_required
@require_POST
def installment_check(request,pk):
    item=get_object_or_404(Installment,pk=pk,invoice__company__workspace=workspace_for(request))
    from .services.installments import review_installment
    review_installment(workspace_for(request),item,not item.checked,actor=request.user.pk)
    messages.success(request,'Conferência atualizada. Essa ação não agenda nem confirma pagamento.')
    return redirect('invoice_detail',pk=item.invoice_id)

@login_required
def profile(request):
    workspace=workspace_for(request)
    form=ProfileForm(request.POST or None,instance=workspace,initial={'full_name':request.user.first_name})
    if request.method=='POST' and form.is_valid():
        form.save();request.user.first_name=form.cleaned_data['full_name'];request.user.save(update_fields=['first_name'])
        messages.success(request,'Seus dados foram atualizados.');return redirect('profile')
    return render(request,'portal/profile.html',{'form':form})

class ChangePassword(PasswordChangeView):
    template_name='portal/form.html'
    success_url=reverse_lazy('profile')
    extra_context={'page_title':'Alterar senha','page_subtitle':'Escolha uma senha exclusiva para o seu acesso.','submit_label':'Atualizar senha','back_url':'profile'}
    def form_valid(self,form):
        messages.success(self.request,'Senha alterada.');return super().form_valid(form)

@login_required
@require_POST
def demo(request):
    raise Http404('Demonstrações disponíveis somente nos testes isolados.')

@login_required
def example_xml(request):
    raise Http404('Exemplos disponíveis somente nos testes isolados.')

def csv_safe(value):
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value

@login_required
def export_csv(request):
    workspace=workspace_for(request)
    notes,_=scoped_invoices(request,workspace)
    kind=request.GET.get('kind','notes')
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="vindex-previsoes.csv"' if kind=='agenda' else 'attachment; filename="vindex-notas.csv"'
    response.write('﻿')
    writer=csv.writer(response,delimiter=';')
    if kind=='agenda':
        rows=Installment.objects.filter(invoice__in=notes).select_related('invoice__company')
        rows=date_filters(request,rows,'due_on')
        state=request.GET.get('state','')
        if state=='overdue': rows=rows.filter(due_on__lt=timezone.localdate())
        elif state=='upcoming': rows=rows.filter(due_on__gte=timezone.localdate())
        elif state=='undated': rows=rows.filter(due_on__isnull=True)
        writer.writerow(['Empresa','CNPJ','Fornecedor','NF-e','Parcela','Vencimento','Valor previsto','Conferida','Demonstracao'])
        for p in rows:
            writer.writerow([csv_safe(p.invoice.company.display_name),format_cnpj(p.invoice.company.cnpj),csv_safe(p.invoice.issuer_name),p.invoice.number,csv_safe(p.number),p.due_on.strftime('%d/%m/%Y') if p.due_on else '',str(p.amount).replace('.',','),'Sim' if p.checked else 'Nao','Sim' if p.invoice.is_demo else 'Nao'])
    else:
        notes=date_filters(request,notes,'issued_on')
        if request.GET.get('review')=='pending': notes=notes.exclude(review_notes='')
        writer.writerow(['Empresa','CNPJ','Fornecedor','NF-e','Emissao','Valor','Chave','Conferencia','Demonstracao'])
        for note in notes:
            writer.writerow([csv_safe(note.company.display_name),format_cnpj(note.company.cnpj),csv_safe(note.issuer_name),note.number,note.issued_on.strftime('%d/%m/%Y'),str(note.total).replace('.',','),note.access_key,'Pendente' if note.needs_review else 'Parcelas extraidas','Sim' if note.is_demo else 'Nao'])
    return response
