from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from pypdf import PdfReader
from portal.models import FiscalDocument
from portal.tests import create_account
from portal.services.nfse_pdf import generate_nfse_pdf
from portal.services.sefaz import SefazError


def sample_document():
    key = '1' * 50
    return SimpleNamespace(service='nfse', environment='2', cancellation_reported=True,
        access_key=key, xml_content=f'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00"><infNFSe Id="NFS{key}"><nNFSe>1</nNFSe><emit><xNome>FICTÍCIO</xNome></emit><DPS><infDPS><serv><cServ><xDescServ>{"Serviço fictício. " * 200}</xDescServ></cServ></serv><valores><vServPrest><vServ>123.45</vServ></vServPrest></valores></infDPS></DPS></infNFSe></NFSe>')


class NfsePdfTests(SimpleTestCase):
    @patch('portal.services.nfse_pdf.validate_xml')
    def test_faithful_values_long_description_and_explicit_scope(self, validate):
        # Fixture de renderização; validação XSD é testada separadamente.
        doc=sample_document(); original=doc.xml_content
        pages=PdfReader(BytesIO(generate_nfse_pdf(doc))).pages
        text='\n'.join(page.extract_text() for page in pages)
        self.assertIn('123.45',text)
        self.assertIn('Não substitui',text)
        self.assertIn('CANCELAMENTO',text)
        self.assertIn('SEM VALIDADE',text)
        self.assertIn('FICTÍCIO',text)
        self.assertGreater(len(pages),1)
        self.assertEqual(doc.xml_content,original)
    @patch('portal.services.nfse_pdf.validate_xml')
    def test_key_mismatch_cannot_generate_pdf(self, validate):
        doc=sample_document();doc.access_key='2'*50
        with self.assertRaises(SefazError):generate_nfse_pdf(doc)


class NfsePdfScopeTests(TestCase):
    @patch('portal.services.nfse_pdf.generate_nfse_pdf',return_value=b'%PDF-TEST')
    def test_foreign_document_denied_before_pdf_generation(self,generate):
        user,workspace,company=create_account('pdf-own@example.test')
        other,other_ws,foreign=create_account('pdf-foreign@example.test')
        args=dict(service='nfse',environment='1',access_key='1'*50,number='1',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='toma',issued_at=timezone.now(),total='123.45',xml_content='<TESTE/>')
        own=FiscalDocument.objects.create(company=company,**args)
        wrong=FiscalDocument.objects.create(company=foreign,**args)
        self.client.force_login(user)
        response=self.client.get(f'/documentos/{own.pk}/dacte/')
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control'])
        generate.reset_mock()
        self.assertEqual(self.client.get(f'/documentos/{wrong.pk}/dacte/').status_code,404)
        generate.assert_not_called()
