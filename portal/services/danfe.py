"""DANFE privado, produzido em memória a partir do XML original da NF-e.

Não consulta a SEFAZ, não emite eventos e não confirma situação fiscal atual.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
import warnings
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from django.views.decorators.debug import sensitive_variables

NS = {'n': 'http://www.portalfiscal.inf.br/nfe'}
MAX_XML_BYTES = 2 * 1024 * 1024


def _precision(root):
    def places(names):
        return max((len((node.text or '').partition('.')[2].rstrip('0'))
                    for node in root.iter() if node.tag.rsplit('}',1)[-1] in names), default=0)
    return max(2,places({'vUnCom','vUnTrib'})), max(0,places({'qCom','qTrib'}))


def _validate_numbers(root):
    price, quantity = _precision(root)
    if price > 10 or quantity > 4:
        raise DanfeError('A precisão dos itens não é compatível com este DANFE. Baixe o XML original, sem arredondamentos adicionais.')
    money = {'vNF','vProd','vBC','vICMS','vBCST','vST','vFrete','vSeg','vDesc','vIPI','vII','vPIS','vCOFINS','vOutro'}
    for node in root.iter():
        name = node.tag.rsplit('}',1)[-1]
        if name not in money | {'vUnCom','vUnTrib','qCom','qTrib'}:
            continue
        value = (node.text or '').strip()
        if not re.fullmatch(r'[0-9]{1,16}(?:\.[0-9]{1,10})?',value):
            raise DanfeError('O XML contém valores numéricos inválidos para gerar um DANFE fiel.')
        precision = price if name in {'vUnCom','vUnTrib'} else quantity if name in {'qCom','qTrib'} else 2
        try:
            if Decimal(format(float(value), f'.{precision}f')) != Decimal(value):
                raise DanfeError('A precisão de um valor não pode ser preservada neste DANFE. O XML original continua disponível.')
        except (InvalidOperation, ValueError, OverflowError):
            raise DanfeError('A precisão dos valores impede a geração deste DANFE. Baixe o XML original.') from None


class DanfeError(ValueError):
    pass


@dataclass(frozen=True)
class DanfeAvailability:
    available: bool
    reason: str = ''


def _read(invoice):
    payload = invoice.xml_content.encode('utf-8')
    if len(payload) > MAX_XML_BYTES:
        raise DanfeError('O XML excede o limite de geração do DANFE. O arquivo original continua disponível.')
    try:
        root = ElementTree.fromstring(payload, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ElementTree.ParseError, DefusedXmlException, ValueError):
        raise DanfeError('O XML não pôde ser lido com segurança para gerar o DANFE.') from None
    info = root.find('n:NFe/n:infNFe', NS)
    if root.tag != '{' + NS['n'] + '}nfeProc' or info is None:
        raise DanfeError('DANFE indisponível: é necessário o XML completo processado da NF-e, com protocolo.')
    value = lambda path: info.findtext(path, '', NS).strip()
    if value('n:ide/n:mod') != '55':
        raise DanfeError('A geração de DANFE atende NF-e modelo 55.')
    if info.get('Id', '') != 'NFe' + invoice.access_key or value('n:dest/n:CNPJ') != invoice.company.cnpj:
        raise DanfeError('O XML não corresponde à chave e ao CNPJ destinatário desta nota.')
    protocol = root.find('n:protNFe/n:infProt', NS)
    if protocol is None or protocol.findtext('n:chNFe', '', NS) != invoice.access_key:
        raise DanfeError('DANFE indisponível: o XML não contém o protocolo correspondente à nota.')
    if protocol.findtext('n:cStat', '', NS) not in {'100', '150'}:
        raise DanfeError('O protocolo do XML não indica autorização de uso para gerar o DANFE.')
    if not protocol.findtext('n:nProt', '', NS) or not protocol.findtext('n:dhRecbto', '', NS):
        raise DanfeError('DANFE indisponível: o protocolo do XML está incompleto. Baixe o XML original.')
    if not re.fullmatch(r'[0-9]{15}(?:[0-9]{2})?',protocol.findtext('n:nProt','',NS)):
        raise DanfeError('DANFE indisponível: o número do protocolo do XML está inválido.')
    if value('n:ide/n:tpAmb') not in {'1', '2'} or value('n:ide/n:tpImp') not in {'1', '2'}:
        raise DanfeError('O XML não informa ambiente e impressão A4 compatíveis com o DANFE disponível.')
    required = ['n:ide/n:nNF', 'n:ide/n:serie', 'n:ide/n:dhEmi', 'n:ide/n:natOp',
                'n:emit/n:xNome', 'n:emit/n:enderEmit/n:xLgr', 'n:emit/n:enderEmit/n:xMun',
                'n:emit/n:enderEmit/n:UF', 'n:dest/n:xNome', 'n:dest/n:enderDest/n:xLgr',
                'n:dest/n:enderDest/n:xMun', 'n:dest/n:enderDest/n:UF', 'n:total/n:ICMSTot/n:vNF']
    if any(not value(path) for path in required):
        raise DanfeError('O XML tem dados incompletos para um DANFE fiel. O XML original continua disponível.')
    _validate_numbers(info)
    items = info.findall('n:det', NS)
    if not 1 <= len(items) <= 990:
        raise DanfeError('DANFE indisponível: o XML deve conter de 1 a 990 itens da NF-e.')
    for item in items:
        for name in ('cProd', 'xProd', 'NCM', 'CFOP', 'uCom', 'qCom', 'vUnCom', 'vProd'):
            if not item.findtext('n:prod/n:' + name, '', NS).strip():
                raise DanfeError('O XML contém itens incompletos para gerar o DANFE sem inventar dados.')
    return payload


def availability(invoice):
    try:
        _read(invoice)
    except DanfeError as error:
        return DanfeAvailability(False, str(error))
    return DanfeAvailability(True)


@sensitive_variables()
def generate_danfe(invoice):
    payload = _read(invoice)
    try:
        from brazilfiscalreport.danfe import Danfe, DanfeConfig, DecimalConfig, InvoiceDisplay, Margins
        root = ElementTree.fromstring(payload,forbid_dtd=True,forbid_entities=True,forbid_external=True)
        price,quantity = _precision(root)
        billing = root.find('n:NFe/n:infNFe/n:cobr/n:fat', NS)
        full_billing = billing is not None and all(billing.findtext('n:'+name,'',NS).strip()
            for name in ('nFat','vOrig','vDesc','vLiq'))
        config = DanfeConfig(invoice_display=InvoiceDisplay.FULL_DETAILS if full_billing else InvoiceDisplay.DUPLICATES_ONLY,
            decimal_config=DecimalConfig(price_precision=price,quantity_precision=quantity),margins=Margins(bottom=10))
        # Bibliotecas podem emitir warnings com campos do XML: não expor em logs.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            document = Danfe(xml=payload.decode('utf-8'), config=config)
            document.set_creator('Vindex Fiscal')
            document.set_title(f'DANFE NF-e {invoice.number}')
            document.set_subject('Representacao auxiliar gerada do XML original. Nao confirma pagamento ou situacao fiscal atual.')
            from fpdf import FPDF
            from pypdf import PdfReader, PdfWriter
            base = PdfReader(BytesIO(bytes(document.output())))
            writer = PdfWriter()
            for page in base.pages:
                width,height = float(page.mediabox.width)*25.4/72,float(page.mediabox.height)*25.4/72
                stamp = FPDF(orientation='L' if width > height else 'P',unit='mm',
                             format=(min(width,height),max(width,height)))
                stamp.add_page()
                stamp.set_auto_page_break(False)
                stamp.set_font('Times','B',7)
                stamp.set_text_color(20,33,61)
                stamp.set_xy(5,height-8)
                stamp.cell(width-10,4,'Vindex Fiscal - DANFE gerado do XML - Situacao fiscal atual nao consultada',align='R')
                if invoice.is_demo:
                    with stamp.local_context(fill_opacity=0.22):
                        stamp.set_font('Times', 'B', 28)
                        stamp.set_text_color(190, 55, 55)
                        with stamp.rotation(45, width/2,height/2):
                            stamp.set_xy(10,height/2)
                            stamp.cell(width-20,12,'FICTICIO - SEM VALOR FISCAL',align='C')
                overlay = PdfReader(BytesIO(bytes(stamp.output())))
                page.merge_page(overlay.pages[0])
                writer.add_page(page)
            writer.add_metadata({'/Creator':'Vindex Fiscal','/Title':f'DANFE NF-e {invoice.number}',
                '/Subject':'DANFE gerado localmente do XML. Situacao fiscal atual nao consultada.'})
            output = BytesIO()
            writer.write(output)
            result = output.getvalue()
        if not result.startswith(b'%PDF-') or len(result) > 20 * 1024 * 1024:
            raise DanfeError('O DANFE gerado excede o limite local ou está inválido. Baixe o XML original.')
        return result
    except DanfeError:
        raise
    except Exception:
        # Não registrar exceção da biblioteca: pode incluir conteúdo fiscal.
        raise DanfeError('Não foi possível gerar o DANFE deste XML. O XML original está preservado e pode ser baixado.') from None
