"""Sinal local do worker: apenas PID/hora, sem dados fiscais ou credenciais."""
import json
import math
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings

HEARTBEAT_INTERVAL = 10
HEARTBEAT_MAX_AGE = 90


@contextmanager
def capture_worker_lock():
    """Um worker contínuo por instalação/volume; liberado pelo SO ao morrer.

    Complementa as reservas de banco por CNPJ. Não usa só o heartbeat como lock.
    """
    target=Path(getattr(settings,'RUNTIME_DIR',None) or Path(settings.BASE_DIR)/'tmp')/'capture-worker.lock'
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('a+b') as file:
        file.seek(0,os.SEEK_END)
        if file.tell()==0:file.write(b'0');file.flush()
        file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:yield True
        finally:
            file.seek(0)
            if os.name=='nt':msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(file.fileno(),fcntl.LOCK_UN)


def heartbeat_path():
    return Path(getattr(settings,'RUNTIME_DIR',None) or Path(settings.BASE_DIR)/'tmp') / 'capture-heartbeat.json'


def write_heartbeat():
    """A troca atômica impede leituras parciais; falha local não para a captura."""
    target = heartbeat_path()
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                prefix='capture-heartbeat-', suffix='.tmp', delete=False) as stream:
            temporary = stream.name
            json.dump({'pid': os.getpid(), 'updated_at': time.time()}, stream)
        os.replace(temporary, target)
        return True
    except OSError:
        return False
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def capture_runtime_status():
    """Fresco por 90 s, inclusive enquanto uma chamada oficial está ocupada."""
    result = {'active': False, 'last_seen': None, 'reason': 'missing'}
    try:
        with heartbeat_path().open(encoding='utf-8') as stream:
            raw = stream.read(513)
        if len(raw) > 512:
            raise ValueError
        value = json.loads(raw)
        stamp = value['updated_at']
        pid = value['pid']
        if type(pid) is not int or pid <= 0 or type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise ValueError
        age = time.time() - stamp
        if age < -5:
            raise ValueError
        result.update(active=age < HEARTBEAT_MAX_AGE, last_seen=datetime.fromtimestamp(stamp, timezone.utc),
            reason='fresh' if age < HEARTBEAT_MAX_AGE else 'stale')
    except FileNotFoundError:
        pass
    except OSError:
        result['reason'] = 'unreadable'
    except (ValueError, KeyError, TypeError, OverflowError):
        result['reason'] = 'invalid'
    return result


def _clear_own_heartbeat():
    try:
        target = heartbeat_path()
        value = json.loads(target.read_text(encoding='utf-8'))
        if value.get('pid') == os.getpid():
            target.unlink(missing_ok=True)
    except (OSError, ValueError, AttributeError):
        pass


@contextmanager
def worker_heartbeat(enabled=True):
    """A thread não acessa banco nem rede. --once não anuncia motor contínuo."""
    if not enabled:
        yield
        return
    stopped = threading.Event()
    def refresh():
        while not stopped.wait(HEARTBEAT_INTERVAL):
            write_heartbeat()
    write_heartbeat()
    thread = threading.Thread(target=refresh, name='vindex-capture-heartbeat', daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=2)
        _clear_own_heartbeat()
