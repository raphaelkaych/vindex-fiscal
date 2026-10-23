import tempfile,json
from pathlib import Path
from io import StringIO,BytesIO
from django.test import TestCase,TransactionTestCase,override_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from cryptography.fernet import Fernet
from portal.tests import create_account


class ProductionPreparationTests(TestCase):
    def test_ciphered_export_excludes_sessions_and_refuses_nonempty_restore(self):
        create_account('backup-test@example.test')
        key=Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as directory,override_settings(CERTIFICATE_ENCRYPTION_KEY=key):
            target=Path(directory)/'synthetic.vfx'
            call_command('migrar_dados_protegidos',exportar=True,arquivo=str(target),stdout=StringIO())
            from portal.services.protected_fixture import decrypt_stream
            stream=BytesIO()
            decrypt_stream(BytesIO(target.read_bytes()),stream,Fernet(key.encode()))
            payload=stream.getvalue()
            self.assertIn(b'backup-test@example.test',payload)
            self.assertNotIn(b'backup-test@example.test',target.read_bytes())
            self.assertNotIn(b'"model": "sessions.session"',payload)
            with self.assertRaises(CommandError):call_command('migrar_dados_protegidos',importar=True,arquivo=str(target),confirmar_banco_vazio=True)
    def test_health_endpoint_does_not_reveal_configuration(self):
        response=self.client.get('/saude/');self.assertEqual(response.status_code,200);self.assertEqual(response.json(),{'ready':True})
    @override_settings(EMAIL_HOST='')
    def test_recovery_explains_missing_mail_transport(self):
        self.assertEqual(self.client.get('/recuperar-senha/').status_code,503)


