"""Representação auxiliar de CT-e 57; sem consulta fiscal ou confirmação bancária."""
from decimal import Decimal
from io import BytesIO
import warnings
from .fiscal_transport import xml_read,validate_xml,CTE
from .sefaz import SefazError


def generate_dacte(document):
    if document.service!='cte':raise SefazError('DACTE atende somente CT-e modelo 57.')
    root=xml_read(document.xml_content.encode());validate_xml('cte','procCTe_v4.00.xsd',root)
    ns={'n':CTE};info=root.find('n:CTe/n:infCte',ns)
    if info is None or info.get('Id')!='CTe'+document.access_key:raise SefazError('XML não corresponde a este CT-e.')
    quantities=root.findall('.//n:qCarga',ns)
    precision=max((len((x.text or '').partition('.')[2].rstrip('0')) for x in quantities),default=3)
    if precision>4:raise SefazError('Precisão de carga não suportada no DACTE. Baixe o XML original.')
    for item in root.iter():
        name=item.tag.rsplit('}',1)[-1] if isinstance(item.tag,str) else ''
        if name in {'vTPrest','vRec','vCarga','vComp','vBC','vICMS','vICMSST','qCarga'} and item.text:
            places=precision if name=='qCarga' else 2
            if Decimal(format(float(item.text),f'.{places}f'))!=Decimal(item.text):raise SefazError('Um valor perderia precisão neste DACTE. Baixe o XML original.')
    try:
        from brazilfiscalreport.dacte import Dacte,DacteConfig,DecimalConfig
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            pdf=Dacte(xml=document.xml_content,config=DacteConfig(decimal_config=DecimalConfig(price_precision=2,quantity_precision=precision),watermark_cancelled=document.cancellation_reported,display_ibs_cbs=True))
            pdf.set_creator('Vindex Fiscal');pdf.set_subject('DACTE gerado do XML recebido. Situacao fiscal atual e pagamento nao consultados.')
            result=bytes(pdf.output())
        if not result.startswith(b'%PDF-') or len(result)>20*1024*1024:raise ValueError
        return result
    except Exception:raise SefazError('Não foi possível gerar o DACTE deste CT-e. O XML original está preservado e disponível.') from None
