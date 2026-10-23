"""Perfil explícito de produção. Nunca usa o .env de desenvolvimento como fallback."""
import os
import sqlite3
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
os.environ.setdefault('VINDEX_ENV_FILE','/etc/vindex/vindex.env')
from dotenv import load_dotenv
load_dotenv(os.environ['VINDEX_ENV_FILE'])
os.environ.setdefault('DJANGO_DEBUG','0')
from .settings import *

if DEBUG:raise ImproperlyConfigured('Produção exige DJANGO_DEBUG=0.')
if not CERTIFICATE_ENCRYPTION_KEY:raise ImproperlyConfigured('Preserve e configure CERTIFICATE_ENCRYPTION_KEY antes de iniciar.')
from cryptography.fernet import Fernet
try:Fernet(CERTIFICATE_ENCRYPTION_KEY.encode())
except (ValueError,TypeError):raise ImproperlyConfigured('Chave de cifra inválida; não gere outra para dados existentes.') from None
if DATABASES['default']['ENGINE'].endswith('sqlite3'):
    target=Path(DATABASES['default']['NAME'])
    if not target.is_absolute() or target.resolve().is_relative_to(BASE_DIR.resolve()):
        raise ImproperlyConfigured('VINDEX_SQLITE_PATH deve ser absoluto e ficar fora do código/build.')
    version=sqlite3.sqlite_version_info
    if not (version>=(3,51,3) or (3,50,7)<=version<(3,51,0) or (3,44,6)<=version<(3,45,0)):
        raise ImproperlyConfigured('SQLite sem correção WAL-reset: use 3.51.3+, 3.50.7+ ou 3.44.6+ da respectiva série, ou PostgreSQL.')
    DATABASES['default']['OPTIONS']['init_command']='PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA wal_autocheckpoint=1000;'
for name in ['VINDEX_RUNTIME_DIR','VINDEX_STATIC_ROOT']:
    target=Path(os.environ.get(name,''))
    if not target.is_absolute() or target.resolve().is_relative_to(BASE_DIR.resolve()):
        raise ImproperlyConfigured(name+' deve ser absoluto e persistente, fora do código.')
# O proxy é confiável somente com a porta Gunicorn restrita ao loopback.
LOGGING={'version':1,'disable_existing_loggers':False,
    'filters':{'private':{'()':'portal.logging_filters.PrivateErrorFilter'}},
    'handlers':{'console':{'class':'logging.StreamHandler','formatter':'safe','filters':['private']}},
    'formatters':{'safe':{'format':'{asctime} {levelname} {name}: {message}','style':'{'}},
    'root':{'handlers':['console'],'level':'WARNING'},
    'loggers':{'django.request':{'handlers':['console'],'level':'ERROR','propagate':False},
               'django.security':{'handlers':['console'],'level':'ERROR','propagate':False}}}
