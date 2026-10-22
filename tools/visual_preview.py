"""Prévia visual isolada: dados fictícios em memória, somente em localhost:8011.

Não usa o banco do cliente e não deve ser usado como servidor de produção.
Execute com: .venv/Scripts/python.exe tools/visual_preview.py
"""
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from cryptography.fernet import Fernet
os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
os.environ['DJANGO_SECRET_KEY']='visual-preview-only-synthetic-key-no-production-access-2026'
os.environ['CERTIFICATE_ENCRYPTION_KEY']=Fernet.generate_key().decode()
os.environ['DJANGO_DEBUG']='1'
os.environ['VINDEX_DB_ENGINE']='sqlite'
os.environ.pop('VINDEX_REDIS_URL',None)

from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':'file:vindex_visual_preview?mode=memory&cache=shared','OPTIONS':{'uri':True}}}
settings.CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'vindex-visual-preview'}}
settings.ALLOWED_HOSTS=['127.0.0.1','localhost']
settings.API_REQUIRE_HTTPS=False
settings.SECURE_SSL_REDIRECT=False
settings.SESSION_COOKIE_SECURE=False
settings.CSRF_COOKIE_SECURE=False
settings.VINDEX_VISUAL_PREVIEW=True

import django
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User,Permission
from portal.models import Workspace
from portal.services.demo import load_demo
from portal.services.boletos import import_boleto,associate_boleto
from portal.services.certificates import save_certificate
from portal.test_boletos import CHARGE,fictional_pdf
from portal.tests import fake_pfx

call_command('migrate',verbosity=0)
user=User.objects.create_user(username='visual@example.test',email='visual@example.test',password='VindexVisual!2026',first_name='Prévia fictícia')
user.user_permissions.add(*Permission.objects.filter(codename__in=['admin_master','operate_clients'],content_type__app_label='portal'))
workspace=Workspace.objects.create(owner=user,name='Cliente fictício · Revisão visual')
load_demo(workspace)
company=workspace.companies.first()
note=company.invoices.filter(installments__isnull=False).first()
part=note.installments.first()
pdf=fictional_pdf('DOCUMENTO FICTICIO - SEM VALOR BANCARIO OU FISCAL\n'+CHARGE)
boleto,_=import_boleto(workspace,{'company':company,'reference':'Boleto fictício · Revisão visual','barcode':CHARGE,
    'beneficiary_name':'Fornecedor fictício','beneficiary_document':note.issuer_cnpj,'payer_document':company.cnpj,
    'amount':str(part.amount),'due_on':part.due_on},payload=pdf)
associate_boleto(workspace,boleto,part,review_reason='Associação fictícia exclusiva para revisão visual.')
save_certificate(company,fake_pfx(company.cnpj),'SenhaTeste123!',is_demo=True)
# Somente este banco em memória: renderizar dados operacionais fictícios para QA.
workspace.companies.all().update(trade_name='EMPRESA FICTICIA - QA ISOLADA')
from portal.models import Invoice,FiscalDocument
Invoice.objects.filter(company__workspace=workspace).update(is_demo=False,issuer_name='FORNECEDOR FICTICIO - SEM VALOR FISCAL')
from django.utils import timezone
for service in ['nfse','cte']:
    FiscalDocument.objects.create(company=company,service=service,environment='2',access_key='0'*50 if service=='nfse' else '0'*44,
        number='TESTE-1',issuer_name='FORNECEDOR FICTICIO - SEM VALOR FISCAL',issuer_cnpj='00000003000125',role='tomador',issued_at=timezone.now(),total='123.45',
        xml_content='<TESTE_SEM_VALOR_FISCAL/>',payment_data=[{'label':'Valor líquido fictício','value':'123.45','source':'/TESTE/vLiq','method':'structured','review':'Conferir com o documento','excerpt':''}])
print('PRÉVIA ISOLADA: http://127.0.0.1:8011 — banco somente em memória.',flush=True)
print('Acesso FICTÍCIO: visual@example.test / VindexVisual!2026',flush=True)
call_command('runserver','127.0.0.1:8011',use_reloader=False,verbosity=1)
