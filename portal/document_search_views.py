from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import Exists,OuterRef,Q
from django.http import Http404,HttpResponse
from django.shortcuts import render,get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from .models import Company,FiscalSearchRecord,FiscalSearchItem,Invoice,FiscalDocument
from .pagination import paginate
from .views import workspace_for
from .services.operational import operational_companies
from .services.fiscal_search import normalize

STATUS=[('','Todas'),('stored','Armazenado · situação atual não consultada'),('partial','Parcial · revisar'),('cancelled','Cancelamento recebido'),('substituted','Substituição recebida')]


class SearchForm(forms.Form):
    type=forms.ChoiceField(label='Tipo',required=False,choices=[('','Todos disponíveis'),('nfe','NF-e'),('nfse','NFS-e'),('cte','CT-e')])
    issuer_cnpj=forms.CharField(label='CNPJ do emitente',required=False,max_length=18)
    issuer=forms.CharField(label='Nome do emitente',required=False,max_length=200)
    recipient_cnpj=forms.CharField(label='CNPJ do destinatário / tomador',required=False,max_length=18)
    number=forms.CharField(label='Número do documento',required=False,max_length=30)
    series=forms.CharField(label='Série',required=False,max_length=30)
    key=forms.CharField(label='Chave de acesso',required=False,max_length=64)
    start=forms.DateField(label='Emissão a partir de',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='Emissão até',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    minimum=forms.DecimalField(label='Valor mínimo (R$)',required=False,max_digits=18,decimal_places=2)
    maximum=forms.DecimalField(label='Valor máximo (R$)',required=False,max_digits=18,decimal_places=2)
    status=forms.ChoiceField(label='Situação informada',choices=STATUS,required=False)
    product=forms.CharField(label='Produto, serviço ou código',required=False,max_length=200)
    code=forms.CharField(label='Código exato do produto / serviço',required=False,max_length=100)
    ncm=forms.RegexField(label='NCM',regex=r'^\d{2,8}$',required=False,max_length=8)
    cfop=forms.RegexField(label='CFOP',regex=r'^\d{4}$',required=False,max_length=4)
    environment=forms.ChoiceField(label='Ambiente',required=False,choices=[('','Todos, identificados separadamente'),('1','Produção'),('2','Homologação')])
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        placeholders={'product':'Nome do produto, serviço ou código','issuer':'Nome ou parte da razão social',
            'issuer_cnpj':'00.000.000/0000-00','recipient_cnpj':'00.000.000/0000-00',
            'number':'Número da nota','series':'Série','key':'Chave completa ou parte dela',
            'code':'Código informado no XML','ncm':'Ex.: 23091000','cfop':'Ex.: 5102',
            'minimum':'Sem mínimo','maximum':'Sem máximo'}
        for name,placeholder in placeholders.items():self.fields[name].widget.attrs['placeholder']=placeholder
        for name in ['ncm','cfop']:self.fields[name].widget.attrs['inputmode']='numeric'
        self.fields['product'].help_text='A busca ignora acentos e diferenças entre maiúsculas e minúsculas.'
    def clean(self):
        data=super().clean()
        if data.get('start') and data.get('end') and data['start']>data['end']:self.add_error('end','A data final deve ser igual ou posterior à inicial.')
        if data.get('minimum') is not None and data.get('maximum') is not None and data['minimum']>data['maximum']:self.add_error('maximum','O valor máximo deve ser igual ou maior que o mínimo.')
        for field in ['issuer_cnpj','recipient_cnpj']:
            if data.get(field):
                normalized=''.join(ch for ch in data[field] if ch.isalnum()).upper()
                if len(normalized)!=14:self.add_error(field,'Informe os 14 caracteres do CNPJ.')
                else:data[field]=normalized
        return data


def filtered(request):
    workspace=workspace_for(request)
    company=None
    if request.GET.get('company'):
        if not request.GET['company'].isdecimal():raise Http404
        company=get_object_or_404(Company,workspace=workspace,pk=request.GET['company'])
    form=SearchForm(request.GET)
    records=FiscalSearchRecord.objects.filter(company__workspace=workspace)
    if company:records=records.filter(company=company)
    item_q=Q()
    if not form.is_valid():return form,records.none(),item_q
    d=form.cleaned_data
    if d.get('issuer'):records=records.filter(issuer_search__contains=normalize(d['issuer']))
    fields={'type':'kind','issuer_cnpj':'issuer_cnpj__iexact','recipient_cnpj':'recipient_cnpj__iexact','number':'number','series':'series','key':'access_key__icontains','start':'issued_on__gte','end':'issued_on__lte','minimum':'total__gte','maximum':'total__lte','status':'status','environment':'environment'}
    for key,lookup in fields.items():
        if d.get(key) is not None and d.get(key)!='':records=records.filter(**{lookup:d[key]})
    if d.get('product'):item_q&=Q(search_text__contains=normalize(d['product']))
    for key in ['code','ncm','cfop']:
        if d.get(key):item_q&=Q(**{key:d[key]})
    if item_q:records=records.filter(Exists(FiscalSearchItem.objects.filter(item_q,record_id=OuterRef('pk'))))
    return form,records,item_q


@login_required
@never_cache
@require_safe
def documents(request):
    form,records,item_q=filtered(request)
    workspace=workspace_for(request)
    query=request.GET.copy();query.pop('page',None)
    qs=records.select_related('company').order_by('-imported_at','-pk')
    from django.db.models import Prefetch
    qs=qs.prefetch_related(Prefetch('items',queryset=FiscalSearchItem.objects.filter(item_q).order_by('position'),to_attr='matching_items'))
    missing=Invoice.objects.filter(company__workspace=workspace,is_demo=False,search_record__isnull=True).count()+FiscalDocument.objects.filter(company__workspace=workspace,search_record__isnull=True).count()
    groups=[]
    for title,description,names in [
        ('Documento','Identifique uma nota ou refine sua situação e ambiente.',['number','series','key','status','environment']),
        ('Participantes','Encontre documentos de um fornecedor ou destinatário.',['issuer','issuer_cnpj','recipient_cnpj']),
        ('Itens e valores','Combine classificação, código e faixa de valor do documento.',['code','ncm','cfop','minimum','maximum'])]:
        groups.append({'title':title,'description':description,'fields':[form[name] for name in names]})
    advanced_names=[field.name for group in groups for field in group['fields']]
    advanced_count=sum(bool(request.GET.get(name)) for name in advanced_names)
    chips=[]
    if form.is_valid():
        for name,value in form.cleaned_data.items():
            if value is None or value=='':continue
            field=form.fields[name]
            label=dict(getattr(field,'choices',[])).get(str(value),value)
            if hasattr(label,'strftime'):label=label.strftime('%d/%m/%Y')
            chip_query=query.copy();chip_query.pop(name,None)
            chips.append({'name':field.label,'value':label,'query':chip_query.urlencode()})
        if request.GET.get('company'):
            selected=Company.objects.get(workspace=workspace,pk=request.GET['company'])
            chip_query=query.copy();chip_query.pop('company',None)
            chips.insert(0,{'name':'Empresa','value':selected.display_name,'query':chip_query.urlencode()})
    return render(request,'portal/fiscal_documents.html',dict(form=form,page=paginate(request,qs,25),companies=operational_companies(workspace),query_string=query.urlencode(),missing_index=missing,item_search=bool(item_q),
        filter_groups=groups,advanced_count=advanced_count,advanced_open=advanced_count or any(form[name].errors for name in advanced_names),filter_chips=chips))


@login_required
@never_cache
@require_safe
def export_xlsx(request):
    form,records,item_q=filtered(request)
    if not form.is_valid():return HttpResponse('Filtros inválidos. Corrija os campos na pesquisa antes de exportar.',status=400)
    items=FiscalSearchItem.objects.filter(item_q,record__in=records)
    if records.count()>50000 or items.count()>150000:
        return HttpResponse('O relatório excede 50 mil documentos ou 150 mil itens. Reduza o período ou selecione uma empresa.',status=413)
    from .services.xlsx_export import fiscal_workbook
    payload=fiscal_workbook(records,items,request.GET)
    response=HttpResponse(payload,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition']='attachment; filename="vindex-documentos-filtrados.xlsx"'
    response['X-Content-Type-Options']='nosniff'
    return response
