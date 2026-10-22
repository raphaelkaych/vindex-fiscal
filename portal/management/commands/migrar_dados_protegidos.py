"""Exportação cifrada e carga somente em banco vazio, nunca no startup."""
import io,tempfile,os
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.apps import apps
from django.db import transaction
from django.core import serializers
from portal.services.certificates import cipher
from portal.services.sefaz_transport import _private_directory
from portal.services.protected_fixture import EncryptedWriter,decrypt_stream,MAGIC


class Command(BaseCommand):
    help='Exporta fixture cifrada ou importa em banco vazio. Exige preservar a chave original dos certificados.'
    def add_arguments(self,parser):
        mode=parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--exportar',action='store_true');mode.add_argument('--importar',action='store_true')
        parser.add_argument('--arquivo',required=True)
        parser.add_argument('--confirmar-banco-vazio',action='store_true')
    @transaction.atomic
    def handle(self,*args,**options):
        target=Path(options['arquivo']).expanduser().resolve()
        if target.is_relative_to(Path(settings.BASE_DIR).resolve()):raise CommandError('Escolha um arquivo fora da pasta do projeto/Git.')
        if options['exportar']:
            if target.exists():raise CommandError('O destino já existe; escolha outro nome para preservar o backup anterior.')
            if not target.parent.is_dir():raise CommandError('Crie primeiro uma pasta privada de backup fora do projeto.')
            try:
                with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as file:
                    writer=EncryptedWriter(file,cipher())
                    serializers.register_serializer('vindex_jsonl','portal.services.precise_jsonl')
                    call_command('dumpdata',format='vindex_jsonl',exclude=['auth.permission','contenttypes','sessions'],use_natural_foreign_keys=True,stdout=writer,verbosity=0)
                    writer.finish()
            except Exception:raise CommandError('Exportação não concluída. Preserve os backups anteriores e confira espaço/permissões; o arquivo incompleto não deve ser restaurado.') from None
            self.stdout.write('Backup cifrado criado fora do projeto. Preserve separadamente a chave original; sessões exigirão novo login.')
            return
        if not options['confirmar_banco_vazio']:raise CommandError('Use --confirmar-banco-vazio somente no banco de destino novo e migrado.')
        if get_user_model().objects.exists() or any(model.objects.exists() for model in apps.get_app_config('portal').get_models()):
            raise CommandError('Destino contém registros. Nenhum dado foi substituído. Importe somente em banco novo.')
        if not target.is_file():raise CommandError('Backup ausente.')
        with tempfile.TemporaryDirectory(prefix='vindex-import-') as folder:
            _private_directory(folder)
            with target.open('rb') as source:streaming=source.read(len(MAGIC))==MAGIC
            temporary=Path(folder)/('restore.jsonl' if streaming else 'restore.json')
            try:
                if streaming:
                    with target.open('rb') as source,temporary.open('wb') as output:decrypt_stream(source,output,cipher())
                else:
                    if target.stat().st_size>512*1024*1024:raise ValueError
                    temporary.write_bytes(cipher().decrypt(target.read_bytes()))
            except Exception:raise CommandError('Backup incompleto, alterado ou chave incompatível. Nenhum dado foi importado.') from None
            try:call_command('loaddata',str(temporary),verbosity=0,stdout=io.StringIO())
            except Exception:raise CommandError('Falha de carga; transação revertida. Confira versão/migrações e o backup protegido.') from None
        self.stdout.write('Carga concluída. Execute conferir_dados e compare os manifestos antes de iniciar a captura.')
