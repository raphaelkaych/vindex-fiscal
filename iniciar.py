"""Inicializador local: cria ambiente, dependências, segredos e banco. Sem serviços pagos."""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import signal
import json
import venv

ROOT=Path(__file__).resolve().parent
ENV=ROOT/'.venv'
PY=ENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
os.chdir(ROOT)

def run(args,env=None):
    subprocess.run([str(value) for value in args],check=True,cwd=ROOT,env=env)


def stop_child(process):
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        if os.name == 'nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        process.wait()


def start_child(args):
    options = {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session':True}
    return subprocess.Popen([str(value) for value in args],cwd=ROOT,**options)


def capture_is_running():
    """Reconhece o sinal do worker iniciado pelo Agendador de Tarefas."""
    try:
        with (ROOT/'tmp'/'capture-heartbeat.json').open(encoding='utf-8') as stream:
            raw=stream.read(513)
        if len(raw)>512: return False
        state=json.loads(raw)
        stamp=state['updated_at']
        return (type(state['pid']) is int and state['pid']>0 and
                type(stamp) in (float,int) and -5<=time.time()-stamp<90)
    except (OSError,ValueError,KeyError,TypeError,OverflowError):
        return False


def serve_with_capture():
    """Um comando inicia web e captura. O banco conserva a fila entre reinícios."""
    worker = None if capture_is_running() else start_child([PY,'manage.py','capturar_sefaz'])
    server = None
    try:
        server = start_child([PY,'manage.py','runserver','127.0.0.1:8000'])
        while server.poll() is None:
            if worker is not None and worker.poll() is not None:
                worker=None
            if worker is None and not capture_is_running():
                print('Reiniciando o processo de captura; o NSU e os intervalos foram preservados.',flush=True)
                time.sleep(3)
                if not capture_is_running():worker = start_child([PY,'manage.py','capturar_sefaz'])
            time.sleep(.5)
        if server.returncode:
            raise subprocess.CalledProcessError(server.returncode,[str(PY),'manage.py','runserver'])
    finally:
        if worker is not None: stop_child(worker)
        if server is not None: stop_child(server)

def main():
    if sys.version_info<(3,10):
        raise SystemExit('Instale Python 3.10 ou superior; recomendamos 3.13 ou 3.14.')
    if not PY.exists():
        print('Preparando o ambiente Python local...',flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    requirements=ROOT/'requirements.txt'
    digest=hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker=ENV/'.vindex-dependencies'
    if not marker.exists() or marker.read_text()!=digest:
        print('Instalando as dependências gratuitas do projeto...',flush=True)
        dependency_env=os.environ.copy()
        # PyYAML oferece implementação Python; não exige Visual C++ quando não há wheel.
        if os.name=='nt': dependency_env.setdefault('PYYAML_FORCE_LIBYAML','0')
        run([PY,'-m','pip','install','-r',requirements],env=dependency_env)
        marker.write_text(digest)
    settings=ROOT/'.env'
    if not settings.exists():
        with settings.open('x',encoding='utf-8') as file:
            file.write('DJANGO_SECRET_KEY='+secrets.token_urlsafe(64)+'\n')
            file.write('CERTIFICATE_ENCRYPTION_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()+'\n')
            file.write('DJANGO_DEBUG=1\nDJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,[::1]\n')
        try: settings.chmod(0o600)
        except OSError: pass
        print('Chaves exclusivas deste ambiente criadas.',flush=True)
    run([PY,'manage.py','migrate','--noinput'])
    run([PY,'manage.py','check'])
    if '--testar' in sys.argv:
        run([PY,'manage.py','test','portal','-v','2'])
    elif '--capturar' in sys.argv:
        if capture_is_running():
            print('O processo de captura já está ativo. Confira o estado no painel Captura SEFAZ.',flush=True)
        else:
            run([PY,'manage.py','capturar_sefaz'])
    elif '--preparar' not in sys.argv:
        print('\nVindex Fiscal: http://127.0.0.1:8000\nA captura de leitura será iniciada para as empresas autorizadas. Para encerrar: Ctrl+C.\n',flush=True)
        serve_with_capture()

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('\nServidor encerrado.')
    except subprocess.CalledProcessError as error:
        print('Uma etapa não foi concluída. Copie o erro acima para continuarmos a configuração.')
        raise SystemExit(error.returncode)
