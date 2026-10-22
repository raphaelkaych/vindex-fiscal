"""Regressão dos totais consolidados. Dados fictícios, sem conexão fiscal."""
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from portal.tests import create_account
from portal.models import Invoice,Installment


class DashboardAggregationTests(TestCase):
    def test_periods_null_dates_and_foreign_workspace_keep_the_same_totals(self):
        user,workspace,company=create_account('final-review@example.test')
        other,other_workspace,foreign=create_account('final-foreign@example.test')
        today=timezone.localdate()
        def note(company,key):
            return Invoice.objects.create(company=company,access_key=key*44,number='1',series='1',issuer_name='FICTÍCIO',issuer_cnpj='00000003000125',issued_on=today,total=Decimal('100'),xml_content='XML FICTÍCIO NÃO UTILIZADO NESTA TELA')
        invoice=note(company,'1');foreign_invoice=note(foreign,'2')
        for n,offset in enumerate([0,6,7,13,14,20,21,30,31,-1,None],1):
            Installment.objects.create(invoice=invoice,number=str(n),amount=Decimal('10'),due_on=today+timedelta(days=offset) if offset is not None else None)
        Installment.objects.create(invoice=foreign_invoice,number='1',amount=Decimal('999'),due_on=today)
        self.client.force_login(user)
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['invoice_count'],1)
        self.assertEqual(response.context['invoice_total'],Decimal('100'))
        self.assertEqual(response.context['upcoming_total'],Decimal('80'))
        self.assertEqual(response.context['overdue_total'],Decimal('10'))
        self.assertEqual(response.context['overdue_count'],1)
        self.assertEqual([bar['amount'] for bar in response.context['chart']],[Decimal('20')]*4)
        self.assertNotContains(response,'XML FICTÍCIO NÃO UTILIZADO')
