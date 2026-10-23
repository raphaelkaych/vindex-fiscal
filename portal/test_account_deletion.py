from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from portal.models import (Workspace, Company, MasterAudit, Invoice, SefazSyncState,
    SefazConsultation, SefazDistributionStream, SefazDocument, SefazScienceRequest)
from portal.services.account_deletion import delete_account
from portal.services.invoices import import_invoice
from portal.services.demo import sample_xml
from portal.services.sefaz_recovery import consultations_for_stream
from portal.tests import create_account


class AccountDeletionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user,self.ws,self.company=create_account('excluir-sintetico@example.test')
        self.user.set_password('SenhaFicticia123!');self.user.save()
        self.other,self.other_ws,self.other_company=create_account('preservar-sintetico@example.test')
        self.client.force_login(self.user)
        self.form={'password':'SenhaFicticia123!','confirmation':self.ws.name,'acknowledged':'on'}

    def test_get_so_mostra_confirmacao(self):
        self.assertContains(self.client.get('/perfil/excluir/'),'Esta ação é definitiva')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_nome_do_cliente_na_ajuda_nao_injeta_html(self):
        self.ws.name='<script>alert(1)</script>';self.ws.save()
        response=self.client.get('/perfil/excluir/')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')

    def test_post_exclui_apenas_conta_autenticada_e_invalida_sessao(self):
        import_invoice(self.ws,sample_xml(self.company.cnpj))
        import_invoice(self.other_ws,sample_xml(self.other_company.cnpj))
        self.assertRedirects(self.client.post('/perfil/excluir/',self.form),'/entrar/')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Company.objects.filter(workspace_id=self.ws.pk).exists())
        self.assertTrue(Invoice.objects.filter(company=self.other_company).exists())
        self.assertTrue(MasterAudit.objects.filter(action='account_erased').exists())
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_senha_confirmacao_e_checkbox_sao_obrigatorios(self):
        for change in [{'password':'incorreta'},{'confirmation':'OUTRO CLIENTE'},{'acknowledged':''}]:
            self.assertEqual(self.client.post('/perfil/excluir/',dict(self.form,**change)).status_code,200)
            self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_servico_nao_permite_excluir_outro_cliente(self):
        with self.assertRaises(ValidationError):delete_account(actor=self.user,workspace_id=self.other_ws.pk,confirmation=self.other_ws.name)
        self.assertTrue(Workspace.objects.filter(pk=self.other_ws.pk).exists())

    def test_csrf_e_exigido(self):
        browser=Client(enforce_csrf_checks=True);browser.force_login(self.user)
        self.assertEqual(browser.post('/perfil/excluir/',self.form).status_code,403)

    def test_conta_suspensa_tambem_pode_pedir_exclusao(self):
        self.ws.access_status='suspended';self.ws.save()
        self.assertEqual(self.client.post('/perfil/excluir/',self.form).status_code,302)
        self.assertFalse(Workspace.objects.filter(pk=self.ws.pk).exists())

    def test_conta_master_nao_e_apagada_por_engano(self):
        self.user.user_permissions.add(Permission.objects.get(codename='admin_master'))
        self.assertContains(self.client.post('/perfil/excluir/',self.form),'Transfira a administração')
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_supervisao_master_nao_pode_excluir_em_nome_do_cliente(self):
        self.other.user_permissions.add(Permission.objects.get(codename='admin_master'))
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(f'/gestao/clientes/{self.ws.pk}/painel/perfil/excluir/',self.form).status_code,403)
        self.assertTrue(Workspace.objects.filter(pk=self.ws.pk).exists())

    def test_fila_intervalo_e_evidencias_de_consulta_e_evento_sobrevivem(self):
        wait=timezone.now()+timedelta(hours=2)
        stream=SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',source='sefaz',last_nsu='000000000000010',next_attempt_at=wait,blocked_until=wait)
        state=SefazSyncState.objects.create(company=self.company,environment='1',source='sefaz')
        doc=SefazDocument.objects.create(state=state,kind='summary',content_hash='f'*64,schema_name='FICTICIO',xml_content='<FICTICIO/>')
        event=SefazScienceRequest.objects.create(company=self.company,document=doc,cnpj=self.company.cnpj,access_key='1'*44,environment='1',authorized_by=self.user,status='accepted')
        item=SefazConsultation.objects.create(state=state,stream=stream,requested_at=timezone.now(),requested_nsu=stream.last_nsu,status='656',response_xml='<FICTICIO/>')
        self.client.post('/perfil/excluir/',self.form)
        stream.refresh_from_db();item.refresh_from_db();event.refresh_from_db()
        self.assertEqual(stream.last_nsu,'000000000000010');self.assertEqual(stream.next_attempt_at,wait)
        self.assertIsNone(item.state_id);self.assertEqual(item.stream_id,stream.pk)
        self.assertEqual(consultations_for_stream(stream).count(),1)
        self.assertIsNone(event.company_id);self.assertIsNone(event.document_id);self.assertEqual(event.status,'accepted')

    def test_consulta_ativa_impede_exclusao_ate_conclusao(self):
        SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',source='sefaz',lease_until=timezone.now()+timedelta(minutes=3))
        self.assertContains(self.client.post('/perfil/excluir/',self.form),'Há uma consulta fiscal em andamento')
        self.assertTrue(Workspace.objects.filter(pk=self.ws.pk).exists())

    def test_manifestacao_em_andamento_tambem_impede_exclusao(self):
        state=SefazSyncState.objects.create(company=self.company,environment='1',source='sefaz')
        doc=SefazDocument.objects.create(state=state,kind='summary',content_hash='f'*64,schema_name='FICTICIO',xml_content='<FICTICIO/>')
        SefazScienceRequest.objects.create(company=self.company,document=doc,cnpj=self.company.cnpj,access_key='1'*44,environment='1',authorized_by=self.user,status='sent')
        self.assertContains(self.client.post('/perfil/excluir/',self.form),'Há uma manifestação fiscal em andamento')
        self.assertTrue(Workspace.objects.filter(pk=self.ws.pk).exists())

    def test_entrega_privada_e_removida_enquanto_envelope_global_permanece(self):
        from portal.models import FiscalConnector,FiscalStream,FiscalEnvelope,FiscalDocument,FiscalDelivery
        config=FiscalConnector.objects.create(company=self.company,service='nfse',enabled=True,authorized_at=timezone.now())
        stream=FiscalStream.objects.create(cnpj=self.company.cnpj,service='nfse',environment='1',cursor='9')
        envelope=FiscalEnvelope.objects.create(stream=stream,nsu='9',content_hash='f'*64,xml_content='<FICTICIO/>')
        doc=FiscalDocument.objects.create(company=self.company,service='nfse',access_key='FICTICIO',number='1',issuer_name='FICTICIO',issuer_cnpj=self.company.cnpj,role='tomador',issued_at=timezone.now(),total='10.00',xml_content='<FICTICIO/>')
        FiscalDelivery.objects.create(connector=config,envelope=envelope,document=doc)
        self.client.post('/perfil/excluir/',self.form)
        self.assertFalse(FiscalDelivery.objects.exists());self.assertFalse(FiscalDocument.objects.exists())
        self.assertTrue(FiscalEnvelope.objects.filter(pk=envelope.pk).exists())
        stream.refresh_from_db();self.assertEqual(stream.cursor,'9')

    def test_exclusao_encerra_recuperacoes_pendentes_sem_apagar_evidencia(self):
        from portal.models import SefazKeyRecovery
        stream=SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',source='sefaz')
        job=SefazKeyRecovery.objects.create(stream=stream,company=self.company,access_key='1'*44)
        self.client.post('/perfil/excluir/',self.form)
        job.refresh_from_db();self.assertIsNone(job.company_id);self.assertEqual(job.result,'rejected')
        self.assertIsNotNone(job.completed_at)

    def test_formulario_nao_reexibe_senha_e_limita_tentativas(self):
        response=self.client.post('/perfil/excluir/',dict(self.form,confirmation='ERRADO'))
        self.assertNotContains(response,'value="SenhaFicticia123!"')
        with patch('portal.account_views.rate_limited',return_value=True):
            self.assertEqual(self.client.post('/perfil/excluir/',self.form).status_code,429)

    def test_volume_de_documentos_nao_excede_limite_de_variaveis_sqlite(self):
        from django.db import connection
        import sqlite3
        if connection.vendor != 'sqlite':
            self.skipTest('Regressão específica do limite de variáveis do SQLite.')
        state=SefazSyncState.objects.create(company=self.company,environment='1',source='sefaz')
        SefazDocument.objects.bulk_create([SefazDocument(state=state,kind='summary',content_hash=format(index,'064x'),schema_name='FICTICIO',xml_content='<FICTICIO/>') for index in range(800)])
        previous=connection.connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,700)
        try:
            delete_account(actor=self.user,workspace_id=self.ws.pk,confirmation=self.ws.name)
        finally:
            connection.connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,previous)
        self.assertFalse(Workspace.objects.filter(pk=self.ws.pk).exists())
        self.assertFalse(SefazDocument.objects.filter(state=state).exists())
