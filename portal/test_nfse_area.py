"""NFS-e sintéticas em banco isolado; nenhuma consulta fiscal ou certificado real."""
from io import BytesIO
from unittest.mock import patch
from django.test import TestCase,SimpleTestCase
from django.contrib.auth.models import Permission
from django.utils import timezone
from pypdf import PdfReader
from portal.models import FiscalDocument,MasterAudit
from portal.tests import create_account
from portal.test_nfse_pdf import sample_document
from portal.services.nfse_pdf import generate_nfse_pdf
from portal.services.nfse_presentation import read_nfse,parties,sections
from portal.services.sefaz import SefazError


class NfseAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.ws,cls.company=create_account('nfse-area@example.test')
        cls.foreign_user,cls.foreign_ws,cls.foreign_company=create_account('nfse-other@example.test')
        sample=sample_document()
        args=dict(service='nfse',environment='1',access_key=sample.access_key,number='SERVICO-123',issuer_name='PRESTADOR FICTICIO',issuer_cnpj='00000003000125',role='tomador',issued_at=timezone.now(),total='123.45',xml_content=sample.xml_content)
        cls.doc=FiscalDocument.objects.create(company=cls.company,**args)
        cls.foreign=FiscalDocument.objects.create(company=cls.foreign_company,**args)
        cls.cte=FiscalDocument.objects.create(company=cls.company,**dict(args,service='cte',number='CTE-ISOLADO'))
        cls.homolog=FiscalDocument.objects.create(company=cls.company,**dict(args,environment='2',number='HOMOLOG-123'))
    def setUp(self):self.client.force_login(self.user)

    def test_list_only_nfse_of_authenticated_workspace_and_production_default(self):
        response=self.client.get('/nfse/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['counts']['total'],1)
        self.assertEqual([doc.pk for doc in response.context['page']],[self.doc.pk])
        self.assertContains(response,'Notas de serviço · NFS-e')
        self.assertNotContains(response,'CTE-ISOLADO')
        self.assertNotContains(response,'HOMOLOG-123')
        self.assertIn('no-store',response['Cache-Control'])

    def test_filters_search_environment_status_dates_and_pagination(self):
        self.assertEqual(self.client.get('/nfse/?q=inexistente').context['counts']['total'],0)
        self.assertEqual(self.client.get('/nfse/?environment=2').context['counts']['total'],1)
        self.assertEqual(self.client.get('/nfse/?environment=').context['counts']['total'],2)
        self.assertEqual(self.client.get('/nfse/?start=2099-01-01').context['counts']['total'],0)
        self.doc.validation_status='partial';self.doc.save(update_fields=['validation_status'])
        response=self.client.get('/nfse/?status=partial&q=SERVICO&per_page=10')
        self.assertEqual(response.context['counts']['partial'],1)
        self.assertEqual(response.context['page'].paginator.per_page,10)
        self.assertContains(response,'PDF de conferência')

    def test_invalid_foreign_company_and_dates_return_no_data(self):
        for query in [f'company={self.foreign_company.pk}','start=2026-12-01&end=2026-01-01','environment=3','status=unknown']:
            response=self.client.get('/nfse/?'+query)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.context['counts']['total'],0)
            self.assertTrue(response.context['form'].errors)

    @patch('portal.services.nfse_pdf.generate_nfse_pdf',return_value=b'%PDF-SYNTHETIC')
    def test_downloads_require_workspace_and_nfse_type_before_generation(self,generate):
        for doc in [self.foreign,self.cte]:
            for suffix in ['', 'xml/', 'pdf/']:
                self.assertEqual(self.client.get(f'/nfse/{doc.pk}/'+suffix).status_code,404)
        generate.assert_not_called()
        xml=self.client.get(f'/nfse/{self.doc.pk}/xml/')
        self.assertEqual(xml.content,self.doc.xml_content.encode())
        pdf=self.client.get(f'/nfse/{self.doc.pk}/pdf/')
        self.assertEqual(pdf.status_code,200)
        self.assertIn('danfse-vindex-',pdf['Content-Disposition'])
        self.assertIn('no-store',pdf['Cache-Control'])

    def test_detail_original_long_description_and_unavailable_values_are_visible(self):
        response=self.client.get(f'/nfse/{self.doc.pk}/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Serviço fictício.')
        self.assertContains(response,'Não informado')
        self.assertContains(response,'não é um arquivo baixado do governo')
        self.assertContains(response,f'/nfse/{self.doc.pk}/xml/')

    def test_master_supervision_is_url_scoped_and_audited(self):
        self.user.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))
        prefix=f'/gestao/clientes/{self.foreign_ws.pk}/painel'
        response=self.client.get(prefix+'/nfse/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['page'][0].pk,self.foreign.pk)
        self.assertContains(response,prefix+f'/nfse/{self.foreign.pk}/')
        self.assertEqual(self.client.get(prefix+f'/nfse/{self.doc.pk}/xml/').status_code,404)
        self.assertEqual(self.client.post(prefix+f'/nfse/{self.foreign.pk}/pdf/').status_code,403)
        self.assertTrue(MasterAudit.objects.filter(actor=self.user,workspace=self.foreign_ws,action='client_panel_read').exists())
        self.assertNotIn('selected_workspace',self.client.session)


class NfseLayoutTests(SimpleTestCase):
    @patch('portal.services.nfse_pdf.validate_xml')
    def test_one_a4_page_qr_link_and_unchanged_xml(self,validate):
        document=sample_document();original=document.xml_content
        pdf=PdfReader(BytesIO(generate_nfse_pdf(document)))
        self.assertEqual(len(pdf.pages),1)
        self.assertAlmostEqual(float(pdf.pages[0].mediabox.width),595.28,places=1)
        links=[annotation.get_object().get('/A',{}).get('/URI','') for annotation in pdf.pages[0].get('/Annots',[])]
        self.assertIn('https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave='+document.access_key,links)
        # Logo e QR incorporados; QR quadrado, legível e dentro da coluna direita.
        self.assertGreaterEqual(len(pdf.pages[0].images),2)
        annotation=next(item.get_object() for item in pdf.pages[0]['/Annots'] if item.get_object().get('/A',{}).get('/URI','').endswith(document.access_key))
        x0,y0,x1,y1=map(float,annotation['/Rect'])
        self.assertAlmostEqual(x1-x0,y1-y0,places=2)
        self.assertGreaterEqual((x1-x0)*25.4/72,15.2)
        self.assertGreater(x0*25.4/72,156)
        self.assertLess(x1*25.4/72,207)
        self.assertIn('portal nacional da NFS-e.',pdf.pages[0].extract_text())
        self.assertEqual(document.xml_content,original)
        self.assertIn('R$ 123,45',pdf.pages[0].extract_text())
        self.assertNotIn('R$ 0,00',pdf.pages[0].extract_text())

    @patch('portal.services.nfse_pdf.validate_xml')
    def test_four_parties_and_substitution_do_not_overflow(self,validate):
        from lxml import etree
        document=sample_document();root=read_nfse(document)
        namespace='{http://www.sped.fazenda.gov.br/nfse}'
        dps=root.find(namespace+'DPS/'+namespace+'infDPS')
        for party in ['prest','toma','interm']:
            node=etree.SubElement(dps,namespace+party)
            etree.SubElement(node,namespace+'xNome').text='PESSOA FICTÍCIA PARA TESTE DE DIAGRAMAÇÃO'
        ibs=etree.SubElement(dps,namespace+'IBSCBS')
        dest=etree.SubElement(ibs,namespace+'dest')
        etree.SubElement(dest,namespace+'xNome').text='DESTINATÁRIO FICTÍCIO'
        document.xml_content=etree.tostring(root.getparent()).decode()
        document.substitution_reported=True;document.substituted_by='2'*50
        pdf=PdfReader(BytesIO(generate_nfse_pdf(document)))
        self.assertEqual(len(pdf.pages),1)
        self.assertIn('SUBSTITUIÇÃO',pdf.pages[0].extract_text())

    @patch('portal.services.nfse_compat.partial_profile')
    def test_partial_pdf_is_not_promoted_to_danfse(self,profile):
        document=sample_document();document.validation_status='partial'
        text=PdfReader(BytesIO(generate_nfse_pdf(document))).pages[0].extract_text()
        self.assertIn('IMPORTAÇÃO PARCIAL',text)
        self.assertIn('CONFERÊNCIA',text)
        self.assertNotIn('DANFSe v2.0',text)
