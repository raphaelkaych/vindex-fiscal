from io import BytesIO,StringIO
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase,TestCase,override_settings
from portal.services.protected_fixture import EncryptedWriter,decrypt_stream
from portal.services.protected_fixture import MAGIC


class StreamingBackupTests(SimpleTestCase):
    def backup(self,text):
        key=Fernet.generate_key();output=BytesIO();writer=EncryptedWriter(output,Fernet(key))
        for offset in range(0,len(text),113):writer.write(text[offset:offset+113])
        writer.finish();return output.getvalue(),key
    def test_multiple_chunks_and_unicode_roundtrip(self):
        text='DADO FICTÍCIO SEM VALOR FISCAL\n'*80000
        data,key=self.backup(text);output=BytesIO();decrypt_stream(BytesIO(data),output,Fernet(key))
        self.assertEqual(output.getvalue().decode(),text)
        self.assertNotIn(b'DADO FICT',data)
    def test_truncation_append_corruption_and_wrong_key_are_rejected(self):
        data,key=self.backup('FICTICIO\n'*200)
        for value in [data[:-1],data+b'x',data[:60]+b'XXXX'+data[64:]]:
            with self.assertRaises(Exception):decrypt_stream(BytesIO(value),BytesIO(),Fernet(key))
        with self.assertRaises(Exception):decrypt_stream(BytesIO(data),BytesIO(),Fernet(Fernet.generate_key()))
    def test_reordering_and_cross_backup_splicing_are_rejected(self):
        import struct
        data,key=self.backup('FICTICIO'*350000)
        def frames(value):
            result=[];offset=len(MAGIC)
            while offset<len(value):
                size=struct.unpack('!I',value[offset:offset+4])[0];result.append(value[offset:offset+4+size]);offset+=4+size
            return result
        first=frames(data)
        with self.assertRaises(Exception):decrypt_stream(BytesIO(MAGIC+first[1]+first[0]+b''.join(first[2:])),BytesIO(),Fernet(key))
        output=BytesIO();writer=EncryptedWriter(output,Fernet(key));writer.write('FICTICIO'*350000);writer.finish()
        second=frames(output.getvalue())
        with self.assertRaises(Exception):decrypt_stream(BytesIO(MAGIC+first[0]+second[1]+b''.join(first[2:])),BytesIO(),Fernet(key))


class ReadinessTests(TestCase):
    @override_settings(DEBUG=False)
    def test_service_locals_do_not_enter_production_exception_reports(self):
        from portal.api.security import SecretRedactingFilter
        namespace={'__name__':'portal.services.fictitious'}
        exec("def fail():\n    payload='XML FICTICIO PRIVADO'\n    raise ValueError('FALHA FICTICIA')",namespace)
        try:namespace['fail']()
        except ValueError as error:
            frame=error.__traceback__.tb_next.tb_frame
            values=dict(SecretRedactingFilter().get_traceback_frame_variables(None,frame))
        self.assertNotEqual(values['payload'],'XML FICTICIO PRIVADO')
    @override_settings(DEBUG=True,EMAIL_HOST_PASSWORD='SEGREDO-FICTICIO-NAO-EXIBIR')
    def test_local_readiness_reports_gaps_without_exposing_secrets(self):
        output=StringIO();call_command('verificar_producao',stdout=output)
        self.assertIn('PENDENTE',output.getvalue());self.assertNotIn('SEGREDO-FICTICIO',output.getvalue())
        with self.assertRaises(CommandError):call_command('verificar_producao',estrito=True,stdout=StringIO())
    @override_settings(DEBUG=False,SECURE_SSL_REDIRECT=True)
    def test_internal_health_is_available_while_login_redirects_to_https(self):
        self.assertEqual(self.client.get('/saude/').status_code,200)
        self.assertEqual(self.client.get('/entrar/').status_code,301)
