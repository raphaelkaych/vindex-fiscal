"""Somente respostas sintéticas: sem certificado, rede ou valor fiscal."""
import base64
import gzip
import uuid
from datetime import timedelta
from xml.etree.ElementTree import Element, SubElement, tostring
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from portal.models import Company, Invoice, Workspace
from portal.sefaz_models import SefazDocument, SefazSyncState
from portal.services.demo import sample_xml
from portal.services.sefaz import (
    MAX_DOCUMENT_BYTES, NFE_NS, SefazBusy, SefazError, SefazNotConfigured,
    SefazRejected, parse_distribution, run_distribution,
)

KEY = '35' + '1' * 42


def summary(key=KEY):
    return f'<resNFe xmlns="{NFE_NS}" versao="1.01"><chNFe>{key}</chNFe><xNome>FICTICIO SEM VALOR FISCAL</xNome></resNFe>'.encode()


def event(key=KEY):
    return f'<procEventoNFe xmlns="{NFE_NS}"><evento><infEvento><chNFe>{key}</chNFe><tpEvento>110111</tpEvento></infEvento></evento><retEvento><infEvento><chNFe>{key}</chNFe><cStat>135</cStat></infEvento></retEvento></procEventoNFe>'.encode()


def response(documents=(), status='138', last='2', maximum='3', environment='2'):
    root = Element('retDistDFeInt', {'xmlns': NFE_NS, 'versao': '1.01'})
    values = {'tpAmb': environment, 'verAplic': 'FICTICIO', 'cStat': status, 'xMotivo': 'RESPOSTA SINTETICA SEM VALOR FISCAL', 'dhResp': timezone.now().isoformat()}
    if last is not None:
        values['ultNSU'] = last
    if maximum is not None:
        values['maxNSU'] = maximum
    for name, value in values.items():
        SubElement(root, name).text = str(value)
    if documents:
        batch = SubElement(root, 'loteDistDFeInt')
        for payload, nsu, schema in documents:
            attrs = {'schema': schema}
            if nsu is not None:
                attrs['NSU'] = nsu
            SubElement(batch, 'docZip', attrs).text = base64.b64encode(gzip.compress(payload)).decode()
    return tostring(root, encoding='utf-8')


class SyntheticTransport:
    source = 'test'
    is_real = False

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def ensure_configured(self, company, environment):
        pass

    def fetch(self, company, environment, last_nsu):
        self.calls.append((company.pk, environment, last_nsu))
        return self.payload


class DistributionTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user('sefaz-sintetico@example.test')
        self.workspace = Workspace.objects.create(owner=owner, name='Workspace FICTICIO')
        self.company = Company.objects.create(workspace=self.workspace, cnpj='00000001000136', legal_name='EMPRESA FICTICIA')
        other = User.objects.create_user('outro-sefaz@example.test')
        self.other_workspace = Workspace.objects.create(owner=other, name='Outro FICTICIO')
        self.other_company = Company.objects.create(workspace=self.other_workspace, cnpj='00000002000180', legal_name='OUTRA FICTICIA')

    def transport(self, **kwargs):
        return SyntheticTransport(response([(summary(), '1', 'resNFe_v1.01.xsd')], **kwargs))

    def execute(self, transport=None, **kwargs):
        return run_distribution(self.workspace, self.company.pk, transport=transport or self.transport(), **kwargs)

    def test_sem_transporte_falha_antes_de_criar_estado(self):
        with self.assertRaises(SefazNotConfigured):
            run_distribution(self.workspace, self.company.pk)
        self.assertFalse(SefazSyncState.objects.exists())

    def test_escopo_workspace_e_empresas_permitidas(self):
        for company_id, allowed in [(self.other_company.pk, None), (self.company.pk, [])]:
            transport = self.transport()
            with self.subTest(company=company_id):
                with self.assertRaises(SefazError):
                    run_distribution(self.workspace, company_id, transport=transport, allowed_companies=allowed)
                self.assertFalse(transport.calls)
        self.assertFalse(SefazSyncState.objects.exists())

    def test_resumo_preservado_sem_inventar_nota_ou_sincronizacao_real(self):
        state = self.execute()
        self.assertEqual(state.last_nsu, '000000000000002')
        self.assertEqual(state.source, 'test')
        self.assertIsNone(state.last_real_success_at)
        self.assertIsNotNone(state.last_response_at)
        self.assertEqual(state.documents.get().kind, 'summary')
        self.assertFalse(Invoice.objects.exists())

    def test_xml_completo_reusa_importador_e_fica_identificado_como_ficticio(self):
        payload = response([(sample_xml(self.company.cnpj), '1', 'procNFe_v4.00.xsd')])
        state = self.execute(SyntheticTransport(payload))
        note = Invoice.objects.get()
        self.assertTrue(note.is_demo)
        self.assertEqual(note.source, 'demo')
        self.assertEqual(state.documents.get().invoice, note)
        self.assertEqual(note.company, self.company)

    def test_xml_destinatario_diferente_nao_avanca_cursor_nem_cria_documento(self):
        second = Company.objects.create(workspace=self.workspace, cnpj='00000004000170', legal_name='FILIAL FICTICIA')
        payload = response([(sample_xml(second.cnpj), '1', 'procNFe_v4.00.xsd')])
        with self.assertRaises(SefazError):
            self.execute(SyntheticTransport(payload))
        self.assertEqual(SefazSyncState.objects.get().last_nsu, '000000000000000')
        self.assertFalse(SefazDocument.objects.exists())
        self.assertFalse(Invoice.objects.exists())

    def test_evento_cancelamento_guardado_sem_mudar_nota_ou_financeiro(self):
        state = self.execute(SyntheticTransport(response([(event(), '1', 'procEventoNFe_v1.00.xsd')])))
        doc = state.documents.get()
        self.assertEqual(doc.kind, 'event')
        self.assertEqual(doc.event_type, '110111')
        self.assertFalse(Invoice.objects.exists())

    def test_nsu_facultativo_preserva_hash_e_nao_inventa_numero(self):
        state = self.execute(SyntheticTransport(response([(summary(), None, 'resNFe_v1.01.xsd')])))
        doc = state.documents.get()
        self.assertEqual(doc.nsu, '')
        self.assertEqual(len(doc.content_hash), 64)
        self.assertEqual(state.last_nsu, '000000000000002')

    def test_idempotencia_mesmo_conteudo_e_nsu(self):
        self.execute()
        state = self.execute(self.transport(last='3', maximum='4'))
        self.assertEqual(state.documents.count(), 1)
        self.assertEqual(state.last_nsu, '000000000000003')

    def test_mesmo_nsu_conteudo_distinto_exige_revisao_sem_avancar(self):
        self.execute()
        changed = summary().replace(b'FICTICIO SEM VALOR FISCAL', b'OUTRO FICTICIO')
        payload = response([(changed, '1', 'resNFe_v1.01.xsd')], last='3', maximum='4')
        with self.assertRaises(SefazError):
            self.execute(SyntheticTransport(payload))
        self.assertEqual(SefazDocument.objects.count(), 1)
        self.assertEqual(SefazSyncState.objects.get().last_nsu, '000000000000002')

    def test_137_e_fim_de_lote_impedem_consulta_por_uma_hora(self):
        for status in ['137', '138']:
            with self.subTest(status=status):
                SefazSyncState.objects.all().delete()
                payload = response([], status='137', last='0', maximum='0') if status == '137' else response([(summary(), '1', 'resNFe_v1.01.xsd')], last='1', maximum='1')
                state = self.execute(SyntheticTransport(payload))
                self.assertGreater(state.next_attempt_at, timezone.now() + timedelta(minutes=59))
                with self.assertRaises(SefazBusy):
                    self.execute()

    def test_656_guarda_cursor_reportado_para_revisao_sem_pular_local(self):
        self.execute()
        with self.assertRaises(SefazRejected):
            self.execute(SyntheticTransport(response([], status='656', last='9', maximum='9')))
        state = SefazSyncState.objects.get()
        self.assertEqual(state.last_nsu, '000000000000002')
        self.assertEqual(state.reported_nsu, '000000000000009')
        self.assertGreater(state.next_attempt_at, timezone.now() + timedelta(minutes=59))
        self.assertIsNone(state.last_real_success_at)

    def test_reserva_concorrente_bloqueia_fetch(self):
        state = self.execute()
        state.lease_token = uuid.uuid4()
        state.lease_until = timezone.now() + timedelta(minutes=5)
        state.save()
        transport = self.transport()
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        self.assertFalse(transport.calls)

    def test_reserva_expirada_pode_ser_retornada(self):
        state = self.execute()
        state.lease_token = uuid.uuid4()
        state.lease_until = timezone.now() - timedelta(seconds=1)
        state.save()
        new_state = self.execute(self.transport(last='3', maximum='4'))
        self.assertIsNone(new_state.lease_token)
        self.assertEqual(new_state.last_nsu, '000000000000003')

    def test_execucao_que_perde_reserva_nao_avanca_estado(self):
        transport = self.transport()
        def fetch(company, environment, last_nsu):
            SefazSyncState.objects.filter(company=company).update(lease_token=uuid.uuid4())
            return transport.payload
        transport.fetch = fetch
        with self.assertRaises(SefazBusy):
            self.execute(transport)
        self.assertEqual(SefazSyncState.objects.get().last_nsu, '000000000000000')
        self.assertFalse(SefazDocument.objects.exists())

    def test_falha_transporte_tem_retentativa_sem_expor_erro_ou_sucesso(self):
        transport = self.transport()
        transport.fetch = lambda *args: (_ for _ in ()).throw(RuntimeError('SEGREDO NAO REGISTRAR'))
        with self.assertRaises(SefazError) as error:
            self.execute(transport)
        self.assertNotIn('SEGREDO', str(error.exception))
        state = SefazSyncState.objects.get()
        self.assertEqual(state.failure_count, 1)
        self.assertIsNone(state.lease_token)
        self.assertIsNone(state.last_response_at)
        self.assertIsNone(state.last_real_success_at)
        self.assertGreater(state.next_attempt_at, timezone.now())

    def test_transporte_manual_nao_declara_captura_real(self):
        transport = self.transport()
        transport.source = 'manual'
        state = self.execute(transport)
        self.assertEqual(state.source, 'manual')
        self.assertIsNone(state.last_real_success_at)

    def test_origem_sefaz_sem_transporte_real_e_rejeitada(self):
        transport = self.transport()
        transport.source = 'sefaz'
        with self.assertRaises(SefazError):
            self.execute(transport)
        self.assertFalse(SefazSyncState.objects.exists())

    def test_ambientes_e_origens_possuem_estados_separados(self):
        self.execute()
        self.execute(self.transport(environment='1'), environment='1')
        self.assertEqual(SefazSyncState.objects.count(), 2)


