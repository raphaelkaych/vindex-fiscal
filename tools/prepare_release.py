"""Build idempotente local/Linux. Não inicia worker nem chama serviço fiscal."""
import os,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.umask(0o077)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.production')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from portal.services.capture_runtime import capture_runtime_status
if __name__=='__main__':
    if capture_runtime_status()['active']:raise SystemExit('Pare os processos PM2 antes de migrar; preserve a fila e os intervalos.')
    if settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):
        source=Path(settings.DATABASES['default']['NAME'])
        if source.exists() and source.stat().st_size:
            folder=Path(os.environ.get('VINDEX_BACKUP_DIR','/var/backups/vindex'))
            call_command('backup_sqlite',criar=True,arquivo=str(folder/('antes-build-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.vdb')))
    else:
        raise SystemExit('Este build PM2 é o perfil SQLite. Use o roteiro PostgreSQL existente, com backup verificado antes de migrate.')
    call_command('check',deploy=True,fail_level='WARNING')
    call_command('migrate',interactive=False)
    call_command('indexar_documentos')
    call_command('collectstatic',interactive=False,verbosity=0)
    print('Build concluído. Web/captura não foram iniciados. Valide proxy, Redis, SMTP e restauração antes de publicar.')
