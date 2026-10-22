"""Worker de leitura DF-e. O banco conserva consentimentos, NSU e intervalos."""
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, OperationalError, InterfaceError
from portal.services.capture import has_due_backlog, run_due
from portal.services.capture_runtime import worker_heartbeat,capture_worker_lock
from portal.services.capture_policy import page_interval


class Command(BaseCommand):
    help = 'Mantém a captura SEFAZ das empresas autorizadas (somente leitura).'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Processa uma volta da fila e encerra.')
        parser.add_argument('--company', type=int, help='Limita a fila a uma empresa já autorizada.')
        parser.add_argument('--interval', type=int, default=15, help='Segundos entre verificações locais da fila (mínimo 5).')
        parser.add_argument('--limit', type=int, default=20, help='Máximo de empresas por volta da fila.')
        parser.add_argument('--aguardar-instancia',action='store_true',help='Permanece em espera se outro worker contínuo possui a reserva local.')

    def handle(self, *args, **options):
        if options['interval'] < 5 or not 1 <= options['limit'] <= 1000:
            raise CommandError('Use --interval de pelo menos 5 e --limit entre 1 e 1000.')
        self.stdout.write('Captura SEFAZ ativa: apenas empresas com leitura autorizada; limites mantidos no banco.')
        if options['once']:
            self._run(options)
            return
        announced=False
        try:
            while True:
                with capture_worker_lock() as acquired:
                    if acquired:
                        with worker_heartbeat():self._run(options)
                        return
                    if not announced:
                        self.stdout.write('Outra instância já mantém a captura nesta instalação. Nenhuma consulta adicional foi iniciada.')
                        announced=True
                    if not options.get('aguardar_instancia'):return
                time.sleep(options['interval'])
        except KeyboardInterrupt:return

    def _run(self, options):
        try:
            while True:
                try:
                    close_old_connections()
                    results = run_due(limit=options['limit'], company_id=options['company'])
                    from portal.services.fiscal_capture import run_due_connectors
                    run_due_connectors(company_id=options['company'],limit=options['limit'])
                    for company, status in results:
                        if status != 'waiting':
                            self.stdout.write(f'Empresa {company}: {status}. Confira a resposta no painel de captura.')
                    if options['once']:
                        break
                    # Toda retomada passa novamente por autorizações, leases e
                    # esperas persistidas, inclusive se houve HTTP antes da falha.
                    progress = any(status == 'completed' for _, status in results)
                    backlog = progress and has_due_backlog(company_id=options['company'])
                except (OperationalError,InterfaceError) as error:
                    cause=error.__cause__
                    code=getattr(cause,'sqlite_errorname',None) or getattr(cause,'sqlstate',None)
                    safe_code=code if code in {'SQLITE_BUSY','SQLITE_LOCKED','40001','40P01','55P03','08003','08006','08001'} else 'indisponivel'
                    message=f'Acesso ao banco indisponível ({type(error).__name__}, código {safe_code}). A fila será reavaliada sem alterar cursores ou intervalos.'
                    self.stderr.write(message)
                    if options['once']:raise CommandError(message) from None
                    backlog=False
                time.sleep(page_interval().total_seconds() if backlog else options['interval'])
        except KeyboardInterrupt:
            self.stdout.write('Captura interrompida. O progresso foi preservado para a próxima inicialização.')
