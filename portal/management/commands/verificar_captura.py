from django.core.management.base import BaseCommand,CommandError
from django.db import connection
from portal.services.capture_runtime import capture_runtime_status


class Command(BaseCommand):
    help='Verifica banco e atividade recente do processo de captura, sem consulta fiscal.'
    def handle(self,*args,**options):
        with connection.cursor() as cursor:cursor.execute('SELECT 1');cursor.fetchone()
        if not capture_runtime_status()['active']:raise CommandError('Processo de captura sem sinal recente. Verifique o supervisor.')
        self.stdout.write('Banco disponível; processo de captura ativo. Estado fiscal deve ser conferido por conector.')
