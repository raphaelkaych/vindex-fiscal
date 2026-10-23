from datetime import date
from decimal import Decimal
from io import BytesIO,StringIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from portal.tests import create_account
from portal.services.demo import sample_xml
from portal.services.invoices import import_invoice
from portal.services.fiscal_search import index_document
from portal.models import FiscalSearchRecord,FiscalSearchItem,FiscalDocument,Invoice

NS='http://www.portalfiscal.inf.br/nfe'
X={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def product_xml(cnpj,number='778'):
    root=ET.fromstring(sample_xml(cnpj,number=number));info=root.find('.//{'+NS+'}infNFe')
    ET.SubElement(info.find('{'+NS+'}ide'),'{'+NS+'}tpAmb').text='1'
    for position,code,description,ncm in [(1,'PET001','Ração especial cão','23091000'),(2,'OUTRO','Brinquedo','95030099')]:
        prod=ET.SubElement(ET.SubElement(info,'{'+NS+'}det',{'nItem':str(position)}),'{'+NS+'}prod')
        for tag,value in {'cProd':code,'xProd':description,'NCM':ncm,'CFOP':'5102','uCom':'UN','qCom':'2.5000','vUnCom':'10.123456','vProd':'25.31'}.items():ET.SubElement(prod,'{'+NS+'}'+tag).text=value
    return ET.tostring(root)


class FiscalSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user,cls.ws,cls.company=create_account('search@example.test')
        cls.other,cls.other_ws,cls.other_company=create_account('foreign-search@example.test')
        cls.note,_=import_invoice(cls.ws,product_xml(cls.company.cnpj))
        cls.foreign,_=import_invoice(cls.other_ws,product_xml(cls.other_company.cnpj,'999'))
    def setUp(self):self.client.force_login(self.user)
    def test_source_index_is_idempotent_and_preserves_original(self):
        index_document(self.note);index_document(self.note)
        self.assertEqual(FiscalSearchRecord.objects.filter(invoice=self.note).count(),1)
        self.assertEqual(FiscalSearchItem.objects.filter(record__invoice=self.note).count(),2)
        item=self.note.search_record.items.get(code='PET001')
        self.assertEqual(item.quantity,Decimal('2.5'));self.assertEqual(item.unit_price,Decimal('10.123456'))
        before=self.note.xml_content;self.note.refresh_from_db();self.assertEqual(self.note.xml_content,before)
    def test_combined_filters_match_the_same_item_and_scope(self):
        response=self.client.get('/documentos/',{'company':self.company.pk,'product':'ração','ncm':'23091000','cfop':'5102','environment':'1','minimum':'100','maximum':'1500'})
        self.assertEqual(response.context['page'].paginator.count,1)
        self.assertContains(response,'Ração especial cão');self.assertNotContains(response,'Brinquedo');self.assertNotContains(response,'999</strong>')
        self.assertEqual(self.client.get('/documentos/',{'product':'ração','ncm':'95030099'}).context['page'].paginator.count,0)
    def test_product_search_handles_portuguese_accents_and_uppercase(self):
        for word in ['RAÇÃO','racao','RAÇAO','Ração']:
            self.assertEqual(self.client.get('/documentos/',{'product':word}).context['page'].paginator.count,1)
    def test_each_identifier_and_period_filter(self):
        r=self.note.search_record
        for key,value in {'issuer_cnpj':'00.000.003/0001-25','recipient_cnpj':self.company.cnpj,'issuer':'Fornecedor','number':r.number,'series':r.series,'key':r.access_key,'start':r.issued_on.isoformat(),'end':r.issued_on.isoformat(),'code':'PET001'}.items():
            with self.subTest(key=key):self.assertEqual(self.client.get('/documentos/',{key:value}).context['page'].paginator.count,1)
    def test_foreign_company_and_exports_are_denied_even_for_master(self):
        self.user.user_permissions.add(Permission.objects.get(codename='admin_master'))
        for path in ['/documentos/','/documentos/exportar.xlsx']:
            self.assertEqual(self.client.get(path,{'company':self.other_company.pk}).status_code,404)
        self.assertEqual(self.client.get(f'/gestao/clientes/{self.other_ws.pk}/painel/documentos/exportar.xlsx').status_code,200)
    def test_invalid_filters_do_not_export_or_silently_broaden(self):
        for params in [{'start':'bad'},{'minimum':'NaN'},{'start':'2026-10-23','end':'2026-01-01'},{'minimum':'20','maximum':'1'},{'type':'nfce'},{'issuer_cnpj':'1'}]:
            self.assertEqual(self.client.get('/documentos/exportar.xlsx',params).status_code,400)
            self.assertEqual(self.client.get('/documentos/',params).context['page'].paginator.count,0)
    def test_xlsx_filters_items_types_and_exact_numbers(self):
        response=self.client.get('/documentos/exportar.xlsx',{'product':'ração'})
        self.assertEqual(response.status_code,200);self.assertIn('no-store',response['Cache-Control'])
        with ZipFile(BytesIO(response.content)) as z:
            self.assertEqual(z.testzip(),None)
            sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(len(sheet.findall('s:sheetData/s:row',X)),2)
            key=sheet.find('.//s:c[@r="G2"]',X);self.assertEqual(key.attrib['t'],'inlineStr')
            detail=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
            self.assertEqual(len(detail.findall('s:sheetData/s:row',X)),2)
            self.assertEqual(detail.find('.//s:c[@r="Q2"]/s:v',X).text,'2.5000000000')
            self.assertEqual(sheet.find('s:autoFilter',X).attrib['ref'],'A1:N2')
            self.assertIn(b'frozen',z.read('xl/worksheets/sheet2.xml'))
    def test_excel_external_content_cannot_be_a_formula(self):
        FiscalSearchItem.objects.filter(record__invoice=self.note,code='PET001').update(description='=HYPERLINK("https://invalid.test")')
        payload=self.client.get('/documentos/exportar.xlsx',{'code':'PET001'}).content
        with ZipFile(BytesIO(payload)) as z:
            xml=z.read('xl/worksheets/sheet2.xml')
            self.assertNotIn(b'<f>',xml);self.assertIn(b'=HYPERLINK',xml)
    def test_excel_does_not_round_large_decimal_to_fifteen_digits(self):
        from portal.services.xlsx_export import workbook
        with ZipFile(BytesIO(workbook([('Precisão',['Valor'],[[Decimal('12345678901234.56')]])]))) as z:
            root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            value=root.find('.//s:c[@r="A2"]',X)
            self.assertEqual(value.attrib['t'],'inlineStr')
            self.assertEqual(value.find('s:is/s:t',X).text,'12345678901234.56')
    def test_missing_values_are_blank_and_partial_status_is_retained(self):
        doc=FiscalDocument.objects.create(company=self.company,service='nfse',access_key='1'*50,number='42',issuer_name='Serviço',issuer_cnpj='00000003000125',role='tomador',issued_at=timezone.now(),total='10',xml_content='<NFSe/>',validation_status='partial')
        self.assertEqual(doc.search_record.status,'partial');self.assertTrue(doc.search_record.diagnostic)
        self.assertFalse(doc.search_record.items.exists())
    def test_backfill_resumes_without_reimport_or_network(self):
        FiscalSearchRecord.objects.filter(invoice=self.note).delete()
        with patch('portal.services.sefaz_transport.SefazTransport.fetch',side_effect=AssertionError('Rede proibida')):
            call_command('indexar_documentos',stdout=StringIO());call_command('indexar_documentos',stdout=StringIO())
        self.assertEqual(Invoice.objects.count(),2);self.assertEqual(FiscalSearchRecord.objects.count(),2)
    def test_index_deletion_follows_private_source(self):
        pk=self.note.pk;self.note.delete()
        self.assertFalse(FiscalSearchRecord.objects.filter(invoice_id=pk).exists())
    def test_indicators_have_scoped_comparison_and_month_links(self):
        response=self.client.get('/indicadores/',{'type':'nfe','company':self.company.pk})
        self.assertEqual(response.status_code,200);self.assertContains(response,'Período anterior:')
        self.assertContains(response,'data-indicator-filter');self.assertContains(response,'analytics-ring')
