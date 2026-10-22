"""Autorização, escopo e retorno da interface. Nenhuma chamada de rede."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from portal.models import DigitalCertificate
from portal.sefaz_models import SefazCaptureConfig, SefazDistributionStream, SefazDocument, SefazSyncState,SefazConsultation
from portal.sefaz_manifest_models import SefazScienceRequest
from portal.tests import create_account, fake_pfx


class CaptureInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user, cls.workspace, cls.company = create_account('capture-ui@example.test')
        cls.other, cls.other_workspace, cls.other_company = create_account('capture-foreign@example.test')
        cls.state = SefazSyncState.objects.create(company=cls.company, environment='1', source='sefaz',
            last_status='138', last_reason='RESPOSTA FICTÍCIA DE TESTE', last_nsu='000000000000001',
            max_nsu='000000000000001', last_response_at=timezone.now(), official_response_at=timezone.now(),
            last_counts={'summary': 1, 'invoice': 0, 'event': 0, 'event_summary': 0, 'imported': 0})
        cls.doc = SefazDocument.objects.create(state=cls.state, kind='summary', nsu='000000000000001',
            content_hash='a' * 64, schema_name='resNFe_v1.01.xsd', access_key='35' + '1' * 42,
            xml_content='<resNFe>XML FICTÍCIO PRIVADO</resNFe>')
        cls.foreign_state = SefazSyncState.objects.create(company=cls.other_company, environment='1', source='sefaz')
        cls.foreign_doc = SefazDocument.objects.create(state=cls.foreign_state, kind='summary',
            content_hash='b' * 64, schema_name='resNFe_v1.01.xsd', xml_content='DOCUMENTO PRIVADO DE OUTRO CLIENTE')

    def setUp(self):
        self.client.force_login(self.user)
        self.runtime_mock = patch('portal.capture_views.capture_runtime_status',
            return_value={'active': False, 'last_seen': None, 'reason': 'missing'})
        self.runtime_mock.start()
        self.addCleanup(self.runtime_mock.stop)

    def certificate(self):
        return DigitalCertificate.objects.create(company=self.company, encrypted_file=b'FICTICIO',
            encrypted_password=b'FICTICIO', subject_name='CERTIFICADO FICTÍCIO', holder_cnpj=self.company.cnpj,
            valid_from=timezone.now()-timedelta(days=1), valid_until=timezone.now()+timedelta(days=30),
            fingerprint='f' * 64)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('capture_list')).status_code, 302)
        self.assertEqual(self.client.get(reverse('capture_document_download', args=[self.doc.pk])).status_code, 302)

    def test_list_shows_only_owned_company_and_one_navigation_item(self):
        self.other_company.legal_name = 'NOME PRIVADO OUTRO CLIENTE'
        self.other_company.save()
        response = self.client.get(reverse('capture_list'))
        self.assertContains(response, self.company.formatted_cnpj)
        self.assertNotContains(response, 'NOME PRIVADO OUTRO CLIENTE')
        self.assertContains(response, 'Depende de autorização')
        self.assertContains(response, 'aria-current="page"', count=1)

    def test_detail_displays_official_response_and_document_separately(self):
        response = self.client.get(reverse('capture_detail', args=[self.company.pk]))
        self.assertContains(response, 'RESPOSTA FICTÍCIA DE TESTE')
        self.assertContains(response, '138')
        self.assertContains(response, 'Resumo · sem XML completo')
        self.assertContains(response, '0 nota(s) vinculada(s)')
        self.assertNotContains(response, self.doc.xml_content)
        self.assertNotContains(response, self.foreign_doc.xml_content)

    def test_foreign_company_and_documents_return_404(self):
        for name, pk in [('capture_detail', self.other_company.pk), ('capture_document', self.foreign_doc.pk),
                         ('capture_document_download', self.foreign_doc.pk)]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 404)
        for name, pk in [('capture_disable', self.other_company.pk), ('capture_science', self.foreign_doc.pk)]:
            with self.subTest(name=name):
                self.assertEqual(self.client.post(reverse(name, args=[pk]), {'authorized': 'on'}).status_code, 404)
        self.assertFalse(SefazCaptureConfig.objects.filter(company=self.other_company).exists())

    def test_synthetic_documents_cannot_be_presented_as_official(self):
        synthetic = SefazSyncState.objects.create(company=self.company, source='test', environment='1')
        document = SefazDocument.objects.create(state=synthetic, kind='summary', content_hash='c'*64,
            schema_name='resNFe_v1.01.xsd', xml_content='SOMENTE SINTÉTICO')
        self.assertEqual(self.client.get(reverse('capture_document', args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('capture_document_download', args=[document.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('capture_detail', args=[self.company.pk])), 'SOMENTE SINTÉTICO')

    def test_download_is_private_xml_and_does_not_send_an_event(self):
        response = self.client.get(reverse('capture_document_download', args=[self.doc.pk]))
        self.assertEqual(response.content.decode(), self.doc.xml_content)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
        self.assertFalse(SefazCaptureConfig.objects.exists())

    def test_fiscal_html_pages_are_private_and_not_stored_in_cache(self):
        for name, args in [('capture_list', []), ('capture_detail', [self.company.pk]),
                           ('capture_document', [self.doc.pk])]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=args))
                self.assertIn('no-store', response['Cache-Control'])
                self.assertIn('private', response['Cache-Control'])

    def test_running_status_uses_shared_cnpj_lease_not_legacy_state(self):
        self.certificate()
        SefazCaptureConfig.objects.create(company=self.company, enabled=True,
            read_authorized_at=timezone.now(), authorized_by=self.user)
        stream = SefazDistributionStream.objects.create(cnpj=self.company.cnpj, environment='1',
            source='sefaz', lease_until=timezone.now()+timedelta(minutes=2))
        response = self.client.get(reverse('capture_detail', args=[self.company.pk]))
        self.assertContains(response, 'Consultando a SEFAZ')
        stream.lease_until = timezone.now()-timedelta(seconds=1)
        stream.save()
        response = self.client.get(reverse('capture_detail', args=[self.company.pk]))
        self.assertNotContains(response, 'Consultando a SEFAZ')

    def test_enabled_queue_without_runtime_shows_stopped_process_and_restart_action(self):
        self.certificate()
        SefazCaptureConfig.objects.create(company=self.company, enabled=True,
            read_authorized_at=timezone.now(), authorized_by=self.user)
        response = self.client.get(reverse('capture_detail', args=[self.company.pk]))
        self.assertEqual(response.context['status'], 'Processo de captura parado')
        self.assertContains(response, 'py iniciar.py')
        self.assertNotContains(response, 'Ativa · consulta agendada')

    def test_missing_certificate_cannot_observe_shared_cnpj_activity(self):
        SefazCaptureConfig.objects.create(company=self.company,enabled=True,
            read_authorized_at=timezone.now(),authorized_by=self.user)
        SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',
            source='sefaz',lease_until=timezone.now()+timedelta(minutes=2))
        response=self.client.get(reverse('capture_detail',args=[self.company.pk]))
        self.assertContains(response,'Certificado necessário')
        self.assertNotContains(response,'Consultando a SEFAZ')

    def test_unchecking_capture_during_renewal_pauses_future_queries(self):
        config=SefazCaptureConfig.objects.create(company=self.company,enabled=True,
            read_authorized_at=timezone.now(),authorized_by=self.user)
        before=self.state.last_nsu
        response=self.client.post(reverse('certificate_upload',args=[self.company.pk]),{
            'file':SimpleUploadedFile('sintetico.pfx',fake_pfx(self.company.cnpj)),
            'password':'SenhaTeste123!','authorized':'on'})
        self.assertRedirects(response,reverse('capture_detail',args=[self.company.pk]))
        config.refresh_from_db();self.state.refresh_from_db()
        self.assertFalse(config.enabled)
        self.assertEqual(self.state.last_nsu,before)

    def test_new_a1_authorizes_selected_connectors_and_schedules_without_http(self):
        from portal.models import FiscalConnector
        with patch('portal.services.fiscal_transport.official_get') as get,patch('portal.services.sefaz_transport.official_post') as post:
            result=self.client.post(reverse('certificate_upload',args=[self.company.pk]),{
                'file':SimpleUploadedFile('sintetico.pfx',fake_pfx(self.company.cnpj)),
                'password':'SenhaTeste123!','authorized':'on','enable_capture':'on','enable_nfse':'on','enable_cte':'on','uf_author':'35'})
        self.assertEqual(result.status_code,302);get.assert_not_called();post.assert_not_called()
        self.assertEqual(FiscalConnector.objects.filter(company=self.company,enabled=True,authorized_at__isnull=False).count(),2)
        self.assertTrue(SefazCaptureConfig.objects.get(company=self.company).enabled)

    def test_renewal_remembers_cte_uf_when_nfe_has_no_uf(self):
        from portal.models import FiscalConnector
        FiscalConnector.objects.create(company=self.company,service='cte',environment='1',enabled=True,uf_author='35',authorized_at=timezone.now(),authorized_by=self.user)
        response=self.client.get(reverse('certificate_upload',args=[self.company.pk]))
        self.assertEqual(response.context['form'].initial['uf_author'],'35')
        self.assertTrue(response.context['form'].initial['enable_cte'])

    def test_recent_runtime_distinguishes_scheduled_and_cooldown_states(self):
        self.certificate()
        SefazCaptureConfig.objects.create(company=self.company, enabled=True,
            read_authorized_at=timezone.now(), authorized_by=self.user)
        with patch('portal.capture_views.capture_runtime_status',
                return_value={'active': True, 'last_seen': timezone.now(), 'reason': 'fresh'}):
            response = self.client.get(reverse('capture_detail', args=[self.company.pk]))
            self.assertEqual(response.context['status'], 'Ativa · consulta agendada')
            self.state.next_attempt_at = timezone.now()+timedelta(hours=1)
            self.state.save()
            response = self.client.get(reverse('capture_detail', args=[self.company.pk]))
            self.assertEqual(response.context['status'], 'Aguardando próxima consulta')

    def test_shared_attempt_is_observed_without_mutating_cursor_or_reading_other_history(self):
        self.certificate()
        SefazCaptureConfig.objects.create(company=self.company,enabled=True,read_authorized_at=timezone.now(),last_error='SEFAZ 656',last_error_code='sefaz_656')
        stamp=timezone.now()-timedelta(minutes=5);wait=timezone.now()+timedelta(hours=2)
        self.state.last_status='656';self.state.save()
        stream=SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',source='sefaz',last_attempt_at=stamp,last_response_at=stamp,last_status='656',last_reason='Rejeição sintética',last_nsu='000000000000001',next_attempt_at=wait)
        self.other_company.cnpj=self.company.cnpj;self.other_company.save()
        SefazConsultation.objects.create(state=self.foreign_state,requested_at=stamp,completed_at=stamp,status='138',reason='HISTÓRICO PRIVADO DE OUTRO CLIENTE',requested_nsu='000000000000001',response_xml='XML PRIVADO DE OUTRO CLIENTE')
        with patch('portal.services.sefaz_transport.official_post') as post,patch('portal.services.fiscal_transport.official_get') as get:
            response=self.client.get(reverse('capture_detail',args=[self.company.pk]))
        post.assert_not_called();get.assert_not_called()
        self.assertEqual(response.context['activity']['last_attempt'],stamp)
        self.assertIsNone(response.context['activity']['last_success'])
        self.assertContains(response,'Aguardando intervalo')
        self.assertNotContains(response,'HISTÓRICO PRIVADO DE OUTRO CLIENTE')
        self.state.refresh_from_db();stream.refresh_from_db()
        self.assertIsNone(self.state.last_attempt_at)
        self.assertEqual(stream.last_nsu,'000000000000001');self.assertEqual(stream.next_attempt_at,wait)

    def test_rejection_is_historical_only_after_own_accepted_response(self):
        self.certificate()
        now=timezone.now()
        SefazCaptureConfig.objects.create(company=self.company,enabled=True,read_authorized_at=now,last_error='Aviso antigo 656',last_error_code='sefaz_656')
        SefazConsultation.objects.create(state=self.state,requested_at=now-timedelta(hours=3),completed_at=now-timedelta(hours=3),status='656',reason='OCORRÊNCIA HISTÓRICA SINTÉTICA',requested_nsu='1')
        SefazConsultation.objects.create(state=self.state,requested_at=now-timedelta(hours=1),completed_at=now-timedelta(hours=1),status='137',requested_nsu='1')
        self.state.last_status='137';self.state.last_response_at=now-timedelta(hours=1);self.state.save()
        response=self.client.get(reverse('capture_detail',args=[self.company.pk]))
        self.assertFalse(response.context['activity']['official_error'])
        self.assertEqual(response.context['activity']['historical_error']['status'],'656')
        self.assertContains(response,'Último erro registrado · histórico')
        self.assertNotContains(response,'<strong>Erro atual:</strong>')

    def test_capture_listing_defers_private_payloads_and_download_still_works(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        SefazConsultation.objects.create(state=self.state,requested_at=timezone.now(),requested_nsu='1',status='138',response_xml='RESPOSTA PRIVADA GRANDE')
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get(reverse('capture_detail',args=[self.company.pk]))
        selects=[q['sql'] for q in queries if q['sql'].lstrip().upper().startswith('SELECT')]
        self.assertFalse(any('"xml_content"' in q or '"response_xml"' in q for q in selects))
        self.assertNotContains(response,self.doc.xml_content)
        download=self.client.get(reverse('capture_document_download',args=[self.doc.pk]))
        self.assertContains(download,self.doc.xml_content)

    def test_enable_requires_explicit_read_authorization(self):
        response = self.client.post(reverse('capture_detail', args=[self.company.pk]), {'uf_author': '35'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errorlist')
        self.assertFalse(SefazCaptureConfig.objects.exists())

    def test_enable_saves_consent_and_schedules_without_network(self):
        self.certificate()
        with patch('portal.services.capture.run_company') as run:
            response = self.client.post(reverse('capture_detail', args=[self.company.pk]),
                {'uf_author': '35', 'authorize_read': 'on'})
        self.assertRedirects(response, reverse('capture_detail', args=[self.company.pk]))
        config = SefazCaptureConfig.objects.get(company=self.company)
        self.assertTrue(config.enabled)
        self.assertEqual(config.environment, '1')
        self.assertEqual(config.authorized_by, self.user)
        self.assertIsNotNone(config.read_authorized_at)
        run.assert_not_called()
        self.state.refresh_from_db()
        self.assertEqual(self.state.last_nsu, '000000000000001')

    def test_missing_certificate_has_specific_visible_requirement(self):
        response = self.client.post(reverse('capture_detail', args=[self.company.pk]),
            {'uf_author': '35', 'authorize_read': 'on'}, follow=True)
        self.assertContains(response, 'Vincule um certificado A1')
        self.assertContains(response, 'Requer atenção')
        self.assertTrue(SefazCaptureConfig.objects.get(company=self.company).enabled)

    def test_disable_is_post_only_and_preserves_progress_and_uf(self):
        SefazCaptureConfig.objects.create(company=self.company, enabled=True, uf_author='35',
            read_authorized_at=timezone.now(), authorized_by=self.user)
        url = reverse('capture_disable', args=[self.company.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        config = SefazCaptureConfig.objects.get(company=self.company)
        self.assertFalse(config.enabled)
        self.assertEqual(config.uf_author, '35')
        self.assertIsNotNone(config.read_authorized_at)
        self.assertTrue(SefazDocument.objects.filter(pk=self.doc.pk).exists())
        self.state.refresh_from_db()
        self.assertEqual(self.state.last_nsu, '000000000000001')

    def test_mutation_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse('capture_detail', args=[self.company.pk]),
            {'uf_author': '35', 'authorize_read': 'on'}).status_code, 403)
        self.assertEqual(client.post(reverse('capture_science', args=[self.doc.pk]),
            {'authorized': 'on'}).status_code, 403)

    def test_science_get_or_missing_checkbox_does_not_send(self):
        url = reverse('capture_science', args=[self.doc.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errorlist')
        self.assertContains(response, 'não confirma a operação comercial')

    def test_science_requires_summary_and_production(self):
        self.doc.kind = 'event'
        self.doc.save()
        response = self.client.post(reverse('capture_science', args=[self.doc.pk]), {'authorized': 'on'}, follow=True)
        self.assertContains(response, 'exige um resumo')
        self.doc.kind = 'summary'
        self.doc.save()
        self.state.environment = '2'
        self.state.save()
        response = self.client.post(reverse('capture_science', args=[self.doc.pk]), {'authorized': 'on'}, follow=True)
        self.assertContains(response, 'exige um resumo')

    def test_science_forwards_only_the_explicit_owned_document(self):
        with patch('portal.services.sefaz_manifest.send_science', return_value=SimpleNamespace(status='accepted')) as send:
            response = self.client.post(reverse('capture_science', args=[self.doc.pk]), {'authorized': 'on'})
        self.assertEqual(response.status_code, 302)
        send.assert_called_once_with(self.workspace, self.company.pk, self.doc.pk, actor=self.user, authorized=True)

    def test_existing_science_request_hides_duplicate_send_button(self):
        SefazScienceRequest.objects.create(company=self.company, document=self.doc, environment='1',
            access_key=self.doc.access_key, authorized_by=self.user, status='uncertain',
            response_reason='RESPOSTA FICTÍCIA INCERTA')
        response = self.client.get(reverse('capture_document', args=[self.doc.pk]))
        self.assertContains(response, 'Já existe uma solicitação de Ciência')
        self.assertNotContains(response, 'Autorizar e enviar Ciência da Emissão')
        self.assertContains(response, 'RESPOSTA FICTÍCIA INCERTA')

    def test_upload_can_authorize_capture_but_does_not_run_it(self):
        payload = fake_pfx(self.company.cnpj)
        with patch('portal.services.capture.run_company') as run:
            response = self.client.post(reverse('certificate_upload', args=[self.company.pk]),
                {'file': SimpleUploadedFile('ficticio.pfx', payload), 'password': 'SenhaTeste123!',
                 'authorized': 'on', 'enable_capture': 'on', 'uf_author': '35'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('capture_detail', args=[self.company.pk]))
        config = SefazCaptureConfig.objects.get(company=self.company)
        self.assertTrue(config.enabled)
        self.assertIsNotNone(config.read_authorized_at)
        self.assertEqual(config.authorized_by, self.user)
        run.assert_not_called()

    def test_upload_rejects_invalid_uf_and_keeps_password_private(self):
        response = self.client.post(reverse('certificate_upload', args=[self.company.pk]),
            {'password': 'SEGREDO-FICTICIO', 'authorized': 'on', 'enable_capture': 'on', 'uf_author': 'XX'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errorlist')
        self.assertNotContains(response, 'SEGREDO-FICTICIO')
        self.assertFalse(SefazCaptureConfig.objects.exists())

    def test_enable_does_not_require_optional_uf(self):
        self.certificate()
        response = self.client.post(reverse('capture_detail', args=[self.company.pk]), {'authorize_read': 'on'})
        self.assertEqual(response.status_code, 302)
        config = SefazCaptureConfig.objects.get(company=self.company)
        self.assertEqual(config.uf_author, '')
        self.assertTrue(config.enabled)
