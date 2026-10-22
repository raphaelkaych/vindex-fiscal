"""Configuração local. Leia LEIA-ME.md antes de publicar."""
import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if len(SECRET_KEY) < 40:
    raise ImproperlyConfigured('Prepare o ambiente com: python iniciar.py --preparar')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = [s.strip() for s in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]').split(',') if s.strip()]
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','drf_spectacular','drf_spectacular_sidecar','portal']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','portal.context.app_context']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'dados.sqlite3','OPTIONS':{'timeout':30,'transaction_mode':'IMMEDIATE'}}}
if os.environ.get('VINDEX_DB_ENGINE','sqlite') == 'postgresql':
    if not os.environ.get('PGDATABASE') or not os.environ.get('PGUSER'):
        raise ImproperlyConfigured('Configure PGDATABASE e PGUSER para PostgreSQL.')
    DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.environ['PGDATABASE'],
                         'USER':os.environ['PGUSER'],'PASSWORD':os.environ.get('PGPASSWORD',''),
                         'HOST':os.environ.get('PGHOST','localhost'),'PORT':os.environ.get('PGPORT','5432'),
                         'CONN_MAX_AGE':60,'OPTIONS':{'sslmode':os.environ.get('PGSSLMODE','require')}}}
elif os.environ.get('VINDEX_DB_ENGINE','sqlite') != 'sqlite':
    raise ImproperlyConfigured('VINDEX_DB_ENGINE deve ser sqlite ou postgresql.')
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':10}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='pt-br'
TIME_ZONE='America/Sao_Paulo'
FISCAL_IDLE_INTERVAL_MINUTES=int(os.environ.get('FISCAL_IDLE_INTERVAL_MINUTES','120'))
USE_I18N=True
USE_TZ=True
STATIC_URL='/static/'
STATICFILES_DIRS=[BASE_DIR/'static']
STATIC_ROOT=BASE_DIR/'staticfiles'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
LOGIN_URL='login'
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware')+1,'portal.account_middleware.AccountStatusMiddleware')
MIDDLEWARE.insert(MIDDLEWARE.index('portal.account_middleware.AccountStatusMiddleware'),'portal.supervision.SupervisionMiddleware')
REGISTRATION_MODE=os.environ.get('VINDEX_REGISTRATION_MODE','open' if DEBUG else 'approval')
if REGISTRATION_MODE not in {'open','approval','closed'}:
    raise ImproperlyConfigured('VINDEX_REGISTRATION_MODE deve ser open, approval ou closed.')
LOGIN_REDIRECT_URL='dashboard'
LOGOUT_REDIRECT_URL='login'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS='DENY'
SECURE_SSL_REDIRECT=not DEBUG
SECURE_HSTS_SECONDS=0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=not DEBUG
SECURE_HSTS_PRELOAD=not DEBUG
DATA_UPLOAD_MAX_MEMORY_SIZE=12*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE=3*1024*1024
DATA_UPLOAD_MAX_NUMBER_FILES=5
CERTIFICATE_ENCRYPTION_KEY=os.environ.get('CERTIFICATE_ENCRYPTION_KEY','')
SEFAZ_EXTRA_CA_FILE=os.environ.get('SEFAZ_EXTRA_CA_FILE','')
# O limite local precisa de cache compartilhado e proteção no proxy na produção.
CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'vindex-local-limits'}}
if os.environ.get('VINDEX_REDIS_URL'):
    CACHES={'default':{'BACKEND':'django.core.cache.backends.redis.RedisCache','LOCATION':os.environ['VINDEX_REDIS_URL']}}

REST_FRAMEWORK={
    'DEFAULT_AUTHENTICATION_CLASSES':['portal.api.authentication.IntegrationAuthentication'],
    'DEFAULT_PERMISSION_CLASSES':['portal.api.permissions.IntegrationScopePermission'],
    'DEFAULT_SCHEMA_CLASS':'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER':'portal.api.errors.api_exception_handler',
    'DEFAULT_RENDERER_CLASSES':['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PAGINATION_CLASS':'portal.api.pagination.IntegrationPagination',
    'PAGE_SIZE':25,
    'DEFAULT_THROTTLE_RATES':{'integration':'120/min','integration_burst':'20/min'},
    'COERCE_DECIMAL_TO_STRING':True,
}
SPECTACULAR_SETTINGS={
    'TITLE':'Vindex Fiscal API','DESCRIPTION':'API independente, limitada ao cliente e aos CNPJs da credencial. Valores são previsões; não confirma pagamento bancário.',
    'VERSION':'1.0.0','SERVE_INCLUDE_SCHEMA':False,'COMPONENT_SPLIT_REQUEST':True,
    'SWAGGER_UI_DIST':'SIDECAR','SWAGGER_UI_FAVICON_HREF':'SIDECAR','REDOC_DIST':'SIDECAR',
    'SWAGGER_UI_SETTINGS':{'persistAuthorization':False},
    'ENUM_NAME_OVERRIDES':{
        'InvoiceSourceEnum':[('xml','Importação XML'),('api_xml','API · XML'),('sefaz','Distribuição SEFAZ'),('demo','Demonstração')],
        'InstallmentSourceEnum':[('xml','Duplicata do XML'),('manual','Revisão manual')],
        'BoletoSourceEnum':[('manual','Dados informados'),('pdf','Importação de PDF'),('api','API Vindex')],
    },
    'POSTPROCESSING_HOOKS':['drf_spectacular.hooks.postprocess_schema_enums','portal.api.schema.add_error_responses'],
}
API_CREDENTIAL_MAX_DAYS=365
API_CREDENTIAL_DEFAULT_DAYS=90
API_REQUIRE_HTTPS=not DEBUG
CSRF_TRUSTED_ORIGINS=[x.strip() for x in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS','').split(',') if x.strip()]
if os.environ.get('VINDEX_TRUST_PROXY')=='1':
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
SECURE_REDIRECT_EXEMPT=[r'^saude/$']
EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST=os.environ.get('DJANGO_EMAIL_HOST','')
EMAIL_PORT=int(os.environ.get('DJANGO_EMAIL_PORT','587'))
EMAIL_HOST_USER=os.environ.get('DJANGO_EMAIL_USER','')
EMAIL_HOST_PASSWORD=os.environ.get('DJANGO_EMAIL_PASSWORD','')
EMAIL_USE_TLS=os.environ.get('DJANGO_EMAIL_TLS','1')=='1'
EMAIL_TIMEOUT=15
DEFAULT_FROM_EMAIL=os.environ.get('DJANGO_DEFAULT_FROM_EMAIL','')
DEFAULT_EXCEPTION_REPORTER_FILTER='portal.api.security.SecretRedactingFilter'
