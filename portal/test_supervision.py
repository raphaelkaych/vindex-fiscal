from unittest.mock import patch
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from portal.tests import create_account
from portal.models import Workspace, Invoice, MasterAudit
from portal.services.invoices import import_invoice
from portal.services.demo import sample_xml


class ClientPanelSupervisionTests(TestCase):
    def setUp(self):
        self.user,self.ws,self.company=create_account('panel-one@example.test')
        self.other,self.other_ws,self.other_company=create_account('panel-two@example.test','00000002000180')
        self.master=User.objects.create_user('supervisor@example.test',password='TestingSupervisor2026!')
        self.master.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))
        self.note,_=import_invoice(self.ws,sample_xml(self.company.cnpj))
        self.foreign,_=import_invoice(self.other_ws,sample_xml(self.other_company.cnpj))
        Invoice.objects.update(is_demo=False)
        self.client.force_login(self.master)

    def base(self,ws=None):
        return f'/gestao/clientes/{(ws or self.ws).pk}/painel/'

    def test_same_dashboard_data_and_scoped_navigation_without_impersonation(self):
        before=Workspace.objects.count()
        response=self.client.get(self.base())
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['workspace'],self.ws)
        self.assertEqual(response.context['request'].user.pk,self.master.pk)
        self.assertEqual(response.context['invoice_count'],1)
        self.assertContains(response,self.base()+'notas/')
        self.assertContains(response,'Supervisão em leitura')
        self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(Workspace.objects.count(),before)
        self.assertTrue(MasterAudit.objects.filter(actor=self.master,workspace=self.ws,action='client_panel_read').exists())
        self.client.force_login(self.user)
        own=self.client.get('/')
        self.assertEqual(own.context['invoice_total'],response.context['invoice_total'])
        self.assertEqual(own.context['upcoming_total'],response.context['upcoming_total'])

    def test_tabs_keep_independent_scope_and_do_not_change_next_request(self):
        for ws in [self.ws,self.other_ws,self.ws]:
            response=self.client.get(self.base(ws)+'notas/')
            self.assertEqual(response.context['current_workspace'],ws)
            self.assertContains(response,self.base(ws)+'agenda/')
        self.client.force_login(self.other)
        response=self.client.get('/')
        self.assertEqual(response.context['workspace'],self.other_ws)
        self.assertNotContains(response,'Supervisão em leitura')

    def test_scoped_lists_downloads_reports_and_company_filters(self):
        prefix=self.base()
        for suffix in ['empresas/','certificados/','notas/','agenda/','documentos/','boletos/','captura/','integracoes/','exportar/',f'empresas/{self.company.pk}/captura/',f'empresas/{self.company.pk}/conectores/']:
            with self.subTest(suffix=suffix):self.assertEqual(self.client.get(prefix+suffix).status_code,200)
        csv=self.client.get(prefix+'exportar/').content.decode('utf-8-sig')
        self.assertIn(self.company.formatted_cnpj,csv)
        self.assertNotIn(self.other_company.formatted_cnpj,csv)
        self.assertEqual(self.client.get(prefix+f'notas/{self.note.pk}/').status_code,200)
        self.assertEqual(self.client.get(prefix+f'notas/{self.note.pk}/xml/').status_code,200)
        self.assertEqual(self.client.get(prefix+f'notas/{self.foreign.pk}/xml/').status_code,404)
        self.assertEqual(self.client.get(prefix+f'notas/?company={self.other_company.pk}').status_code,404)

    def test_mutations_and_form_routes_are_blocked_before_view(self):
        for suffix in ['empresas/nova/','notas/importar/',f'empresas/{self.company.pk}/editar/',f'empresas/{self.company.pk}/certificado/','integracoes/nova/']:
            with self.subTest(suffix=suffix):self.assertEqual(self.client.get(self.base()+suffix).status_code,403)
        for suffix in ['',f'empresas/{self.company.pk}/captura/',f'empresas/{self.company.pk}/certificado/remover/',f'empresas/{self.company.pk}/conectores/']:
            with self.subTest(suffix=suffix):self.assertEqual(self.client.post(self.base()+suffix,{}).status_code,403)
        self.assertEqual(self.ws.companies.count(),1)

    def test_permission_is_required_on_every_request_and_not_from_session_or_query(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.base()).status_code,403)
        self.assertEqual(self.client.get('/?workspace='+str(self.other_ws.pk)).context['workspace'],self.ws)
        self.client.logout()
        self.assertEqual(self.client.get(self.base()).status_code,302)
        self.client.force_login(self.master)
        self.master.user_permissions.clear()
        self.assertEqual(self.client.get(self.base()).status_code,403)

    def test_preview_requires_existing_workspace(self):
        self.assertEqual(self.client.get('/gestao/clientes/999999/painel/').status_code,404)
