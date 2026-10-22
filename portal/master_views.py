from .pagination import paginate
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q,Count,Min,Max,OuterRef,Subquery,IntegerField
from django.db.models.functions import Coalesce
from django.http import HttpResponse,Http404
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_POST,require_safe
from django.views.decorators.cache import never_cache
from django.utils import timezone
from .models import Workspace,Company,Invoice,DigitalCertificate,MasterAudit,FiscalDocument
from .api_models import ApiCredential


def master_required(view):
    @login_required
    @never_cache
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.has_perm('portal.admin_master'):raise PermissionDenied
        return view(request,*args,**kwargs)
    return wrapped


@master_required
@require_safe
def management(request):
    from .services.operational import operational_companies
    clients=Workspace.objects.select_related('owner').annotate(company_count=Count('companies',filter=Q(companies__pk__in=operational_companies().values('pk')),distinct=True))
    q=request.GET.get('q','')[:150]
    if q:
        digits=''.join(char for char in q if char.isdecimal())
        clients=clients.filter(Q(name__icontains=q)|Q(owner__email__icontains=q)|Q(companies__cnpj__icontains=digits if len(digits)>=8 else q)).distinct()
    status=request.GET.get('status','')
    if status in {'active','pending','suspended'}:clients=clients.filter(access_status=status)
    nfe=Invoice.objects.filter(company__workspace_id=OuterRef('pk'),is_demo=False).order_by().values('company__workspace_id').annotate(total=Count('pk')).values('total')[:1]
    fiscal=FiscalDocument.objects.filter(company__workspace_id=OuterRef('pk'),validation_status='schema').order_by().values('company__workspace_id').annotate(total=Count('pk')).values('total')[:1]
    clients=clients.annotate(nfe_count=Coalesce(Subquery(nfe,output_field=IntegerField()),0),fiscal_count=Coalesce(Subquery(fiscal,output_field=IntegerField()),0))
    from .services.capture_runtime import capture_runtime_status
    from .models import FiscalConnector,SefazCaptureConfig,FiscalDelivery
    totals={'clients':Workspace.objects.count(),'pending':Workspace.objects.filter(access_status='pending').count(),
        'companies':operational_companies().count(),'nfe':Invoice.objects.filter(is_demo=False).count(),
        'fiscal':FiscalDocument.objects.filter(validation_status='schema').count(),'errors':FiscalConnector.objects.exclude(last_error='').count()+SefazCaptureConfig.objects.exclude(last_error='').count(),
        'document_errors':FiscalDelivery.objects.exclude(error='').count()}
    query=request.GET.copy();query.pop('page',None)
    return render(request,'portal/master.html',{'page_title':'Gestão Vindex','page':paginate(request,clients.order_by('name','pk'),25),'q':q,'status':status,'query_string':query.urlencode(),'totals':totals,'runtime':capture_runtime_status()})


@master_required
@require_safe
def supervise(request,workspace_id):
    client=get_object_or_404(Workspace.objects.select_related('owner'),pk=workspace_id)
    from .services.operational import operational_companies
    companies=operational_companies(client).select_related('certificate','capture_config').prefetch_related('sefaz_states','fiscal_connectors')
    invoices=Invoice.objects.filter(company__workspace=client,is_demo=False).select_related('company')
    if request.GET.get('company'):
        if not request.GET['company'].isdecimal():raise Http404
        company=get_object_or_404(Company,pk=request.GET['company'],workspace=client)
        invoices=invoices.filter(company=company)
    MasterAudit.objects.create(actor=request.user,workspace=client,action='supervision_read')
    fiscal=FiscalDocument.objects.filter(company__workspace=client).select_related('company').defer('xml_content','official_pdf')
    if request.GET.get('company'):
        fiscal=fiscal.filter(company=company)
    fiscal_type=request.GET.get('fiscal_type','')
    if fiscal_type not in {'','nfse','cte'}:raise Http404
    fiscal_page=paginate(request,fiscal.filter(service=fiscal_type) if fiscal_type else fiscal,25,'fiscal_page','fiscal_per_page')
    def fiscal_page_url(number):
        query=request.GET.copy();query['fiscal_page']=number
        return '?'+query.urlencode()
    return render(request,'portal/supervise.html',{'supervised_workspace':client,'companies':companies,'invoice_count':invoices.count(),
        'nfe_dates':invoices.aggregate(first=Min('issued_on'),latest=Max('issued_on'),captured=Max('imported_at')),
        'fiscal_counts':list(fiscal.values('service','validation_status','company__legal_name','company__cnpj').annotate(total=Count('pk'),first=Min('issued_at'),latest=Max('issued_at'),captured=Max('imported_at'))),
        'fiscal_documents':fiscal_page,'fiscal_type':fiscal_type,
        'fiscal_prev_url':fiscal_page_url(fiscal_page.previous_page_number()) if fiscal_page.has_previous() else '',
        'fiscal_next_url':fiscal_page_url(fiscal_page.next_page_number()) if fiscal_page.has_next() else '',
        'page':paginate(request,invoices,25),'activities':client.events.all()[:15],
        'operations_allowed':request.user.has_perm('portal.operate_clients'),'master_audit':MasterAudit.objects.filter(workspace=client).select_related('actor')[:20]})


