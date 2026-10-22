"""Administração e filas com dados estritamente sintéticos, sem HTTP fiscal."""
from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch
from django.contrib.auth.models import Permission,User
from django.test import TestCase,Client
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.urls import reverse
from portal.tests import create_account,fake_pfx
from portal.models import Company,DigitalCertificate,SefazCaptureConfig,SefazDistributionStream,SefazSyncState,FiscalConnector,FiscalStream,MasterAudit,Workspace,Invoice
from portal.services.master_lifecycle import company_action,account_action
from portal.services.capture import run_due,run_company
from portal.services.company_status import capture_block_reason
from portal.services.demo import sample_xml
from portal.services.invoices import import_invoice


class MasterLifecycleTests(TestCase):
    def setUp(self):
        self.user,self.ws,self.company=create_account('lifecycle@example.test')
        self.other,self.other_ws,self.twin=create_account('lifecycle-twin@example.test')
        self.twin.cnpj=self.company.cnpj;self.twin.save()
        self.master=User.objects.create_user('lifecycle-master@example.test',password='SyntheticStrong!2026')
        self.master.user_permissions.add(*Permission.objects.filter(content_type__app_label='portal',codename__in=['admin_master','operate_clients']))
        self.client.force_login(self.master)
        for company in [self.company,self.twin]:
            DigitalCertificate.objects.create(company=company,encrypted_file=b'FICTICIO',encrypted_password=b'FICTICIO',subject_name='SINTETICO',holder_cnpj=company.cnpj,valid_from=timezone.now()-timedelta(days=1),valid_until=timezone.now()+timedelta(days=20),fingerprint='f'*64)
            SefazCaptureConfig.objects.create(company=company,enabled=True,environment='1',read_authorized_at=timezone.now(),authorized_by=company.workspace.owner)
            for service in ['nfse','cte']:FiscalConnector.objects.create(company=company,service=service,environment='1',enabled=True,authorized_at=timezone.now(),authorized_by=company.workspace.owner,uf_author='35')
        self.stream=SefazDistributionStream.objects.create(cnpj=self.company.cnpj,environment='1',source='sefaz',last_nsu='000000000000123',max_nsu='000000000000200',next_attempt_at=timezone.now()+timedelta(hours=3))

    def url(self,company=None,workspace=None):
        company=company or self.company
        return reverse('master_company_manage',args=[(workspace or self.ws).pk,company.pk])

    def test_management_requires_both_permissions_and_matching_workspace(self):
        self.client.force_login(self.user);self.assertEqual(self.client.get(self.url()).status_code,403)
        viewer=User.objects.create_user('only-master@example.test')
        viewer.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))
        self.client.force_login(viewer);self.assertEqual(self.client.get(self.url()).status_code,403)
        self.client.force_login(self.master);self.assertEqual(self.client.get(self.url(self.twin)).status_code,404)
        self.assertContains(self.client.get(self.url()),self.other_ws.name)

    def test_get_preview_does_not_deactivate_and_post_requires_confirmation_csrf(self):
        self.assertEqual(self.client.get(self.url()+'?action=deactivate').status_code,200)
        self.company.refresh_from_db();self.assertTrue(self.company.is_active)
        self.client.post(self.url(),{'action':'deactivate'})
        self.company.refresh_from_db();self.assertTrue(self.company.is_active)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.master)
        self.assertEqual(csrf.post(self.url(),{'action':'deactivate','confirmed':'on'}).status_code,403)

    def test_company_deactivation_is_reversible_and_does_not_damage_twin(self):
        note,_=import_invoice(self.ws,sample_xml(self.company.cnpj))
        before=note.xml_content;wait=self.stream.next_attempt_at
        company_action(self.master,self.ws.pk,self.company.pk,'deactivate')
        self.company.refresh_from_db();self.assertFalse(self.company.is_active)
        self.assertTrue(capture_block_reason(self.company));self.assertEqual(capture_block_reason(self.twin),'')
        with patch('portal.services.capture.run_company') as execute:
            results=run_due()
        execute.assert_not_called();self.assertEqual(results,[(self.twin.pk,'waiting')])
        note.refresh_from_db();self.assertEqual(note.xml_content,before)
        self.stream.refresh_from_db();self.assertEqual(self.stream.next_attempt_at,wait);self.assertEqual(self.stream.last_nsu,'000000000000123')
        company_action(self.master,self.ws.pk,self.company.pk,'activate');self.company.refresh_from_db();self.assertTrue(self.company.is_active)

    def test_account_suspension_blocks_capture_and_preserves_preferences(self):
        account_action(self.master,self.ws.pk,'deactivate')
        self.ws.refresh_from_db();self.assertEqual(self.ws.access_status,'suspended')
        self.assertTrue(SefazCaptureConfig.objects.get(company=self.company).enabled)
        with patch('portal.services.capture.run_company') as execute:results=run_due()
        execute.assert_not_called();self.assertEqual(results,[(self.twin.pk,'waiting')])
        self.assertTrue(MasterAudit.objects.filter(workspace=self.ws,action='client_deactivate').exists())

    def test_certificate_removal_pauses_only_own_services(self):
        company_action(self.master,self.ws.pk,self.company.pk,'remove_certificate')
        self.assertFalse(DigitalCertificate.objects.filter(company=self.company).exists())
        self.assertTrue(DigitalCertificate.objects.filter(company=self.twin).exists())
        self.assertFalse(SefazCaptureConfig.objects.get(company=self.company).enabled)
        self.assertFalse(FiscalConnector.objects.filter(company=self.company,enabled=True).exists())
        self.assertEqual(FiscalConnector.objects.filter(company=self.twin,enabled=True).count(),2)
        self.assertTrue(SefazDistributionStream.objects.filter(pk=self.stream.pk).exists())

    def test_service_pause_does_not_pause_other_service_or_twin(self):
        company_action(self.master,self.ws.pk,self.company.pk,'pause_nfse')
        self.assertFalse(FiscalConnector.objects.get(company=self.company,service='nfse').enabled)
        self.assertTrue(FiscalConnector.objects.get(company=self.company,service='cte').enabled)
        self.assertTrue(FiscalConnector.objects.get(company=self.twin,service='nfse').enabled)
        self.assertTrue(SefazCaptureConfig.objects.get(company=self.company).enabled)

    def test_resume_never_creates_authorization_or_changes_cursor(self):
        cfg=FiscalConnector.objects.get(company=self.company,service='nfse');cfg.enabled=False;cfg.authorized_at=None;cfg.save()
        r=self.client.post(self.url(),{'action':'resume_nfse','confirmed':'on','environment':'1'})
        self.assertContains(r,'Não há autorização')
        cfg.refresh_from_db();self.assertFalse(cfg.enabled)
        self.stream.refresh_from_db();self.assertEqual(self.stream.last_nsu,'000000000000123')

    def test_replacement_uses_existing_encryption_and_never_echoes_password(self):
        from portal.services.certificates import cipher
        payload=fake_pfx(self.company.cnpj);password='SenhaTeste123!'
        with patch('portal.services.sefaz_transport.official_post') as post,patch('portal.services.fiscal_transport.official_get') as get:
            r=self.client.post(self.url(),{'action':'certificate','file':SimpleUploadedFile('sintetico.pfx',payload),'password':password,'authorized':'on'})
        self.assertEqual(r.status_code,302);post.assert_not_called();get.assert_not_called()
        cert=DigitalCertificate.objects.get(company=self.company)
        self.assertEqual(cipher().decrypt(bytes(cert.encrypted_file)),payload)
        self.assertTrue(MasterAudit.objects.filter(action='certificate_replaced',workspace=self.ws).exists())
        before=bytes(cert.encrypted_file)
        r=self.client.post(self.url(),{'action':'certificate','file':SimpleUploadedFile('sintetico.pfx',payload),'password':'SENHA_ERRADA_NAO_ECOAR','authorized':'on'})
        self.assertNotContains(r,'SENHA_ERRADA_NAO_ECOAR')
        cert.refresh_from_db();self.assertEqual(bytes(cert.encrypted_file),before)

    def test_historical_company_cannot_be_physically_deleted(self):
        note,_=import_invoice(self.ws,sample_xml(self.company.cnpj));original=note.xml_content
        r=self.client.post(self.url(),{'action':'delete','confirmed':'on','confirmation':f'EXCLUIR EMPRESA {self.company.pk}'})
        self.assertContains(r,'Exclusão bloqueada');note.refresh_from_db();self.assertEqual(note.xml_content,original)
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_empty_company_delete_keeps_shared_stream_and_requires_typed_confirmation(self):
        empty=Company.objects.create(workspace=self.ws,legal_name='FICTÍCIA VAZIA',cnpj='00000003000125')
        Company.objects.create(workspace=self.other_ws,legal_name='OUTRO VÍNCULO FICTÍCIO',cnpj=empty.cnpj)
        shared=SefazDistributionStream.objects.create(cnpj=empty.cnpj,environment='1',source='sefaz',last_nsu='000000000000090')
        url=self.url(empty)
        self.client.post(url,{'action':'delete','confirmed':'on','confirmation':'ERRADO'})
        self.assertTrue(Company.objects.filter(pk=empty.pk).exists())
        company_action(self.master,self.ws.pk,empty.pk,'delete')
        self.assertFalse(Company.objects.filter(pk=empty.pk).exists())
        self.assertTrue(SefazDistributionStream.objects.filter(pk=shared.pk,last_nsu='000000000000090').exists())

    def test_empty_account_delete_keeps_tombstone_audit_and_nonempty_is_blocked(self):
        owner=User.objects.create_user('empty-account@example.test')
        empty=Workspace.objects.create(owner=owner,name='CONTA SINTÉTICA VAZIA');identifier=empty.pk
        url=reverse('master_account_manage',args=[identifier])
        self.client.post(url,{'action':'delete','confirmed':'on','confirmation':f'EXCLUIR CLIENTE {identifier}'})
        self.assertFalse(Workspace.objects.filter(pk=identifier).exists());self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        self.assertTrue(MasterAudit.objects.filter(action='client_deleted',workspace__isnull=True,details__contains=f'id {identifier}').exists())
        r=self.client.post(reverse('master_account_manage',args=[self.ws.pk]),{'action':'delete','confirmed':'on','confirmation':f'EXCLUIR CLIENTE {self.ws.pk}'})
        self.assertContains(r,'Exclusão bloqueada');self.assertTrue(Workspace.objects.filter(pk=self.ws.pk).exists())

    def test_account_deletion_cannot_cascade_django_admin_audit(self):
        from django.contrib.admin.models import LogEntry,ADDITION
        from django.core.exceptions import ValidationError
        owner=User.objects.create_user('old-admin-audit@example.test')
        workspace=Workspace.objects.create(owner=owner,name='FICTÍCIO COM AUDITORIA')
        log=LogEntry.objects.create(user=owner,object_repr='REGISTRO FICTÍCIO',action_flag=ADDITION,change_message='AUDITORIA SINTÉTICA')
        with self.assertRaises(ValidationError):account_action(self.master,workspace.pk,'delete')
        self.assertTrue(LogEntry.objects.filter(pk=log.pk).exists());self.assertTrue(Workspace.objects.filter(pk=workspace.pk).exists())

    def test_nfe_same_identity_is_queried_once_per_queue_pass_and_delivered_to_both(self):
        from portal.test_sefaz import SyntheticTransport,response,summary
        self.stream.next_attempt_at=None;self.stream.last_nsu='000000000000000';self.stream.save()
        transport=SyntheticTransport(response([(summary(),'1','resNFe_v1.01.xsd')],last='2',maximum='3',environment='1'))
        transport.source='sefaz';transport.is_real=True
        execute=run_company
        with patch('portal.services.sefaz_transport.load_identity',return_value=None),patch('portal.services.capture.run_company',side_effect=lambda ws,cid:execute(ws,cid,transport=transport)):
            result=run_due()
        self.assertEqual(len(transport.calls),1)
        self.assertEqual(SefazSyncState.objects.filter(company__in=[self.company,self.twin],last_nsu='000000000000002').count(),2)

    def test_typed_same_identity_is_queried_once_per_pass(self):
        from portal.services.fiscal_capture import run_due_connectors
        with patch('portal.services.fiscal_capture.run_connector') as execute:
            run_due_connectors()
        self.assertEqual(execute.call_count,2) # uma vez por serviço, não por conta

    def test_bad_a1_before_query_does_not_starve_valid_twin(self):
        from portal.services.sefaz import SefazNotConfigured
        self.stream.next_attempt_at=None;self.stream.save()
        with patch('portal.services.capture.run_company',side_effect=[SefazNotConfigured('A1 FICTÍCIO inválido'),None]) as execute:
            result=run_due()
        self.assertEqual(execute.call_count,2)
        self.assertEqual(result,[(self.company.pk,'error'),(self.twin.pk,'completed')])

    def test_typed_bad_a1_before_query_does_not_starve_valid_twin(self):
        from portal.services.sefaz import SefazError
        from portal.services.fiscal_capture import run_due_connectors
        valid=[]
        def execute(config):
            if config.company_id==self.company.pk:raise SefazError('A1 FICTÍCIO inválido')
            valid.append(config.service)
        with patch('portal.services.fiscal_capture.run_connector',side_effect=execute):run_due_connectors()
        self.assertCountEqual(valid,['nfse','cte'])

    def test_readonly_audit_command_never_calls_transport_or_exposes_payload(self):
        from portal.models import SefazConsultation
        state=SefazSyncState.objects.create(company=self.company,environment='1',source='sefaz')
        SefazConsultation.objects.create(state=state,requested_at=timezone.now(),requested_nsu='123',reported_nsu='123',status='656',response_xml='PAYLOAD_PRIVADO_NAO_ECOAR')
        out=StringIO()
        with patch('portal.services.sefaz_transport.official_post') as post:call_command('auditar_distribuicao',cnpj=self.company.cnpj,ambiente='1',stdout=out)
        post.assert_not_called();self.assertNotIn('PAYLOAD_PRIVADO_NAO_ECOAR',out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['local_attempt_records'],1)

    def test_transient_initial_payload_write_failure_preserves_response_for_local_recovery(self):
        import re
        from django.db import OperationalError
        from portal.models import SefazConsultation
        from portal.services.sefaz import SefazError
        from portal.services.capture import recover_received_response
        from portal.test_sefaz import SyntheticTransport,response,summary
        self.stream.next_attempt_at=None;self.stream.last_nsu='000000000123317';self.stream.max_nsu='000000000123319';self.stream.save()
        payload=response([(summary(),'000000000123318','resNFe_v1.01.xsd')],last='000000000123318',maximum='000000000123319',environment='1')
        payload=re.sub(rb'(\d{2}:\d{2}:\d{2})\.\d+',rb'\1',payload)
        transport=SyntheticTransport(payload)
        transport.source='sefaz';transport.is_real=True
        original=SefazConsultation.save;failed=[]
        def save(instance,*args,**kwargs):
            if kwargs.get('update_fields')==['response_xml'] and not failed:
                failed.append(True);raise OperationalError('database is locked FICTÍCIO')
            return original(instance,*args,**kwargs)
        with patch.object(SefazConsultation,'save',new=save),patch('portal.services.sefaz_transport.load_identity',return_value=None):
            with self.assertRaises(SefazError):run_company(self.ws,self.company.pk,transport=transport)
            attempt=SefazConsultation.objects.get();self.assertTrue(attempt.response_xml)
            self.stream.refresh_from_db();wait=self.stream.next_attempt_at
            self.assertEqual(self.stream.last_nsu,'000000000123317')
            with patch('portal.services.sefaz_transport.official_post') as network:
                recovered=recover_received_response(self.company,SefazCaptureConfig.objects.get(company=self.company),self.stream)
            network.assert_not_called();self.assertTrue(recovered)
        self.stream.refresh_from_db()
        self.assertEqual(self.stream.last_nsu,'000000000123318')
        self.assertEqual(self.stream.next_attempt_at,wait)
        self.assertEqual(len(transport.calls),1)