class DistributionParserTests(TestCase):
    def test_rejeita_dtd_base64_invalido_e_xml_sem_fuso(self):
        payloads = [
            b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///nao-ler">]><x>&secret;</x>',
            response([(summary(), '1', 'resNFe_v1.01.xsd')]),
            response([], status='137', last='0', maximum='0').replace(timezone.now().isoformat().encode(), b'invalido'),
        ]
        # Data sintética sem fuso, independente da diferença entre relógios.
        import re
        payloads[1] = re.sub(rb'(<docZip[^>]*>).*?(</docZip>)', rb'\1!INVALIDO!\2', payloads[1])
        payloads[-1] = re.sub(rb'<dhResp>.*?</dhResp>', b'<dhResp>2026-10-20T10:00:00</dhResp>', payloads[-1])
        for payload in payloads:
            with self.subTest(payload=payload[:70]):
                with self.assertRaises(SefazError):
                    parse_distribution(payload)

    def test_bomba_gzip_limitada_a_2mb(self):
        payload = b'<resNFe xmlns="' + NFE_NS.encode() + b'">' + b'A' * MAX_DOCUMENT_BYTES + b'</resNFe>'
        with self.assertRaisesMessage(SefazError, '2 MB'):
            parse_distribution(response([(payload, '1', 'resNFe_v1.01.xsd')]))

    def test_rejeita_mais_de_50_documentos(self):
        with self.assertRaises(SefazError):
            parse_distribution(response([(summary(), str(i), 'resNFe_v1.01.xsd') for i in range(1, 52)], last='51', maximum='51'))

    def test_rejeita_ambiente_trocado_nsu_invalido_e_138_sem_documentos(self):
        payloads = [response([], status='137', last='0', maximum='0', environment='1'), response([], status='137', last='x', maximum='0'), response([])]
        for payload in payloads:
            with self.assertRaises(SefazError):
                parse_distribution(payload)

    def test_rejeita_dois_retornos_e_schema_incompativel(self):
        base = response([], status='137', last='0', maximum='0')
        payloads = [b'<soap>' + base + base + b'</soap>', response([(summary(), '1', 'procNFe_v4.00.xsd')])]
        for payload in payloads:
            with self.assertRaises(SefazError):
                parse_distribution(payload)

    def test_rejeita_nsu_duplicado_ou_fora_do_cursor(self):
        for documents in [[(summary(), '1', 'resNFe_v1.01.xsd')] * 2, [(summary(), '3', 'resNFe_v1.01.xsd')]]:
            with self.assertRaises(SefazError):
                parse_distribution(response(documents))

    def test_aceita_envelope_soap_sem_manifestar(self):
        base = response([(summary(), None, 'resNFe_v1.01.xsd')])
        envelope = b'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body>' + base + b'</s:Body></s:Envelope>'
        self.assertEqual(parse_distribution(envelope).documents[0].kind, 'summary')

    def test_rejeicao_656_nao_exige_nsu_maximo_maior_que_reportado(self):
        parsed = parse_distribution(response([], status='656', last='900', maximum='0'))
        self.assertEqual(parsed.status, '656')
        self.assertEqual(parsed.last_nsu, '000000000000900')
        self.assertEqual(parsed.max_nsu, '000000000000000')

    def test_retorno_aceito_continua_rejeitando_nsu_maior_que_maximo(self):
        for status in ('137', '138'):
            docs = [(summary(), '1', 'resNFe_v1.01.xsd')] if status == '138' else []
            with self.assertRaisesMessage(SefazError, 'supera o NSU máximo'):
                parse_distribution(response(docs, status=status, last='3', maximum='2'))
