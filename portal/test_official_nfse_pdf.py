from unittest.mock import patch
from types import SimpleNamespace
from django.test import TestCase
from django.utils import timezone
from portal.tests import create_account
from portal.models import FiscalDocument,FiscalConnector
from portal.services.nfse_official_pdf import retrieve_if_configured,validate_pdf,ADAPTERS
from portal.services.sefaz import SefazError


def fictional_pdf(key):
    from fpdf import FPDF
    pdf=FPDF();pdf.add_page();pdf.set_font('Helvetica',size=10);pdf.multi_cell(0,6,'FICTICIO - SEM VALOR FISCAL '+key)
    return bytes(pdf.output())


class PdfAdapterTests(TestCase):
    def setUp(self):
        self.user,self.ws,self.company=create_account('pdf-adapter@example.test')
        self.doc=FiscalDocument.objects.create(company=self.company,service='nfse',environment='1',access_key='1'*50,number='1',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='tomador',issued_at=timezone.now(),total='123.45',xml_content='<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe><emit><enderNac><cMun>3509502</cMun></enderNac></emit></infNFSe></NFSe>')
        FiscalConnector.objects.create(company=self.company,service='nfse',enabled=True,authorized_at=timezone.now())
    def test_no_adapter_does_not_invent_official_pdf_or_make_network_calls(self):
        with patch('portal.services.fiscal_transport.official_get') as network:
            self.assertFalse(retrieve_if_configured(self.doc));network.assert_not_called()
        self.assertIsNone(self.doc.official_pdf)
    @patch('portal.services.fiscal_capture.load_identity')
    def test_adapter_associates_exact_key_and_failure_keeps_original(self,identity):
        # Adaptador inteiramente sintético, somente no teste isolado.
        original=self.doc.xml_content
        adapter=SimpleNamespace(source='ADAPTADOR FICTICIO',fetch=lambda *args:fictional_pdf(self.doc.access_key))
        with patch.dict(ADAPTERS,{('3509502','1'):adapter}):self.assertTrue(retrieve_if_configured(self.doc))
        self.doc.refresh_from_db();self.assertTrue(bytes(self.doc.official_pdf).startswith(b'%PDF-'));self.assertEqual(self.doc.xml_content,original)
        with self.assertRaises(SefazError):validate_pdf(fictional_pdf('2'*50),self.doc.access_key)
