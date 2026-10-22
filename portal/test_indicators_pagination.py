from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs,urlsplit
from django.test import SimpleTestCase,TestCase,RequestFactory
from django.utils import timezone
from portal.pagination import paginate
from portal.tests import create_account
from portal.models import Company,FiscalDocument


class NavigationTests(SimpleTestCase):
    def test_distant_page_first_last_size_and_filters_survive(self):
        request=RequestFactory().get('/notas/',{'company':'4','q':'nota teste','from':'2026-01-01','per_page':'10','page':'8'})
        page=paginate(request,range(203));self.assertEqual(page.number,8)
        self.assertEqual([x['number'] for x in page.navigation_links],[6,7,8,9,10])
        query=parse_qs(urlsplit(page.last_url).query)
        self.assertEqual(query['page'],['21']);self.assertEqual(query['company'],['4']);self.assertEqual(query['q'],['nota teste'])
        self.assertEqual(query['per_page'],['10']);self.assertEqual(page.paginator.count,203)
    def test_independent_master_page_and_size_are_bounded(self):
        request=RequestFactory().get('/gestao/',{'page':'3','fiscal_page':'2','fiscal_per_page':'50'})
        page=paginate(request,range(120),25,'fiscal_page','fiscal_per_page')
        query=parse_qs(urlsplit(page.next_url).query)
        self.assertEqual(query['page'],['3']);self.assertEqual(query['fiscal_page'],['3'])
        invalid=paginate(RequestFactory().get('/',{'per_page':'99999999'}),range(120),25)
        self.assertEqual(invalid.paginator.per_page,25)


class AnalyticsTests(TestCase):
    def setUp(self):
        self.user,self.ws,self.company=create_account('analytic-own@example.test')
        self.other,self.foreign_ws,self.foreign=create_account('analytic-foreign@example.test','00000002000180')
        self.company2=Company.objects.create(workspace=self.ws,legal_name='INTERNA FICTICIA',cnpj='00000002000180')
        self.client.force_login(self.user)
    def doc(self,company,key,**extra):
        args=dict(service='nfse',environment='1',access_key=str(key).zfill(50),number=str(key),issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='tomador',issued_at=datetime.fromisoformat('2026-10-20T10:00:00-03:00'),total='100.00',xml_content='<TESTE_FICTICIO/>')
        args.update(extra);return FiscalDocument.objects.create(company=company,**args)
    def test_dedup_internal_roles_partial_cancellation_environment_and_tenant(self):
        self.doc(self.company,1,role='emitente');self.doc(self.company2,1)
        self.doc(self.company,2,validation_status='partial');self.doc(self.company,3,cancellation_reported=True)
        self.doc(self.company,4,cancellation_reported=True,substitution_reported=True)
        self.doc(self.foreign,5,total='9999.00');self.doc(self.company,6,environment='2',total='999.00')
        response=self.client.get('/indicadores/?from=2026-01-01&to=2026-12-31')
        self.assertEqual(response.status_code,200);self.assertEqual(response.context['record_count'],4)
        panel=response.context['panels'][0]
        self.assertEqual(panel['value'],Decimal('100.00'));self.assertEqual(panel['partial'],1)
        self.assertEqual(panel['cancelled'],2);self.assertEqual(panel['substituted'],1);self.assertEqual(panel['issued'],1)
        self.assertEqual(self.client.get(f'/indicadores/?company={self.foreign.pk}').status_code,404)
    def test_invalid_dates_and_unknown_type_are_not_silent_unfiltered_totals(self):
        self.assertEqual(self.client.get('/indicadores/?from=invalid').status_code,400)
        self.assertEqual(self.client.get('/indicadores/?type=unknown').status_code,404)
        self.assertEqual(self.client.get('/indicadores/?from=2026-12-31&to=2026-01-01').status_code,400)
