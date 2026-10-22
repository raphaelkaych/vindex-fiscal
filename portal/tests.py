from datetime import timedelta
from decimal import Decimal
from io import StringIO
from urllib.parse import urlencode
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID,ObjectIdentifier
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,Client,override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Workspace,Company,Invoice,Installment,DigitalCertificate
from .forms import CompanyForm
from .validators import validate_cnpj
from .services.invoices import parse_nfe,import_invoice,InvoiceImportError
from .services.certificates import save_certificate,CertificateError,cipher
from .services.demo import sample_xml,load_demo,DEMO_COMPANIES
from .views import csv_safe

TEST_PASSWORD='UmaSenhaDeTeste!78542'

def create_account(email,cnpj=DEMO_COMPANIES[0][2]):
    user=User.objects.create_user(username=email,email=email,password=TEST_PASSWORD,first_name='Raphael')
    workspace=Workspace.objects.create(owner=user,name='Grupo de teste')
    company=Company.objects.create(workspace=workspace,legal_name='Empresa de teste',cnpj=cnpj)
    return user,workspace,company

def fake_pfx(cnpj,password='SenhaTeste123!',expired=False,include_cnpj=True):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CERTIFICADO FICTICIO - SEM VALOR FISCAL')])
    now=timezone.now()
    builder=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=40)).not_valid_after(now+timedelta(days=-1 if expired else 100))
    if include_cnpj:
        encoded=cnpj.encode('ascii')
        builder=builder.add_extension(x509.SubjectAlternativeName([x509.OtherName(ObjectIdentifier('2.16.76.1.3.3'),b'\x0c'+bytes([len(encoded)])+encoded)]),critical=False)
    cert=builder.sign(key,hashes.SHA256())
    return pkcs12.serialize_key_and_certificates(b'exemplo',key,cert,None,serialization.BestAvailableEncryption(password.encode()))

class XMLTests(TestCase):
    def setUp(self):
        self.user,self.workspace,self.company=create_account('xml@example.test')
        self.xml=sample_xml(self.company.cnpj,total='103148.10')
    def test_parcelas_valores_exatos(self):
        note,created=import_invoice(self.workspace,self.xml)
        self.assertTrue(created)
        self.assertEqual(note.total,Decimal('103148.10'))
        self.assertEqual(list(note.installments.values_list('amount',flat=True)),[Decimal('51574.05')]*2)
        self.assertFalse(note.review_notes)
    def test_reimportar_nao_duplica(self):
        import_invoice(self.workspace,self.xml)
        note,created=import_invoice(self.workspace,self.xml)
        self.assertFalse(created)
        self.assertEqual(Invoice.objects.count(),1)
        self.assertEqual(Installment.objects.count(),2)
    def test_cnpj_terceiro_nao_e_importado(self):
        with self.assertRaises(InvoiceImportError):
            import_invoice(self.workspace,sample_xml(DEMO_COMPANIES[1][2]))
        self.assertFalse(Invoice.objects.exists())
    def test_sem_parcelas_nao_inventa_vencimento(self):
        note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj,due_dates=[]))
        self.assertTrue(note.needs_review)
        self.assertEqual(note.installments.count(),0)
    def test_parcela_sem_data_e_sinalizada(self):
        note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj,due_dates=[None]))
        self.assertTrue(note.needs_review)
        self.assertIsNone(note.installments.get().due_on)
    def test_entidade_externa_bloqueada(self):
        payload=b'<!DOCTYPE x [<!ENTITY evil SYSTEM "file:///etc/passwd">]><x>&evil;</x>'
        with self.assertRaises(InvoiceImportError): parse_nfe(payload)
    def test_html_e_pdf_rejeitados(self):
        for payload in [b'<html>nota</html>',b'%PDF-1.4 nao e XML']:
            with self.subTest(payload=payload):
                with self.assertRaises(InvoiceImportError): parse_nfe(payload)
    def test_valor_nao_finito_rejeitado(self):
        with self.assertRaises(InvoiceImportError): parse_nfe(self.xml.replace(b'<vNF>103148.10</vNF>',b'<vNF>NaN</vNF>'))
    def test_nota_de_devolucao_nao_gera_despesa(self):
        note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj,purpose='4'))
        self.assertTrue(note.needs_review)
        self.assertFalse(note.installments.exists())
    def test_protocolo_com_outra_chave_rejeitado(self):
        payload=self.xml.replace(b'<chNFe>',b'<chNFe>9',1)
        with self.assertRaises(InvoiceImportError): parse_nfe(payload)
    def test_soma_divergente_sinalizada(self):
        payload=self.xml.replace(b'<vDup>51574.05</vDup>',b'<vDup>50000.00</vDup>',1)
        note,_=import_invoice(self.workspace,payload)
        self.assertTrue(note.needs_review)
    def test_demo_idempotente(self):
        load_demo(self.workspace)
        first=Invoice.objects.count()
        load_demo(self.workspace)
        self.assertEqual(Invoice.objects.count(),first)
        self.assertEqual(first,4)
        self.assertEqual(Invoice.objects.filter(is_demo=True).count(),4)

class AccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user,self.workspace,self.company=create_account('owner@example.test')
        self.other,self.other_workspace,self.other_company=create_account('other@example.test',DEMO_COMPANIES[1][2])
        self.note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj))
        self.other_note,_=import_invoice(self.other_workspace,sample_xml(self.other_company.cnpj,number='99999'))
        self.client.force_login(self.user)
    def test_paginas_do_proprietario_renderizam(self):
        targets=['dashboard','companies','company_create','certificates','invoices','import_xml','agenda','profile','password_change']
        for target in targets:
            with self.subTest(target=target): self.assertEqual(self.client.get(reverse(target)).status_code,200)
        for target in ['company_edit','certificate_upload']:
            self.assertEqual(self.client.get(reverse(target,args=[self.company.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('invoice_detail',args=[self.note.pk])).status_code,200)
    def test_cliente_nao_acessa_nota_xml_ou_empresa_do_outro(self):
        for target,key in [('invoice_detail',self.other_note.pk),('xml_download',self.other_note.pk),('company_edit',self.other_company.pk),('certificate_upload',self.other_company.pk)]:
            with self.subTest(target=target): self.assertEqual(self.client.get(reverse(target,args=[key])).status_code,404)
    def test_filtro_nao_permite_empresa_alheia(self):
        for target in ['dashboard','invoices','agenda','export_csv']:
            with self.subTest(target=target): self.assertEqual(self.client.get(reverse(target),{'company':self.other_company.pk}).status_code,404)
    def test_painel_e_exportacao_nao_vazam_notas(self):
        for target in ['dashboard','invoices','agenda','export_csv']:
            response=self.client.get(reverse(target))
            self.assertNotContains(response,'99999')
            self.assertNotContains(response,self.other_company.cnpj)
    def test_nao_consegue_alterar_parcela_alheia(self):
        item=self.other_note.installments.first()
        self.assertEqual(self.client.post(reverse('installment_check',args=[item.pk])).status_code,404)
        item.refresh_from_db();self.assertFalse(item.checked)
    def test_conferencia_nao_altera_valor_ou_cria_pagamento(self):
        item=self.note.installments.first()
        self.client.post(reverse('installment_check',args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.checked)
        self.assertEqual(item.amount,Decimal('600.00'))
    def test_download_xml_privado(self):
        response=self.client.get(reverse('xml_download',args=[self.note.pk]))
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response['Content-Disposition'])
        self.client.logout()
        self.assertEqual(self.client.get(reverse('xml_download',args=[self.note.pk])).status_code,302)
    def test_cnpj_com_mascara_e_aceito(self):
        form=CompanyForm(data={'legal_name':'Filial de teste','trade_name':'','cnpj':'00.000.002/0001-80'},workspace=self.workspace)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['cnpj'],DEMO_COMPANIES[1][2])
    def test_cnpj_duplicado_no_cliente_rejeitado(self):
        form=CompanyForm(data={'legal_name':'Duplicada','trade_name':'','cnpj':self.company.cnpj},workspace=self.workspace)
        self.assertFalse(form.is_valid())
    def test_importacao_multipla_real_via_http(self):
        xml=SimpleUploadedFile('nota.xml',sample_xml(self.company.cnpj,number='5555'),content_type='application/xml')
        response=self.client.post(reverse('import_xml'),{'files':xml})
        self.assertEqual(response.status_code,302)
        self.assertTrue(Invoice.objects.filter(number='5555',company=self.company).exists())
    def test_exportacao_agenda_com_data(self):
        response=self.client.get(reverse('export_csv'),{'kind':'agenda','from':str(timezone.localdate()),'state':'upcoming'})
        self.assertEqual(response.status_code,200)
        self.assertIn('Valor previsto',response.content.decode('utf-8-sig'))
    def test_filtro_data_invalida_nao_causa_erro_interno(self):
        self.assertEqual(self.client.get(reverse('agenda'),{'from':'texto'}).status_code,400)
    def test_csrf_obrigatorio(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('demo')).status_code,403)
    def test_acoes_de_escrita_nao_aceitam_get(self):
        self.assertEqual(self.client.get(reverse('demo')).status_code,405)
        self.assertEqual(self.client.get(reverse('certificate_delete',args=[self.company.pk])).status_code,405)
    def test_cadastro_separa_workspace(self):
        self.client.logout()
        response=self.client.post(reverse('register'),{'full_name':'Nova pessoa','email':'NEW@example.test','workspace_name':'Novo grupo','password1':TEST_PASSWORD,'password2':TEST_PASSWORD})
        self.assertEqual(response.status_code,302)
        user=User.objects.get(username='new@example.test')
        self.assertEqual(user.workspace.name,'Novo grupo')
        self.assertEqual(user.workspace.companies.count(),0)
    def test_login_email_normalizado(self):
        self.client.logout()
        response=self.client.post(reverse('login'),{'username':'OWNER@example.test','password':TEST_PASSWORD})
        self.assertEqual(response.status_code,302)
    def test_telas_apos_demo_renderizam(self):
        self.client.post(reverse('demo'))
        for name in ['dashboard','companies','certificates','invoices','agenda']:
            with self.subTest(name=name): self.assertEqual(self.client.get(reverse(name)).status_code,200)
    def test_csv_nao_injeta_formulas(self):
        for value in ['=SUM(1,2)','+cmd','-123','@SUM(1)','   =A1']:
            self.assertTrue(csv_safe(value).startswith("'"))

class CertificateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.workspace,cls.company=create_account('cert@example.test')
        cls.pfx=fake_pfx(cls.company.cnpj)
    def setUp(self): self.client.force_login(self.user)
    def test_arquivo_e_senha_sao_cifrados(self):
        cert=save_certificate(self.company,self.pfx,'SenhaTeste123!')
        self.assertNotEqual(bytes(cert.encrypted_file),self.pfx)
        self.assertNotIn(b'SenhaTeste123!',bytes(cert.encrypted_password))
        self.assertEqual(cipher().decrypt(bytes(cert.encrypted_file)),self.pfx)
        self.assertEqual(cipher().decrypt(bytes(cert.encrypted_password)),b'SenhaTeste123!')
        self.assertEqual(cert.holder_cnpj,self.company.cnpj)
    def test_senha_errada_rejeitada(self):
        with self.assertRaises(CertificateError): save_certificate(self.company,self.pfx,'errada')
        self.assertFalse(DigitalCertificate.objects.exists())
    def test_cnpj_incompativel_rejeitado(self):
        other=Company.objects.create(workspace=self.workspace,legal_name='Outra',cnpj=DEMO_COMPANIES[1][2])
        with self.assertRaises(CertificateError): save_certificate(other,self.pfx,'SenhaTeste123!')
    def test_certificado_vencido_rejeitado(self):
        with self.assertRaises(CertificateError): save_certificate(self.company,fake_pfx(self.company.cnpj,expired=True),'SenhaTeste123!')
    def test_sem_cnpj_rejeitado(self):
        with self.assertRaises(CertificateError): save_certificate(self.company,fake_pfx(self.company.cnpj,include_cnpj=False),'SenhaTeste123!')
    def test_remover_preserva_notas(self):
        save_certificate(self.company,self.pfx,'SenhaTeste123!')
        note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj))
        self.client.post(reverse('certificate_delete',args=[self.company.pk]))
        self.assertFalse(DigitalCertificate.objects.exists())
        self.assertTrue(Invoice.objects.filter(pk=note.pk).exists())
    def test_upload_via_http_e_renovacao(self):
        for attempt in range(2):
            response=self.client.post(reverse('certificate_upload',args=[self.company.pk]),{'file':SimpleUploadedFile('teste.pfx',self.pfx),'password':'SenhaTeste123!','authorized':'on'})
            self.assertEqual(response.status_code,302)
        self.assertEqual(DigitalCertificate.objects.filter(company=self.company).count(),1)
    def test_senha_nao_reaparece_no_html_de_erro(self):
        password='SenhaQueNaoPodeAparecer777'
        response=self.client.post(reverse('certificate_upload',args=[self.company.pk]),{'file':SimpleUploadedFile('teste.pfx',self.pfx),'password':password,'authorized':'on'})
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,password)
