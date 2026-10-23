"""Projeção local dos XMLs. Nenhuma rede, manifestação ou alteração do original."""
import hashlib
import unicodedata
from decimal import Decimal,InvalidOperation
from django.db import transaction
from django.utils import timezone
from portal.models import FiscalSearchRecord,FiscalSearchItem,Invoice,FiscalDocument,SefazDocument
from .fiscal_transport import xml_read
from .sefaz import SefazError


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value.casefold()) if not unicodedata.combining(c))


def text(node,path):
    if node is None:return ''
    namespace=node.tag.split('}')[0]+'}' if '}' in node.tag else ''
    return (node.findtext('/'.join(namespace+x for x in path.split('/'))) or '').strip()


def node_at(node,path):
    namespace=node.tag.split('}')[0]+'}' if '}' in node.tag else ''
    return node.find('/'.join(namespace+x for x in path.split('/')))


def numeric(value,places=10):
    if not value:return None
    try:
        number=Decimal(value)
        if not number.is_finite() or abs(number)>=Decimal(10)**(30-places):return None
        return number.quantize(Decimal(10)**-places)
    except InvalidOperation:return None


def cancellation(xml,key):
    try:
        root=xml_read(xml.encode());ns={'n':'http://www.portalfiscal.inf.br/nfe'}
        ret=root.find('.//n:retEvento/n:infEvento',ns)
        return ret is not None and ret.findtext('n:cStat',namespaces=ns) in {'135','136'} and ret.findtext('n:chNFe',namespaces=ns)==key and ret.findtext('n:tpEvento',namespaces=ns)=='110111'
    except SefazError:return False


@transaction.atomic
def index_document(source):
    is_nfe=isinstance(source,Invoice)
    lookup={'invoice':source} if is_nfe else {'document':source}
    if is_nfe and source.is_demo:
        FiscalSearchRecord.objects.filter(**lookup).delete();return
    values=dict(company=source.company,kind='nfe' if is_nfe else source.service,
        environment='' if is_nfe else source.environment,access_key=source.access_key,number=source.number,series=source.series if is_nfe else '',
        issuer_name=source.issuer_name,issuer_search=normalize(source.issuer_name),issuer_cnpj=source.issuer_cnpj,recipient_cnpj='',
        issued_on=source.issued_on if is_nfe else timezone.localtime(source.issued_at).date(),
        imported_at=source.imported_at,total=source.total,status='stored',diagnostic='',
        xml_hash=hashlib.sha256(source.xml_content.encode()).hexdigest())
    items=[]
    if not is_nfe:values['status']='substituted' if source.substitution_reported else 'cancelled' if source.cancellation_reported else 'partial' if source.validation_status=='partial' else 'stored'
    elif any(cancellation(xml,source.access_key) for xml in SefazDocument.objects.filter(state__company=source.company,kind='event',event_type='110111',access_key=source.access_key).values_list('xml_content',flat=True)):
        values['status']='cancelled'
    try:
        root=xml_read(source.xml_content.encode())
        if is_nfe:
            info=node_at(root,'NFe/infNFe') if root.tag.endswith('nfeProc') else node_at(root,'infNFe')
            if info is None:raise SefazError('XML sem infNFe')
            if text(info,'ide/mod')!='55':raise SefazError('Modelo não suportado')
            values.update(environment=text(info,'ide/tpAmb'),series=text(info,'ide/serie'),recipient_cnpj=text(info,'dest/CNPJ'))
            namespace=info.tag.split('}')[0]+'}'
            for pos,det in enumerate(info.findall(namespace+'det'),1):
                prod=node_at(det,'prod')
                items.append(dict(position=pos,description=text(prod,'xProd'),code=text(prod,'cProd')[:100],ncm=text(prod,'NCM'),cfop=text(prod,'CFOP'),unit=text(prod,'uCom')[:20],quantity=numeric(text(prod,'qCom')),unit_price=numeric(text(prod,'vUnCom')),total=numeric(text(prod,'vProd'),2)))
        elif source.service=='nfse':
            info=node_at(root,'infNFSe')
            if info is None:raise SefazError('XML sem infNFSe')
            dps='DPS/infDPS/'
            values.update(environment=source.environment,series=text(info,dps+'serie'),recipient_cnpj=text(info,dps+'toma/CNPJ'))
            description=text(info,dps+'serv/cServ/xDescServ')
            if description:items.append(dict(position=1,description=description,code=text(info,dps+'serv/cServ/cTribNac'),total=numeric(text(info,dps+'valores/vServPrest/vServ'),2)))
        else:
            info=node_at(root,'CTe/infCte') if root.tag.endswith('cteProc') else node_at(root,'infCte')
            if info is None:raise SefazError('XML sem infCte')
            values.update(environment=source.environment,series=text(info,'ide/serie'),recipient_cnpj=text(info,'dest/CNPJ'))
            description=text(info,'infCTeNorm/infCarga/proPred')
            if description:items.append(dict(position=1,description=description))
        if not is_nfe:
            values['status']='substituted' if source.substitution_reported else 'cancelled' if source.cancellation_reported else 'partial' if source.validation_status=='partial' else 'stored'
    except (SefazError,ValueError,TypeError):
        values['diagnostic']='Não foi possível indexar os detalhes deste XML. Confira o documento original.'
    record,_=FiscalSearchRecord.objects.update_or_create(**lookup,defaults=values)
    record.items.all().delete()
    FiscalSearchItem.objects.bulk_create([FiscalSearchItem(record=record,search_text=normalize(item.get('description','')+'\n'+item.get('code','')),**item) for item in items],batch_size=100)
    return record


def register_signals():
    from django.db.models.signals import post_save
    def saved(sender,instance,raw=False,**kwargs):
        if not raw:index_document(instance)
    for model in (Invoice,FiscalDocument):
        post_save.connect(saved,sender=model,weak=False,dispatch_uid='fiscal_search_'+model.__name__)
    def event_saved(sender,instance,raw=False,**kwargs):
        if not raw and instance.kind=='event' and instance.event_type=='110111' and cancellation(instance.xml_content,instance.access_key):
            FiscalSearchRecord.objects.filter(invoice__company_id=instance.state.company_id,access_key=instance.access_key).update(status='cancelled')
    post_save.connect(event_saved,sender=SefazDocument,weak=False,dispatch_uid='fiscal_search_cancellation')
