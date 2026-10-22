import hashlib
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase,SimpleTestCase
from django.utils import timezone
from portal.tests import create_account,fake_pfx
from portal.models import FiscalConnector,FiscalStream,FiscalEnvelope,FiscalConsultation,FiscalDelivery,FiscalDocument,Installment
from portal.services.fiscal_transport import NFSE,xml_read
from portal.services.nfse_compat import signature_status,partial_profile,identify
from portal.services.fiscal_capture import deliver
from portal.services.sefaz import SefazError


def xml_sample(cnpj,key='1'*50):
    return f'<NFSe xmlns="{NFSE}" versao="1.00"><infNFSe Id="NFS{key}"><nNFSe>1</nNFSe><dhProc>{timezone.now().isoformat()}</dhProc><emit><CNPJ>00000003000125</CNPJ><xNome>FICTICIO</xNome><enderNac><cMun>3509502</cMun></enderNac></emit><DPS><infDPS><tpAmb>1</tpAmb><dhEmi>2026-10-21T10:00:00-03:00</dhEmi><toma><CNPJ>{cnpj}</CNPJ></toma><valores><vServPrest><vServ>123.45</vServ></vServPrest><trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN><pAliq>2.00</pAliq></tribMun></trib></valores></infDPS></DPS></infNFSe></NFSe>'


class IntegrityTests(SimpleTestCase):
    def signed(self):
        from cryptography.hazmat.primitives.serialization import pkcs12,Encoding
        from signxml import XMLSigner
        key,cert,_=pkcs12.load_key_and_certificates(fake_pfx('00000001000136'),b'SenhaTeste123!')
        root=xml_read(xml_sample('00000001000136').encode())
        return XMLSigner().sign(root,key=key,cert=cert.public_bytes(Encoding.PEM),reference_uri='#NFS'+'1'*50,id_attribute='Id')
    def test_signed_original_and_tampered_value_are_distinguished(self):
        root=self.signed();self.assertEqual(signature_status(root),'verified_embedded_key')
        root.find('.//{'+NFSE+'}vServ').text='999.00'
        self.assertEqual(signature_status(root),'invalid')
    def test_unknown_pattern_is_identified_and_not_promoted(self):
        root=xml_read(b'<CompNfse xmlns="http://www.abrasf.org.br/nfse.xsd" versao="2.04"/>')
        self.assertEqual(identify(root)['pattern'],'abrasf')
        with self.assertRaises(SefazError):partial_profile(root)
    @patch('portal.services.nfse_compat.schema')
    def test_profile_never_mutates_original_and_does_not_accept_general_schema_failure(self,schema):
        # Teste do perfil; XSD real também é exercitado sobre originais no diagnóstico.
        from lxml import etree
        root=xml_read(xml_sample('00000001000136').encode());original=etree.tostring(root)
        schema.return_value.validate.return_value=True
        self.assertEqual(partial_profile(root)['profile'],['pAliq_order'])
        self.assertEqual(etree.tostring(root),original)
        schema.return_value.validate.return_value=False
        with self.assertRaises(SefazError):partial_profile(root)


class RecoveryTests(TestCase):
    @patch('portal.services.fiscal_import.validate_xml')
    def test_issued_nfse_and_substitution_event_stay_scoped(self,validate):
        from portal.services.fiscal_import import import_fiscal
        root=xml_read(self.xml.encode())
        root.find('.//{'+NFSE+'}emit/{'+NFSE+'}CNPJ').text=self.company.cnpj
        root.find('.//{'+NFSE+'}toma/{'+NFSE+'}CNPJ').text=self.foreign.cnpj
        from lxml import etree
        doc=import_fiscal(self.config,SimpleNamespace(kind='complete',xml_content=etree.tostring(root).decode()))
        self.assertEqual(doc.role,'emitente')
        event=f'<evento xmlns="{NFSE}" versao="1.00"><infEvento><chNFSe>{doc.access_key}</chNFSe><e105102><chSubstituta>{"2"*50}</chSubstituta></e105102></infEvento></evento>'
        import_fiscal(self.config,SimpleNamespace(kind='event',xml_content=event))
        doc.refresh_from_db();self.assertTrue(doc.substitution_reported);self.assertTrue(doc.cancellation_reported)
        self.assertEqual(doc.substituted_by,'2'*50);self.assertEqual(Installment.objects.count(),0)
    def setUp(self):
        self.user,self.ws,self.company=create_account('recovery-nfse@example.test')
        self.other,self.other_ws,self.foreign=create_account('recovery-foreign@example.test','00000002000180')
        self.config=FiscalConnector.objects.create(company=self.company,service='nfse',enabled=True,authorized_at=timezone.now())
        self.stream=FiscalStream.objects.create(cnpj=self.company.cnpj,service='nfse',environment='1',cursor='1',next_attempt_at=timezone.now())
        self.xml=xml_sample(self.company.cnpj)
        self.envelope=FiscalEnvelope.objects.create(stream=self.stream,nsu='1',xml_content=self.xml,kind='complete',content_hash=hashlib.sha256(self.xml.encode()).hexdigest())
        FiscalConsultation.objects.create(stream=self.stream,cursor_sent='0',status='DOCUMENTOS_LOCALIZADOS',http_status=200,completed_at=timezone.now(),response_content='RESPOSTA SINTETICA')
    @patch('portal.services.fiscal_import.validate_xml',side_effect=SefazError('Schema incompatível'))
    @patch('portal.services.nfse_compat.schema')
    @patch('portal.services.fiscal_capture.load_identity')
    def test_partial_is_visible_excluded_from_values_idempotent_and_keeps_cursor_and_xml(self,identity,schema,validate):
        schema.return_value.validate.return_value=True
        deliver(self.stream);doc=FiscalDocument.objects.get()
        self.assertEqual(doc.validation_status,'partial');self.assertEqual(Installment.objects.count(),0)
        self.assertEqual(doc.xml_content,self.xml)
        row=FiscalDelivery.objects.get();self.assertEqual(row.processing_status,'partial');self.assertTrue(row.error)
        self.stream.refresh_from_db();self.assertEqual(self.stream.cursor,'1')
        self.envelope.refresh_from_db();self.assertEqual(self.envelope.xml_content,self.xml)
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/documentos/pendentes/'),'Importação parcial')
        response=self.client.get('/indicadores/?from=2026-01-01&to=2026-12-31')
        self.assertEqual(response.context['partial_count'],1);self.assertEqual(response.context['panels'][0]['value'],0)
        deliver(self.stream);self.assertEqual(FiscalDocument.objects.count(),1)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get('/documentos/pendentes/'),'Importação parcial')
        self.assertEqual(self.client.get(f'/conectores/documentos/{row.pk}/xml/').status_code,404)
    @patch('portal.services.fiscal_capture.load_identity')
    def test_unknown_document_stays_pending_without_false_success(self,identity):
        self.envelope.kind='unknown';self.envelope.xml_content='<CompNfse versao="2.04"/>';self.envelope.save()
        deliver(self.stream);row=FiscalDelivery.objects.get()
        self.assertEqual(row.processing_status,'unsupported');self.assertTrue(row.error)
        self.assertEqual(row.diagnostics['pattern'],'abrasf');self.assertFalse(FiscalDocument.objects.exists())
    @patch('portal.services.fiscal_import.validate_xml',side_effect=SefazError('Schema incompatível'))
    def test_partial_refuses_hash_change_before_interpretation(self,validate):
        from portal.services.fiscal_import import import_fiscal
        self.envelope.content_hash='0'*64
        with self.assertRaisesMessage(SefazError,'original preservado'):import_fiscal(self.config,self.envelope)
