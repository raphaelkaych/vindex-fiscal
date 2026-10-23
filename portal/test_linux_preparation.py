import logging,os,subprocess,sys,tempfile
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.test import SimpleTestCase
from portal.logging_filters import PrivateErrorFilter


class LinuxPreparationTests(SimpleTestCase):
    def test_error_log_does_not_copy_private_exception_or_traceback(self):
        try:raise ValueError('XML_PRIVADO_SENHA_CERTIFICADO')
        except ValueError:info=sys.exc_info()
        record=logging.LogRecord('django.request',40,'',1,'payload privado %s',('SEGREDO',),info)
        PrivateErrorFilter().filter(record)
        self.assertIsNone(record.exc_info);self.assertNotIn('SEGREDO',record.getMessage());self.assertNotIn('XML_PRIVADO',record.getMessage());self.assertIn('ValueError',record.getMessage())
    def test_production_requires_persistent_database_and_refuses_debug(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);config=folder/'private.env'
            config.write_text('DJANGO_SECRET_KEY='+'s'*64+'\nCERTIFICATE_ENCRYPTION_KEY='+Fernet.generate_key().decode())
            env={k:v for k,v in os.environ.items() if not k.startswith(('DJANGO_','VINDEX_','CERTIFICATE_'))}
            env.update(VINDEX_ENV_FILE=str(config),DJANGO_SETTINGS_MODULE='config.production',DJANGO_DEBUG='0',VINDEX_SQLITE_PATH=str(settings.BASE_DIR/'unsafe.sqlite3'),VINDEX_RUNTIME_DIR=str(folder/'runtime'),VINDEX_STATIC_ROOT=str(folder/'static'))
            result=subprocess.run([sys.executable,'-c','from django.conf import settings; print(settings.DEBUG)'],cwd=settings.BASE_DIR,env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('fora do código',result.stderr)
            env['DJANGO_DEBUG']='1'
            result=subprocess.run([sys.executable,'-c','from django.conf import settings; print(settings.DEBUG)'],cwd=settings.BASE_DIR,env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('DJANGO_DEBUG=0',result.stderr)
