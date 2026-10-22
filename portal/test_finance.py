"""Dados estritamente fictícios; nenhuma consulta bancária ou fiscal."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from portal.models import Installment, InstallmentRevision
from portal.services.invoices import import_invoice, parse_nfe, InvoiceImportError
from portal.services.installments import save_installment, review_installment
from portal.services.demo import sample_xml
from portal.tests import create_account


class FinanceRevisionTests(TestCase):
    def setUp(self):
        self.user,self.workspace,self.company=create_account('finance@example.test')
        self.other,self.other_workspace,self.other_company=create_account('finance-other@example.test')
        self.note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj,due_dates=[]))
        self.client.force_login(self.user)

    def data(self,**extra):
        return dict(number='Condição informada',amount='123.45',due_on=None,review_note='Documento fictício: condição revisada com o fornecedor.',**extra)

    def test_manual_without_due_does_not_invent_date_or_payment(self):
        item=save_installment(self.workspace,self.note,self.data())
        self.assertIsNone(item.due_on)
        self.assertFalse(item.checked)
        self.assertEqual(item.source,'manual')
        self.assertEqual(item.revisions.count(),1)
        self.assertTrue(self.note.review_notes)

    def test_manual_revision_keeps_original_and_complete_audit(self):
        note,_=import_invoice(self.workspace,sample_xml(self.company.cnpj,number='12'))
        item=note.installments.first()
        original=item.original_data.copy()
        data=self.data();data['amount']='222.00'
        save_installment(self.workspace,note,data,installment=item)
        item.refresh_from_db()
        self.assertEqual(item.original_data,original)
        self.assertEqual(item.revisions.get().before['amount'],'600.00')
        self.assertEqual(item.revisions.get().after['amount'],'222.00')

    def test_cross_client_and_company_scope_rejected_before_write(self):
        for workspace,allowed in [(self.other_workspace,None),(self.workspace,[])]:
            with self.assertRaises(ValidationError): save_installment(workspace,self.note,self.data(),allowed_companies=allowed)
        self.assertEqual(Installment.objects.count(),0)
        with self.assertRaises(InvoiceImportError):
            import_invoice(self.workspace,sample_xml(self.company.cnpj,number='97'),allowed_companies=[])
        self.assertFalse(self.company.invoices.filter(number='97').exists())

    def test_money_reason_and_duplicate_validation(self):
        for value in ['NaN','Infinity','0','-2','0.001','1e20']:
            data=self.data();data['amount']=value
            with self.assertRaises(ValidationError): save_installment(self.workspace,self.note,data)
        data=self.data();data['review_note']=''
        with self.assertRaises(ValidationError): save_installment(self.workspace,self.note,data)
        save_installment(self.workspace,self.note,self.data())
        with self.assertRaises(ValidationError): save_installment(self.workspace,self.note,self.data())
        self.assertEqual(Installment.objects.count(),1)

    def test_checking_only_changes_review(self):
        item=save_installment(self.workspace,self.note,self.data())
        item=review_installment(self.workspace,item,True)
        self.assertTrue(item.checked)
        self.assertEqual(item.amount,Decimal('123.45'))
        self.assertIsNone(item.due_on)
        with self.assertRaises(ValidationError): review_installment(self.other_workspace,item,False)

    def test_manual_form_scope_and_submission(self):
        url=reverse('installment_create',args=[self.note.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,self.data()|{'due_on':'','amount':'0.01'}).status_code,302)
        self.assertEqual(self.note.installments.get().amount,Decimal('.01'))
        other_note,_=import_invoice(self.other_workspace,sample_xml(self.other_company.cnpj))
        self.assertEqual(self.client.get(reverse('installment_create',args=[other_note.pk])).status_code,404)

    def test_dashboard_route_preserved(self):
        response=self.client.get(reverse('dashboard'))
        self.assertTemplateUsed(response,'portal/dashboard.html')
        self.assertContains(response,'Visão geral')
        response=self.client.get(reverse('integration_list'))
        self.assertTemplateUsed(response,'portal/integrations.html')

    def test_xml_payment_is_only_declaration_not_an_installment(self):
        xml=sample_xml(self.company.cnpj,due_dates=[])
        xml=xml.replace(b'</infNFe>',b'<pag><detPag><indPag>0</indPag><tPag>17</tPag><vPag>1200.00</vPag></detPag></pag></infNFe>')
        result=parse_nfe(xml)
        self.assertEqual(result['payment_details'][0]['declared_amount'],'1200.00')
        self.assertEqual(result['installments'],[])
