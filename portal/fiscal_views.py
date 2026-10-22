from .pagination import paginate
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse,Http404
from django.shortcuts import get_object_or_404,render,redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods,require_safe
from .models import Company,FiscalConnector,FiscalDocument,FiscalStream,FiscalDelivery,AuditEntry
from .views import workspace_for
from .services.capture import UF_CODES
from .capture_forms import UF_CHOICES
from .services.fiscal_capture import requirements
from .services.sefaz import SefazError


class ConnectorForm(forms.Form):
    service=forms.ChoiceField(label='Conector',choices=[('nfse','NFS-e nacional / ADN'),('cte','CT-e modelo 57')])
    environment=forms.ChoiceField(label='Ambiente',choices=[('1','Produção'),('2','Homologação')])
    uf_author=forms.ChoiceField(label='UF do autor (obrigatória para CT-e)',required=False,choices=UF_CHOICES)
    enabled=forms.BooleanField(label='Habilitar este conector',required=False)
    authorize=forms.BooleanField(label='Autorizo consultas de leitura deste CNPJ neste serviço e ambiente. Não autoriza eventos fiscais.',required=False)
    def clean(self):
        data=super().clean()
        if data.get('enabled') and not data.get('authorize'):self.add_error('authorize','Confirme a autorização específica de leitura.')
        if data.get('service')=='cte' and data.get('enabled') and not data.get('uf_author'):self.add_error('uf_author','Selecione a UF desta empresa.')
        return data


@login_required
@never_cache
@require_http_methods(['GET','POST'])
def connectors(request,company_id):
    company=get_object_or_404(Company,workspace=workspace_for(request),pk=company_id)
    form=ConnectorForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        with transaction.atomic():
            config,_=FiscalConnector.objects.get_or_create(company=company,service=d['service'],environment=d['environment'])
            config.enabled=d['enabled'];config.uf_author=d['uf_author']
            if d['enabled']:config.authorized_at=timezone.now();config.authorized_by=request.user
            config.save()
            try:requirements(config);config.last_error=''
            except SefazError as e:config.last_error=str(e)
            config.save(update_fields=['last_error'])
            AuditEntry.objects.create(workspace=company.workspace,description=f'Conector {config.service} {"habilitado" if config.enabled else "pausado"}, ambiente {config.environment}; autorização de leitura.')
        messages.success(request,'Configuração salva. O processo periódico validará os requisitos antes da consulta.')
        return redirect('fiscal_connectors',company_id=company.pk)
    rows=[]
    for config in company.fiscal_connectors.all():
        try:requirements(config);can_observe=True
        except SefazError:can_observe=False
        stream=FiscalStream.objects.filter(cnpj=company.cnpj,service=config.service,environment=config.environment).first() if can_observe else None
        from django.db.models import Count
        from .services.fiscal_coverage import coverage
        rows.append({'coverage':coverage(stream),'config':config,'stream':stream,'counts':list(config.deliveries.values('envelope__kind').annotate(total=Count('pk'))),'documents':config.deliveries.select_related('envelope').defer('envelope__xml_content').order_by('-pk')[:20],
            'imported_count':company.fiscal_documents.filter(service=config.service,environment=config.environment,validation_status='schema').count(),'partial_count':company.fiscal_documents.filter(service=config.service,environment=config.environment,validation_status='partial').count(),'pending_count':config.deliveries.exclude(error='').count(),
            'last_import':company.fiscal_documents.filter(service=config.service,environment=config.environment).only('imported_at').order_by('-imported_at').first()})
    return render(request,'portal/fiscal_connectors.html',{'company':company,'form':form,'rows':rows})


@login_required
@never_cache
@require_safe
def documents(request):
    from .models import Invoice
    from django.db.models import F,Value,CharField,BooleanField
    from django.db.models.functions import TruncDate
    workspace=workspace_for(request)
    qs=FiscalDocument.objects.filter(company__workspace=workspace)
    nfe=Invoice.objects.filter(company__workspace=workspace,is_demo=False)
    kind=request.GET.get('type','')
    if kind:
        if kind not in {'cte','nfse','nfe'}:raise Http404
        qs=qs.filter(service=kind)
    if request.GET.get('company'):
        if not request.GET['company'].isdecimal():raise Http404
        selected=get_object_or_404(Company,workspace=workspace,pk=request.GET['company']);qs=qs.filter(company=selected);nfe=nfe.filter(company=selected)
    fields=['doc_id','doc_type','doc_number','company_name','cnpj','supplier','issued','captured','amount','cancelled','processing']
    other=qs.order_by().annotate(doc_id=F('pk'),doc_type=F('service'),doc_number=F('number'),company_name=F('company__legal_name'),cnpj=F('company__cnpj'),supplier=F('issuer_name'),issued=TruncDate('issued_at'),captured=F('imported_at'),amount=F('total'),cancelled=F('cancellation_reported'),processing=F('validation_status')).values(*fields)
    products=nfe.order_by().annotate(doc_id=F('pk'),doc_type=Value('nfe',output_field=CharField()),doc_number=F('number'),company_name=F('company__legal_name'),cnpj=F('company__cnpj'),supplier=F('issuer_name'),issued=F('issued_on'),captured=F('imported_at'),amount=F('total'),cancelled=Value(False,output_field=BooleanField()),processing=Value('schema',output_field=CharField())).values(*fields)
    # Os conjuntos são disjuntos por doc_type/doc_id; DISTINCT apenas repetia
    # trabalho sobre todo o histórico antes do COUNT e da paginação.
    combined=products if kind=='nfe' else other if kind else products.union(other,all=True)
    query=request.GET.copy();query.pop('page',None)
    from .services.operational import operational_companies
    return render(request,'portal/fiscal_documents.html',{'page':paginate(request,combined.order_by('-captured','doc_type','-doc_id'),25),'companies':operational_companies(workspace),'query_string':query.urlencode()})


