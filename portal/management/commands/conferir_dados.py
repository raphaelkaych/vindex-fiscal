import json,hashlib
from django.core.management.base import BaseCommand,CommandError
from django.apps import apps
from django.db import transaction
from portal.models import DigitalCertificate
from portal.services.certificates import cipher


class Command(BaseCommand):
    help='Manifesto de contagens/identidades para conferir migração; não mostra dados fiscais nem segredos.'
    @transaction.atomic
    def handle(self,*args,**options):
        manifest={}
        for model in apps.get_app_config('portal').get_models():
            digest=hashlib.sha256();relations=hashlib.sha256();count=0
            foreign_keys=[field.attname for field in model._meta.concrete_fields if field.is_relation]
            for row in model.objects.order_by('pk').values_list('pk',*foreign_keys):
                digest.update((str(row[0])+'\n').encode());relations.update(json.dumps(row,separators=(',',':')).encode());count+=1
            manifest[model.__name__]={'count':count,'ids_sha256':digest.hexdigest(),'relations_sha256':relations.hexdigest()}
        failures=0
        for cert in DigitalCertificate.objects.filter(is_demo=False).iterator():
            try:
                box=cipher();box.decrypt(bytes(cert.encrypted_file));box.decrypt(bytes(cert.encrypted_password))
            except Exception:failures+=1
        manifest['certificate_decryption_failures']=failures
        self.stdout.write(json.dumps(manifest,sort_keys=True))
        if failures:raise CommandError('Há certificados que não podem ser abertos com a chave configurada. Não prossiga com a migração.')