@master_required
@require_POST
@transaction.atomic
def client_action(request,workspace_id):
    if not request.user.has_perm('portal.operate_clients'):raise PermissionDenied
    client=get_object_or_404(Workspace.objects.select_for_update(),pk=workspace_id)
    action=request.POST.get('action')
    if action=='suspended' and client.owner_id==request.user.pk:raise PermissionDenied
    if action=='suspended' and (client.owner.is_staff or client.owner.is_superuser or client.owner.has_perm('portal.admin_master')):raise PermissionDenied
    if action in {'active','pending','suspended'}:
        client.access_status=action;client.save(update_fields=['access_status'])
    elif action in {'pause_capture','resume_capture'}:
        client.capture_paused=action=='pause_capture';client.save(update_fields=['capture_paused'])
    elif action=='revoke_api':
        ApiCredential.objects.filter(workspace=client,revoked_at__isnull=True).update(revoked_at=timezone.now())
    else:raise PermissionDenied
    MasterAudit.objects.create(actor=request.user,workspace=client,action=action)
    return redirect('master_client',workspace_id=client.pk)


@master_required
@require_safe
def supervised_xml(request,workspace_id,pk):
    client=get_object_or_404(Workspace,pk=workspace_id)
    invoice=get_object_or_404(Invoice,pk=pk,company__workspace=client,is_demo=False)
    MasterAudit.objects.create(actor=request.user,workspace=client,action='xml_download',details=f'NF-e id {invoice.pk}')
    response=HttpResponse(invoice.xml_content,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="nfe-{invoice.access_key}.xml"'
    response['X-Content-Type-Options']='nosniff'
    return response


@master_required
@require_safe
def supervised_fiscal(request,workspace_id,pk):
    client=get_object_or_404(Workspace,pk=workspace_id)
    document=get_object_or_404(FiscalDocument,pk=pk,company__workspace=client)
    MasterAudit.objects.create(actor=request.user,workspace=client,action='fiscal_xml_download',details=f'{document.service} id {document.pk}')
    response=HttpResponse(document.xml_content,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="{document.service}-{document.access_key}.xml"'
    response['X-Content-Type-Options']='nosniff';return response


@master_required
@require_safe
def supervised_document(request,workspace_id,kind,pk):
    client=get_object_or_404(Workspace,pk=workspace_id)
    if kind not in {'nfe','nfse','cte'}:raise Http404
    doc=get_object_or_404(Invoice if kind=='nfe' else FiscalDocument,pk=pk,company__workspace=client,**({'is_demo':False} if kind=='nfe' else {'service':kind}))
    output=request.GET.get('format','')
    if output not in {'','xml','pdf'}:raise Http404
    MasterAudit.objects.create(actor=request.user,workspace=client,action='supervision_document_'+(output or 'read'),details=f'{kind} id {pk}')
    error=''
    if output=='xml':
        response=HttpResponse(doc.xml_content,content_type='application/xml; charset=utf-8');response['Content-Disposition']=f'attachment; filename="{kind}-{doc.access_key}.xml"';response['X-Content-Type-Options']='nosniff';return response
    if output=='pdf':
        from .services.sefaz import SefazError
        from .services.danfe import DanfeError,generate_danfe
        from .services.dacte import generate_dacte
        from .services.nfse_pdf import generate_nfse_pdf
        try:
            data=generate_danfe(doc) if kind=='nfe' else generate_nfse_pdf(doc) if kind=='nfse' else generate_dacte(doc)
        except (SefazError,DanfeError) as e:error=str(e)
        else:
            response=HttpResponse(data,content_type='application/pdf');response['Content-Disposition']=f'attachment; filename="{kind}-{doc.access_key}.pdf"';response['X-Content-Type-Options']='nosniff';return response
    return render(request,'portal/supervise_document.html',{'supervised_workspace':client,'document':doc,'kind':kind,'error':error,
        'issued':doc.issued_on if kind=='nfe' else timezone.localtime(doc.issued_at).date(),'evidence':doc.payment_evidence if kind=='nfe' else doc.payment_data})
