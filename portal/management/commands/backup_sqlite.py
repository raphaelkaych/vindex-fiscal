from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from portal.services import sqlite_backup
from cryptography.fernet import InvalidToken


class Command(BaseCommand):
    help='Snapshot SQLite cifrado via API de backup; inclui transações do WAL.'
    requires_system_checks=[]
    def add_arguments(self,parser):
        mode=parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--criar',action='store_true');mode.add_argument('--verificar',action='store_true');mode.add_argument('--restaurar',action='store_true')
        parser.add_argument('--arquivo',required=True)
        parser.add_argument('--destino')
    def handle(self,*args,**options):
        if not settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):raise CommandError('Use migrar_dados_protegidos para PostgreSQL.')
        archive=Path(options['arquivo']).expanduser().resolve()
        if archive.is_relative_to(settings.BASE_DIR.resolve()):raise CommandError('Guarde snapshots fora do projeto/Git.')
        try:
            if options['criar']:sqlite_backup.create(settings.DATABASES['default']['NAME'],archive)
            elif options['verificar']:sqlite_backup.verify(archive)
            else:
                if not options['destino']:raise CommandError('Informe --destino para um arquivo inexistente.')
                sqlite_backup.restore(archive,options['destino'])
        except (ValueError,OSError,sqlite_backup.sqlite3.Error,InvalidToken):
            raise CommandError('Snapshot não concluído: confira origem, destino inexistente, chave original, integridade, permissões e espaço. Nenhum banco foi substituído.') from None
        self.stdout.write('Snapshot cifrado criado/verificado/restaurado com sucesso. Nenhuma consulta fiscal foi executada.')
