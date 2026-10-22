"""Dados fictícios, sem valor fiscal. Nenhum certificado ou cliente real é incluído."""
from datetime import timedelta
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring
from django.utils import timezone
from django.db import transaction
from portal.models import Company
from .invoices import import_invoice

DEMO_COMPANIES=[('Aurora Commerce','Aurora Commerce Demonstracao Ltda','00000001000136'),('Nova Alvo','Nova Alvo Demonstracao Ltda','00000002000180')]
ISSUER='00000003000125'

def sample_xml(owner,number='1001',total='1200.00',due_dates=None,purpose='1',issuer_name='Fornecedor de Exemplo Ltda'):
    today=timezone.localdate()
    due_dates=due_dates if due_dates is not None else [today+timedelta(days=15),today+timedelta(days=45)]
    prefix='35'+today.strftime('%y%m')+ISSUER+'55'+'001'+str(number).zfill(9)+'1'+'12345678'
    weights=[]
    for index in range(len(prefix)): weights.append(2+(index%8))
    remainder=sum(int(c)*weight for c,weight in zip(reversed(prefix),weights))%11
    key=prefix+str(0 if remainder in (0,1) else 11-remainder)
    root=Element('nfeProc',{'xmlns':'http://www.portalfiscal.inf.br/nfe','versao':'4.00'})
    nfe=SubElement(root,'NFe'); info=SubElement(nfe,'infNFe',{'Id':'NFe'+key,'versao':'4.00'})
    def put(parent,name,value): SubElement(parent,name).text=str(value)
    ide=SubElement(info,'ide')
    for k,v in [('mod','55'),('serie','1'),('nNF',number),('dhEmi',f'{today}T10:00:00-03:00'),('finNFe',purpose)]: put(ide,k,v)
    emit=SubElement(info,'emit'); put(emit,'CNPJ',ISSUER); put(emit,'xNome',issuer_name)
    dest=SubElement(info,'dest'); put(dest,'CNPJ',owner); put(dest,'xNome','Empresa de demonstracao')
    tot=SubElement(SubElement(info,'total'),'ICMSTot'); put(tot,'vNF',total)
    if due_dates:
        cobr=SubElement(info,'cobr'); amount=(Decimal(total)/len(due_dates)).quantize(Decimal('.01'))
        for index,due in enumerate(due_dates,1):
            dup=SubElement(cobr,'dup'); put(dup,'nDup',str(index).zfill(3))
            if due: put(dup,'dVenc',due)
            put(dup,'vDup',amount if index<len(due_dates) else Decimal(total)-amount*(len(due_dates)-1))
    pag=SubElement(SubElement(info,'pag'),'detPag'); put(pag,'tPag','15'); put(pag,'vPag',total)
    prot=SubElement(SubElement(root,'protNFe'),'infProt'); put(prot,'chNFe',key); put(prot,'cStat','100')
    return tostring(root,encoding='utf-8',xml_declaration=True)

@transaction.atomic
def load_demo(workspace):
    for short,legal,cnpj in DEMO_COMPANIES:
        Company.objects.get_or_create(workspace=workspace,cnpj=cnpj,defaults={'legal_name':legal,'trade_name':short})
    today=timezone.localdate()
    examples=[(DEMO_COMPANIES[0][2],'1001','4850.00',[today+timedelta(days=5),today+timedelta(days=35)],'Distribuidora Horizonte · Exemplo'),(DEMO_COMPANIES[0][2],'1002','1390.00',[today-timedelta(days=3)],'Embalagens Origem · Exemplo'),(DEMO_COMPANIES[1][2],'2001','7200.00',[today+timedelta(days=10),today+timedelta(days=40),today+timedelta(days=70)],'Industria Azul · Exemplo'),(DEMO_COMPANIES[1][2],'2002','890.00',[],'Suprimentos Central · Exemplo')]
    created=0
    for cnpj,number,total,dates,issuer in examples:
        _,new=import_invoice(workspace,sample_xml(cnpj,number,total,dates,issuer_name=issuer),is_demo=True)
        created+=int(new)
    return created
