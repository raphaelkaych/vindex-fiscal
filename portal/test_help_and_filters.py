from urllib.parse import parse_qs
from django.contrib.auth.models import Permission
from django.test import TestCase
from portal.tests import create_account


class HelpAndFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.ws,cls.company=create_account('help-owner@example.test')
        cls.other,cls.other_ws,cls.other_company=create_account('help-other@example.test')
    def setUp(self):self.client.force_login(self.user)
    def test_tutorial_requires_login_and_does_not_offer_management_to_regular_users(self):
        response=self.client.get('/tutorial/')
        self.assertEqual(response.status_code,200);self.assertIn('no-store',response['Cache-Control'])
        for anchor in ['primeiros-passos','captura','documentos','pesquisa','indicadores','financeiro','integracoes','conta','duvidas']:
            self.assertContains(response,f'id="{anchor}"')
        self.assertNotContains(response,'id="gestao"')
        self.assertContains(response,'nem confirma operações comerciais automaticamente')
        self.client.logout();self.assertEqual(self.client.get('/tutorial/').status_code,302)
    def test_master_tutorial_and_supervision_keep_the_url_scope(self):
        self.user.user_permissions.add(Permission.objects.get(codename='admin_master'))
        self.assertContains(self.client.get('/tutorial/'),'id="gestao"')
        url=f'/gestao/clientes/{self.other_ws.pk}/painel/tutorial/'
        response=self.client.get(url)
        self.assertContains(response,f'/gestao/clientes/{self.other_ws.pk}/painel/documentos/')
        self.assertNotContains(response,f'/gestao/clientes/{self.other_ws.pk}/painel/notas/importar/')
        self.assertEqual(self.client.post(url).status_code,403)
    def test_tutorial_has_no_write_method(self):
        self.assertEqual(self.client.post('/tutorial/').status_code,405)
    def test_search_refinements_start_collapsed_and_open_when_used_or_invalid(self):
        response=self.client.get('/documentos/')
        self.assertFalse(response.context['advanced_open'])
        response=self.client.get('/documentos/',{'ncm':'23091000'})
        self.assertTrue(response.context['advanced_open']);self.assertContains(response,'Mais filtros')
        response=self.client.get('/documentos/',{'minimum':'invalid'})
        self.assertTrue(response.context['advanced_open']);self.assertContains(response,'Confira os campos destacados')
        self.assertNotContains(response,'Exportar estes resultados')
    def test_filter_chips_remove_one_filter_and_preserve_the_others(self):
        response=self.client.get('/documentos/',{'company':self.company.pk,'product':'ração','start':'2026-10-01','page':'4'})
        chips=response.context['filter_chips']
        company=next(c for c in chips if c['name']=='Empresa')
        query=parse_qs(company['query'])
        self.assertNotIn('company',query);self.assertNotIn('page',query)
        self.assertEqual(query['product'],['ração']);self.assertEqual(query['start'],['2026-10-01'])
        self.assertContains(response,'Exportar estes resultados')
    def test_reflected_filter_text_is_escaped(self):
        response=self.client.get('/documentos/',{'product':'<script>alert(1)</script>'})
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'&lt;script&gt;')
    def test_indicator_shortcuts_preserve_valid_scope_and_drop_unrelated_query_fields(self):
        response=self.client.get('/indicadores/',{'company':self.company.pk,'type':'nfse','environment':'2','unrelated':'ignored'})
        self.assertEqual(len(response.context['period_presets']),3)
        for preset in response.context['period_presets']:
            query=parse_qs(preset['query'])
            self.assertEqual(query['company'],[str(self.company.pk)]);self.assertEqual(query['type'],['nfse']);self.assertEqual(query['environment'],['2'])
            self.assertIn('from',query);self.assertIn('to',query);self.assertNotIn('unrelated',query)
            self.assertEqual(self.client.get('/indicadores/?'+preset['query']).status_code,200)
        self.assertEqual(self.client.get('/indicadores/',{'company':self.other_company.pk}).status_code,404)
