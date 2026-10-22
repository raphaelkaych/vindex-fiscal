from io import StringIO
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.contrib.auth.models import Permission,User
from django.core.management import call_command
from django.core.management.base import CommandError
from portal.tests import create_account
from portal.models import MasterAudit,Workspace


class MasterTests(TestCase):
    @patch('portal.services.nfse_pdf.generate_nfse_pdf',return_value=b'%PDF-TEST')
    def test_nfse_supervision_dates_and_pdf_follow_explicit_client(self,generate):
        from portal.models import FiscalDocument
        from django.utils import timezone
        args=dict(service='nfse',environment='1',access_key='1'*50,number='FICTICIA',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='tomador',issued_at=timezone.now(),total='123.45',xml_content='<TESTE/>')
        own=FiscalDocument.objects.create(company=self.company,**args)
        foreign=FiscalDocument.objects.create(company=self.other_company,**args)
        self.client.force_login(self.master)
        overview=self.client.get(f'/gestao/clientes/{self.ws.pk}/')
        self.assertEqual(overview.context['fiscal_counts'][0]['total'],1)
        self.assertEqual(overview.context['fiscal_counts'][0]['company__cnpj'],self.company.cnpj)
        filtered=self.client.get(f'/gestao/clientes/{self.ws.pk}/?fiscal_type=cte')
        self.assertEqual(filtered.context['fiscal_documents'].paginator.count,0)
        self.assertEqual(self.client.get(f'/gestao/clientes/{self.ws.pk}/?company={self.other_company.pk}').status_code,404)
        url=f'/gestao/clientes/{self.ws.pk}/documentos/nfse/{own.pk}/?format=pdf'
        self.assertEqual(self.client.get(url).status_code,200)
        generate.reset_mock()
        self.assertEqual(self.client.get(f'/gestao/clientes/{self.other_ws.pk}/documentos/nfse/{own.pk}/?format=pdf').status_code,404)
        generate.assert_not_called()

    def test_supervised_document_requires_matching_workspace_in_every_tab(self):
        from portal.models import Invoice
        from portal.services.invoices import import_invoice
        from portal.services.demo import sample_xml
        own,_=import_invoice(self.ws,sample_xml(self.company.cnpj))
        self.client.force_login(self.master)
        url=f'/gestao/clientes/{self.ws.pk}/documentos/nfe/{own.pk}/'
        self.assertContains(self.client.get(url),'Supervisão em leitura')
        self.assertEqual(self.client.get(url+'?format=xml').status_code,200)
        self.assertEqual(self.client.get(f'/gestao/clientes/{self.other_ws.pk}/documentos/nfe/{own.pk}/').status_code,404)
    def test_operational_action_requires_csrf(self):
        from django.test import Client
        self.master.user_permissions.add(Permission.objects.get(codename='operate_clients',content_type__app_label='portal'))
        client=Client(enforce_csrf_checks=True);client.force_login(self.master)
        self.assertEqual(client.post(f'/gestao/clientes/{self.ws.pk}/acao/',{'action':'pause_capture'}).status_code,403)
        self.ws.refresh_from_db();self.assertFalse(self.ws.capture_paused)

    @override_settings(REGISTRATION_MODE='approval')
    def test_registration_cannot_grant_master_and_requires_approval(self):
        result=self.client.post('/criar-conta/',{'full_name':'Teste','email':'pending@example.test','workspace_name':'Pendente','password1':'UniqueStrongAccount2026!','password2':'UniqueStrongAccount2026!','is_superuser':'1','is_staff':'1'})
        self.assertEqual(result.status_code,302)
        user=User.objects.get(username='pending@example.test')
        self.assertFalse(user.is_staff);self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_perm('portal.admin_master'))
        self.assertEqual(user.workspace.access_status,'pending');self.assertEqual(self.client.get('/').status_code,403)
    def setUp(self):
        self.user,self.ws,self.company=create_account('cliente-master-test@example.test')
        self.other,self.other_ws,self.other_company=create_account('outro-master-test@example.test')
        self.master=User.objects.create_user('master@example.test',password='TestingMasterStrong2026!')
        self.master.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))

    def test_common_user_cannot_manage_or_choose_client(self):
        self.client.force_login(self.user)
        for url in ['/gestao/',f'/gestao/clientes/{self.other_ws.pk}/',f'/gestao/clientes/{self.other_ws.pk}/acao/']:
            self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.get(f'/empresas/{self.other_company.pk}/editar/').status_code,404)

    def test_master_client_context_is_url_bound_and_read_only(self):
        self.client.force_login(self.master)
        for ws in [self.ws,self.other_ws,self.ws]:
            response=self.client.get(f'/gestao/clientes/{ws.pk}/')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.context['supervised_workspace'].pk,ws.pk)
        self.assertEqual(self.client.post(f'/gestao/clientes/{self.ws.pk}/').status_code,405)
        self.assertEqual(MasterAudit.objects.filter(action='supervision_read').count(),3)
        self.assertEqual(self.client.post(f'/gestao/clientes/{self.ws.pk}/acao/',{'action':'suspended'}).status_code,403)

    def test_explicit_operation_is_audited_and_does_not_pause_capture_implicitly(self):
        self.master.user_permissions.add(Permission.objects.get(codename='operate_clients',content_type__app_label='portal'))
        self.client.force_login(self.master)
        self.client.post(f'/gestao/clientes/{self.ws.pk}/acao/',{'action':'suspended'})
        self.ws.refresh_from_db();self.assertEqual(self.ws.access_status,'suspended');self.assertFalse(self.ws.capture_paused)
        self.assertTrue(MasterAudit.objects.filter(actor=self.master,workspace=self.ws,action='suspended').exists())

    def test_suspended_web_is_blocked_and_existing_accounts_remain_active(self):
        self.assertEqual(self.ws.access_status,'active')
        self.ws.access_status='suspended';self.ws.save();self.client.force_login(self.user)
        self.assertEqual(self.client.get('/notas/').status_code,403)

    def test_command_has_hidden_password_and_no_default_privilege(self):
        self.assertFalse(self.user.has_perm('portal.admin_master'))
        with patch('builtins.input',return_value='novo-master@example.test'),patch('portal.management.commands.criar_admin_master.getpass',side_effect=['StrongUniqueMaster!2026','StrongUniqueMaster!2026']):
            call_command('criar_admin_master',stdout=StringIO())
        user=User.objects.get(username='novo-master@example.test')
        self.assertTrue(user.check_password('StrongUniqueMaster!2026'))
        self.assertTrue(user.has_perm('portal.admin_master'));self.assertFalse(user.is_superuser)

    def test_existing_account_requires_explicit_grant(self):
        with patch('builtins.input',side_effect=[self.user.username,'NAO']):
            with self.assertRaises(CommandError):call_command('criar_admin_master',stdout=StringIO())
        self.assertFalse(User.objects.get(pk=self.user.pk).has_perm('portal.admin_master'))

    @override_settings(REGISTRATION_MODE='closed')
    def test_closed_registration_denies_public_creation(self):
        self.assertEqual(self.client.post('/criar-conta/',{'is_superuser':'1'}).status_code,403)
