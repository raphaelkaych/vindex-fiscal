"""Recuperação por chave com documentos sintéticos e sem rede."""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from xml.etree import ElementTree as XML

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from portal.models import FiscalDocument, Invoice, SefazConsultation, SefazKeyRecovery
from portal.services.capture import run_company, recover_received_response
from portal.services.capture_policy import consumption_interval
from portal.services.sefaz import SefazBusy, SefazError, SefazRejected, parse_distribution
from portal.services.sefaz_key_recovery import queue_from_cte, claim_key_recovery
from portal.services.sefaz_recovery import point_query_allowed_at
from portal.services.sefaz_transport import distribution_request
from portal.test_danfe import complete_synthetic_xml
from portal.test_sefaz import summary, event
from portal import test_sefaz_recovery as recovery_fixtures
from portal.test_sefaz_recovery import RecoveryTransport, payload, nsu


def synthetic_key(number=1):
    base = '35' + '2610' + '00000002000180' + '55' + '001' + str(number).zfill(9) + '1' + '12345678'
    remainder = sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(base))) % 11
    return base + str(0 if remainder < 2 else 11 - remainder)


def evidence(company, key, environment='1'):
    raw = f'<cteProc xmlns="http://www.portalfiscal.inf.br/cte"><CTe><infCte><dest><CNPJ>{company.cnpj}</CNPJ></dest><infCTeNorm><infDoc><infNFe><chave>{key}</chave></infNFe></infDoc></infCTeNorm></infCte></CTe></cteProc>'
    return FiscalDocument.objects.create(company=company, service='cte', environment=environment,
        access_key='FICTICIO-'+key, number='1', issuer_name='FICTICIO', issuer_cnpj='00000002000180',
        role='destinatario', issued_at=timezone.now(), total='10.00', xml_content=raw)


class KeyTransport(RecoveryTransport):
    def validate_response(self, raw, *, query_kind='distNSU'):
        from portal.services.sefaz_transport import SefazTransport
        SefazTransport().validate_response(raw,query_kind=query_kind)

    def fetch_key(self, company, environment, key):
        self.calls.append((company.pk, environment, key))
        return self.payload


