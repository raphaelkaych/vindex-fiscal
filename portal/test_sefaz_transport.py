"""mTLS, schemas e manifestações com A1 sintético; nenhuma conexão de rede."""
import base64
import hashlib
import ssl
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from lxml import etree
from portal.tests import create_account, fake_pfx
from portal.models import DigitalCertificate
from portal.sefaz_models import SefazSyncState, SefazDocument
from portal.sefaz_manifest_models import SefazScienceRequest
from portal.services.capture import configure_capture
from portal.services.certificates import save_certificate
from portal.services.sefaz import NFE_NS, SefazError, SefazNotConfigured
from portal.services.sefaz_transport import (
    SefazTransport, distribution_request, identity_context, load_identity, official_post, server_context,
)
from portal.services.sefaz_schema import validate_message
from portal.services.sefaz_manifest import DS, send_science, science_message

KEY = '35' + '1' * 42


def science_response(key=KEY, environment='1', sequence='1', code='135'):
    return f'''<retEnvEvento xmlns="{NFE_NS}" versao="1.00"><idLote>1</idLote>
<tpAmb>{environment}</tpAmb><verAplic>TESTE</verAplic><cOrgao>91</cOrgao><cStat>128</cStat><xMotivo>LOTE SINTETICO PROCESSADO</xMotivo>
<retEvento versao="1.00"><infEvento><tpAmb>{environment}</tpAmb><verAplic>TESTE</verAplic><cOrgao>91</cOrgao><cStat>{code}</cStat><xMotivo>RESPOSTA SINTETICA SEM VALOR FISCAL</xMotivo>
<chNFe>{key}</chNFe><tpEvento>210210</tpEvento><nSeqEvento>{sequence}</nSeqEvento><dhRegEvento>2026-10-21T13:00:00-03:00</dhRegEvento><nProt>135260000000001</nProt></infEvento></retEvento></retEnvEvento>'''.encode()


class TransportSchemaTests(SimpleTestCase):
    def test_request_uses_default_nfe_namespace_and_official_schema(self):
        for environment in ('1', '2'):
            payload = distribution_request('00000001000136', environment, '000000000000123')
            node = validate_message(payload, 'distDFeInt_v1.01.xsd', 'distDFeInt')
            self.assertIsNone(node.prefix)  # cStat404 rejects prefixed NF-e tags.
            self.assertTrue(all(child.prefix is None for child in node.iter()))
            self.assertEqual(node.findtext(f'{{{NFE_NS}}}tpAmb'), environment)
            self.assertIsNone(node.find(f'{{{NFE_NS}}}cUFAutor'))

    def test_request_with_uf_and_invalid_inputs(self):
        validate_message(distribution_request('00000001000136', '1', '0'*15, '35'), 'distDFeInt_v1.01.xsd', 'distDFeInt')
        for args in [('bad','1','0'*15), ('00000001000136','3','0'*15), ('00000001000136','1','0'), ('00000001000136','1','0'*15,'99')]:
            with self.assertRaises(SefazError): distribution_request(*args)

    def test_tls_verifies_server_and_hostname(self):
        context = server_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_unsafe_xml_and_soap_fault_do_not_pass_schema(self):
        for payload in [b'<!DOCTYPE x [<!ENTITY a "bad">]><x/>', b'<Envelope><Fault>bad</Fault></Envelope>']:
            with self.assertRaises(SefazError): validate_message(payload, 'retDistDFeInt_v1.01.xsd', 'retDistDFeInt')

    @patch('portal.services.sefaz_transport.http.client.HTTPSConnection')
    @patch('portal.services.sefaz_transport.identity_context')
    def test_http_redirect_is_not_followed(self, identity, connection):
        identity.return_value.__enter__.return_value = object()
        response = connection.return_value.getresponse.return_value
        response.status = 302; response.read.return_value = b''
        with self.assertRaisesMessage(SefazError, 'HTTP 302'):
            official_post(object(), 'www1.nfe.fazenda.gov.br', '/fixed', 'action', b'<safe/>')
        self.assertEqual(connection.return_value.request.call_count, 1)
        connection.return_value.close.assert_called_once()


class IdentityAndScienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user, cls.workspace, cls.company = create_account('transport-test@example.test')
        cls.other, cls.other_workspace, cls.other_company = create_account('transport-other@example.test')
        cls.pfx = fake_pfx(cls.company.cnpj)
        save_certificate(cls.company, cls.pfx, 'SenhaTeste123!')
        configure_capture(cls.workspace, cls.company.pk, actor=cls.user, authorize_read=True)
        cls.state = SefazSyncState.objects.get(company=cls.company, source='sefaz', environment='1')
        cls.document = SefazDocument.objects.create(state=cls.state, kind='summary', content_hash='a'*64,
            access_key=KEY, schema_name='resNFe_v1.01.xsd', xml_content='<resNFe>FICTICIO</resNFe>')

    def science(self, **kwargs):
        return send_science(self.workspace, self.company.pk, self.document.pk,
                           actor=self.user, authorized=True, **kwargs)

    def test_encrypted_identity_reopens_and_temp_files_are_removed(self):
        key, cert, chain = load_identity(self.company)
        self.assertIsNotNone(key)
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            real_temp = tempfile.TemporaryDirectory
            def inside(**kwargs): return real_temp(dir=directory, **kwargs)
            with patch('portal.services.sefaz_transport.tempfile.TemporaryDirectory', side_effect=inside):
                with identity_context(self.company) as context:
                    self.assertEqual(list(Path(directory).iterdir()), [])
                    self.assertTrue(context.check_hostname)

    def test_missing_demo_and_corrupted_certificates_fail_closed(self):
        with self.assertRaises(SefazNotConfigured): load_identity(self.other_company)
        stored = DigitalCertificate.objects.get(company=self.company)
        stored.is_demo=True; stored.save()
        with self.assertRaises(SefazNotConfigured): load_identity(self.company)
        stored.is_demo=False; stored.encrypted_password=b'NOT-FERNET'; stored.save()
        with self.assertRaisesMessage(SefazNotConfigured, 'protegido'): load_identity(self.company)

    def test_signature_and_digest_survive_exact_soap_serialization(self):
        signed, soap = science_message(self.company, '1', KEY)
        for payload in (signed, soap):
            root = etree.fromstring(payload)
            info = root.find(f'.//{{{NFE_NS}}}infEvento')
            self.assertEqual(info.findtext(f'{{{NFE_NS}}}tpEvento'), '210210')
            signature = root.find(f'.//{{{DS}}}Signature')
            digest = base64.b64decode(signature.findtext(f'.//{{{DS}}}DigestValue'))
            self.assertEqual(digest, hashlib.sha1(etree.tostring(info, method='c14n')).digest())
            cert = x509.load_der_x509_certificate(base64.b64decode(signature.findtext(f'.//{{{DS}}}X509Certificate')))
            cert.public_key().verify(base64.b64decode(signature.findtext(f'{{{DS}}}SignatureValue')),
                etree.tostring(signature.find(f'{{{DS}}}SignedInfo'), method='c14n'), padding.PKCS1v15(), hashes.SHA1())
        self.assertNotIn(b'PRIVATE KEY', soap)
        self.assertNotIn(b'SenhaTeste123!', soap)

    def test_current_official_schemas_accept_alphanumeric_cnpj_and_key(self):
        from portal.validators import validate_cnpj
        from django.core.exceptions import ValidationError
        for suffix in range(100):
            candidate='AB0000010001'+f'{suffix:02}'
            try:
                validate_cnpj(candidate)
                break
            except ValidationError:
                continue
        else:
            self.fail('CNPJ sintético alfanumérico não gerado.')
        self.company.cnpj=candidate;self.company.save(update_fields=['cnpj'])
        save_certificate(self.company,fake_pfx(candidate),'SenhaTeste123!')
        alpha_key=KEY[:6]+candidate+KEY[20:]
        signed,soap=science_message(self.company,'1',alpha_key)
        self.assertIn(candidate.encode(),signed)
        self.assertEqual(validate_message(signed,'envEvento_v1.00.xsd','envEvento').tag,f'{{{NFE_NS}}}envEvento')

    @patch('portal.services.sefaz_manifest.official_post')
    def test_authorization_and_workspace_are_required_before_network(self, post):
        with self.assertRaises(SefazError): send_science(self.workspace,self.company.pk,self.document.pk,actor=self.user)
        with self.assertRaises(SefazError): send_science(self.other_workspace,self.company.pk,self.document.pk,actor=self.other,authorized=True)
        post.assert_not_called()
        self.assertFalse(SefazScienceRequest.objects.exists())

    @patch('portal.services.sefaz_manifest.official_post', return_value=science_response())
    def test_science_is_recorded_once_without_confirming_operation(self, post):
        result = self.science()
        self.assertEqual(result.status, 'accepted')
        self.assertEqual(result.response_code, '135')
        self.assertEqual(result.authorized_by, self.user)
        with self.assertRaisesMessage(SefazError,'já foi solicitada'): self.science()
        self.assertEqual(post.call_count,1)
        self.assertEqual(self.company.invoices.count(),0)

    @patch('portal.services.sefaz_manifest.official_post', side_effect=SefazError('Timeout de teste'))
    def test_uncertain_response_prevents_automatic_resubmission(self, post):
        with self.assertRaises(SefazError): self.science()
        self.assertEqual(SefazScienceRequest.objects.get().status,'uncertain')
        with self.assertRaises(SefazError): self.science()
        self.assertEqual(post.call_count,1)

    @patch('portal.services.sefaz_manifest.official_post', return_value=science_response(environment='2'))
    def test_response_from_other_environment_does_not_register_success(self, post):
        with self.assertRaisesMessage(SefazError,'ambiente'): self.science()
        self.assertEqual(SefazScienceRequest.objects.get().status,'uncertain')

    @patch('portal.services.sefaz_manifest.official_post', return_value=science_response(sequence='2'))
    def test_response_from_other_sequence_does_not_register_success(self, post):
        with self.assertRaisesMessage(SefazError,'sequência'): self.science()
        self.assertEqual(SefazScienceRequest.objects.get().status,'uncertain')

    @patch('portal.services.sefaz_manifest.official_post', return_value=science_response(code='573'))
    def test_duplicate_response_is_not_presented_as_success(self, post):
        result = self.science()
        self.assertEqual(result.status,'rejected')
        self.assertEqual(result.response_code,'573')

    @patch('portal.services.sefaz_manifest.official_post', return_value=science_response().replace(b'<nProt>135260000000001</nProt>',b''))
    def test_registration_without_protocol_is_not_success(self, post):
        with self.assertRaisesMessage(SefazError,'sem protocolo'): self.science()
        self.assertEqual(SefazScienceRequest.objects.get().status,'uncertain')

    @patch('portal.services.sefaz_manifest.official_post', return_value=science_response())
    def test_same_cnpj_in_another_workspace_does_not_resend_event(self, post):
        self.science()
        save_certificate(self.other_company, self.pfx, 'SenhaTeste123!')
        configure_capture(self.other_workspace,self.other_company.pk,actor=self.other,authorize_read=True)
        state=SefazSyncState.objects.get(company=self.other_company,source='sefaz',environment='1')
        document=SefazDocument.objects.create(state=state,kind='summary',content_hash='b'*64,
            access_key=KEY,schema_name='resNFe_v1.01.xsd',xml_content='FICTICIO')
        with self.assertRaisesMessage(SefazError,'já foi solicitada'):
            send_science(self.other_workspace,self.other_company.pk,document.pk,actor=self.other,authorized=True)
        self.assertEqual(post.call_count,1)

