"""Entrada PM2: carrega ambiente privado antes de configurar Gunicorn."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.umask(0o077)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.production')
from dotenv import load_dotenv
load_dotenv(os.environ.get('VINDEX_ENV_FILE','/etc/vindex/vindex.env'))
port=int(os.environ.get('VINDEX_WEB_PORT','8000'))
if not 1024<=port<=65535:raise SystemExit('Porta web inválida: utilize 1024 a 65535.')
if __name__=='__main__':
    # Um processo web com duas threads para o piloto SQLite. Sem --preload.
    sys.argv=['gunicorn','config.wsgi:application','--bind',f'127.0.0.1:{port}',
        '--workers','1','--threads','2','--timeout','120','--graceful-timeout','150',
        '--error-logfile','-','--log-level','critical','--worker-tmp-dir','/dev/shm',
        '--forwarded-allow-ips','127.0.0.1']
    from gunicorn.app.wsgiapp import run
    run()
