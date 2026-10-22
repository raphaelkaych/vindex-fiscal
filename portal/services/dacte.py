"""Representação auxiliar de CT-e 57; sem consulta fiscal ou confirmação bancária."""
from decimal import Decimal
from io import BytesIO
import warnings
from .cte_presentation import read_cte,qr_url
from .fiscal_transport import CTE
from .sefaz import SefazError


def generate_dacte(document):
    if document.service!='cte':raise SefazError('DACTE atende somente CT-e modelo 57.')
    if getattr(document,'validation_status','schema')!='schema':raise SefazError('CT-e parcial não permite gerar DACTE. Baixe o XML original para revisão.')
    root,info=read_cte(document,validate=True)
    ns={'n':CTE}
    consultation_url=qr_url(root,document.access_key,document.environment)
    if not consultation_url:
        raise SefazError('O XML recebido não contém o QR Code de consulta do CT-e. O original está disponível; DACTE não gerado para evitar um QR vazio.')
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
        from brazilfiscalreport.generate_qrcode import make_qr_code_image
        from PIL import Image
        qr_image=make_qr_code_image(consultation_url,box_size=6,border=4)

        class PrivateDacte(Dacte):
            """Protege o QR das marcas d'água, sem alterar a biblioteca instalada."""
            def _draw_header(self):
                self._header_active=True
                try:super()._draw_header()
                finally:self._header_active=False

            def image(self,name,*args,**kwargs):
                if getattr(self,'_header_active',False) and isinstance(name,Image.Image):
                    # Somente o QR do cabeçalho é PIL; código de barras é SVG.
                    # Mantém o centro da área original e reserva margem branca.
                    kwargs=dict(kwargs)
                    kwargs['x']+= (kwargs['w']-30)/2
                    kwargs['y']+= (kwargs['h']-30)/2
                    kwargs.update(w=30,h=30,link=consultation_url)
                    if not hasattr(self,'_qr_boxes'):self._qr_boxes={}
                    self._qr_boxes[self.page_no()]=(kwargs['x'],kwargs['y'])
                    name=qr_image
                return super().image(name,*args,**kwargs)

            def _draw_void_watermark(self):
                super()._draw_void_watermark()
                if not hasattr(self,'_marked_pages'):self._marked_pages=set()
                self._marked_pages.add(self.page_no())
                box=getattr(self,'_qr_boxes',{}).get(self.page_no())
                if box:
                    x,y=box
                    with self.local_context(fill_color=(255,255,255)):
                        self.rect(x-1,y-1,32,32,style='F')
                    # O fundo branco impede que o aviso de homologação ou
                    # cancelamento atravesse os módulos ou a margem do QR.
                    super().image(qr_image,x=x,y=y,w=30,h=30,link=consultation_url)

            def complete_status_marks(self):
                original_page=self.page
                if document.environment=='2' or document.cancellation_reported:
                    for number in range(1,len(self.pages)+1):
                        if number not in getattr(self,'_marked_pages',set()):
                            self.page=number;self._draw_void_watermark()
                self.page=original_page

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            pdf=PrivateDacte(xml=document.xml_content,config=DacteConfig(decimal_config=DecimalConfig(price_precision=2,quantity_precision=precision),watermark_cancelled=document.cancellation_reported,display_ibs_cbs=True))
            pdf.complete_status_marks()
            pdf.set_creator('Vindex Fiscal');pdf.set_subject('DACTE gerado do XML recebido. Situacao fiscal atual e pagamento nao consultados.')
            result=bytes(pdf.output())
        if not result.startswith(b'%PDF-') or len(result)>20*1024*1024:raise ValueError
        return result
    except Exception:raise SefazError('Não foi possível gerar o DACTE deste CT-e. O XML original está preservado e disponível.') from None
