"""Conferência de impressão: XML inteiramente fictício, sem banco ou rede.

Amostra mínima do renderizador; não é fixture de homologação do schema fiscal.
"""
from pathlib import Path
from brazilfiscalreport.dacte import Dacte,DacteConfig

KEY='35'+'0'*42
PARTY='<CNPJ>00000001000136</CNPJ><xNome>EMPRESA FICTICIA SEM VALOR FISCAL</xNome><IE>ISENTO</IE>'
ADDR='<xLgr>RUA FICTICIA</xLgr><nro>123</nro><xBairro>TESTE</xBairro><xMun>SAO PAULO</xMun><UF>SP</UF><CEP>01001000</CEP>'


def synthetic_cte_xml(orientation='1',environment='2',references=0):
    parties=''.join(f'<{tag}>{PARTY}<ender{suffix}>{ADDR}</ender{suffix}></{tag}>' for tag,suffix in [('emit','Emit'),('rem','Reme'),('dest','Dest'),('exped','Exped'),('receb','Receb')])
    payload=f'''<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00"><CTe><infCte Id="CTe{KEY}" versao="4.00"><ide><cUF>35</cUF><cCT>00000000</cCT><CFOP>5353</CFOP><natOp>PRESTACAO FICTICIA PARA TESTE</natOp><mod>57</mod><serie>1</serie><nCT>1</nCT><dhEmi>2026-10-21T10:00:00-03:00</dhEmi><tpImp>1</tpImp><tpEmis>1</tpEmis><tpAmb>2</tpAmb><tpCTe>0</tpCTe><modal>01</modal><tpServ>0</tpServ><xMunIni>SAO PAULO</xMunIni><UFIni>SP</UFIni><xMunFim>SAO PAULO</xMunFim><UFFim>SP</UFFim><toma3><toma>3</toma></toma3></ide>{parties}<vPrest><vTPrest>123.45</vTPrest><vRec>123.45</vRec><Comp><xNome>FRETE FICTICIO</xNome><vComp>123.45</vComp></Comp></vPrest><imp><ICMS><ICMS00><CST>00</CST><vBC>123.45</vBC><pICMS>0.00</pICMS><vICMS>0.00</vICMS></ICMS00></ICMS></imp><infCTeNorm><infCarga><vCarga>1000.00</vCarga><proPred>CARGA FICTICIA</proPred><infQ><cUnid>01</cUnid><tpMed>PESO</tpMed><qCarga>10.0000</qCarga></infQ></infCarga><infDoc/><infModal versaoModal="4.00"><rodo><RNTRC>00000000</RNTRC></rodo></infModal></infCTeNorm><compl><xObs>DOCUMENTO INTEIRAMENTE FICTICIO. SEM VALOR FISCAL.</xObs></compl></infCte></CTe><protCTe><infProt><chCTe>{KEY}</chCTe><cStat>100</cStat><nProt>135260000000001</nProt><dhRecbto>2026-10-21T10:00:00-03:00</dhRecbto></infProt></protCTe></cteProc>'''
    from xml.etree import ElementTree as ET
    namespace='http://www.portalfiscal.inf.br/cte'
    ns={'n':namespace}
    root=ET.fromstring(payload)
    root.find('n:CTe/n:infCte/n:ide/n:tpImp',ns).text=orientation
    root.find('n:CTe/n:infCte/n:ide/n:tpAmb',ns).text=environment
    supplemental=ET.SubElement(root.find('n:CTe',ns),'{'+namespace+'}infCTeSupl')
    ET.SubElement(supplemental,'{'+namespace+'}qrCodCTe').text='https://dfe-portal.svrs.rs.gov.br/cte/qrCode?chCTe='+KEY+'&tpAmb='+environment
    origin=root.find('n:CTe/n:infCte/n:infCTeNorm/n:infDoc',ns)
    for index in range(references):
        note=ET.SubElement(origin,'{'+namespace+'}infNFe')
        ET.SubElement(note,'{'+namespace+'}chave').text='35'+f'{index:042d}'
    return ET.tostring(root,encoding='unicode')


def main():
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from django.conf import settings
    if not settings.configured:
        settings.configure(SECRET_KEY='synthetic-pdf-preview-only',INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes','portal'],DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}})
        import django
        django.setup()
    import pypdfium2 as pdfium
    from types import SimpleNamespace
    from unittest.mock import patch
    from portal.services.dacte import generate_dacte
    document=SimpleNamespace(service='cte',environment='2',validation_status='schema',access_key=KEY,cancellation_reported=False,xml_content=synthetic_cte_xml(references=3))
    output=Path(__file__).resolve().parents[1]/'tmp'/'pdfs';output.mkdir(parents=True,exist_ok=True)
    # Fixture de renderização, não de homologação fiscal/XSD.
    with patch('portal.services.cte_presentation.validate_xml'):
        data=generate_dacte(document)
    (output/'dacte-ficticio.pdf').write_bytes(data)
    pdf=pdfium.PdfDocument(data)
    for index in range(len(pdf)):
        page=pdf[index];bitmap=page.render(scale=2);bitmap.to_pil().save(output/f'dacte-ficticio-{index+1:02}.png');bitmap.close();page.close()
    print(f'DACTE fictício: {len(pdf)} página(s) renderizada(s) para conferência.')
    pdf.close()


if __name__=='__main__':main()
