"""PDFs e XMLs exclusivamente sintéticos, sem consulta fiscal ou dados reais."""
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as XML
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader
from portal.tests import create_account
from portal.services.demo import sample_xml
from portal.services.invoices import import_invoice
from portal.services.danfe import availability, generate_danfe, DanfeError

N = 'http://www.portalfiscal.inf.br/nfe'
NS = {'n': N}


def complete_synthetic_xml(cnpj, items=3, orientation='1', environment='1'):
    """Acrescenta dados declaradamente fictícios ao exemplo do projeto."""
    root=XML.fromstring(sample_xml(cnpj,total=f'{items*40}.00',issuer_name='FORNECEDOR FICTICIO SEM VALOR FISCAL'))
    info=root.find('n:NFe/n:infNFe',NS)
    def put(parent,name,value):
        node=parent.find('n:'+name,NS)
        if node is None: node=XML.SubElement(parent,f'{{{N}}}{name}')
        node.text=str(value);return node
    ide=info.find('n:ide',NS)
    for key,value in [('natOp','VENDA FICTICIA PARA TESTE'),('tpNF','1'),('tpAmb',environment),('tpImp',orientation),('tpEmis','1')]:put(ide,key,value)
    for tag,name in [('emit','enderEmit'),('dest','enderDest')]:
        person=info.find('n:'+tag,NS)
        address=XML.SubElement(person,f'{{{N}}}{name}')
        for key,value in [('xLgr','RUA FICTICIA'),('nro','123'),('xBairro','BAIRRO DE TESTE'),('cMun','3550308'),('xMun','SAO PAULO'),('UF','SP'),('CEP','01001000'),('cPais','1058'),('xPais','BRASIL')]:put(address,key,value)
        put(person,'IE','ISENTO')
    put(info.find('n:emit',NS),'CRT','3')
    totals=info.find('n:total/n:ICMSTot',NS)
    for name in ['vBC','vICMS','vICMSDeson','vFCP','vBCST','vST','vFCPST','vFCPSTRet','vFrete','vSeg','vDesc','vII','vIPI','vIPIDevol','vPIS','vCOFINS','vOutro']:
        put(totals,name,'0.00')
    put(totals,'vProd',f'{items*40}.00')
    transport=XML.SubElement(info,f'{{{N}}}transp');put(transport,'modFrete','9')
    for index in range(1,items+1):
        item=XML.SubElement(info,f'{{{N}}}det',nItem=str(index))
        product=XML.SubElement(item,f'{{{N}}}prod')
        for name,value in [('cProd',f'FICTICIO-{index:03}'),('cEAN','SEM GTIN'),('xProd',f'PRODUTO FICTICIO {index:03} - DESCRICAO PARA CONFERENCIA DO DANFE'),('NCM','49019900'),('CFOP','5102'),('uCom','UN'),('qCom','2.0000'),('vUnCom','20.0000000000'),('vProd','40.00'),('cEANTrib','SEM GTIN'),('uTrib','UN'),('qTrib','2.0000'),('vUnTrib','20.0000000000'),('indTot','1')]:put(product,name,value)
        tax=XML.SubElement(item,f'{{{N}}}imposto');icms=XML.SubElement(XML.SubElement(tax,f'{{{N}}}ICMS'),f'{{{N}}}ICMS00')
        for name,value in [('orig','0'),('CST','00'),('modBC','3'),('vBC','0.00'),('pICMS','0.00'),('vICMS','0.00')]:put(icms,name,value)
    additional=XML.SubElement(info,f'{{{N}}}infAdic');put(additional,'infCpl','DOCUMENTO INTEGRALMENTE FICTICIO PARA TESTE. SEM VALOR FISCAL.')
    protocol=root.find('n:protNFe/n:infProt',NS)
    for name,value in [('nProt','135260000000001'),('dhRecbto','2026-10-21T10:01:00-03:00'),('tpAmb',environment),('verAplic','TESTE')]:put(protocol,name,value)
    return XML.tostring(root,encoding='utf-8',xml_declaration=True)


class DanfeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.workspace,cls.company=create_account('danfe-test@example.test')
        cls.other,cls.foreign_workspace,cls.foreign_company=create_account('danfe-other@example.test')
        cls.note,_=import_invoice(cls.workspace,complete_synthetic_xml(cls.company.cnpj),is_demo=False)
        cls.foreign,_=import_invoice(cls.foreign_workspace,complete_synthetic_xml(cls.foreign_company.cnpj),is_demo=False)

    def setUp(self):self.client.force_login(self.user)

    def test_pdf_contains_original_key_totals_products_and_provenance(self):
        self.note.is_demo=True
        original=self.note.xml_content
        self.assertTrue(availability(self.note).available)
        data=generate_danfe(self.note)
        self.assertTrue(data.startswith(b'%PDF-'))
        pdf=PdfReader(BytesIO(data));text='\n'.join(p.extract_text() for p in pdf.pages)
        self.assertIn(self.note.access_key,text.replace(' ',''))
        self.assertIn('PRODUTO FICTICIO 003',text)
        self.assertIn('120,00',text)
        self.assertIn('Vindex Fiscal',text)
        self.assertIn('SEM VALOR FISCAL',text)
        self.note.refresh_from_db();self.assertEqual(self.note.xml_content,original)

    def test_download_is_private_pdf_attachment_and_requires_login(self):
        response=self.client.get(reverse('danfe_download',args=[self.note.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'],'application/pdf')
        self.assertIn('attachment;',response['Content-Disposition'])
        self.assertIn('no-store',response['Cache-Control'])
        self.client.logout()
        self.assertEqual(self.client.get(reverse('danfe_download',args=[self.note.pk])).status_code,302)

    @patch('portal.danfe_views.generate_danfe')
    def test_foreign_workspace_is_denied_before_generation(self,generate):
        self.assertEqual(self.client.get(reverse('danfe_download',args=[self.foreign.pk])).status_code,404)
        generate.assert_not_called()

    def test_pages_offer_both_xml_and_pdf_only_when_available(self):
        for name,args in [('invoice_detail',[self.note.pk]),('invoices',[])]:
            response=self.client.get(reverse(name,args=args))
            self.assertContains(response,reverse('danfe_download',args=[self.note.pk]))
            self.assertContains(response,reverse('xml_download',args=[self.note.pk]))

    def test_partial_xml_keeps_xml_and_explains_pdf_unavailability(self):
        note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj,number='9999'),is_demo=False)
        self.assertFalse(availability(note).available)
        page=self.client.get(reverse('invoice_detail',args=[note.pk]))
        self.assertNotContains(page,reverse('danfe_download',args=[note.pk]))
        response=self.client.get(reverse('danfe_download',args=[note.pk]))
        self.assertEqual(response.status_code,422)
        self.assertContains(response,'Baixar XML original',status_code=422)

    def test_summary_and_unsafe_xml_never_generate_pdf(self):
        for xml in ['<resNFe xmlns="'+N+'"/>','<!DOCTYPE n [<!ENTITY x SYSTEM "file:///private">]><n>&x;</n>']:
            self.note.xml_content=xml
            self.assertFalse(availability(self.note).available)
            with self.assertRaises(DanfeError):generate_danfe(self.note)

    def test_different_recipient_or_key_is_rejected(self):
        for before,after in [(self.company.cnpj,'00000004000170'),('NFe'+self.note.access_key,'NFe'+'9'*44)]:
            self.note.refresh_from_db();self.note.xml_content=self.note.xml_content.replace(before,after)
            self.assertFalse(availability(self.note).available)

    def test_multi_page_pdf_preserves_last_product(self):
        self.note.is_demo=True
        self.note.xml_content=complete_synthetic_xml(self.company.cnpj,items=90).decode()
        data=generate_danfe(self.note);pdf=PdfReader(BytesIO(data))
        self.assertGreater(len(pdf.pages),1)
        self.assertIn('PRODUTO FICTICIO 090','\n'.join(page.extract_text() for page in pdf.pages))
        self.assertTrue(all('SEM VALOR FISCAL' in page.extract_text() for page in pdf.pages))
        self.assertTrue(all('Vindex Fiscal' in page.extract_text() for page in pdf.pages))

    def test_landscape_and_homologation_are_identified(self):
        self.note.xml_content=complete_synthetic_xml(self.company.cnpj,orientation='2',environment='2').decode()
        self.note.is_demo=False
        pdf=PdfReader(BytesIO(generate_danfe(self.note)))
        self.assertGreater(float(pdf.pages[0].mediabox.width),float(pdf.pages[0].mediabox.height))
        self.assertIn('SEM VALOR FISCAL',pdf.pages[0].extract_text())

    @patch('brazilfiscalreport.danfe.Danfe',side_effect=RuntimeError('PRIVATE-XML-CONTENT'))
    def test_library_errors_are_comprehensible_without_exposing_payload(self,library):
        response=self.client.get(reverse('danfe_download',args=[self.note.pk]))
        self.assertEqual(response.status_code,422)
        self.assertNotIn(b'PRIVATE-XML-CONTENT',response.content)
        self.assertContains(response,'XML original',status_code=422)

    def test_post_does_not_emit_events_or_modify_invoice(self):
        response=self.client.post(reverse('danfe_download',args=[self.note.pk]))
        self.assertEqual(response.status_code,405)
        self.assertEqual(self.note.company_id,self.company.pk)

    def test_unit_price_precision_is_taken_from_xml(self):
        self.note.xml_content=self.note.xml_content.replace('20.0000000000','20.12345678')
        text=PdfReader(BytesIO(generate_danfe(self.note))).pages[0].extract_text()
        self.assertIn('20,12345678',text.replace('\n',''))

    def test_missing_invoice_billing_is_not_invented_as_zero(self):
        text=PdfReader(BytesIO(generate_danfe(self.note))).pages[0].extract_text()
        self.assertNotIn('VALOR ORIGINAL',text)
        self.assertIn('60,00',text)

    def test_values_that_cannot_be_preserved_do_not_create_misleading_pdf(self):
        self.note.xml_content=self.note.xml_content.replace('120.00','9999999999999999.99')
        self.assertFalse(availability(self.note).available)
        with self.assertRaisesMessage(DanfeError,'precisão'):generate_danfe(self.note)
