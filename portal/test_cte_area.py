"""CT-e inteiramente sintéticos. Nenhuma consulta real é executada."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase,SimpleTestCase
from django.contrib.auth.models import Permission
from django.utils import timezone
from pypdf import PdfReader
from portal.tests import create_account
from portal.models import FiscalDocument,MasterAudit
from portal.services.cte_presentation import read_cte,qr_url,party_rows,references
from portal.services.dacte import generate_dacte
from portal.services.sefaz import SefazError
from tools.check_dacte_pdf import synthetic_cte_xml,KEY


def document_sample(**kwargs):
    args=dict(service='cte',environment='2',validation_status='schema',access_key=KEY,cancellation_reported=False,xml_content=synthetic_cte_xml())
    args.update(kwargs)
    return SimpleNamespace(**args)


class CteAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.ws,cls.company=create_account('cte-area@example.test')
        cls.other,cls.other_ws,cls.other_company=create_account('cte-foreign@example.test')
        args=dict(service='cte',environment='1',access_key=KEY,number='CTE-123',issuer_name='TRANSPORTADOR FICTICIO',issuer_cnpj=cls.company.cnpj,role='dest',issued_at=timezone.now(),total='123.45',xml_content=synthetic_cte_xml(environment='1',references=40))
        cls.doc=FiscalDocument.objects.create(company=cls.company,**args)
        cls.foreign=FiscalDocument.objects.create(company=cls.other_company,**args)
        cls.nfse=FiscalDocument.objects.create(company=cls.company,**dict(args,service='nfse',access_key='1'*50,number='NFSE-ISOLADA'))
        cls.homolog=FiscalDocument.objects.create(company=cls.company,**dict(args,environment='2',number='HOMOLOG-CTE',xml_content=synthetic_cte_xml()))
    def setUp(self):self.client.force_login(self.user)

    def test_list_defaults_to_production_and_current_workspace(self):
        response=self.client.get('/cte/')
        self.assertEqual(response.status_code,200)
        self.assertEqual([d.pk for d in response.context['page']],[self.doc.pk])
        self.assertEqual(response.context['counts']['validated'],1)
        self.assertNotContains(response,'NFSE-ISOLADA')
        self.assertNotContains(response,'HOMOLOG-CTE')
        self.assertContains(response,'DACTE (PDF)')
        self.assertIn('no-store',response['Cache-Control'])

    def test_filters_dates_company_pagination_and_cancelled(self):
        self.doc.cancellation_reported=True;self.doc.save(update_fields=['cancellation_reported'])
        response=self.client.get('/cte/?q=CTE-123&status=cancelled&per_page=10')
        self.assertEqual(response.context['counts']['cancelled'],1)
        self.assertEqual(response.context['page'].paginator.per_page,10)
        self.assertEqual(self.client.get('/cte/?q=inexistente').context['counts']['total'],0)
        self.assertEqual(self.client.get('/cte/?environment=2').context['counts']['total'],1)
        self.assertEqual(self.client.get('/cte/?environment=').context['counts']['total'],2)
        self.assertEqual(self.client.get('/cte/?start=2099-01-01').context['counts']['total'],0)
        for query in [f'company={self.other_company.pk}','start=2026-12-01&end=2026-01-01','environment=3','status=unknown']:
            response=self.client.get('/cte/?'+query)
            self.assertEqual(response.context['counts']['total'],0)
            self.assertTrue(response.context['form'].errors)

    def test_detail_parties_values_and_paged_references(self):
        response=self.client.get(f'/cte/{self.doc.pk}/?references_page=2&references_per_page=10')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['references'].paginator.count,40)
        self.assertEqual(response.context['references'].number,2)
        self.assertContains(response,'Carga transportada')
        self.assertContains(response,'Tomador do serviço')
        self.assertContains(response,'Valor a receber declarado')
        self.assertContains(response,'Destinatário')

    @patch('portal.services.dacte.generate_dacte',return_value=b'%PDF-SYNTHETIC')
    def test_typed_downloads_deny_foreign_workspace_and_other_types(self,generate):
        for doc in [self.foreign,self.nfse]:
            for suffix in ['', 'xml/', 'pdf/']:
                self.assertEqual(self.client.get(f'/cte/{doc.pk}/'+suffix).status_code,404)
        generate.assert_not_called()
        self.assertEqual(self.client.get(f'/cte/{self.doc.pk}/xml/').content,self.doc.xml_content.encode())
        response=self.client.get(f'/cte/{self.doc.pk}/pdf/')
        self.assertEqual(response.status_code,200)
        self.assertIn('dacte-',response['Content-Disposition'])
        self.assertIn('no-store',response['Cache-Control'])

    @patch('portal.services.dacte.generate_dacte',side_effect=SefazError('XML incompleto; original preservado.'))
    def test_pdf_error_keeps_xml_and_returns_message(self,generate):
        response=self.client.get(f'/cte/{self.doc.pk}/pdf/',follow=True)
        self.assertContains(response,'XML incompleto; original preservado.')
        self.assertContains(response,'Baixar XML original')
        self.doc.refresh_from_db();self.assertTrue(self.doc.xml_content)

    def test_master_scoping_read_only_and_audit(self):
        self.user.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))
        prefix=f'/gestao/clientes/{self.other_ws.pk}/painel'
        response=self.client.get(prefix+'/cte/')
        self.assertEqual(response.context['page'][0].pk,self.foreign.pk)
        self.assertContains(response,prefix+f'/cte/{self.foreign.pk}/pdf/')
        self.assertEqual(self.client.get(prefix+f'/cte/{self.doc.pk}/xml/').status_code,404)
        self.assertEqual(self.client.post(prefix+f'/cte/{self.foreign.pk}/pdf/').status_code,403)
        self.assertTrue(MasterAudit.objects.filter(actor=self.user,workspace=self.other_ws,action='client_panel_read').exists())


class DactePdfTests(SimpleTestCase):
    def test_all_complemented_keys_are_listed(self):
        from lxml import etree
        root,info=read_cte(document_sample())
        namespace='{http://www.portalfiscal.inf.br/cte}'
        for index in range(3):
            item=etree.SubElement(info,namespace+'infCteComp')
            etree.SubElement(item,namespace+'chCTe').text=str(index)*44
        self.assertEqual([item['key'] for item in references(info)],['0'*44,'1'*44,'2'*44])

    @patch('portal.services.cte_presentation.validate_xml')
    def test_pdf_values_key_barcodes_homologation_and_original(self,validate):
        doc=document_sample();original=doc.xml_content
        data=generate_dacte(doc);pdf=PdfReader(BytesIO(data))
        text='\n'.join(page.extract_text() for page in pdf.pages)
        self.assertIn('DACTE',text)
        self.assertIn('123,45',text)
        self.assertIn(KEY,text.replace(' ',''))
        self.assertIn('SEM VALOR FISCAL',text)
        self.assertEqual(doc.xml_content,original)
        self.assertGreaterEqual(len(pdf.pages[0].images),1)
        validate.assert_called_once()

    @patch('portal.services.cte_presentation.validate_xml')
    def test_cancelled_pdf_is_marked(self,validate):
        pdf=PdfReader(BytesIO(generate_dacte(document_sample(cancellation_reported=True,xml_content=synthetic_cte_xml(references=120)))))
        self.assertGreater(len(pdf.pages),1)
        for page in pdf.pages:self.assertIn('CANCELADA',page.extract_text())

    @patch('portal.services.cte_presentation.validate_xml')
    def test_many_references_keep_last_key_in_pdf(self,validate):
        doc=document_sample(xml_content=synthetic_cte_xml(references=120))
        pdf=PdfReader(BytesIO(generate_dacte(doc)))
        text=''.join(page.extract_text() for page in pdf.pages).replace(' ','')
        self.assertIn('35'+f'{119:042d}',text)
        self.assertGreater(len(pdf.pages),1)

    @patch('portal.services.cte_presentation.validate_xml')
    def test_inconsistent_identity_environment_protocol_and_partial_are_rejected(self,validate):
        for changes in [dict(service='nfse'),dict(access_key='1'*44),dict(environment='1'),dict(validation_status='partial'),
                        dict(xml_content=synthetic_cte_xml().replace('<ns0:cStat>100</ns0:cStat>','<ns0:cStat>999</ns0:cStat>'))]:
            with self.subTest(changes=list(changes)):
                with self.assertRaises(SefazError):generate_dacte(document_sample(**changes))

    @patch('portal.services.cte_presentation.validate_xml')
    def test_missing_or_foreign_qr_is_not_printed_as_authentic(self,validate):
        from lxml import etree
        for qr in ['', 'https://example.test/?chCTe='+KEY+'&tpAmb=2', 'https://dfe-portal.svrs.rs.gov.br/cte/qrCode?chCTe='+'9'*44+'&tpAmb=2']:
            root,info=read_cte(document_sample())
            node=root.find('n:CTe/n:infCTeSupl/n:qrCodCTe',{'n':'http://www.portalfiscal.inf.br/cte'})
            node.text=qr
            doc=document_sample(xml_content=etree.tostring(root).decode())
            with self.assertRaises(SefazError):generate_dacte(doc)
