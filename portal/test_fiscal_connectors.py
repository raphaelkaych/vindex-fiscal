import base64,gzip,json
from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace
from django.test import TestCase
from django.utils import timezone
from portal.tests import create_account
from portal.models import FiscalConnector,FiscalStream,FiscalEnvelope,FiscalConsultation,FiscalDocument
from portal.services.fiscal_capture import run_connector
from portal.services.fiscal_transport import NfseTransport,CteTransport,Batch,unzip,xml_read,validate_xml,CTE
from portal.services.sefaz import SefazError,SefazBusy
from portal.services.payment_evidence import extract_payment_data


class ConnectorTests(TestCase):
    @patch('portal.services.fiscal_import.validate_xml')
    @patch('portal.services.fiscal_capture.load_identity')
    def test_periodic_queue_imports_later_documents_for_each_workspace(self,identity,validate):
        from portal.services.fiscal_capture import run_due_connectors
        # Somente transporte/A1/XSD são substituídos: fila, cursor, importador,
        # deduplicação e escopo usam os modelos reais do banco isolado.
        self.other_company.cnpj='00000002000180';self.other_company.save()
        FiscalConnector.objects.create(company=self.other_company,service='nfse',enabled=True,authorized_at=timezone.now(),authorized_by=self.other)
        def fetch(config,cursor):
            number=int(cursor)+1;key=str(number)*50
            xml=f'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00"><infNFSe Id="NFS{key}"><nNFSe>{number}</nNFSe><emit><CNPJ>00000003000125</CNPJ><xNome>FICTICIO</xNome></emit><DPS><infDPS><dhEmi>2026-10-21T10:00:00-03:00</dhEmi><toma><CNPJ>{config.company.cnpj}</CNPJ></toma><valores><vServPrest><vServ>123.45</vServ></vServPrest></valores></infDPS></DPS></infNFSe></NFSe>'
            return 200,json.dumps({'TipoAmbiente':'PRODUCAO','StatusProcessamento':'DOCUMENTOS_LOCALIZADOS','LoteDFe':[{'NSU':number,'TipoDocumento':'NFSE','ArquivoXml':base64.b64encode(gzip.compress(xml.encode())).decode()}]}).encode()
        with patch.object(NfseTransport,'fetch',side_effect=fetch):
            run_due_connectors()
            self.assertEqual(FiscalDocument.objects.count(),2)
            FiscalStream.objects.update(next_attempt_at=timezone.now()-timedelta(seconds=1))
            run_due_connectors()  # Nova execução, sem estado em memória anterior.
        self.assertEqual(FiscalDocument.objects.count(),4)
        self.assertEqual(set(FiscalStream.objects.values_list('cursor',flat=True)),{'2'})
        for user,company,foreign in [(self.user,self.company,self.other_company),(self.other,self.other_company,self.company)]:
            self.client.force_login(user)
            self.assertEqual(FiscalDocument.objects.filter(company=company).count(),2)
            self.assertContains(self.client.get('/documentos/'),'123,45')
            doc=FiscalDocument.objects.filter(company=foreign).first()
            self.assertEqual(self.client.get(f'/documentos/{doc.pk}/xml/').status_code,404)

    @patch('portal.services.fiscal_capture.load_identity')
    def test_adn_404_with_explicit_no_documents_is_normal_wait(self,identity):
        payload=json.dumps({'TipoAmbiente':'PRODUCAO','StatusProcessamento':'NENHUM_DOCUMENTO_LOCALIZADO','Erros':[{'Codigo':'E2220','Descricao':'Nenhum documento localizado'}]}).encode()
        transport=NfseTransport();transport.fetch=lambda *args:(404,payload)
        batch=run_connector(self.config,transport);self.assertTrue(batch.accepted)
        self.config.refresh_from_db();self.assertEqual(self.config.last_error,'')
        stream=FiscalStream.objects.get();self.assertIsNotNone(stream.last_accepted_at);self.assertEqual(stream.cursor,'0');self.assertGreater(stream.next_attempt_at,timezone.now()+timedelta(minutes=59))
    def test_received_adn_response_is_replayed_locally_preserving_cooldown(self):
        from portal.services.fiscal_capture import recover_fiscal_response
        wait=timezone.now()+timedelta(hours=3)
        stream=FiscalStream.objects.create(cnpj=self.company.cnpj,service='nfse',environment='1',next_attempt_at=wait)
        data={'TipoAmbiente':'PRODUCAO','StatusProcessamento':'DOCUMENTOS_LOCALIZADOS','LoteDFe':[{'NSU':1,'TipoDocumento':'OUTRO','ArquivoXml':base64.b64encode(gzip.compress(b'<outro/>')).decode()}]}
        attempt=FiscalConsultation.objects.create(stream=stream,cursor_sent='0',http_status=200,response_content=json.dumps(data),error='Falha sintética de armazenamento')
        with patch('portal.services.fiscal_transport.official_get') as network:
            self.assertTrue(recover_fiscal_response(self.config,stream))
        network.assert_not_called();stream.refresh_from_db();attempt.refresh_from_db()
        self.assertEqual(stream.cursor,'1');self.assertEqual(stream.next_attempt_at,wait)
        self.assertEqual(stream.envelopes.count(),1);self.assertTrue(attempt.counts['recovered_local'])
        self.assertFalse(recover_fiscal_response(self.config,stream))
    def test_company_without_own_certificate_cannot_observe_shared_stream(self):
        FiscalStream.objects.create(cnpj=self.company.cnpj,service='nfse',environment='1',cursor='12345',last_reason='PRIVATE-SHARED-METADATA')
        self.client.force_login(self.user)
        response=self.client.get(f'/empresas/{self.company.pk}/conectores/')
        self.assertNotContains(response,'PRIVATE-SHARED-METADATA')

    @patch('portal.services.dacte.generate_dacte',return_value=b'%PDF-SYNTHETIC')
    def test_dacte_download_is_private_and_checks_workspace_before_generation(self,generate):
        args=dict(service='cte',environment='1',access_key='0'*44,number='TESTE',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='dest',issued_at=timezone.now(),total='10.00',xml_content='<TESTE/>')
        own=FiscalDocument.objects.create(company=self.company,**args);foreign=FiscalDocument.objects.create(company=self.other_company,**args)
        self.client.force_login(self.user)
        response=self.client.get(f'/documentos/{own.pk}/dacte/');self.assertEqual(response.status_code,200);self.assertEqual(response['Content-Type'],'application/pdf');self.assertIn('no-store',response['Cache-Control'])
        generate.reset_mock();self.assertEqual(self.client.get(f'/documentos/{foreign.pk}/dacte/').status_code,404);generate.assert_not_called()
    @patch('portal.services.fiscal_import.validate_xml')
    def test_typed_cte_import_checks_role_and_is_idempotent_without_financial_duplicates(self,validate):
        # Isola a regra de domínio; schemas completos são conferidos separadamente.
        from portal.services.fiscal_import import import_fiscal
        from portal.models import Installment
        key='1'*44
        xml=f'<cteProc xmlns="{CTE}"><CTe><infCte Id="CTe{key}"><ide><mod>57</mod><nCT>1</nCT><dhEmi>2026-10-21T10:00:00-03:00</dhEmi></ide><emit><CNPJ>00000003000125</CNPJ><xNome>FICTICIO</xNome></emit><dest><CNPJ>{self.company.cnpj}</CNPJ></dest><vPrest><vTPrest>123.45</vTPrest></vPrest></infCte></CTe><protCTe><infProt><chCTe>{key}</chCTe><cStat>100</cStat></infProt></protCTe></cteProc>'
        envelope=SimpleNamespace(kind='complete',xml_content=xml)
        config=SimpleNamespace(company=self.company,service='cte',environment='1')
        first=import_fiscal(config,envelope);second=import_fiscal(config,envelope)
        self.client.force_login(self.user)
        self.assertContains(self.client.get('/documentos/'),'123,45')
        self.assertEqual(first.pk,second.pk);self.assertEqual(str(first.total),'123.45');self.assertEqual(first.role,'dest')
        self.assertEqual(Installment.objects.count(),0)
        self.other_company.cnpj='00000002000180';self.other_company.save()
        config.company=self.other_company
        with self.assertRaises(SefazError):import_fiscal(config,envelope)

    @patch('portal.services.fiscal_import.validate_xml')
    def test_cancellation_requires_matching_accepted_return_and_never_marks_paid(self,validate):
        from portal.services.fiscal_import import import_fiscal
        doc=FiscalDocument.objects.create(company=self.company,service='cte',environment='1',access_key='1'*44,number='1',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='dest',issued_at=timezone.now(),total='10.00',xml_content='<TESTE/>')
        config=SimpleNamespace(company=self.company,service='cte',environment='1')
        def event_xml(return_key):return f'<procEventoCTe xmlns="{CTE}"><eventoCTe><infEvento><chCTe>{doc.access_key}</chCTe><tpEvento>110111</tpEvento></infEvento></eventoCTe><retEventoCTe><infEvento><chCTe>{return_key}</chCTe><tpEvento>110111</tpEvento><cStat>135</cStat></infEvento></retEventoCTe></procEventoCTe>'
        with self.assertRaises(SefazError):import_fiscal(config,SimpleNamespace(kind='event',xml_content=event_xml('2'*44)))
        doc.refresh_from_db();self.assertFalse(doc.cancellation_reported)
        import_fiscal(config,SimpleNamespace(kind='event',xml_content=event_xml(doc.access_key)))
        doc.refresh_from_db();self.assertTrue(doc.cancellation_reported)
    def test_new_api_is_scoped_even_when_owner_is_master(self):
        from portal.models import ApiCredential
        from django.contrib.auth.models import Permission
        from rest_framework.test import APIClient
        self.user.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))
        args=dict(service='cte',environment='1',access_key='0'*44,number='TESTE',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='dest',issued_at=timezone.now(),total='10.00',xml_content='<TESTE/>')
        own=FiscalDocument.objects.create(company=self.company,**args)
        foreign=FiscalDocument.objects.create(company=self.other_company,**args)
        credential,token=ApiCredential.issue(workspace=self.ws,name='Teste',scopes=['read'],companies=[self.company],expires_at=timezone.now()+timedelta(days=1))
        client=APIClient();client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        response=client.get('/api/v1/documentos-fiscais/')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['count'],1)
        self.assertEqual(client.get(f'/api/v1/documentos-fiscais/{foreign.pk}/xml/').status_code,404)
        self.assertEqual(client.get('/api/v1/documentos-fiscais/?workspace='+str(self.other_ws.pk)).status_code,400)
        self.assertEqual(client.get(f'/api/v1/documentos-fiscais/{own.pk}/xml/').status_code,200)
        self.assertEqual(client.get('/api/v1/conectores/').json()['count'],1)
        self.assertEqual(client.post('/api/v1/conectores/',{}).status_code,403)
    def setUp(self):
        self.user,self.ws,self.company=create_account('fiscal-new@example.test')
        self.other,self.other_ws,self.other_company=create_account('fiscal-other@example.test')
        self.config=FiscalConnector.objects.create(company=self.company,service='nfse',authorized_at=timezone.now(),authorized_by=self.user,enabled=True)

    def fake(self,status='DOCUMENTOS_LOCALIZADOS',cursor='1',accepted=True,end=False):
        batch=Batch(status,'Resposta sintética de teste',cursor,'',accepted,end,[(cursor,'OUTRO',b'<outro/>')] if accepted else [])
        return SimpleNamespace(fetch=lambda *args:(200,b'{"synthetic":true}'),parse=lambda *args:batch)

    @patch('portal.services.fiscal_capture.load_identity')
    def test_cursor_is_persisted_and_duplicate_does_not_create_second_envelope(self,identity):
        run_connector(self.config,self.fake())
        stream=FiscalStream.objects.get();self.assertEqual(stream.cursor,'1')
        self.assertEqual(FiscalConsultation.objects.get().response_content,'{"synthetic":true}')
        stream.next_attempt_at=timezone.now()-timedelta(seconds=1);stream.save()
        run_connector(self.config,self.fake(end=True))
        self.assertEqual(FiscalEnvelope.objects.count(),1)
        self.assertEqual(FiscalDocument.objects.count(),0)

    @patch('portal.services.fiscal_capture.load_identity')
    def test_rejection_does_not_advance_cursor_and_blocks_next_attempt(self,identity):
        run_connector(self.config,self.fake(status='REJEICAO',cursor='999',accepted=False,end=True))
        stream=FiscalStream.objects.get();self.assertEqual(stream.cursor,'0')
        with self.assertRaises(SefazBusy):run_connector(self.config,self.fake())
        self.assertGreater(stream.next_attempt_at,timezone.now()+timedelta(minutes=59))

    @patch('portal.services.fiscal_capture.load_identity')
    def test_service_waits_are_independent_and_lease_prevents_concurrent_query(self,identity):
        stream=FiscalStream.objects.create(cnpj=self.company.cnpj,service='cte',environment='1',next_attempt_at=timezone.now()+timedelta(hours=1))
        run_connector(self.config,self.fake())
        self.assertEqual(FiscalStream.objects.count(),2)
        s=FiscalStream.objects.get(service='nfse');s.next_attempt_at=None;s.lease_token=__import__('uuid').uuid4();s.lease_until=timezone.now()+timedelta(minutes=2);s.save()
        with self.assertRaises(SefazBusy):run_connector(self.config,self.fake())

    @patch('portal.services.fiscal_capture.load_identity')
    def test_missing_consent_and_paused_client_never_fetch(self,identity):
        transport=self.fake();self.config.authorized_at=None
        with self.assertRaises(SefazError):run_connector(self.config,transport)
        self.config.authorized_at=timezone.now();self.ws.capture_paused=True;self.ws.save()
        with self.assertRaises(SefazError):run_connector(self.config,transport)
        self.assertFalse(FiscalConsultation.objects.exists())

    @patch('portal.services.fiscal_capture.load_identity')
    def test_crash_after_response_keeps_evidence_and_wait(self,identity):
        transport=self.fake();transport.parse=lambda *args:(_ for _ in ()).throw(SefazError('Schema incompatível'))
        with self.assertRaises(SefazError):run_connector(self.config,transport)
        self.assertTrue(FiscalConsultation.objects.get().response_content)
        self.assertEqual(FiscalStream.objects.get().cursor,'0')

    def test_adn_contract_environment_gzip_and_no_documents(self):
        encoded=base64.b64encode(gzip.compress(b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"/>')).decode()
        data={'TipoAmbiente':'PRODUCAO','StatusProcessamento':'DOCUMENTOS_LOCALIZADOS','LoteDFe':[{'NSU':10,'TipoDocumento':'NFSE','ArquivoXml':encoded}]}
        batch=NfseTransport().parse(json.dumps(data).encode(),'1','0')
        self.assertEqual(batch.cursor,'10');self.assertEqual(len(batch.documents),1)
        with self.assertRaises(SefazError):NfseTransport().parse(json.dumps(data).encode(),'2','0')
        batch=NfseTransport().parse(json.dumps({'TipoAmbiente':'PRODUCAO','StatusProcessamento':'NENHUM_DOCUMENTO_LOCALIZADO'}).encode(),'1','10')
        self.assertTrue(batch.accepted);self.assertTrue(batch.end)

    def test_cte_official_response_schema_and_environment(self):
        data=f'<retDistDFeInt xmlns="{CTE}" versao="1.00"><tpAmb>1</tpAmb><verAplic>TESTE</verAplic><cStat>137</cStat><xMotivo>Nenhum documento localizado</xMotivo><dhResp>2026-10-21T10:00:00</dhResp><ultNSU>000000000000000</ultNSU><maxNSU>000000000000000</maxNSU></retDistDFeInt>'.encode()
        batch=CteTransport().parse(data,'1','0');self.assertEqual(batch.status,'137');self.assertTrue(batch.end)
        with self.assertRaises(SefazError):CteTransport().parse(data,'2','0')
        with self.assertRaises(SefazError):validate_xml('cte','procCTe_v4.00.xsd',xml_read(b'<cteProc/>'))

    def test_unsafe_or_bomb_document_is_rejected(self):
        for data in [b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>',b'<x>']:
            with self.assertRaises(SefazError):xml_read(data)
        with self.assertRaises(SefazError):unzip(base64.b64encode(gzip.compress(b'x'*(2*1024*1024+1))).decode())

    def test_private_routes_and_company_config_cannot_escape_workspace(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/empresas/{self.other_company.pk}/conectores/').status_code,404)
        self.assertEqual(self.client.post(f'/empresas/{self.company.pk}/conectores/',{'service':'nfse','environment':'1','enabled':'on'}).status_code,200)
        self.assertEqual(self.client.get('/documentos/?company='+str(self.other_company.pk)).status_code,404)

    def test_payment_evidence_never_invents_bank_from_card_or_random_numbers(self):
        xml='<root><card><CNPJ>12345678000199</CNPJ><cAut>12345</cAut></card><infCpl>sequencia 12345678901234</infCpl></root>'
        self.assertEqual(extract_payment_data(xml),[])
        xml='<root><vLiq>123.45</vLiq><infCpl>Chave Pix: financeiro@example.test; Agencia: 1234; Conta: 12345-6</infCpl></root>'
        fields=extract_payment_data(xml);self.assertTrue(any(f['value']=='123.45' for f in fields))
        text=[f for f in fields if f['method']=='labeled_text'];self.assertEqual(len(text),3)
        self.assertTrue(all(f['excerpt'] and f['review']=='Revisão necessária' for f in text))