class SyntheticRestoreTests(TransactionTestCase):
    def test_legacy_encrypted_json_remains_readable_in_empty_database(self):
        from django.contrib.auth.models import User
        key=Fernet.generate_key().decode()
        payload=json.dumps([{'model':'auth.user','pk':321,'fields':{'username':'legacy-synthetic@example.test','email':'legacy-synthetic@example.test','password':'!','is_active':True,'is_staff':False,'is_superuser':False,'date_joined':'2026-10-21T00:00:00Z','groups':[],'user_permissions':[]}}]).encode()
        with tempfile.TemporaryDirectory() as directory,override_settings(CERTIFICATE_ENCRYPTION_KEY=key):
            target=Path(directory)/'legacy.vfx';target.write_bytes(Fernet(key.encode()).encrypt(payload))
            call_command('migrar_dados_protegidos',importar=True,arquivo=str(target),confirmar_banco_vazio=True,stdout=StringIO())
        self.assertTrue(User.objects.filter(username='legacy-synthetic@example.test').exists())
    def test_roundtrip_restores_owner_company_and_permissions_in_isolated_database(self):
        # TransactionTestCase fornece banco descartável; flush nunca é executado
        # pelo comando de produção, que recusa destino com qualquer registro.
        from portal.models import Workspace,Company
        from django.contrib.auth.models import User,Permission
        user,workspace,company=create_account('restore-only-test@example.test')
        user.user_permissions.add(Permission.objects.get(codename='admin_master',content_type__app_label='portal'))
        before=(workspace.pk,company.pk,company.cnpj)
        with tempfile.TemporaryDirectory() as directory,override_settings(CERTIFICATE_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            from portal.services.certificates import save_certificate
            from portal.tests import fake_pfx
            from portal.models import FiscalConnector,FiscalStream,FiscalEnvelope,FiscalDocument,FiscalDelivery
            from django.utils import timezone
            from datetime import timedelta
            import hashlib
            save_certificate(company,fake_pfx(company.cnpj),'SenhaTeste123!')
            archived_at=timezone.now()
            archived=Company.objects.create(workspace=workspace,legal_name='EMPRESA DESATIVADA FICTÍCIA',cnpj='00000003000125',deactivated_at=archived_at)
            config=FiscalConnector.objects.create(company=company,service='nfse',enabled=True,authorized_at=timezone.now(),authorized_by=user)
            wait=timezone.now()+timedelta(hours=2)
            stream=FiscalStream.objects.create(cnpj=company.cnpj,service='nfse',environment='1',cursor='198',next_attempt_at=wait)
            original='<TESTE_FICTICIO_SEM_VALOR_FISCAL/>'
            envelope=FiscalEnvelope.objects.create(stream=stream,nsu='198',kind='complete',xml_content=original,content_hash=hashlib.sha256(original.encode()).hexdigest())
            doc=FiscalDocument.objects.create(company=company,service='nfse',environment='1',access_key='1'*50,number='FICTICIO',issuer_name='FICTICIO',issuer_cnpj='00000003000125',role='tomador',issued_at=timezone.now(),total='123.45',xml_content=original,validation_status='partial',validation_details={'reason':'FICTICIO'})
            FiscalDelivery.objects.create(connector=config,envelope=envelope,document=doc,processing_status='partial',error='REVISAR FICTICIO')
            from portal.models import SefazDistributionStream,SefazNsuRecovery,SefazSyncState,SefazConsultation,SefazKeyRecovery
            nfe_stream=SefazDistributionStream.objects.create(cnpj=company.cnpj,environment='1',source='sefaz',
                last_nsu='000000000000020',next_attempt_at=wait,blocked_until=wait)
            recovery=SefazNsuRecovery.objects.create(stream=nfe_stream,first_nsu='000000000000011',last_nsu='000000000000015',
                next_nsu='000000000000013',recovered_count=1,unavailable_count=1,next_attempt_at=wait)
            state=SefazSyncState.objects.create(company=company,environment='1',source='sefaz')
            SefazConsultation.objects.create(state=state,requested_at=timezone.now(),requested_nsu='000000000000012',
                query_kind='consNSU',recovery=recovery,status='137',response_xml=original)
            key_recovery=SefazKeyRecovery.objects.create(stream=nfe_stream,access_key='1'*44,result='rejected',completed_at=timezone.now())
            SefazConsultation.objects.create(stream=nfe_stream,requested_at=timezone.now(),requested_nsu='',
                query_kind='consChNFe',requested_key='1'*44,key_recovery=key_recovery,status='640',response_xml=original)
            target=Path(directory)/'restore-synthetic.vfx'
            call_command('migrar_dados_protegidos',exportar=True,arquivo=str(target),stdout=StringIO())
            call_command('flush',interactive=False,verbosity=0)
            call_command('migrar_dados_protegidos',importar=True,arquivo=str(target),confirmar_banco_vazio=True,stdout=StringIO())
            from portal.services.sefaz_transport import load_identity
            private_key,certificate,chain=load_identity(Company.objects.get(pk=before[1]))
            self.assertIsNotNone(private_key)
            restored_stream=FiscalStream.objects.get()
            self.assertEqual(restored_stream.cursor,'198');self.assertEqual(restored_stream.next_attempt_at,wait)
            self.assertEqual(FiscalDocument.objects.get().xml_content,original)
            self.assertEqual(FiscalDelivery.objects.get().document_id,doc.pk)
            self.assertEqual(Company.objects.get(pk=archived.pk).deactivated_at,archived_at)
            restored_recovery=SefazNsuRecovery.objects.get()
            self.assertEqual(restored_recovery.next_nsu,'000000000000013')
            self.assertEqual(restored_recovery.unavailable_count,1)
            self.assertEqual(restored_recovery.next_attempt_at,wait)
            self.assertEqual(SefazDistributionStream.objects.get().blocked_until,wait)
            self.assertEqual(SefazConsultation.objects.get(query_kind='consNSU').recovery_id,restored_recovery.pk)
            archived_attempt=SefazConsultation.objects.get(query_kind='consChNFe')
            self.assertEqual(archived_attempt.key_recovery_id,SefazKeyRecovery.objects.get().pk)
            self.assertIsNone(archived_attempt.state_id)
            self.assertEqual(archived_attempt.requested_key,'1'*44)
            self.assertEqual(archived_attempt.stream_id,SefazDistributionStream.objects.get().pk)
        restored=User.objects.get(username='restore-only-test@example.test')
        self.assertTrue(restored.has_perm('portal.admin_master'))
        self.assertEqual(restored.workspace.pk,before[0]);self.assertEqual(Company.objects.get(pk=before[1]).workspace.owner_id,restored.pk)