class KeyRecoveryTests(TestCase):
    def setUp(self):
        recovery_fixtures.NsuRecoveryTests.setUp(self)
        self.key = synthetic_key()
        self.evidence = evidence(self.company, self.key)
        self.job, _ = queue_from_cte(self.workspace, self.company.pk, self.evidence.pk, self.key)

    def execute(self, raw):
        return run_company(self.workspace, self.company.pk, transport=KeyTransport(raw))

    def test_pedido_por_chave_e_valido_no_schema_oficial(self):
        from portal.services.sefaz_schema import validate_message
        raw = distribution_request(self.company.cnpj, '1', self.key, query_kind='consChNFe')
        validate_message(raw, 'distDFeInt_v1.01.xsd', 'distDFeInt')
        self.assertIn(b'<consChNFe><chNFe>', raw)
        with self.assertRaises(SefazError):
            distribution_request(self.company.cnpj, '1', self.key[:-1]+str((int(self.key[-1])+1)%10), query_kind='consChNFe')

    def test_compatibilidade_sem_cursores_e_restrita_a_consulta_por_chave(self):
        from portal.services.sefaz_transport import SefazTransport
        import re
        raw=payload([(summary(self.key),None,'resNFe_v1.01.xsd')])
        raw=re.sub(rb'<(?:ultNSU|maxNSU)>[^<]*</(?:ultNSU|maxNSU)>',b'',raw)
        SefazTransport().validate_response(raw,query_kind='consChNFe')
        with self.assertRaises(SefazError):SefazTransport().validate_response(raw)
        with self.assertRaises(SefazError):SefazTransport().validate_response(re.sub(rb'<dhResp>[^<]*</dhResp>',b'',raw),query_kind='consChNFe')
        result=parse_distribution(raw,'1',query_kind='consChNFe',requested_key=self.key)
        self.assertEqual(result.last_nsu,'');self.assertEqual(result.max_nsu,'')
        self.execute(raw)
        self.job.refresh_from_db();self.assertEqual(self.job.result,'summary')

    def test_consulta_importa_xml_sem_nsu_e_preserva_progresso(self):
        self.stream.failure_count=7;self.stream.save()
        raw = complete_synthetic_xml(self.company.cnpj)
        root = XML.fromstring(raw)
        n = {'n':'http://www.portalfiscal.inf.br/nfe'}
        old = root.find('n:NFe/n:infNFe',n).get('Id').removeprefix('NFe')
        raw = raw.replace(old.encode(),self.key.encode())
        self.execute(payload([(raw,None,'procNFe_v4.00.xsd')],last=nsu(0),maximum=nsu(0)))
        self.stream.refresh_from_db();self.job.refresh_from_db()
        self.assertEqual(self.stream.last_nsu, nsu(10));self.assertEqual(self.stream.max_nsu,nsu(40))
        self.assertEqual(self.stream.failure_count,0)
        self.assertEqual(self.job.result,'xml');self.assertIsNotNone(self.job.completed_at)
        self.assertTrue(Invoice.objects.filter(company=self.company,access_key=self.key).exists())
        self.assertEqual(SefazConsultation.objects.get().requested_key,self.key)
        self.assertEqual(SefazConsultation.objects.get().query_kind,'consChNFe')

    def test_137_pontual_nao_comprova_fim_do_historico(self):
        self.execute(payload(status='137',last=nsu(0),maximum=nsu(0)))
        self.job.refresh_from_db();self.stream.refresh_from_db()
        self.assertEqual(self.job.result,'unavailable');self.assertFalse(self.stream.documents.exists())
        self.assertEqual(self.stream.last_nsu,nsu(10))

    def test_656_nao_e_contornado_por_consulta_por_chave(self):
        wait=timezone.now()+timedelta(hours=2)
        self.stream.blocked_until=wait;self.stream.next_attempt_at=wait;self.stream.save()
        with patch('portal.services.sefaz_transport.official_post') as network:
            with self.assertRaises(SefazBusy):self.execute(payload(status='137'))
        network.assert_not_called();self.assertFalse(SefazConsultation.objects.exists())

    def test_rejeicao_persistente_amplia_espera_sem_avancar_cursor(self):
        self.stream.failure_count=7;self.stream.save()
        with self.assertRaises(SefazRejected):self.execute(payload(status='656',last=nsu(0),maximum=nsu(0)))
        self.stream.refresh_from_db();self.job.refresh_from_db()
        self.assertGreater(self.stream.blocked_until,timezone.now()+timedelta(hours=7,minutes=59))
        self.assertEqual(self.stream.last_nsu,nsu(10));self.assertIsNone(self.job.completed_at)
        self.assertEqual(consumption_interval(100),timedelta(hours=24))

    def test_656_por_chave_nao_toma_o_lugar_da_distribuicao_na_proxima_janela(self):
        with self.assertRaises(SefazRejected):self.execute(payload(status='656',last=nsu(0),maximum=nsu(0)))
        self.stream.refresh_from_db();self.stream.blocked_until=timezone.now()-timedelta(seconds=1)
        self.stream.next_attempt_at=timezone.now()-timedelta(seconds=1);self.stream.save()
        self.job.next_attempt_at=timezone.now()-timedelta(seconds=1);self.job.save()
        self.execute(payload(status='137',last=nsu(10),maximum=nsu(10)))
        self.assertEqual(SefazConsultation.objects.order_by('-pk').first().query_kind,'distNSU')

    def test_quota_e_unica_para_nsu_e_chave(self):
        for index in range(18):
            SefazConsultation.objects.create(state=self.state,stream=self.stream,requested_at=timezone.now()-timedelta(minutes=50,seconds=index),
                requested_nsu=nsu(11),query_kind='consNSU' if index%2 else 'consChNFe')
        self.assertGreater(point_query_allowed_at(self.stream,timezone.now()),timezone.now())
        token,_=claim_key_recovery(self.stream,self.job,self.company)
        self.assertIsNone(token)

    def test_chave_divergente_ou_evento_nao_e_importado(self):
        for raw in [summary(synthetic_key(2)),event(self.key)]:
            schema='resNFe_v1.01.xsd' if b'resNFe' in raw else 'procEventoNFe_v1.00.xsd'
            with self.assertRaises(SefazError):
                parse_distribution(payload([(raw,None,schema)]),'1',query_kind='consChNFe',requested_key=self.key)

    def test_falta_de_permissao_fica_finalizada_sem_repetir(self):
        with self.assertRaises(SefazRejected):self.execute(payload(status='640',last=nsu(0),maximum=nsu(0)))
        self.job.refresh_from_db();self.assertEqual(self.job.result,'rejected');self.assertIsNotNone(self.job.completed_at)

    def test_referencia_de_outro_cliente_e_recusada(self):
        from portal.tests import create_account
        _,_,other=create_account('chave-outro@example.test')
        foreign=evidence(other,synthetic_key(2))
        with self.assertRaises(SefazError):queue_from_cte(self.workspace,self.company.pk,foreign.pk,synthetic_key(2))

    def test_referencia_repetida_nao_gera_segunda_consulta(self):
        job,new=queue_from_cte(self.workspace,self.company.pk,self.evidence.pk,self.key)
        self.assertFalse(new);self.assertEqual(job.pk,self.job.pk);self.assertEqual(SefazKeyRecovery.objects.count(),1)

    def test_resumo_nao_e_transformado_em_nota_completa(self):
        self.execute(payload([(summary(self.key),None,'resNFe_v1.01.xsd')],last=nsu(0),maximum=nsu(0)))
        self.job.refresh_from_db();self.assertEqual(self.job.result,'summary');self.assertFalse(Invoice.objects.exists())

    def test_replay_local_por_chave_nao_repete_http(self):
        import re
        xml=complete_synthetic_xml(self.company.cnpj)
        root=XML.fromstring(xml);ns={'n':'http://www.portalfiscal.inf.br/nfe'}
        old=root.find('n:NFe/n:infNFe',ns).get('Id').removeprefix('NFe')
        xml=xml.replace(old.encode(),self.key.encode())
        raw=payload([(xml,None,'procNFe_v4.00.xsd')],last=nsu(0),maximum=nsu(0))
        raw=re.sub(rb'<(?:ultNSU|maxNSU)>[^<]*</(?:ultNSU|maxNSU)>',b'',raw)
        wait=timezone.now()+timedelta(hours=1)
        self.stream.next_attempt_at=wait;self.stream.blocked_until=wait;self.stream.save()
        config=self.company.capture_config;config.last_error='FALHA FICTICIA DE SCHEMA';config.last_error_code='capture_failed';config.save()
        item=SefazConsultation.objects.create(state=self.state,stream=self.stream,requested_at=timezone.now(),
            requested_nsu='',query_kind='consChNFe',requested_key=self.key,key_recovery=self.job,status='138',response_xml=raw.decode(),error='FALHA FICTICIA')
        with patch('portal.services.sefaz_transport.official_post') as network:
            self.assertTrue(recover_received_response(self.company,self.company.capture_config,self.stream))
            self.assertFalse(recover_received_response(self.company,self.company.capture_config,self.stream))
        network.assert_not_called();self.job.refresh_from_db();self.assertIsNotNone(self.job.completed_at)
        item.refresh_from_db();self.state.refresh_from_db();self.stream.refresh_from_db();config.refresh_from_db()
        self.assertEqual(item.counts['imported'],1);self.assertEqual(self.state.last_counts['invoice'],1)
        self.assertEqual(self.stream.next_attempt_at,wait);self.assertEqual(self.stream.last_nsu,nsu(10))
        self.assertEqual(Invoice.objects.filter(company=self.company).count(),1);self.assertEqual(config.last_error,'')

    def test_comando_sem_executar_so_diagnostica(self):
        output=StringIO()
        call_command('recuperar_nfe_referenciadas',company=self.company.pk,desde=timezone.localdate().isoformat(),stdout=output)
        self.assertIn('Diagnóstico sem alterações',output.getvalue())
        self.assertNotIn(self.key,output.getvalue())

    def test_novo_vinculo_precisa_de_referencia_propria_para_reagendar(self):
        self.job.company=None;self.job.evidence=None;self.job.completed_at=timezone.now();self.job.result='rejected';self.job.save()
        job,new=queue_from_cte(self.workspace,self.company.pk,self.evidence.pk,self.key)
        self.assertTrue(new);self.assertEqual(job.pk,self.job.pk);self.assertEqual(job.company_id,self.company.pk)
        self.assertIsNone(job.completed_at)

    def test_outro_workspace_nao_recebe_chaves_das_solicitacoes_privadas(self):
        from portal.models import DigitalCertificate
        from portal.tests import create_account
        from portal.services.capture import configure_capture
        from portal.capture_views import _shared_metadata
        user,workspace,company=create_account('chave-metadados-outro@example.test')
        company.cnpj=self.company.cnpj;company.save()
        DigitalCertificate.objects.create(company=company,encrypted_file=b'FICTICIO',encrypted_password=b'FICTICIO',subject_name='FICTICIO',holder_cnpj=company.cnpj,fingerprint='a'*64,valid_from=timezone.now()-timedelta(days=1),valid_until=timezone.now()+timedelta(days=30))
        config=configure_capture(workspace,company.pk,actor=user,authorize_read=True)
        shared=_shared_metadata(company,config)
        self.assertEqual(shared['key_recoveries'],[])