@login_required
@never_cache
@require_safe
def document_detail(request,pk,service=None):
    qs=FiscalDocument.objects.filter(company__workspace=workspace_for(request))
    if service:qs=qs.filter(service=service)
    doc=get_object_or_404(qs,pk=pk)
    from .services.nfse_official_pdf import capabilities
    if doc.service=='nfse':
        from .services.nfse_presentation import read_nfse,parties,sections,extra_fields,DPS
        context={'document':doc,'pdf_capabilities':capabilities(doc)}
        try:
            info=read_nfse(doc)
            context.update(parties=parties(info),sections=sections(info),ibs_fields=extra_fields(info,'IBSCBS')+extra_fields(info,DPS+'IBSCBS'))
        except SefazError as error:context['presentation_error']=str(error)
        return render(request,'portal/nfse_detail.html',context)
    return render(request,'portal/fiscal_document.html',{'document':doc,'pdf_capabilities':capabilities(doc) if doc.service=='nfse' else {}})


@login_required
@never_cache
@require_safe
def document_xml(request,pk,service=None):
    qs=FiscalDocument.objects.filter(company__workspace=workspace_for(request))
    if service:qs=qs.filter(service=service)
    doc=get_object_or_404(qs,pk=pk)
    response=HttpResponse(doc.xml_content,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="{doc.service}-{doc.access_key}.xml"';response['X-Content-Type-Options']='nosniff'
    return response


@login_required
@never_cache
@require_safe
def envelope_xml(request,pk):
    delivery=get_object_or_404(FiscalDelivery.objects.select_related('envelope'),pk=pk,connector__company__workspace=workspace_for(request))
    response=HttpResponse(delivery.envelope.xml_content,content_type='application/xml; charset=utf-8')
    response['Content-Disposition']='attachment; filename="documento-distribuido.xml"';response['X-Content-Type-Options']='nosniff'
    return response


@login_required
@never_cache
@require_safe
def document_pdf(request,pk,service=None):
    qs=FiscalDocument.objects.filter(company__workspace=workspace_for(request))
    if service:qs=qs.filter(service=service)
    doc=get_object_or_404(qs,pk=pk)
    from .services.dacte import generate_dacte
    from .services.nfse_pdf import generate_nfse_pdf
    try:payload=generate_nfse_pdf(doc) if doc.service=='nfse' else generate_dacte(doc)
    except SefazError as error:
        messages.error(request,str(error));return redirect('fiscal_document',pk=doc.pk)
    response=HttpResponse(payload,content_type='application/pdf')
    prefix=('danfse-recuperado' if doc.official_pdf_source and doc.official_pdf is not None else 'nfse-conferencia' if doc.validation_status=='partial' else 'danfse-vindex') if doc.service=='nfse' else 'dacte'
    response['Content-Disposition']=f'attachment; filename="{prefix}-{doc.access_key}.pdf"';response['X-Content-Type-Options']='nosniff'
    return response


class NfseFilterForm(forms.Form):
    q=forms.CharField(label='Buscar número, prestador ou chave',required=False,max_length=100)
    company=forms.ModelChoiceField(label='Empresa',queryset=Company.objects.none(),required=False,empty_label='Todas as empresas')
    environment=forms.ChoiceField(label='Ambiente',required=False,choices=[('1','Produção'),('2','Homologação'),('','Todos')])
    status=forms.ChoiceField(label='Situação',required=False,choices=[('','Todas'),('schema','Schema validado'),('partial','Parcial — revisar'),('cancelled','Cancelamento recebido'),('substituted','Substituição recebida')])
    start=forms.DateField(label='Emissão a partir de',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='Emissão até',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    def clean(self):
        data=super().clean()
        if data.get('start') and data.get('end') and data['end']<data['start']:
            self.add_error('end','A data final deve ser igual ou posterior à inicial.')
        return data


@login_required
@never_cache
@require_safe
def nfse_list(request):
    from django.db.models import Q,Count
    workspace=workspace_for(request)
    data=request.GET.copy();data.setdefault('environment','1')
    form=NfseFilterForm(data)
    form.fields['company'].queryset=Company.objects.filter(workspace=workspace).order_by('legal_name')
    qs=FiscalDocument.objects.filter(company__workspace=workspace,service='nfse')
    if form.is_valid():
        filters=form.cleaned_data
        if filters['q']:
            q=filters['q'];qs=qs.filter(Q(number__icontains=q)|Q(issuer_name__icontains=q)|Q(issuer_cnpj__icontains=q)|Q(access_key__icontains=q))
        if filters['company']:qs=qs.filter(company=filters['company'])
        if filters['environment']:qs=qs.filter(environment=filters['environment'])
        if filters['status'] in {'schema','partial'}:qs=qs.filter(validation_status=filters['status'])
        elif filters['status']=='cancelled':qs=qs.filter(cancellation_reported=True)
        elif filters['status']=='substituted':qs=qs.filter(substitution_reported=True)
        if filters['start']:qs=qs.filter(issued_at__date__gte=filters['start'])
        if filters['end']:qs=qs.filter(issued_at__date__lte=filters['end'])
    else:qs=qs.none()
    counts=qs.aggregate(total=Count('pk'),partial=Count('pk',filter=Q(validation_status='partial')),cancelled=Count('pk',filter=Q(cancellation_reported=True)))
    qs=qs.select_related('company').defer('xml_content','official_pdf','validation_details','payment_data').order_by('-issued_at','-pk')
    return render(request,'portal/nfse_list.html',{'form':form,'counts':counts,'page':paginate(request,qs,25)})
