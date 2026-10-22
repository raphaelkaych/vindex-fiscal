"""Somente dados sintéticos: nenhuma consulta fiscal ou bancária real."""
import hashlib
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse, resolve
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema
from pypdf import PdfWriter
from rest_framework.test import APIClient

from portal.api_models import ApiCredential, CredentialCompany
from portal.boleto_models import Boleto, BoletoEvent
from portal.models import Workspace, Company, Invoice, Installment, DigitalCertificate
from portal.services.boletos import mod11, validate_code
from portal.services.demo import sample_xml, DEMO_COMPANIES, ISSUER
from portal.services.invoices import import_invoice


def synthetic_barcode(reference='1234567890123456789012345'):
    raw = '0019' + '0' + '1000' + '0000060000' + reference
    return raw[:4] + str(mod11(raw[:4] + raw[5:])) + raw[5:]


def synthetic_pdf(width=200):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=100)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@override_settings(API_REQUIRE_HTTPS=False)
class IntegrationApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        # Mantém o algoritmo PBKDF2 real, reduzindo somente custo em fixtures sintéticas.
        cls.hasher_patch = patch('django.contrib.auth.hashers.PBKDF2PasswordHasher.iterations', 1000)
        cls.hasher_patch.start()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.hasher_patch.stop()

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='api-ficticio@example.test', password='SenhaSintetica!123')
        cls.other_user = User.objects.create_user(username='outro-ficticio@example.test', password='SenhaSintetica!456')
        cls.workspace = Workspace.objects.create(owner=cls.user, name='Cliente API FICTÍCIO')
        cls.other_workspace = Workspace.objects.create(owner=cls.other_user, name='Outro cliente FICTÍCIO')
        cls.company = Company.objects.create(workspace=cls.workspace, legal_name='Empresa autorizada FICTÍCIA', cnpj=DEMO_COMPANIES[0][2])
        cls.not_allowed = Company.objects.create(workspace=cls.workspace, legal_name='Empresa sem autorização FICTÍCIA', cnpj=DEMO_COMPANIES[1][2])
        # Mesmo CNPJ em outro Workspace não concede acesso nem identifica a mesma conta.
        cls.foreign_company = Company.objects.create(workspace=cls.other_workspace, legal_name='Empresa outro cliente FICTÍCIA', cnpj=cls.company.cnpj)
        cls.invoice, _ = import_invoice(cls.workspace, sample_xml(cls.company.cnpj), is_demo=False)
        cls.not_allowed_invoice, _ = import_invoice(cls.workspace, sample_xml(cls.not_allowed.cnpj, number='1002'), is_demo=False)
        cls.foreign_invoice, _ = import_invoice(cls.other_workspace, sample_xml(cls.foreign_company.cnpj), is_demo=False)
        cls.installment = cls.invoice.installments.first()
        cls.not_allowed_installment = cls.not_allowed_invoice.installments.first()
        cls.foreign_installment = cls.foreign_invoice.installments.first()
        cls.pdf = synthetic_pdf()
        cls.barcode = synthetic_barcode()
        cls.boleto = Boleto.objects.create(company=cls.company, barcode=cls.barcode, amount='600.00', due_on=cls.installment.due_on,
            beneficiary_document=ISSUER, payer_document=cls.company.cnpj, private_pdf=cls.pdf,
            pdf_sha256=hashlib.sha256(cls.pdf).hexdigest(), validation_state='validated')
        cls.foreign_boleto = Boleto.objects.create(company=cls.foreign_company, private_pdf=b'PRIVATE-FOREIGN-SYNTHETIC', amount='999.00')
        cls.not_allowed_boleto = Boleto.objects.create(company=cls.not_allowed, amount='888.00')
        for company in (cls.company, cls.foreign_company, cls.not_allowed):
            DigitalCertificate.objects.create(company=company, encrypted_file=b'SYNTHETIC-PRIVATE-PFX', encrypted_password=b'SYNTHETIC-SECRET',
                subject_name='FICTÍCIO', holder_cnpj=company.cnpj, valid_from=timezone.now() - timedelta(days=1),
                valid_until=timezone.now() + timedelta(days=30), fingerprint='a'*64)
        cls.credential, cls.token = ApiCredential.issue(workspace=cls.workspace, name='ERP fictício', scopes=['read', 'write'],
            companies=[cls.company], expires_at=timezone.now() + timedelta(days=30))

    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + self.token)

    def test_existing_credential_cannot_bypass_pending_or_suspended_workspace(self):
        for status in ['pending','suspended']:
            with self.subTest(status=status):
                cache.clear()
                Workspace.objects.filter(pk=self.workspace.pk).update(access_status=status)
                self.assertEqual(self.api.get('/api/v1/empresas/').status_code,401)
                self.assertEqual(self.api.post('/api/v1/empresas/',{},format='json').status_code,401)
                self.credential.refresh_from_db();self.assertIsNone(self.credential.last_used_at)
        Workspace.objects.filter(pk=self.workspace.pk).update(access_status='active')
        self.assertEqual(self.api.get('/api/v1/empresas/').status_code,200)

    def issue(self, scopes, companies=None):
        return ApiCredential.issue(workspace=self.workspace, name='Fixture fictícia', scopes=scopes,
            companies=[self.company] if companies is None else companies, expires_at=timezone.now() + timedelta(days=5))

    def test_authentication_required_even_when_session_logged_in(self):
        self.api.credentials()
        self.api.force_login(self.user)
        response = self.api.get('/api/v1/empresas/')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'authentication_failed')
        self.assertEqual(response['WWW-Authenticate'], 'Bearer')

    def test_opaque_secret_only_hash_stored(self):
        self.credential.refresh_from_db()
        self.assertTrue(self.credential.secret_hash.startswith('pbkdf2_sha256$'))
        self.assertNotIn(self.token, str(ApiCredential.objects.values().get(pk=self.credential.pk)))
        self.assertNotIn(self.token.split('.')[1], self.credential.secret_hash)
        self.assertTrue(self.credential.verifies(self.token.split('.')[1]))
        self.assertFalse(self.credential.verifies('incorrect-secret'))

    def test_invalid_expired_revoked_and_inactive_credentials(self):
        for kind in ('invalid', 'expired', 'revoked', 'inactive'):
            with self.subTest(kind=kind):
                cache.clear()
                self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + self.token)
                ApiCredential.objects.filter(pk=self.credential.pk).update(expires_at=timezone.now()+timedelta(days=1), revoked_at=None)
                User.objects.filter(pk=self.user.pk).update(is_active=True)
                if kind == 'invalid': self.api.credentials(HTTP_AUTHORIZATION='Bearer vfx_' + '0'*16 + '.' + 'x'*43)
                if kind == 'expired': ApiCredential.objects.filter(pk=self.credential.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
                if kind == 'revoked': ApiCredential.objects.filter(pk=self.credential.pk).update(revoked_at=timezone.now())
                if kind == 'inactive': User.objects.filter(pk=self.user.pk).update(is_active=False)
                self.assertEqual(self.api.get('/api/v1/notas/').status_code, 401)

    def test_scopes_checked_for_both_read_and_write(self):
        _, token = self.issue(['read'])
        self.api.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(self.api.get('/api/v1/notas/').status_code, 200)
        self.assertEqual(self.api.post('/api/v1/empresas/', {}, format='json').status_code, 403)
        _, token = self.issue(['write'])
        self.api.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(self.api.get('/api/v1/notas/').status_code, 403)

    @override_settings(API_REQUIRE_HTTPS=True, SECURE_SSL_REDIRECT=False)
    def test_https_required_for_production_authentication(self):
        self.assertEqual(self.api.get('/api/v1/empresas/').status_code, 401)
        self.assertEqual(self.api.get('/api/v1/empresas/', secure=True).status_code, 200)

    def test_empty_company_scope_is_no_access(self):
        _, token = self.issue(['read', 'write'], companies=[])
        self.api.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(self.api.get('/api/v1/empresas/').json()['count'], 0)
        self.assertEqual(self.api.get(f'/api/v1/notas/{self.invoice.pk}/').status_code, 404)

    def test_corrupted_company_grant_still_cannot_cross_workspace(self):
        # bulk_create simula corrupção fora dos serviços e ignora clean() de propósito.
        CredentialCompany.objects.bulk_create([CredentialCompany(credential=self.credential, company=self.foreign_company)])
        self.assertFalse(self.credential.allowed_companies.filter(pk=self.foreign_company.pk).exists())
        self.assertEqual(self.api.get(f'/api/v1/notas/{self.foreign_invoice.pk}/').status_code, 404)

    def test_credential_rejects_foreign_company_and_expiry(self):
        with self.assertRaises(ValidationError): self.issue(['read'], [self.foreign_company])
        with self.assertRaises(ValidationError):
            ApiCredential.issue(workspace=self.workspace, name='Expirada', scopes=['read'], companies=[], expires_at=timezone.now()-timedelta(days=1))
        with self.assertRaises(ValidationError):
            ApiCredential.issue(workspace=self.workspace, name='Excessiva', scopes=['read'], companies=[], expires_at=timezone.now()+timedelta(days=366))
        with self.assertRaises(ValidationError): CredentialCompany(credential=self.credential, company=self.foreign_company).save()

    def test_lists_and_details_cannot_cross_company_or_workspace(self):
        resources = [('empresas', self.company, self.not_allowed, self.foreign_company),
                     ('notas', self.invoice, self.not_allowed_invoice, self.foreign_invoice),
                     ('parcelas', self.installment, self.not_allowed_installment, self.foreign_installment),
                     ('boletos', self.boleto, self.not_allowed_boleto, self.foreign_boleto),
                     ('certificados', self.company.certificate, self.not_allowed.certificate, self.foreign_company.certificate)]
        for route, allowed, denied, foreign in resources:
            with self.subTest(route=route):
                response = self.api.get(f'/api/v1/{route}/')
                self.assertEqual(response.status_code, 200)
                ids = {item['id'] for item in response.json()['results']}
                self.assertIn(allowed.pk, ids)
                self.assertNotIn(denied.pk, ids)
                self.assertNotIn(foreign.pk, ids)
                self.assertEqual(self.api.get(f'/api/v1/{route}/{allowed.pk}/').status_code, 200)
                self.assertEqual(self.api.get(f'/api/v1/{route}/{denied.pk}/').status_code, 404)
                self.assertEqual(self.api.get(f'/api/v1/{route}/{foreign.pk}/').status_code, 404)

    def test_private_downloads_require_full_scope(self):
        allowed = self.api.get(f'/api/v1/notas/{self.invoice.pk}/xml/')
        self.assertEqual(allowed.status_code, 200)
        self.assertIn(b'nfeProc', allowed.content)
        self.assertIn('no-store', allowed['Cache-Control'])
        self.assertEqual(self.api.get(f'/api/v1/notas/{self.foreign_invoice.pk}/xml/').status_code, 404)
        self.assertEqual(self.api.get(f'/api/v1/notas/{self.not_allowed_invoice.pk}/xml/').status_code, 404)
        allowed = self.api.get(f'/api/v1/boletos/{self.boleto.pk}/arquivo/')
        self.assertEqual(allowed.content, self.pdf)
        self.assertEqual(self.api.get(f'/api/v1/boletos/{self.foreign_boleto.pk}/arquivo/').status_code, 404)

    def test_read_only_credential_cannot_import_patch_or_associate(self):
        _, token = self.issue(['read'])
        self.api.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        requests = [
            self.api.post('/api/v1/notas/importar/', {}, format='json'),
            self.api.post('/api/v1/boletos/importar/', {}, format='json'),
            self.api.patch(f'/api/v1/boletos/{self.boleto.pk}/', {}, format='json'),
            self.api.patch(f'/api/v1/parcelas/{self.installment.pk}/', {}, format='json'),
            self.api.post(f'/api/v1/boletos/{self.boleto.pk}/associar/', {}, format='json'),
            self.api.post(f'/api/v1/parcelas/{self.installment.pk}/conferir/', {}, format='json'),
        ]
        self.assertTrue(all(response.status_code == 403 for response in requests))

    def test_certificate_metadata_has_no_secret_fields(self):
        body = self.api.get('/api/v1/certificados/').content.decode()
        for secret in ('encrypted_file', 'encrypted_password', 'SYNTHETIC-PRIVATE', 'SYNTHETIC-SECRET', 'fingerprint'):
            self.assertNotIn(secret, body)
        self.assertIn('valid_until', body)
        self.assertEqual(self.api.get(f'/api/v1/certificados/{self.company.certificate.pk}/arquivo/').status_code, 404)

    def test_company_creation_uses_authenticated_workspace_and_adds_explicit_scope(self):
        response = self.api.post('/api/v1/empresas/', {'legal_name': 'Novo CNPJ FICTÍCIO', 'cnpj': ISSUER}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        created = Company.objects.get(pk=response.json()['id'])
        self.assertEqual(created.workspace, self.workspace)
        self.assertTrue(self.credential.allowed_companies.filter(pk=created.pk).exists())
        self.assertEqual(self.api.get(f'/api/v1/empresas/{created.pk}/').status_code, 200)

    def test_company_creation_cannot_inject_workspace_or_authorize_existing_company(self):
        before = Company.objects.count()
        response = self.api.post('/api/v1/empresas/', {'legal_name':'Invasão fictícia','cnpj':ISSUER,'workspace':self.other_workspace.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Company.objects.count(), before)
        self.assertEqual(self.api.post('/api/v1/empresas/', {'legal_name':'Já existe','cnpj':self.not_allowed.cnpj}, format='json').status_code, 400)
        self.assertFalse(self.credential.allowed_companies.filter(pk=self.not_allowed.pk).exists())

    def test_company_cnpj_accepts_formatted_input(self):
        response = self.api.post('/api/v1/empresas/', {'legal_name':'Fictícia', 'cnpj':'00.000.003/0001-25'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['cnpj'], ISSUER)

    def test_filters_ordering_and_pagination_are_allowlisted(self):
        self.assertEqual(self.api.get('/api/v1/notas/', {'company':self.not_allowed.pk}).status_code, 404)
        self.assertEqual(self.api.get('/api/v1/notas/', {'cnpj':self.not_allowed.cnpj}).status_code, 404)
        for params in ({'workspace':self.other_workspace.pk}, {'ordering':'company__workspace__owner__email'}, {'from':'bad'}, {'source':'fictional'}, {'from':'2026-10-20','to':'2026-01-01'}):
            with self.subTest(params=params): self.assertEqual(self.api.get('/api/v1/notas/', params).status_code, 400)
        response = self.api.get('/api/v1/parcelas/', {'page_size':1,'ordering':'-amount'})
        self.assertEqual(len(response.json()['results']), 1)
        self.assertIsNotNone(response.json()['next'])
        self.assertEqual(self.api.get('/api/v1/notas/', {'supplier':'inexistente'}).json()['count'], 0)

    def test_xml_import_scope_validated_before_write_and_idempotent(self):
        before = Invoice.objects.count()
        blocked = self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('ficticio.xml', sample_xml(self.not_allowed.cnpj, number='9001'))}, format='multipart')
        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertEqual(Invoice.objects.count(), before)
        for expected, created in ((201, True), (200, False)):
            response = self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('ficticio.xml', sample_xml(self.company.cnpj, number='9001'))}, format='multipart')
            self.assertEqual(response.status_code, expected, response.content)
            self.assertEqual(response.json()['created'], created)
            self.assertEqual(response.json()['invoice']['source'], 'api_xml')
        self.assertEqual(Invoice.objects.count(), before+1)

    def test_xml_invalid_or_non_nfe_cannot_leak_payload(self):
        payload = b'<private>SYNTHETIC-PRIVATE-MARKER</private>'
        response = self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('ficticio.xml', payload)}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertNotIn('SYNTHETIC-PRIVATE-MARKER', response.content.decode())
        self.assertEqual(self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('ficticio.pdf', payload)}, format='multipart').status_code, 400)

    def test_large_xml_and_unknown_write_fields_rejected(self):
        self.assertEqual(self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('large.xml', b' '* (2*1024*1024+1))}, format='multipart').status_code, 400)
        response = self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('f.xml', sample_xml(self.company.cnpj, number='9002')), 'workspace':self.workspace.pk}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_money_and_financial_status_keep_meaning(self):
        result = self.api.get(f'/api/v1/notas/{self.invoice.pk}/').json()
        self.assertEqual(result['total'], '1200.00')
        self.assertEqual(result['installments'][0]['amount'], '600.00')
        self.assertEqual(result['installments'][0]['financial_status'], 'forecast')
        self.assertEqual(self.api.get(f'/api/v1/boletos/{self.boleto.pk}/').json()['financial_status'], 'unknown')

    def test_installment_creation_correction_and_check_reuse_services(self):
        data = {'invoice':self.invoice.pk,'number':'MANUAL','amount':'20.03','due_on':None,'review_note':'Condição comercial fictícia revisada.'}
        response = self.api.post('/api/v1/parcelas/', data, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        item = Installment.objects.get(pk=response.json()['id'])
        response = self.api.patch(f'/api/v1/parcelas/{item.pk}/', {'amount':'20.04','review_note':'Correção sintética com evidência.'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['amount'], '20.04')
        self.assertEqual(item.revisions.count(), 2)
        response = self.api.post(f'/api/v1/parcelas/{item.pk}/conferir/', {'checked':True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['checked'])
        self.assertEqual(response.json()['financial_status'], 'forecast')

    def test_installment_writes_cannot_escape_relationship_scope(self):
        before = Installment.objects.count()
        for invoice in (self.foreign_invoice, self.not_allowed_invoice):
            response = self.api.post('/api/v1/parcelas/', {'invoice':invoice.pk,'number':'NEW','amount':'10.00','review_note':'Fictício'}, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Installment.objects.count(), before)
        for item in (self.foreign_installment, self.not_allowed_installment):
            self.assertEqual(self.api.patch(f'/api/v1/parcelas/{item.pk}/', {'amount':'5.00','review_note':'Teste'}, format='json').status_code, 404)
            self.assertEqual(self.api.post(f'/api/v1/parcelas/{item.pk}/conferir/', {'checked':True}, format='json').status_code, 404)

    def test_installment_correction_requires_reason_and_preserves_xml_snapshot(self):
        original = self.installment.original_data
        self.assertEqual(self.api.patch(f'/api/v1/parcelas/{self.installment.pk}/', {'amount':'25.00'}, format='json').status_code, 400)
        self.assertEqual(self.api.patch(f'/api/v1/parcelas/{self.installment.pk}/', {'invoice':self.foreign_invoice.pk,'review_note':'Teste'}, format='json').status_code, 400)
        response = self.api.patch(f'/api/v1/parcelas/{self.installment.pk}/', {'amount':'25.00','review_note':'Revisão sintética.'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.installment.refresh_from_db()
        self.assertEqual(self.installment.original_data, original)

    def test_monetary_float_rejected_without_rounding(self):
        data = {'invoice':self.invoice.pk,'number':'FLOAT','amount':10.01,'review_note':'Teste sintético'}
        self.assertEqual(self.api.post('/api/v1/parcelas/', data, format='json').status_code, 400)
        data['amount'] = '10.001'
        self.assertEqual(self.api.post('/api/v1/parcelas/', data, format='json').status_code, 400)

    def test_boleto_structured_import_is_idempotent_and_scoped(self):
        data = {'company':self.company.pk,'barcode':synthetic_barcode('2234567890123456789012345'), 'payer_document':self.company.cnpj}
        for expected in (201,200):
            response = self.api.post('/api/v1/boletos/importar/', data, format='json')
            self.assertEqual(response.status_code, expected, response.content)
            self.assertEqual(response.json()['boleto']['source'], 'api')
        before = Boleto.objects.count()
        data['company'] = self.not_allowed.pk
        self.assertEqual(self.api.post('/api/v1/boletos/importar/', data, format='json').status_code, 400)
        data['company'] = self.foreign_company.pk
        self.assertEqual(self.api.post('/api/v1/boletos/importar/', data, format='json').status_code, 400)
        self.assertEqual(Boleto.objects.count(), before)

    def test_pdf_import_private_download_and_unreadable_scan_review(self):
        before = Boleto.objects.count()
        pdf = synthetic_pdf(width=201)
        response = self.api.post('/api/v1/boletos/importar/', {'company':self.company.pk,'file':SimpleUploadedFile('ficticio.pdf', pdf)}, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()['boleto']
        self.assertTrue(body['has_pdf'])
        self.assertTrue(body['needs_review'])
        self.assertIsNone(body['amount'])
        self.assertIsNone(body['due_on'])
        self.assertNotIn('private_pdf', body)
        self.assertEqual(self.api.get(f"/api/v1/boletos/{body['id']}/arquivo/").content, pdf)
        response = self.api.post('/api/v1/boletos/importar/', {'company':self.company.pk,'file':SimpleUploadedFile('ficticio.pdf', pdf)}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Boleto.objects.count(), before+1)

    def test_boleto_import_rejects_invalid_code_pdf_and_payer_mismatch(self):
        before = Boleto.objects.count()
        self.assertEqual(self.api.post('/api/v1/boletos/importar/', {'company':self.company.pk,'barcode':'0'*44}, format='json').status_code, 400)
        self.assertEqual(self.api.post('/api/v1/boletos/importar/', {'company':self.company.pk,'file':SimpleUploadedFile('f.pdf', b'not a pdf')}, format='multipart').status_code, 400)
        self.assertEqual(self.api.post('/api/v1/boletos/importar/', {'company':self.company.pk,'barcode':self.barcode,'payer_document':self.not_allowed.cnpj}, format='json').status_code, 400)
        self.assertEqual(Boleto.objects.count(), before)

    def test_boleto_association_audit_without_duplicate_obligation(self):
        before = Installment.objects.count()
        response = self.api.post(f'/api/v1/boletos/{self.boleto.pk}/associar/', {'installment':self.installment.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['installment'], self.installment.pk)
        self.assertEqual(response.json()['invoice'], self.invoice.pk)
        self.assertEqual(Installment.objects.count(), before)
        self.assertTrue(BoletoEvent.objects.filter(boleto=self.boleto, action='associado', source='api', actor_label=f'ApiCredential:{self.credential.pk}').exists())
        response = self.api.post(f'/api/v1/boletos/{self.boleto.pk}/associar/', {'installment':None}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['installment'])

    def test_boleto_association_cannot_reference_other_client_or_company(self):
        for installment in (self.foreign_installment, self.not_allowed_installment):
            response = self.api.post(f'/api/v1/boletos/{self.boleto.pk}/associar/', {'installment':installment.pk}, format='json')
            self.assertEqual(response.status_code, 400)
        for boleto in (self.foreign_boleto, self.not_allowed_boleto):
            self.assertEqual(self.api.post(f'/api/v1/boletos/{boleto.pk}/associar/', {'installment':self.installment.pk}, format='json').status_code, 404)
        self.boleto.refresh_from_db()
        self.assertIsNone(self.boleto.installment_id)

    def test_boleto_correction_rejects_identity_and_audits_changes(self):
        self.assertEqual(self.api.patch(f'/api/v1/boletos/{self.boleto.pk}/', {'company':self.foreign_company.pk}, format='json').status_code, 400)
        self.assertEqual(self.api.patch(f'/api/v1/boletos/{self.foreign_boleto.pk}/', {'reference':'Teste'}, format='json').status_code, 404)
        response = self.api.patch(f'/api/v1/boletos/{self.boleto.pk}/', {'reference':'Revisão FICTÍCIA'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(BoletoEvent.objects.filter(boleto=self.boleto, action='revisado', source='api').exists())

    def test_rate_limits_before_hash_and_after_authentication(self):
        self.api.credentials(HTTP_AUTHORIZATION='Bearer invalid')
        for _ in range(30): self.assertEqual(self.api.get('/api/v1/notas/').status_code, 401)
        self.assertEqual(self.api.get('/api/v1/notas/').status_code, 429)
        cache.clear()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer '+self.token)
        from portal.api.throttling import IntegrationThrottle
        with patch.object(IntegrationThrottle, 'get_rate', return_value='1/min'):
            self.assertEqual(self.api.get('/api/v1/notas/').status_code, 200)
            self.assertEqual(self.api.get('/api/v1/notas/').status_code, 429)

    def test_pre_authentication_limit_prevents_hash_work(self):
        key = 'vindex-api-attempt:' + hashlib.sha256(b'127.0.0.1').hexdigest()
        cache.set(key, 180, 60)
        with patch.object(ApiCredential, 'verifies') as verify:
            self.assertEqual(self.api.get('/api/v1/notas/').status_code, 429)
            verify.assert_not_called()

    def test_unknown_route_and_invalid_json_are_standard_errors(self):
        response = self.api.get('/api/v1/inexistente/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'not_found')
        response = self.api.post('/api/v1/boletos/importar/', '{invalid JSON', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'validation_error')

    def test_unexpected_error_never_returns_traceback_or_document_payload(self):
        with patch('portal.api.views.import_invoice', side_effect=RuntimeError('SYNTHETIC-PAYLOAD-SECRET')):
            response = self.api.post('/api/v1/notas/importar/', {'file':SimpleUploadedFile('f.xml', sample_xml(self.company.cnpj))}, format='multipart')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['error']['code'], 'internal_error')
        self.assertNotIn('SYNTHETIC-PAYLOAD-SECRET', response.content.decode())
        self.assertNotIn('Traceback', response.content.decode())

    def test_openapi_validated_against_real_routes_and_no_private_fields(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        validate_schema(schema)
        expected = {'/api/v1/empresas/':{'get','post'}, '/api/v1/notas/importar/':{'post'},
                    '/api/v1/notas/{id}/xml/':{'get'}, '/api/v1/parcelas/':{'get','post'},
                    '/api/v1/parcelas/{id}/':{'get','patch'}, '/api/v1/parcelas/{id}/conferir/':{'post'},
                    '/api/v1/boletos/importar/':{'post'}, '/api/v1/boletos/{id}/associar/':{'post'},
                    '/api/v1/boletos/{id}/arquivo/':{'get'}, '/api/v1/certificados/':{'get'}}
        for path, methods in expected.items():
            self.assertTrue(methods.issubset(schema['paths'][path]))
            self.assertIsNotNone(resolve(path.replace('{id}', str(self.invoice.pk))))
        encoded = str(schema)
        for name in ('encrypted_file','encrypted_password','secret_hash','private_pdf','CERTIFICATE_ENCRYPTION_KEY'):
            self.assertNotIn(name, encoded)
        self.assertEqual(schema['components']['securitySchemes']['VindexIntegration']['scheme'], 'bearer')

    def test_documentation_assets_are_local_without_saved_authorization(self):
        response = self.api.get('/api/v1/docs/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/static/drf_spectacular_sidecar/')
        self.assertNotContains(response, 'cdn.jsdelivr.net')
        self.assertContains(response, '"persistAuthorization": false')
        self.assertEqual(self.api.get('/api/v1/redoc/').status_code, 200)

    def test_malformed_ordering_is_client_error(self):
        response=self.api.get('/api/v1/notas/?ordering=--issued_on')
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['error']['code'],'validation_error')

    def test_error_filter_redacts_redis_urls_and_database_settings(self):
        from portal.api.security import SecretRedactingFilter
        filter=SecretRedactingFilter()
        for key in ('CACHES','DATABASES'):
            value=filter.cleanse_setting(key,{'LOCATION':'redis://user:synthetic-secret@example.test:6379'})
            self.assertNotIn('synthetic-secret',str(value))

    def test_management_shows_secret_once_and_revocation_is_post_scoped(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('integration_create'), {'name':'Integração FICTÍCIA', 'scopes':['read'],
            'companies':[self.company.pk], 'expires_at':(timezone.localtime()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')})
        self.assertEqual(response.status_code, 200, response.content)
        token = response.context['token']
        self.assertContains(response, token)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        listing = self.client.get(reverse('integration_list'))
        self.assertNotContains(listing, token)
        credential = response.context['credential']
        self.assertEqual(self.client.get(reverse('integration_revoke', args=[credential.pk])).status_code, 405)
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.post(reverse('integration_revoke', args=[credential.pk])).status_code, 404)
        credential.refresh_from_db()
        self.assertIsNone(credential.revoked_at)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('integration_revoke', args=[credential.pk])).status_code, 302)
        self.api.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        self.assertEqual(self.api.get('/api/v1/notas/').status_code, 401)

    def test_management_cannot_select_foreign_company_and_requires_login(self):
        self.assertEqual(self.client.get(reverse('integration_list')).status_code, 302)
        self.client.force_login(self.user)
        before = ApiCredential.objects.count()
        response = self.client.post(reverse('integration_create'), {'name':'FICTÍCIA','scopes':['read'], 'companies':[self.foreign_company.pk],
            'expires_at':(timezone.localtime()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ApiCredential.objects.count(), before)
        self.assertNotIn('token', response.context)

    def test_management_create_and_revoke_require_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('integration_create'), {'name':'Sem CSRF'}).status_code, 403)
        self.assertEqual(client.post(reverse('integration_revoke', args=[self.credential.pk])).status_code, 403)
