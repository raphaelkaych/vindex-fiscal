"""Somente testes em PostgreSQL descartável de homologação, nunca a base real."""
from .settings import *
from django.core.exceptions import ImproperlyConfigured

database=DATABASES['default']
if not database['ENGINE'].endswith('postgresql') or not str(database['NAME']).startswith('vindex_homologacao'):
    raise ImproperlyConfigured('Use PostgreSQL separado com PGDATABASE iniciado por vindex_homologacao. Este arquivo não permite testar contra o banco real.')
database['TEST']={'NAME':'test_'+str(database['NAME'])}
# Testes de aplicação não usam cache, e-mail ou cookies de produção.
DEBUG=True
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
API_REQUIRE_HTTPS=False
REGISTRATION_MODE='open'
CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'vindex-postgres-tests'}}
EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
