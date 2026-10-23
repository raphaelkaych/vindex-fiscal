"""Retomada e recuperação: certificados, respostas e documentos sintéticos."""
import re
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from portal.models import Company, DigitalCertificate, Invoice, Workspace
from portal.sefaz_models import SefazCaptureConfig, SefazConsultation, SefazDistributionStream, SefazNsuRecovery, SefazSyncState
from portal.services.capture import configure_capture, recover_received_response, run_company, run_due
from portal.services.sefaz import SefazBusy, SefazError, SefazRejected, parse_distribution
from portal.services.sefaz_recovery import claim_recovery, resume_cursor
from portal.services.sefaz_transport import distribution_request
from portal.test_sefaz import SyntheticTransport, response, summary


def nsu(value):
    return str(value).zfill(15)


def payload(documents=(), **kwargs):
    raw = response(documents, environment='1', **kwargs)
    return re.sub(rb'(\d{2}:\d{2}:\d{2})\.\d+', rb'\1', raw)


class RecoveryTransport(SyntheticTransport):
    source = 'sefaz'
    is_real = True

    def fetch_nsu(self, company, environment, number):
        self.calls.append((company.pk, environment, number))
        return self.payload


class NsuRecoveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('recuperacao@example.test')
        self.workspace = Workspace.objects.create(owner=self.user, name='RECUPERACAO FICTICIA')
        self.company = Company.objects.create(workspace=self.workspace, legal_name='EMPRESA FICTICIA', cnpj='00000001000136')
        DigitalCertificate.objects.create(company=self.company, encrypted_file=b'FICTICIO', encrypted_password=b'FICTICIO',
            subject_name='FICTICIO', holder_cnpj=self.company.cnpj, fingerprint='f'*64,
            valid_from=timezone.now()-timedelta(days=1), valid_until=timezone.now()+timedelta(days=30))
        configure_capture(self.workspace, self.company.pk, actor=self.user, authorize_read=True)
        self.state = SefazSyncState.objects.get(company=self.company)
        self.stream = SefazDistributionStream.objects.create(cnpj=self.company.cnpj, environment='1',
            source='sefaz', last_nsu=nsu(10), max_nsu=nsu(40))
        self.identity = patch('portal.services.sefaz_transport.load_identity')
        self.identity.start()
        self.addCleanup(self.identity.stop)

    def reject(self, reported=20, wait=None, reason='Deve ser utilizado o ultNSU nas solicitacoes subsequentes. Tente apos 1 hora'):
        raw = payload(status='656', last=nsu(reported), maximum=nsu(0))
        raw = raw.replace(b'RESPOSTA SINTETICA SEM VALOR FISCAL', reason.encode())
        self.stream.last_status = '656'
        self.stream.reported_nsu = nsu(reported)
        self.stream.next_attempt_at = wait
        self.stream.save()
        return SefazConsultation.objects.create(state=self.state, requested_at=timezone.now()-timedelta(hours=3),
            completed_at=timezone.now()-timedelta(hours=3), requested_nsu=nsu(10), reported_nsu=nsu(reported), status='656', response_xml=raw.decode())

    def execute(self, raw):
        transport = RecoveryTransport(raw)
        result = run_company(self.workspace, self.company.pk, transport=transport)
        return result, transport

    def job(self, first=11, last=20):
        self.stream.next_attempt_at = timezone.now()+timedelta(hours=2)
        self.stream.save()
        return SefazNsuRecovery.objects.create(stream=self.stream, first_nsu=nsu(first), last_nsu=nsu(last), next_nsu=nsu(first))

    def test_retomada_usa_resposta_oficial_e_preserva_intervalo_nao_recebido(self):
        self.reject()
        state, transport = self.execute(payload([(summary(), nsu(21), 'resNFe_v1.01.xsd')], last=nsu(21), maximum=nsu(21)))
        self.assertEqual(transport.calls[0][2], nsu(20))
        self.assertEqual(state.last_nsu, nsu(21))
        job = self.stream.recoveries.get()
        self.assertEqual((job.first_nsu, job.last_nsu, job.next_nsu), (nsu(11), nsu(20), nsu(11)))
        self.assertEqual(self.state.consultations.first().resume_from_nsu, nsu(10))
        self.assertEqual(Invoice.objects.count(), 0)

    def test_retomada_nao_antecipa_cooldown_antigo(self):
        wait = timezone.now()+timedelta(minutes=30)
        self.reject(wait=wait)
        transport = RecoveryTransport(payload(status='137', last=nsu(20), maximum=nsu(20)))
        with self.assertRaises(SefazBusy):
            run_company(self.workspace, self.company.pk, transport=transport)
        self.assertFalse(transport.calls)
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.last_nsu, nsu(10))
        self.assertEqual(self.stream.next_attempt_at, wait)
        self.assertFalse(self.stream.recoveries.exists())

    def test_metadados_sem_corpo_nao_autorizam_troca(self):
        item = self.reject()
        item.response_xml = ''
        item.save()
        self.assertEqual(resume_cursor(self.stream), nsu(10))

    def test_rejeicao_por_quota_nao_autoriza_retomada(self):
        self.reject(reason='Ultrapassou o limite de consultas por hora')
        self.assertEqual(resume_cursor(self.stream), nsu(10))

    def test_resposta_outro_ambiente_nao_e_usada(self):
        item = self.reject()
        item.response_xml = item.response_xml.replace('<tpAmb>1</tpAmb>', '<tpAmb>2</tpAmb>')
        item.save()
        with self.assertRaises(SefazError):
            resume_cursor(self.stream)

    def test_nova_656_na_retomada_nao_cria_lacuna_nem_avanca_cursor(self):
        self.reject()
        raw = payload(status='656', last=nsu(22), maximum=nsu(0)).replace(b'RESPOSTA SINTETICA SEM VALOR FISCAL', b'Deve ser utilizado o ultNSU')
        with self.assertRaises(SefazRejected):
            self.execute(raw)
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.last_nsu, nsu(10))
        self.assertFalse(self.stream.recoveries.exists())
        self.assertGreater(self.stream.blocked_until, timezone.now()+timedelta(minutes=119))
        self.assertEqual(resume_cursor(self.stream), nsu(22))

    def test_consulta_pontual_nao_altera_cursor_da_distribuicao(self):
        job = self.job()
        state, transport = self.execute(payload([(summary(), nsu(11), 'resNFe_v1.01.xsd')], last=nsu(0), maximum=nsu(0)))
        self.stream.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(self.stream.last_nsu, nsu(10))
        self.assertEqual(self.stream.max_nsu, nsu(40))
        self.assertEqual(job.next_nsu, nsu(12))
        self.assertEqual(job.recovered_count, 1)
        self.assertEqual(self.state.consultations.first().query_kind, 'consNSU')
        self.assertEqual(state.documents.count(), 1)

    def test_nsu_nao_disponivel_fica_explicito_sem_inventar_documento(self):
        job = self.job(first=11, last=11)
        self.execute(payload(status='137', last=nsu(0), maximum=nsu(0)))
        job.refresh_from_db()
        self.assertEqual(job.unavailable_count, 1)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(self.stream.documents.count(), 0)
        from portal.capture_views import _status, _activity
        self.state.refresh_from_db()
        activity=_activity(self.company,self.company.capture_config,self.state)
        status,tone=_status(self.company,self.company.capture_config,self.state,{'active':True},activity)
        self.assertIn('NSUs indisponíveis',status)
        self.assertEqual(tone,'warning')

    def test_nsu_divergente_na_consulta_pontual_nao_avanca_recuperacao(self):
        job = self.job()
        with self.assertRaises(SefazError):
            self.execute(payload([(summary(), nsu(12), 'resNFe_v1.01.xsd')], last=nsu(0), maximum=nsu(0)))
        job.refresh_from_db()
        self.assertEqual(job.next_nsu, nsu(11))
        self.assertFalse(self.stream.documents.exists())

    def test_limite_rolling_por_cnpj_independe_do_workspace(self):
        job = self.job()
        now = timezone.now()
        for offset in range(18):
            SefazConsultation.objects.create(state=self.state, requested_at=now-timedelta(minutes=59, seconds=offset),
                requested_nsu=nsu(offset+1), query_kind='consNSU')
        token, _ = claim_recovery(self.stream, job)
        self.assertIsNone(token)
        job.refresh_from_db()
        self.assertGreater(job.next_attempt_at, now)
        self.stream.refresh_from_db()
        self.assertIsNone(self.stream.lease_token)

    def test_consultas_pontuais_respeitam_intervalo_e_reserva_global(self):
        job = self.job()
        token, _ = claim_recovery(self.stream, job)
        self.assertIsNotNone(token)
        with self.assertRaises(SefazBusy):
            claim_recovery(self.stream, job)

    def test_656_pontual_bloqueia_tambem_distribuicao(self):
        self.stream.reported_nsu=nsu(99)
        self.stream.save()
        job = self.job()
        with self.assertRaises(SefazRejected):
            self.execute(payload(status='656', last=nsu(0), maximum=nsu(0)))
        self.stream.refresh_from_db()
        job.refresh_from_db()
        self.assertGreater(self.stream.blocked_until, timezone.now()+timedelta(minutes=119))
        self.assertEqual(job.next_nsu, nsu(11))
        self.assertEqual(self.stream.last_nsu, nsu(10))
        self.assertEqual(self.stream.reported_nsu,nsu(0))

    def test_captura_pausada_nao_recupera_por_fora_da_autorizacao(self):
        self.job()
        SefazCaptureConfig.objects.filter(company=self.company).update(enabled=False)
        with patch('portal.services.sefaz_transport.official_post') as network:
            self.assertEqual(run_due(), [])
        network.assert_not_called()

    def test_corpo_aceito_na_retomada_pode_ser_recuperado_localmente(self):
        self.reject()
        raw = payload([(summary(), nsu(21), 'resNFe_v1.01.xsd')], last=nsu(21), maximum=nsu(21))
        item = SefazConsultation.objects.create(state=self.state, requested_at=timezone.now(), requested_nsu=nsu(20),
            resume_from_nsu=nsu(10), status='138', response_xml=raw.decode(), error='Falha sintética')
        wait = timezone.now()+timedelta(hours=1)
        self.stream.next_attempt_at = wait
        self.stream.save()
        self.assertTrue(recover_received_response(self.company, self.company.capture_config, self.stream))
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.last_nsu, nsu(21))
        self.assertGreaterEqual(self.stream.next_attempt_at, wait)
        self.assertTrue(self.stream.recoveries.exists())

    def test_pedido_consnsu_valida_no_schema_oficial(self):
        from portal.services.sefaz_schema import validate_message
        raw = distribution_request(self.company.cnpj, '1', nsu(11), query_kind='consNSU')
        validate_message(raw, 'distDFeInt_v1.01.xsd', 'distDFeInt')
        self.assertIn(b'<consNSU>', raw)
        self.assertNotIn(b'<distNSU>', raw)

    def test_dois_clientes_compartilham_um_consumidor_na_recuperacao(self):
        self.job()
        other_user = User.objects.create_user('segundo-vinculo@example.test')
        other_workspace = Workspace.objects.create(owner=other_user, name='SEGUNDO FICTICIO')
        other = Company.objects.create(workspace=other_workspace, legal_name='MESMO CNPJ FICTICIO', cnpj=self.company.cnpj)
        certificate = DigitalCertificate.objects.get(company=self.company)
        certificate.pk = None
        certificate.company = other
        certificate.save()
        configure_capture(other_workspace, other.pk, actor=other_user, authorize_read=True)
        transport = RecoveryTransport(payload([(summary(), nsu(11), 'resNFe_v1.01.xsd')], last=nsu(0), maximum=nsu(0)))
        with patch('portal.services.sefaz_transport.SefazTransport', return_value=transport):
            run_due()
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(SefazDistributionStream.objects.count(), 1)
        self.assertEqual(self.state.documents.count(), 1)
        self.assertEqual(SefazSyncState.objects.get(company=other).documents.count(), 1)

    def test_recuperacao_preservada_reprocessa_localmente_sem_http(self):
        job = self.job()
        raw = payload([(summary(), nsu(11), 'resNFe_v1.01.xsd')], last=nsu(0), maximum=nsu(0))
        SefazConsultation.objects.create(state=self.state, requested_at=timezone.now(), requested_nsu=nsu(11),
            query_kind='consNSU', recovery=job, status='138', response_xml=raw.decode(), error='Falha sintética de armazenamento')
        wait = self.stream.next_attempt_at
        with patch('portal.services.sefaz_transport.official_post') as post:
            self.assertTrue(recover_received_response(self.company, self.company.capture_config, self.stream))
        post.assert_not_called()
        self.stream.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(job.next_nsu, nsu(12))
        self.assertEqual(self.stream.last_nsu, nsu(10))
        self.assertEqual(self.stream.next_attempt_at, wait)
        self.assertFalse(recover_received_response(self.company, self.company.capture_config, self.stream))

    def test_erro_de_gravacao_reverte_documentos_e_intervalo_juntos(self):
        self.reject()
        raw = payload([(summary(), nsu(21), 'resNFe_v1.01.xsd')], last=nsu(21), maximum=nsu(21))
        with patch('portal.services.sefaz_recovery.record_resume_gap', side_effect=SefazError('Falha sintética de armazenamento')):
            with self.assertRaises(SefazError):
                self.execute(raw)
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.last_nsu, nsu(10))
        self.assertFalse(self.stream.documents.exists())
        self.assertFalse(self.stream.recoveries.exists())
        self.assertTrue(self.state.consultations.first().response_xml)

    def test_timeout_pontual_bloqueia_repeticao_de_ambas_as_filas(self):
        job = self.job()
        previous_wait = self.stream.next_attempt_at
        transport = RecoveryTransport(b'')
        with patch.object(transport, 'fetch_nsu', side_effect=SefazError('Timeout sintético')):
            with self.assertRaises(SefazError):
                run_company(self.workspace, self.company.pk, transport=transport)
        self.stream.refresh_from_db()
        self.assertGreaterEqual(self.stream.next_attempt_at,previous_wait)
        self.assertGreater(self.stream.blocked_until, timezone.now()+timedelta(minutes=59))
        with self.assertRaises(SefazBusy):
            claim_recovery(self.stream, job)

    def test_cliente_sem_certificado_valido_nao_ve_metadados_compartilhados(self):
        from portal.capture_views import _shared_metadata
        self.job()
        certificate = DigitalCertificate.objects.get(company=self.company)
        certificate.valid_until = timezone.now()-timedelta(seconds=1)
        certificate.save()
        company = Company.objects.select_related('workspace','certificate').get(pk=self.company.pk)
        self.assertEqual(_shared_metadata(company, self.company.capture_config), {})

    def test_painel_identifica_intervalo_pendente_sem_afirmar_cobertura_completa(self):
        from django.urls import reverse
        self.job()
        self.client.force_login(self.user)
        result = self.client.get(reverse('capture_detail', args=[self.company.pk]))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'recuperação do histórico pendente')
        self.assertContains(result, 'não há garantia de histórico completo')

    def test_nsu_ja_preservado_e_pulado_sem_repetir_http(self):
        from portal.sefaz_models import SefazStreamDocument
        doc = parse_distribution(payload([(summary(), nsu(11), 'resNFe_v1.01.xsd')],last=nsu(11),maximum=nsu(11)), '1').documents[0]
        SefazStreamDocument.objects.create(stream=self.stream, **{field:getattr(doc, field) for field in
            ('nsu','kind','content_hash','schema_name','access_key','event_type','xml_content')})
        job = self.job(first=11,last=11)
        token, _ = claim_recovery(self.stream, job)
        self.assertIsNone(token)
        job.refresh_from_db()
        self.assertIsNotNone(job.completed_at)

    def test_recuperacao_finalizada_nao_repete_contagem_apos_falha_de_entrega(self):
        job = self.job(first=11,last=11)
        self.execute(payload(status='137',last=nsu(0),maximum=nsu(0)))
        item = self.state.consultations.first()
        item.error = 'Falha sintética posterior ao armazenamento'
        item.save()
        self.assertFalse(recover_received_response(self.company,self.company.capture_config,self.stream))
        job.refresh_from_db()
        self.assertEqual(job.unavailable_count,1)

    def test_limite_de_quinze_digitos_na_ultima_posicao(self):
        job = self.job(first=999999999999999,last=999999999999999)
        self.execute(payload(status='137',last=nsu(0),maximum=nsu(0)))
        job.refresh_from_db()
        self.assertEqual(len(job.next_nsu),15)
        self.assertIsNotNone(job.completed_at)

    def test_auditoria_separa_retomada_e_consulta_pontual_da_cadeia_sequencial(self):
        from io import StringIO
        import json
        from django.core.management import call_command
        SefazConsultation.objects.create(state=self.state,requested_at=timezone.now()-timedelta(hours=5),
            completed_at=timezone.now()-timedelta(hours=5),requested_nsu=nsu(0),reported_nsu=nsu(10),max_nsu=nsu(40),status='138')
        self.reject()
        self.execute(payload([(summary(),nsu(21),'resNFe_v1.01.xsd')],last=nsu(21),maximum=nsu(21)))
        self.execute(payload(status='137',last=nsu(0),maximum=nsu(0)))
        out = StringIO()
        call_command('auditar_distribuicao',cnpj=self.company.cnpj,ambiente='1',stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(data['local_accepted_chain_differences'],[])
        self.assertEqual(data['attempts_before_documented_one_hour'],[])
        self.assertEqual(len(data['recorded_resumptions_after_656']),1)
