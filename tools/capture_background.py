"""Entrada sem janela para o Agendador de Tarefas do Windows.

Não prepara ambiente nem muda banco/configurações: execute iniciar.py --preparar
antes de instalar a tarefa. O worker usa as autorizações e os limites já salvos.
"""
import os
from pathlib import Path
import sys
from contextlib import contextmanager
from datetime import datetime


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def instance_lock(path):
    """Impede dois helpers locais; leases no banco protegem outros workers."""
    with path.open('a+b') as lock:
        if lock.seek(0, os.SEEK_END) == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            yield False
            return
        try:
            yield True
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    log_dir = ROOT / 'tmp'
    log_dir.mkdir(exist_ok=True)
    with instance_lock(log_dir / 'capture-background.lock') as acquired:
        if not acquired:
            return 0
        # tmp/ é privado da instalação e está ignorado no repositório. Nunca
        # registrar certificados, senhas, XMLs ou variáveis de ambiente aqui.
        with (log_dir / 'capture-worker.log').open('a', encoding='utf-8', buffering=1) as log:
            previous_stdout, previous_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            try:
                stamp = datetime.now().astimezone().isoformat(timespec='seconds')
                print(f'[{stamp}] Iniciando captura de leitura em segundo plano.', flush=True)
                from django.core.management import execute_from_command_line
                execute_from_command_line(['manage.py', 'capturar_sefaz','--aguardar-instancia'])
                return 0
            except KeyboardInterrupt:
                print('Captura interrompida. O progresso permanece no banco.', flush=True)
                return 0
            except SystemExit as error:
                code = error.code if isinstance(error.code, int) else 1
                if code:
                    print('A captura encerrou com erro. Confira a configuração e o painel SEFAZ.', flush=True)
                return code
            except Exception:
                # Não ecoar exceções desconhecidas que possam conter segredos.
                print('Falha ao iniciar ou manter a captura. Confira o ambiente e o painel SEFAZ.', flush=True)
                return 1
            finally:
                log.flush()
                sys.stdout, sys.stderr = previous_stdout, previous_stderr


if __name__ == '__main__':
    raise SystemExit(main())
