"""Backup diário supervisionado. Nunca restaura ou apaga cópias automaticamente."""
import os,sys,time
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.umask(0o077)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.production')
import django
django.setup()
from django.core.management import call_command
from django.conf import settings
folder=Path(os.environ.get('VINDEX_BACKUP_DIR','/var/backups/vindex'))
if not folder.is_absolute() or folder.resolve().is_relative_to(settings.BASE_DIR.resolve()):raise SystemExit('Diretório de backups deve ficar fora do código.')
if not settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):raise SystemExit('Configure backup PostgreSQL; este processo é exclusivo SQLite.')
if __name__=='__main__':
    while True:
        try:
            folder.mkdir(mode=0o700,parents=True,exist_ok=True)
            target=folder/('vindex-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.vdb')
            call_command('backup_sqlite',criar=True,arquivo=str(target))
        except Exception:
            print('Falha no backup diário. Confira espaço, permissões e chave original; cópias anteriores preservadas.',file=sys.stderr,flush=True)
            raise SystemExit(1) from None
        print('Backup diário concluído. Mantenha também cópia cifrada fora do servidor.',flush=True)
        time.sleep(24*60*60)
