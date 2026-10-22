from collections import defaultdict
from datetime import date,timedelta
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import BadRequest
from django.http import Http404
from django.db.models import Case,When,Value,BooleanField
from django.shortcuts import render,get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from .models import Invoice,FiscalDocument,FiscalDelivery,SefazDocument,Company
from .views import workspace_for
from .services.fiscal_transport import xml_read
from .services.sefaz import SefazError
from .services.operational import operational_companies

NFE='http://www.portalfiscal.inf.br/nfe'
NAMES={'nfe':'NF-e de produtos','nfse':'NFS-e de serviços','cte':'CT-e de transporte'}


@login_required
@never_cache
def indicators(request):
    workspace=workspace_for(request);today=timezone.localdate()
    try:
        start=date.fromisoformat(request.GET.get('from') or (today-timedelta(days=365)).isoformat())
        end=date.fromisoformat(request.GET.get('to') or today.isoformat())
    except ValueError:raise BadRequest('Informe datas válidas para os indicadores.') from None
    if start>end or (end-start).days>3660:raise BadRequest('Selecione um período válido de até dez anos por consulta.')
    kind=request.GET.get('type','all');environment=request.GET.get('environment','1')
    if kind not in {'all','nfe','nfse','cte'} or environment not in {'1','2','all'}:raise Http404
    companies=operational_companies(workspace)
    if request.GET.get('company'):
        if not request.GET['company'].isdecimal():raise Http404
        selected=get_object_or_404(Company,workspace=workspace,pk=request.GET['company']);companies=companies.filter(pk=selected.pk)
    groups={};unknown_environment=0
    def add(service,env,key,issued,total,partial,cancelled,substituted,roles,captured,pdf):
        nonlocal unknown_environment
        if environment!='all' and env!=environment:
            if env=='?':unknown_environment+=1
            return
        token=(service,env,key)
        if token in groups:
            old=groups[token];old['roles']|=roles;old['partial']|=partial or old['total']!=total
            old['cancelled']|=cancelled;old['substituted']|=substituted;old['pdf']|=pdf
            return
        groups[token]=dict(service=service,environment=env,issued=issued,total=total,partial=partial,cancelled=cancelled,substituted=substituted,roles=roles,captured=captured,pdf=pdf)
    if kind in {'all','nfe'}:
        notes=Invoice.objects.filter(company__in=companies,is_demo=False,issued_on__range=(start,end))
        keys=list(notes.values_list('access_key',flat=True));cancelled=set()
        # Eventos só alteram o indicador se há retorno aceito correspondente.
        events=SefazDocument.objects.filter(state__company__in=companies,kind='event',event_type='110111',access_key__in=keys)
        for event in events.only('access_key','xml_content').iterator(chunk_size=50):
            try:
                root=xml_read(event.xml_content.encode());ret=root.find('.//{'+NFE+'}retEvento/{'+NFE+'}infEvento')
                if ret is not None and ret.findtext('{'+NFE+'}cStat') in {'135','136'} and ret.findtext('{'+NFE+'}chNFe')==event.access_key:cancelled.add(event.access_key)
            except SefazError:pass
        for note in notes.values('access_key','issued_on','total','source','xml_content').iterator(chunk_size=25):
            try:env=xml_read(note['xml_content'].encode()).findtext('.//{'+NFE+'}ide/{'+NFE+'}tpAmb') or '?'
            except SefazError:env='?'
            add('nfe',env,note['access_key'],note['issued_on'],note['total'],False,note['access_key'] in cancelled,False,{'received'},note['source']=='sefaz',False)
    if kind!='nfe':
        docs=FiscalDocument.objects.filter(company__in=companies,issued_at__date__range=(start,end))
        if kind!='all':docs=docs.filter(service=kind)
        docs=docs.annotate(pdf_present=Case(When(official_pdf__isnull=False,then=Value(True)),default=Value(False),output_field=BooleanField()))
        for doc in docs.values('service','environment','access_key','issued_at','total','validation_status','cancellation_reported','substitution_reported','role','official_pdf_source','pdf_present').iterator():
            roles=set()
            if doc['service']=='nfse':
                if 'emitente' in doc['role']:roles.add('issued')
                if 'tomador' in doc['role']:roles.add('received')
            add(doc['service'],doc['environment'],doc['access_key'],timezone.localtime(doc['issued_at']).date(),doc['total'],doc['validation_status']=='partial',doc['cancellation_reported'],doc['substitution_reported'],roles,True,bool(doc['official_pdf_source']) and doc['pdf_present'])
    months=[];cursor=start.replace(day=1)
    while cursor<=end:
        months.append(cursor.strftime('%Y-%m'));cursor=date(cursor.year+int(cursor.month==12),cursor.month%12+1,1)
    panels=[]
    for service,env in sorted({(g['service'],g['environment']) for g in groups.values()}):
        records=[g for g in groups.values() if g['service']==service and g['environment']==env]
        monthly={m:{'month':m,'count':0,'eligible':0,'value':Decimal(0)} for m in months}
        for g in records:
            row=monthly[g['issued'].strftime('%Y-%m')];row['count']+=1
            if not g['partial'] and not g['cancelled'] and not g['substituted']:row['value']+=g['total'];row['eligible']+=1
        rows=list(monthly.values());maxcount=max([r['count'] for r in rows]+[1]);maxvalue=max([r['value'] for r in rows]+[Decimal(1)])
        for i,row in enumerate(rows):
            row['height']=max(1,int(100*row['count']/maxcount))
            row['x']=str(round(Decimal(20)+Decimal(560)*i/max(1,len(rows)-1),2));row['y']=str(round(Decimal(140)-Decimal(120)*row['value']/maxvalue,2))
        panels.append({'name':NAMES[service],'environment':'Produção' if env=='1' else 'Homologação' if env=='2' else 'Não identificado','rows':rows,
            'count':len(records),'partial':sum(g['partial'] for g in records),'cancelled':sum(g['cancelled'] for g in records),'substituted':sum(g['substituted'] for g in records),
            'issued':sum('issued' in g['roles'] for g in records),'received':sum('received' in g['roles'] for g in records),
            'value':sum((r['value'] for r in rows),Decimal(0)),'points':' '.join(r['x']+','+r['y'] for r in rows),
            'share':int(100*len(records)/max(1,len(groups)))})
    deliveries=FiscalDelivery.objects.filter(connector__company__in=companies,envelope__received_at__date__range=(start,end))
    if kind!='all':deliveries=deliveries.filter(connector__service=kind)
    if environment!='all':deliveries=deliveries.filter(connector__environment=environment)
    return render(request,'portal/indicators.html',{'panels':panels,'companies':operational_companies(workspace),'from_date':start.isoformat(),'to_date':end.isoformat(),
        'record_count':len(groups),'captured_count':sum(g['captured'] for g in groups.values()),'partial_count':sum(g['partial'] for g in groups.values()),
        'pending_count':deliveries.exclude(error='').count(),'official_pdf_count':sum(g['pdf'] for g in groups.values()),'unknown_environment':unknown_environment})
