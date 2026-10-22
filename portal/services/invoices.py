"""Importação de dados de XML. Não valida assinatura, autenticidade fiscal ou pagamento."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from django.core.exceptions import ValidationError
from django.db import transaction
from portal.models import Company,Invoice,Installment,AuditEntry
from portal.validators import validate_cnpj
NS={'n':'http://www.portalfiscal.inf.br/nfe'}
class InvoiceImportError(ValueError): pass

def parse_nfe(payload):
    if len(payload)>2*1024*1024: raise InvoiceImportError('XML acima do limite de 2 MB.')
    try:
        root=ElementTree.fromstring(payload,forbid_dtd=True,forbid_entities=True,forbid_external=True)
        text_xml=payload.decode('utf-8-sig')
    except (ElementTree.ParseError,DefusedXmlException,UnicodeDecodeError,ValueError):
        raise InvoiceImportError('O arquivo não é um XML de NF-e válido e seguro.') from None
    nfe=root if root.tag=='{%s}NFe'%NS['n'] else root.find('n:NFe',NS)
    if nfe is None or root.tag not in ['{%s}NFe'%NS['n'],'{%s}nfeProc'%NS['n']]:
        raise InvoiceImportError('Envie um XML de NF-e. PDF, NFS-e, resumos e eventos não são aceitos nesta versão.')
    info=nfe.find('n:infNFe',NS)
    if info is None: raise InvoiceImportError('O XML não contém os dados da NF-e.')
    def get(path,default=''): return info.findtext(path,default=default,namespaces=NS).strip()
    if get('n:ide/n:mod')!='55': raise InvoiceImportError('Nesta versão, importe notas de produto do modelo 55 (NF-e).')
    key=info.attrib.get('Id','').removeprefix('NFe')
    if not re.fullmatch('[A-Z0-9]{44}',key): raise InvoiceImportError('A chave de acesso está ausente ou inválida.')
    protocol=root.find('n:protNFe/n:infProt',NS)
    if protocol is not None:
        if protocol.findtext('n:cStat','',NS) not in ('100','150'): raise InvoiceImportError('O protocolo informado não indica uma autorização de uso.')
        if protocol.findtext('n:chNFe','',NS)!=key: raise InvoiceImportError('A chave do protocolo não corresponde à nota.')
    try:
        owner=validate_cnpj(get('n:dest/n:CNPJ'))
        issuer=validate_cnpj(get('n:emit/n:CNPJ'))
        issued_on=date.fromisoformat((get('n:ide/n:dhEmi') or get('n:ide/n:dEmi'))[:10])
    except (ValidationError,ValueError):
        raise InvoiceImportError('Confira os CNPJs do destinatário e do emitente e a data de emissão.') from None
    def money(value):
        try:
            result=Decimal(value)
            if not result.is_finite() or result<=0 or result>=Decimal('10000000000000000') or result!=result.quantize(Decimal('.01')): raise ValueError
            return result
        except (InvalidOperation,ValueError): raise InvoiceImportError('A nota contém um valor ausente, inválido ou fora do limite.') from None
    total=money(get('n:total/n:ICMSTot/n:vNF'))
    if not get('n:emit/n:xNome') or not re.fullmatch(r'\d{1,9}',get('n:ide/n:nNF')):
        raise InvoiceImportError('O fornecedor e o número da nota são obrigatórios.')
    warnings,installments=[],[]
    purpose=get('n:ide/n:finNFe','1')
    if purpose!='1': warnings.append('Nota de finalidade especial: nenhuma previsão financeira foi criada automaticamente.')
    else:
        duplicates=info.findall('n:cobr/n:dup',NS)
        seen=set()
        for index,dup in enumerate(duplicates,1):
            declared_number=dup.findtext('n:nDup','',NS).strip()
            number=declared_number or f'Sem número (XML {index})'
            if len(number)>60: raise InvoiceImportError('O identificador de uma duplicata excede 60 caracteres.')
            if not declared_number: warnings.append(f'Duplicata na posição {index} sem número declarado: identificador técnico exibido para revisão.')
            if number in seen: raise InvoiceImportError('A nota repete o número de uma duplicata.')
            seen.add(number)
            amount=dup.findtext('n:vDup','',NS).strip()
            if not amount:
                warnings.append(f'Parcela {number} sem valor: previsão não criada.')
                continue
            amount=money(amount)
            due=dup.findtext('n:dVenc','',NS).strip()
            try: due=date.fromisoformat(due) if due else None
            except ValueError: raise InvoiceImportError('Existe uma duplicata com vencimento inválido.') from None
            if not due: warnings.append(f'Parcela {number} sem vencimento: confira as condições de pagamento.')
            installments.append({'number':number[:60],'amount':amount,'due_on':due,'original_data':{'declared_number':declared_number,'xml_position':index,'amount':str(amount),'due_on':due.isoformat() if due else None}})
        if not duplicates: warnings.append('A nota não informa duplicatas estruturadas. Confira as condições de pagamento antes de criar uma previsão.')
        if installments and sum(i['amount'] for i in installments)!=total:
            warnings.append('A soma das duplicatas difere do total da nota. Confira descontos, pagamentos parciais e condições comerciais.')
    methods={'01':'Dinheiro','03':'Cartão de crédito','04':'Cartão de débito','15':'Boleto','17':'Pix','90':'Sem pagamento','99':'Outros'}
    codes=[el.text for el in info.findall('n:pag/n:detPag/n:tPag',NS)]
    def declared_value(value,label):
        if not value: return None
        try:
            parsed=Decimal(value)
            if not parsed.is_finite() or parsed<0 or parsed>=Decimal('10000000000000000') or parsed!=parsed.quantize(Decimal('.01')): raise ValueError
            return format(parsed,'.2f')
        except (ValueError,InvalidOperation):
            warnings.append(f'{label} declarado com valor inválido: confira o XML.')
            return None
    payments=[]
    for payment in info.findall('n:pag/n:detPag',NS):
        def field(name): return payment.findtext('n:'+name,'',NS).strip()
        payments.append({'method_code':field('tPag')[:2],'description':field('xPag')[:100],
                         'timing_code':field('indPag')[:1],
                         'declared_amount':declared_value(field('vPag'),'Pagamento'),
                         'declared_date':field('dPag')[:10]})
    billing={}
    for name in ('nFat','vOrig','vDesc','vLiq'):
        value=get('n:cobr/n:fat/n:'+name)
        if value: billing[name]=value[:60] if name=='nFat' else declared_value(value,'Fatura')
    return {'owner':owner,'access_key':key,'number':get('n:ide/n:nNF'),'series':get('n:ide/n:serie')[:6],'issuer_name':get('n:emit/n:xNome')[:200],'issuer_cnpj':issuer,'issued_on':issued_on,'total':total,'purpose':purpose[:2],'payment_method':', '.join(dict.fromkeys(methods.get(v,'Não identificado') for v in codes)),'payment_details':payments,'billing_details':billing,'review_notes':'\n'.join(warnings),'xml_content':text_xml,'installments':installments}

@transaction.atomic
def import_invoice(workspace,payload,is_demo=False,allowed_companies=None,source='xml'):
    data=parse_nfe(payload)
    owner=data.pop('owner')
    companies=Company.objects.filter(workspace=workspace,cnpj=owner)
    if allowed_companies is not None: companies=companies.filter(pk__in=allowed_companies)
    company=companies.first()
    if company is None: raise InvoiceImportError('O CNPJ destinatário não está cadastrado entre as suas empresas. Cadastre a empresa correta antes de importar.')
    duplicates=data.pop('installments')
    if source not in {'xml','api_xml','sefaz','demo'}: raise InvoiceImportError('Origem de importação inválida.')
    invoice,created=Invoice.objects.get_or_create(company=company,access_key=data['access_key'],defaults={**data,'is_demo':is_demo,'source':'demo' if is_demo else source})
    if created:
        Installment.objects.bulk_create([Installment(invoice=invoice,**item) for item in duplicates])
        AuditEntry.objects.create(workspace=workspace,description=f'NF-e {invoice.number} importada para {company.display_name}'[:250])
    return invoice,created
