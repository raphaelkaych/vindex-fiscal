"""Respostas e certificados sintéticos, sem rede nem valor fiscal."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from portal.models import Company, DigitalCertificate, Invoice, Workspace
from portal.sefaz_models import (
    SefazCaptureConfig, SefazConsultation, SefazDistributionStream,
    SefazDocument, SefazStreamDocument, SefazSyncState,
)
from portal.services.capture import configure_capture, has_due_backlog, run_company, run_due, schedule_company
from portal.services.demo import sample_xml
from portal.services.invoices import InvoiceImportError
from portal.services.sefaz import SefazBusy, SefazError, SefazNotConfigured, SefazRejected
from portal.test_sefaz import SyntheticTransport, event, response, summary


class ContinuousCaptureTests(TestCase):
    def test_resposta_aceita_preservada_e_recuperada_sem_http_ou_antecipar_espera(self):
        from portal.services.capture import recover_received_response
        self.enable()
        wait=timezone.now()+timedelta(hours=1)
        stream=SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',source='sefaz',next_attempt_at=wait,last_error='Falha sintética de armazenamento')
        state=SefazSyncState.objects.get(company=self.company,environment='1',source='sefaz')
        payload=response([(summary(),'000000000000001','resNFe_v1.01.xsd')],environment='1',last='000000000000001',maximum='000000000000003')
        # O contrato NF-e exige segundos sem fração no horário oficial.
        import re
        payload=re.sub(rb'(\d{2}:\d{2}:\d{2})\.\d+',rb'\1',payload)
        attempt=SefazConsultation.objects.create(state=state,requested_at=timezone.now(),requested_nsu=stream.last_nsu,status='138',response_xml=payload.decode(),error='Falha sintética de armazenamento')
        with patch('portal.services.sefaz_transport.official_post') as network:
            self.assertTrue(recover_received_response(self.company,self.company.capture_config,stream))
        network.assert_not_called();stream.refresh_from_db();attempt.refresh_from_db()
        self.assertEqual(stream.last_nsu,'000000000000001');self.assertEqual(stream.next_attempt_at,wait)
        self.assertEqual(stream.documents.count(),1);self.assertEqual(attempt.error_code,'recovered_local')
        self.assertFalse(recover_received_response(self.company,self.company.capture_config,stream))
    def setUp(self):
        self.user = User.objects.create_user('captura-ficticia@example.test')
        self.workspace = Workspace.objects.create(owner=self.user, name='FICTICIO A')
        self.company = Company.objects.create(workspace=self.workspace,
            legal_name='EMPRESA FICTICIA', cnpj='00000001000136')
        self.other_user = User.objects.create_user('outra-captura@example.test')
        self.other_workspace = Workspace.objects.create(owner=self.other_user, name='FICTICIO B')
        self.other_company = Company.objects.create(workspace=self.other_workspace,
            legal_name='OUTRA FICTICIA', cnpj='00000002000180')
        self.certificate(self.company)

    def certificate(self, company, **overrides):
        values = dict(encrypted_file=b'NAO_E_CERTIFICADO', encrypted_password=b'NAO_E_SENHA',
            subject_name='TESTE SEM VALOR FISCAL', holder_cnpj=company.cnpj,
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=30), fingerprint='f' * 64)
        values.update(overrides)
        return DigitalCertificate.objects.update_or_create(company=company, defaults=values)[0]

    def enable(self, company=None, **overrides):
        company = company or self.company
        values = dict(enabled=True, environment='1', authorize_read=True,
                      actor=company.workspace.owner)
        values.update(overrides)
        return configure_capture(company.workspace, company.pk, **values)

    def transport(self, docs=None, **overrides):
        if docs is None:
            docs = [(summary(), '1', 'resNFe_v1.01.xsd')]
        values = dict(last='2', maximum='3', environment='1')
        values.update(overrides)
        return SyntheticTransport(response(docs, **values))

    def execute(self, transport=None, company=None):
        company = company or self.company
        return run_company(company.workspace, company.pk, transport=transport or self.transport())

    def test_autorizacao_e_escopo_antes_de_agendar(self):
        with self.assertRaises(SefazError):
            configure_capture(self.workspace, self.other_company.pk, authorize_read=True)
        with self.assertRaises(SefazError):
            configure_capture(self.workspace, self.company.pk, actor=self.other_user, authorize_read=True)
        with self.assertRaises(SefazError):
            configure_capture(self.workspace, self.company.pk)
        self.assertFalse(SefazCaptureConfig.objects.exists())
        self.assertFalse(SefazSyncState.objects.exists())

    def test_agendamento_automatico_e_renovacao_preservam_cursor_e_intervalo(self):
        config = self.enable()
        state = SefazSyncState.objects.get(company=self.company, source='sefaz')
        state.last_nsu = '000000000000120'
        state.next_attempt_at = timezone.now() + timedelta(hours=1)
        state.save()
        self.certificate(self.company, fingerprint='e' * 64)
        schedule_company(self.company)
        state.refresh_from_db()
        self.assertTrue(config.enabled)
        self.assertEqual(config.authorized_by, self.user)
        self.assertIsNotNone(config.read_authorized_at)
        self.assertEqual(state.last_nsu, '000000000000120')
        self.assertGreater(state.next_attempt_at, timezone.now())

    def test_autorizacao_homologacao_nao_autoriza_producao(self):
        self.enable(environment='2')
        with self.assertRaises(SefazError):
            configure_capture(self.workspace, self.company.pk, environment='1')
        self.assertEqual(SefazCaptureConfig.objects.get().environment, '2')

    def test_desativacao_preserva_historico_mas_impede_http(self):
        self.enable()
        self.execute()
        configure_capture(self.workspace, self.company.pk, enabled=False)
        transport = self.transport()
        with self.assertRaises(SefazNotConfigured):
            self.execute(transport)
        self.assertFalse(transport.calls)
        self.assertEqual(SefazDocument.objects.count(), 1)

    def test_certificado_ausente_vencido_futuro_ficticio_ou_de_outra_raiz_bloqueia_http(self):
        self.enable()
        variants = [None, {'valid_until': timezone.now() - timedelta(seconds=1)},
            {'valid_from': timezone.now() + timedelta(days=1)},
            {'is_demo': True}, {'holder_cnpj': self.other_company.cnpj}]
        for variant in variants:
            with self.subTest(variant=variant):
                DigitalCertificate.objects.filter(company=self.company).delete()
                if variant is not None:
                    self.certificate(self.company, **variant)
                transport = self.transport()
                with self.assertRaises(SefazNotConfigured):
                    self.execute(transport)
                self.assertFalse(transport.calls)
                config = SefazCaptureConfig.objects.get(company=self.company)
                self.assertTrue(config.last_error)
        self.assertFalse(SefazConsultation.objects.exists())

    def test_retorno_e_historico_separam_resumos_eventos_e_completos(self):
        self.enable()
        transport = self.transport([
            (summary(), '1', 'resNFe_v1.01.xsd'),
            (event(), '2', 'procEventoNFe_v1.00.xsd'),
        ], last='2', maximum='3')
        state = self.execute(transport)
        self.assertEqual(state.last_nsu, '000000000000002')
        self.assertEqual(state.last_counts['summary'], 1)
        self.assertEqual(state.last_counts['event'], 1)
        self.assertEqual(state.last_counts['invoice'], 0)
        self.assertEqual(state.last_counts['imported'], 0)
        self.assertIn('SINTETICA', state.last_reason)
        self.assertIsNotNone(state.official_response_at)
        self.assertIsNone(state.last_real_success_at)
        history = state.consultations.get()
        self.assertEqual(history.status, '138')
        self.assertEqual(history.counts, state.last_counts)
        self.assertEqual(history.requested_nsu, '000000000000000')
        self.assertFalse(Invoice.objects.exists())

    def test_importacao_no_painel_correto_e_idempotencia(self):
        self.enable()
        docs = [(sample_xml(self.company.cnpj), '1', 'procNFe_v4.00.xsd')]
        state = self.execute(self.transport(docs))
        self.assertEqual(Invoice.objects.get().company, self.company)
        self.assertTrue(Invoice.objects.get().is_demo)
        self.assertEqual(state.last_counts['imported'], 1)
        state = self.execute(self.transport(docs, last='3', maximum='4'))
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(SefazStreamDocument.objects.count(), 1)
        self.assertEqual(state.documents.count(), 1)
        self.assertEqual(state.last_counts['imported'], 0)
        self.assertFalse(self.other_company.invoices.exists())

    def test_documento_de_outro_papel_guardado_sem_importacao_errada(self):
        self.enable()
        docs = [(sample_xml(self.other_company.cnpj), '1', 'procNFe_v4.00.xsd')]
        state = self.execute(self.transport(docs))
        stored = state.documents.get()
        self.assertIn('destinatário difere', stored.processing_error)
        self.assertIsNone(stored.invoice)
        self.assertEqual(state.last_nsu, '000000000000002')
        self.assertFalse(Invoice.objects.exists())

    def test_xml_completo_invalido_nao_perde_lote_nem_reinicia_nsu(self):
        self.enable()
        broken = sample_xml(self.company.cnpj).replace(b'<vNF>2480.00</vNF>', b'<vNF>INVALIDO</vNF>')
        # Alteração estrutural garantida, sem depender dos valores da amostra.
        broken = broken.replace(b'<mod>55</mod>', b'<mod>65</mod>')
        state = self.execute(self.transport([(broken, '1', 'procNFe_v4.00.xsd')]))
        self.assertIn('modelo 55', state.documents.get().processing_error)
        self.assertEqual(state.last_nsu, '000000000000002')
        self.assertFalse(Invoice.objects.exists())

    def test_cnpj_em_clientes_distintos_usa_um_cursor_e_entregas_isoladas(self):
        self.enable()
        twin = Company.objects.create(workspace=self.other_workspace,
            cnpj=self.company.cnpj, legal_name='MESMO CNPJ FICTICIO AUTORIZADO')
        self.certificate(twin)
        self.enable(twin)
        docs = [(sample_xml(self.company.cnpj), '1', 'procNFe_v4.00.xsd')]
        self.execute(self.transport(docs, last='1', maximum='1'))
        self.assertEqual(SefazDistributionStream.objects.count(), 1)
        self.assertEqual(SefazStreamDocument.objects.count(), 1)
        self.assertEqual(SefazDocument.objects.count(), 2)
        self.assertEqual(Invoice.objects.count(), 2)
        self.assertEqual(self.company.invoices.get().company.workspace, self.workspace)
        self.assertEqual(twin.invoices.get().company.workspace, self.other_workspace)
        self.assertNotEqual(self.company.invoices.get().pk, twin.invoices.get().pk)
        transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(transport, twin)
        self.assertFalse(transport.calls)
        self.assertFalse(self.other_company.invoices.exists())

    def test_mesmo_cnpj_sem_autorizacao_ou_certificado_nao_recebe_dados(self):
        self.enable()
        twin = Company.objects.create(workspace=self.other_workspace,
            cnpj=self.company.cnpj, legal_name='MESMO CNPJ SEM CERTIFICADO')
        # Configuração autorizada, mas nenhum A1: ainda não pode receber.
        self.enable(twin)
        unauthorized = Company.objects.create(workspace=self.other_workspace,
            cnpj='00000001000217', legal_name='OUTRA FILIAL NAO AUTORIZADA')
        self.certificate(unauthorized)
        self.execute()
        self.assertFalse(SefazDocument.objects.filter(state__company=twin).exists())
        self.assertFalse(SefazDocument.objects.filter(state__company=unauthorized).exists())
        self.assertIn('certificado', SefazCaptureConfig.objects.get(company=twin).last_error)

    def test_cliente_recem_autorizado_recebe_caixa_existente_sem_nova_chamada(self):
        self.enable()
        self.execute(self.transport(last='1', maximum='1'))
        twin = Company.objects.create(workspace=self.other_workspace,
            cnpj=self.company.cnpj, legal_name='MESMO CNPJ NOVA AUTORIZACAO')
        self.certificate(twin)
        self.enable(twin)
        transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(transport, twin)
        self.assertFalse(transport.calls)
        self.assertEqual(SefazDocument.objects.filter(state__company=twin).count(), 1)

    def test_reserva_global_impede_consulta_concorrente(self):
        self.enable()
        SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1', source='test', lease_token=uuid.uuid4(),
            lease_until=timezone.now() + timedelta(minutes=5))
        transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        self.assertFalse(transport.calls)
        self.assertFalse(SefazConsultation.objects.exists())

    def test_lease_expirada_retoma_do_nsu_persistido(self):
        self.enable()
        SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1', source='test', last_nsu='000000000000010',
            max_nsu='000000000000020', lease_token=uuid.uuid4(),
            lease_until=timezone.now() - timedelta(seconds=1))
        transport = self.transport(last='11', maximum='20')
        self.execute(transport)
        self.assertEqual(transport.calls[0][2], '000000000000010')

    def test_137_nao_disponivel_aguarda_uma_hora_inclusive_apos_reagendar(self):
        self.enable()
        state = self.execute(self.transport([], status='137', last='0', maximum='0'))
        self.assertEqual(state.last_status, '137')
        self.assertGreater(state.next_attempt_at, timezone.now() + timedelta(minutes=59))
        schedule_company(self.company)
        transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        self.assertFalse(transport.calls)

    def test_656_preserva_cursor_e_registra_motivo_oficial(self):
        self.enable()
        self.execute()
        with self.assertRaises(SefazRejected):
            self.execute(self.transport([], status='656', last='90', maximum='90'))
        stream = SefazDistributionStream.objects.get()
        state = SefazSyncState.objects.get(company=self.company, source='test')
        self.assertEqual(stream.last_nsu, '000000000000002')
        self.assertEqual(stream.reported_nsu, '000000000000090')
        self.assertEqual(state.last_status, '656')
        self.assertGreater(stream.next_attempt_at, timezone.now() + timedelta(minutes=59))
        self.assertEqual(state.consultations.first().status, '656')

    def test_espera_656_respeita_relogio_oficial_adiantado_e_margem(self):
        from portal.services.capture import _claim, _store_response
        from portal.services.sefaz import parse_distribution
        self.enable()
        self.execute(self.transport(last='2', maximum='3'))
        stream = SefazDistributionStream.objects.get(cnpj=self.company.cnpj)
        token = _claim(stream)
        result = parse_distribution(self.transport([], status='656', last='2', maximum='0').payload, '1')
        official = timezone.now() + timedelta(minutes=2)
        from dataclasses import replace
        result = replace(result, responded_at=official)
        stored = _store_response(stream, token, result)
        self.assertGreaterEqual(stored.next_attempt_at, official + timedelta(hours=2))
        self.assertEqual(stored.last_nsu, '000000000000002')

    def test_espera_656_substitui_aviso_worker_antigo_sem_nova_consulta(self):
        config=self.enable()
        config.last_error='Falha antiga';config.last_error_code='worker';config.save()
        wait=timezone.now()+timedelta(hours=3)
        stream=SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1',source='sefaz',last_status='656',last_reason='Consumo Indevido',
            last_nsu='000000000000123',next_attempt_at=wait)
        with patch('portal.services.capture.run_company') as run:
            self.assertEqual(run_due(),[(self.company.pk,'waiting')])
        run.assert_not_called();config.refresh_from_db();stream.refresh_from_db()
        self.assertEqual(config.last_error_code,'sefaz_656')
        self.assertIn('Consumo Indevido',config.last_error)
        self.assertEqual(stream.next_attempt_at,wait)
        self.assertEqual(stream.last_nsu,'000000000000123')

    def test_espera_nao_oculta_falha_local_ainda_presente(self):
        config=self.enable()
        config.last_error='Falha local';config.last_error_code='worker';config.save()
        SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1',source='sefaz',last_status='656',last_error='Processamento pendente',
            next_attempt_at=timezone.now()+timedelta(hours=3))
        with patch('portal.services.capture.recover_received_response',return_value=False),patch('portal.services.capture.run_company'):
            run_due()
        config.refresh_from_db();self.assertEqual(config.last_error_code,'worker')

    def test_rejeicao_de_schema_com_nsu_zero_nao_equivale_a_fim_de_fila(self):
        self.enable()
        with self.assertRaises(SefazRejected):
            self.execute(self.transport([], status='404', last='0', maximum='0'))
        stream = SefazDistributionStream.objects.get()
        self.assertLess(stream.next_attempt_at, timezone.now() + timedelta(minutes=2))
        self.assertGreater(stream.next_attempt_at, timezone.now() + timedelta(seconds=50))

    def test_excecao_interna_nao_expoe_segredo_e_programa_retentativa(self):
        self.enable()
        transport = self.transport()
        transport.fetch = lambda *args: (_ for _ in ()).throw(RuntimeError('SEGREDO NAO EXIBIR'))
        with self.assertRaises(SefazError) as caught:
            self.execute(transport)
        self.assertNotIn('SEGREDO', str(caught.exception))
        stream = SefazDistributionStream.objects.get()
        self.assertIsNone(stream.lease_token)
        self.assertGreater(stream.next_attempt_at, timezone.now())
        history = SefazConsultation.objects.get()
        self.assertEqual(history.error_code, 'capture_failed')
        self.assertNotIn('SEGREDO', history.error)
        self.assertFalse(SefazDocument.objects.exists())

    def test_perda_da_lease_nao_grava_documentos_nem_avanca_nsu(self):
        self.enable()
        transport = self.transport()
        def fetch(*args):
            SefazDistributionStream.objects.update(lease_token=uuid.uuid4())
            return transport.payload
        transport.fetch = fetch
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        self.assertEqual(SefazDistributionStream.objects.get().last_nsu, '000000000000000')
        self.assertFalse(SefazStreamDocument.objects.exists())

    def test_reinicio_apos_recebimento_retoma_importacao_sem_reconsultar_pagina(self):
        self.enable()
        transport = self.transport([(sample_xml(self.company.cnpj), '1', 'procNFe_v4.00.xsd')],
            last='1', maximum='1')
        from portal.services.capture import _fanout
        calls = []
        def fail_after_receive(*args):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('INTERRUPCAO SINTETICA')
            return _fanout(*args)
        with patch('portal.services.capture._fanout', side_effect=fail_after_receive):
            with self.assertRaises(SefazError):
                self.execute(transport)
        self.assertEqual(SefazStreamDocument.objects.count(), 1)
        self.assertFalse(Invoice.objects.exists())
        next_transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(next_transport)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertFalse(next_transport.calls)
        self.assertEqual(SefazDistributionStream.objects.get().last_nsu, '000000000000001')

    def test_origem_falsa_nao_declara_consulta_real(self):
        self.enable()
        transport = self.transport()
        transport.source = 'sefaz'
        with self.assertRaises(SefazError):
            self.execute(transport)
        self.assertFalse(transport.calls)
        self.assertFalse(SefazConsultation.objects.exists())

    def test_worker_isola_falhas_e_processa_todos_clientes_autorizados(self):
        self.enable()
        self.certificate(self.other_company)
        self.enable(self.other_company)
        with patch('portal.services.capture.run_company', side_effect=[
                SefazNotConfigured('Certificado indisponível.'), None]) as run:
            results = run_due()
        self.assertEqual(results, [(self.company.pk, 'error'), (self.other_company.pk, 'completed')])
        self.assertEqual(run.call_args_list[0].args, (self.workspace, self.company.pk))
        self.assertEqual(run.call_args_list[1].args, (self.other_workspace, self.other_company.pk))

    def test_worker_nao_agenda_empresa_desativada_ou_sem_consentimento(self):
        self.enable()
        SefazCaptureConfig.objects.filter(company=self.company).update(enabled=False)
        SefazCaptureConfig.objects.create(company=self.other_company, enabled=True)
        with patch('portal.services.capture.run_company') as run:
            self.assertEqual(run_due(), [])
        run.assert_not_called()

    def test_fanout_real_exige_abrir_a1_do_outro_cliente_antes_de_entregar(self):
        self.enable()
        twin = Company.objects.create(workspace=self.other_workspace,
            cnpj=self.company.cnpj, legal_name='MESMO CNPJ FICTICIO CIFRA INVALIDA')
        self.certificate(twin)
        self.enable(twin)
        transport = self.transport()
        transport.source, transport.is_real = 'sefaz', True
        with patch('portal.services.sefaz_transport.load_identity',
                   side_effect=SefazNotConfigured('Não foi possível abrir o A1 protegido.')) as identity:
            state = self.execute(transport)
        self.assertEqual(state.documents.count(), 1)
        identity.assert_called_once_with(twin)
        self.assertFalse(SefazDocument.objects.filter(state__company=twin).exists())
        self.assertIn('A1 protegido', SefazCaptureConfig.objects.get(company=twin).last_error)

    def test_cooldown_sem_documentos_pendentes_nao_abre_certificado_nem_refaz_fanout(self):
        self.enable()
        SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1', source='sefaz', last_status='137',
            next_attempt_at=timezone.now() + timedelta(hours=1))
        with patch('portal.services.capture.run_company') as run, patch(
                'portal.services.sefaz_transport.load_identity') as identity:
            results = run_due()
        self.assertEqual(results, [(self.company.pk, 'waiting')])
        run.assert_not_called()
        identity.assert_not_called()

    def test_cooldown_com_documento_pendente_retoma_entrega_com_prova_do_a1(self):
        self.enable()
        stream = SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1', source='sefaz', last_status='138',
            last_nsu='000000000000001', max_nsu='000000000000001',
            next_attempt_at=timezone.now() + timedelta(hours=1))
        from portal.services.sefaz import parse_distribution
        doc = parse_distribution(self.transport().payload, '1').documents[0]
        SefazStreamDocument.objects.create(stream=stream, **{
            field: getattr(doc, field) for field in (
                'kind', 'nsu', 'schema_name', 'content_hash', 'access_key', 'event_type', 'xml_content')})
        with patch('portal.services.sefaz_transport.load_identity') as identity, patch(
                'portal.services.sefaz_transport.SefazTransport.fetch') as fetch:
            results = run_due()
        self.assertEqual(results, [(self.company.pk, 'waiting')])
        identity.assert_called_once()
        fetch.assert_not_called()
        self.assertEqual(SefazDocument.objects.filter(state__company=self.company).count(), 1)

    def test_timeout_real_aguarda_uma_hora_sem_repetir_resultado_desconhecido(self):
        self.enable()
        transport = self.transport()
        transport.source, transport.is_real = 'sefaz', True
        transport.fetch = lambda *args: (_ for _ in ()).throw(SefazError('Timeout de 45 segundos.'))
        with self.assertRaises(SefazError):
            self.execute(transport)
        stream = SefazDistributionStream.objects.get(source='sefaz')
        self.assertGreater(stream.next_attempt_at, timezone.now() + timedelta(minutes=59))

    def test_erro_local_pode_ser_reprocessado_sem_nova_chamada_a_sefaz(self):
        self.enable()
        transport = self.transport([(sample_xml(self.company.cnpj), '1', 'procNFe_v4.00.xsd')],
            last='1', maximum='1')
        with patch('portal.services.capture.import_invoice',
                   side_effect=InvoiceImportError('Falha transitória sintética.')):
            state = self.execute(transport)
        doc = state.documents.get()
        self.assertIsNone(doc.invoice)
        self.assertIn('transitória', doc.processing_error)
        self.assertIsNotNone(doc.last_processing_attempt_at)
        self.assertGreater(doc.next_processing_attempt_at, timezone.now() + timedelta(minutes=59))
        SefazDocument.objects.filter(pk=doc.pk).update(next_processing_attempt_at=timezone.now() - timedelta(seconds=1))
        next_transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(next_transport)
        doc.refresh_from_db()
        self.assertIsNotNone(doc.invoice)
        self.assertEqual(doc.processing_error, '')
        self.assertIsNone(doc.next_processing_attempt_at)
        self.assertFalse(next_transport.calls)

    def test_prefilter_do_worker_nao_oculta_retentativa_local(self):
        self.enable()
        stream = SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1', source='sefaz', last_status='138',
            next_attempt_at=timezone.now() + timedelta(hours=1))
        doc = SefazStreamDocument.objects.create(stream=stream, kind='invoice',
            nsu='000000000000001', content_hash='b' * 64, schema_name='procNFe_v4.00.xsd',
            xml_content=sample_xml(self.company.cnpj).decode())
        state = SefazSyncState.objects.get(company=self.company, source='sefaz')
        SefazDocument.objects.create(state=state, stream_document=doc, kind='invoice',
            content_hash=doc.content_hash, schema_name=doc.schema_name, xml_content=doc.xml_content,
            processing_error='Falha antiga já corrigida.', next_processing_attempt_at=timezone.now() - timedelta(seconds=1))
        with patch('portal.services.sefaz_transport.load_identity') as identity, patch(
                'portal.services.sefaz_transport.SefazTransport.fetch') as fetch:
            results = run_due()
        self.assertEqual(results, [(self.company.pk, 'waiting')])
        identity.assert_called_once()
        fetch.assert_not_called()
        self.assertEqual(Invoice.objects.filter(company=self.company).count(), 1)

    def test_backlog_rapido_exige_autorizacao_do_mesmo_cnpj_e_ambiente(self):
        self.enable()
        stream = SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='2', source='sefaz', last_status='138',
            last_nsu='000000000000001', max_nsu='000000000000010')
        self.assertFalse(has_due_backlog())
        stream.environment = '1'
        stream.save()
        self.assertTrue(has_due_backlog())
        self.assertTrue(has_due_backlog(company_id=self.company.pk))
        self.assertFalse(has_due_backlog(company_id=self.other_company.pk))
        stream.next_attempt_at = timezone.now() + timedelta(hours=1)
        stream.save()
        self.assertFalse(has_due_backlog())

    def test_656_com_nsu_reportado_superior_a_maximo_zero_e_rejeicao_preservada(self):
        self.enable()
        self.execute()
        transport = self.transport([], status='656', last='900', maximum='0')
        with self.assertRaises(SefazRejected):
            self.execute(transport)
        stream = SefazDistributionStream.objects.get()
        history = SefazConsultation.objects.first()
        self.assertEqual(history.status, '656')
        self.assertEqual(history.reported_nsu, '000000000000900')
        self.assertEqual(history.max_nsu, '000000000000000')
        self.assertEqual(history.response_xml, transport.payload.decode('utf-8'))
        self.assertEqual(stream.last_nsu, '000000000000002')
        self.assertEqual(stream.max_nsu, '000000000000003')
        self.assertEqual(stream.reported_nsu, '000000000000900')
        self.assertGreater(stream.next_attempt_at, timezone.now() + timedelta(minutes=59))

    def test_resposta_bruta_e_metadados_sobrevivem_a_erro_de_parser_sem_avancar_cursor(self):
        self.enable()
        transport = self.transport(last='8', maximum='2')
        transport.source, transport.is_real = 'sefaz', True
        with self.assertRaisesMessage(SefazError, 'supera o NSU máximo'):
            self.execute(transport)
        history = SefazConsultation.objects.get()
        self.assertEqual(history.response_xml, transport.payload.decode('utf-8'))
        self.assertEqual(history.status, '138')
        self.assertIn('SINTETICA', history.reason)
        self.assertIsNotNone(history.official_response_at)
        self.assertEqual(history.reported_nsu, '000000000000008')
        self.assertEqual(history.max_nsu, '000000000000002')
        self.assertIn('supera', history.error)
        stream = SefazDistributionStream.objects.get()
        self.assertEqual(stream.last_nsu, '000000000000000')
        self.assertEqual(stream.last_status, '138')
        self.assertGreater(stream.next_attempt_at, timezone.now() + timedelta(minutes=59))
        self.assertFalse(SefazStreamDocument.objects.exists())

    def test_resposta_unsafe_guardada_privada_sem_extrair_metadados(self):
        self.enable()
        transport = SyntheticTransport(b'<!DOCTYPE x [<!ENTITY s "INSEGURO">]><x>&s;</x>')
        with self.assertRaises(SefazError):
            self.execute(transport)
        history = SefazConsultation.objects.get()
        self.assertEqual(history.response_xml, transport.payload.decode('utf-8'))
        self.assertEqual(history.status, '')
        self.assertEqual(history.reason, '')
        self.assertIsNone(history.official_response_at)

    def test_evidencia_e_persistida_antes_do_parser(self):
        self.enable()
        transport = self.transport()
        def parser(payload, environment):
            self.assertEqual(SefazConsultation.objects.get().response_xml, payload.decode('utf-8'))
            raise SefazError('Falha sintética após preservar evidência.')
        with patch('portal.services.capture.parse_distribution', side_effect=parser):
            with self.assertRaises(SefazError):
                self.execute(transport)
        self.assertEqual(SefazConsultation.objects.get().status, '138')

    def test_evidencia_antecede_validacao_xsd_do_transporte(self):
        self.enable()
        transport = self.transport()
        def validator(payload):
            self.assertEqual(SefazConsultation.objects.get().response_xml, payload.decode('utf-8'))
            raise SefazError('Resposta incompatível com XSD.')
        transport.validate_response = validator
        with self.assertRaisesMessage(SefazError, 'incompatível com XSD'):
            self.execute(transport)
        history = SefazConsultation.objects.get()
        self.assertEqual(history.status, '138')
        self.assertIn('XSD', history.error)

    def orphan(self, elapsed=10, next_at=None):
        now = timezone.now()
        return SefazDistributionStream.objects.create(cnpj=self.company.cnpj,
            environment='1', source='sefaz', last_nsu='000000000000012',
            max_nsu='000000000000100', last_attempt_at=now - timedelta(minutes=elapsed),
            lease_token=uuid.uuid4(), lease_until=now - timedelta(minutes=elapsed - 5),
            next_attempt_at=next_at)

    def test_lease_real_orfa_aguarda_hora_da_tentativa_original_sem_avancar_cursor(self):
        self.enable()
        stream = self.orphan()
        transport = self.transport(last='13', maximum='100')
        transport.source, transport.is_real = 'sefaz', True
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        stream.refresh_from_db()
        self.assertFalse(transport.calls)
        self.assertIsNone(stream.lease_token)
        self.assertIsNone(stream.lease_until)
        self.assertEqual(stream.next_attempt_at, stream.last_attempt_at + timedelta(hours=1))
        self.assertEqual(stream.last_nsu, '000000000000012')
        self.assertEqual(stream.failure_count, 1)
        self.assertIn('resultado oficial é incerto', stream.last_error)
        # Repetir a verificação não acrescenta outra hora ou outra falha.
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        stream.refresh_from_db()
        self.assertEqual(stream.failure_count, 1)
        self.assertEqual(stream.next_attempt_at, stream.last_attempt_at + timedelta(hours=1))

    def test_lease_real_orfa_preserva_espera_preexistente_mais_longa(self):
        self.enable()
        future = timezone.now() + timedelta(hours=2)
        stream = self.orphan(next_at=future)
        transport = self.transport()
        transport.source, transport.is_real = 'sefaz', True
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        stream.refresh_from_db()
        self.assertEqual(stream.next_attempt_at, future)

    def test_hora_de_lease_orfa_ja_decorrida_permite_query_sem_espera_extra(self):
        self.enable()
        self.orphan(elapsed=70)
        transport = self.transport([], status='137', last='12', maximum='12')
        transport.source, transport.is_real = 'sefaz', True
        state = self.execute(transport)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][2], '000000000000012')
        self.assertEqual(state.last_status, '137')
        self.assertEqual(state.last_error, '')

    def test_recuperacao_de_lease_fecha_historico_incompleto_sem_inventar_resposta(self):
        self.enable()
        stream = self.orphan()
        state = SefazSyncState.objects.get(company=self.company, source='sefaz')
        history = SefazConsultation.objects.create(state=state,
            requested_at=stream.last_attempt_at + timedelta(milliseconds=5),
            requested_nsu=stream.last_nsu)
        completed = SefazConsultation.objects.create(state=state,
            requested_at=stream.last_attempt_at - timedelta(hours=2),
            completed_at=stream.last_attempt_at - timedelta(hours=1),
            requested_nsu='000000000000001', status='138')
        with patch('portal.services.capture.run_company') as run:
            self.assertEqual(run_due(), [(self.company.pk, 'waiting')])
        run.assert_not_called()
        history.refresh_from_db()
        completed.refresh_from_db()
        self.assertEqual(history.error_code, 'interrupted')
        self.assertIsNotNone(history.completed_at)
        self.assertEqual(history.status, '')
        self.assertIsNone(history.official_response_at)
        self.assertEqual(completed.error_code, '')

    def test_recuperacao_de_lease_preserva_metadados_extraidos_do_xml_ja_gravado(self):
        self.enable()
        stream = self.orphan()
        state = SefazSyncState.objects.get(company=self.company, source='sefaz')
        payload = self.transport([], status='656', last='900', maximum='0').payload
        history = SefazConsultation.objects.create(state=state,
            requested_at=stream.last_attempt_at + timedelta(milliseconds=5),
            requested_nsu=stream.last_nsu, response_xml=payload.decode())
        run_due()
        history.refresh_from_db()
        stream.refresh_from_db()
        self.assertEqual(history.error_code, 'interrupted')
        self.assertEqual(history.status, '656')
        self.assertEqual(history.reported_nsu, '000000000000900')
        self.assertEqual(history.max_nsu, '000000000000000')
        self.assertIsNotNone(history.official_response_at)
        self.assertEqual(stream.last_nsu, '000000000000012')

    def test_cas_nao_limpa_reserva_que_outro_processo_renovou(self):
        self.enable()
        stream = self.orphan()
        new_token = uuid.uuid4()
        SefazDistributionStream.objects.filter(pk=stream.pk).update(
            lease_token=new_token, lease_until=timezone.now() + timedelta(minutes=5))
        from portal.services.capture import _recover_orphan
        self.assertFalse(_recover_orphan(stream))
        stream.refresh_from_db()
        self.assertEqual(stream.lease_token, new_token)
        self.assertEqual(stream.failure_count, 0)

    def test_recuperacao_respeita_cooldown_estendido_desde_leitura_do_stream(self):
        self.enable()
        stream = self.orphan()
        future = timezone.now() + timedelta(hours=3)
        SefazDistributionStream.objects.filter(pk=stream.pk).update(next_attempt_at=future)
        from portal.services.capture import _recover_orphan
        self.assertTrue(_recover_orphan(stream))
        stream.refresh_from_db()
        self.assertEqual(stream.next_attempt_at, future)
