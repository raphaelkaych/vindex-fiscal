"""Verificações da interface renderizada. Dados estritamente fictícios."""
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from portal.tests import create_account
from portal.services.demo import sample_xml
from portal.services.invoices import import_invoice


class InterfaceRefinementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.workspace,cls.company=create_account('visual-test@example.test')
        cls.other,cls.other_workspace,cls.other_company=create_account('visual-other@example.test')
        cls.note,_=import_invoice(cls.workspace,sample_xml(cls.company.cnpj))
        cls.foreign,_=import_invoice(cls.other_workspace,sample_xml(cls.other_company.cnpj,number='99999'))

    def setUp(self): self.client.force_login(self.user)

    def test_pages_share_theme_status_and_navigation_controls(self):
        pages=[reverse(name) for name in ['dashboard','companies','company_create','certificates','invoices','import_xml','agenda','profile','password_change','boletos','boleto_import','integration_list','integration_create']]
        pages.extend([reverse('invoice_detail',args=[self.note.pk]),reverse('certificate_upload',args=[self.company.pk]),reverse('installment_create',args=[self.note.pk])])
        for url in pages:
            with self.subTest(url=url):
                response=self.client.get(url)
                self.assertEqual(response.status_code,200)
                for text in ['portal/refinement.css','data-theme-toggle','data-action-status','data-menu-backdrop','data-mobile-close']:
                    self.assertContains(response,text)
                self.assertContains(response,'data-theme-toggle',count=1)
                self.assertNotContains(response,'theme-select-label')
                html=response.content.decode()
                self.assertLess(html.index('portal/theme.js'),html.index('portal/app.css'))

    def test_navigation_identifies_one_active_location(self):
        for name,args in [('dashboard',[]),('companies',[]),('invoices',[]),('agenda',[]),('boletos',[]),('integration_list',[]),('certificates',[]),('profile',[]),('import_xml',[]),('installment_create',[self.note.pk])]:
            with self.subTest(name=name):
                response=self.client.get(reverse(name,args=args))
                sidebar=response.content.decode().split('<aside',1)[1].split('</aside>',1)[0]
                self.assertEqual(sidebar.count('aria-current="page"'),1)

    def test_invalid_form_keeps_non_sensitive_values(self):
        before=self.workspace.companies.count()
        response=self.client.post(reverse('company_create'),{'legal_name':'EMPRESA FICTÍCIA PARA REVISÃO','trade_name':'Exemplo visual','cnpj':'000'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'value="EMPRESA FICTÍCIA PARA REVISÃO"')
        self.assertContains(response,'value="Exemplo visual"')
        self.assertContains(response,'errorlist')
        self.assertEqual(self.workspace.companies.count(),before)

    def test_certificate_error_does_not_keep_password(self):
        secret='SENHA-FICTICIA-NAO-RENDERIZAR'
        response=self.client.post(reverse('certificate_upload',args=[self.company.pk]),{'password':secret,'authorized':'on','file':SimpleUploadedFile('invalido.txt',b'FICTICIO')})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'errorlist')
        self.assertNotContains(response,secret)
        self.assertTrue(response.context['form']['authorized'].value())

    def test_copy_control_does_not_change_document_scope(self):
        response=self.client.get(reverse('invoice_detail',args=[self.note.pk]))
        self.assertContains(response,'data-copy-target="invoice-key"')
        self.assertContains(response,self.note.access_key)
        self.assertNotContains(response,self.foreign.access_key)
        self.assertEqual(self.client.get(reverse('invoice_detail',args=[self.foreign.pk])).status_code,404)

    def test_anonymous_access_screens_have_theme_controls(self):
        self.client.logout()
        for name in ['login','register']:
            response=self.client.get(reverse(name))
            self.assertContains(response,'data-theme-toggle',count=1)
            self.assertNotContains(response,'theme-select-label')
            self.assertContains(response,'portal/refinement.css')
            self.assertContains(response,'data-action-status')
