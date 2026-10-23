"""Snapshot SQLite consistente, inclusive WAL, cifrado e verificável."""
import os,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
from .certificates import cipher
from .protected_fixture import EncryptedWriter,decrypt_stream
HEADER=b'VINDEX-SQLITE-1\n'


class NullSink:
    def write(self,data):return len(data)


def verify(source):
    with Path(source).open('rb') as file:
        if file.read(len(HEADER))!=HEADER:raise ValueError('Formato de snapshot inválido.')
        decrypt_stream(file,NullSink(),cipher())


def create(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    if not source.is_file():raise ValueError('Banco de origem ausente; não será criado um banco vazio.')
    if target.exists():raise ValueError('O arquivo de destino já existe.')
    # Temporário privado no mesmo volume dos backups, nunca no diretório público.
    with tempfile.TemporaryDirectory(prefix='vindex-snapshot-',dir=target.parent) as folder:
        if os.name!='nt':os.chmod(folder,0o700)
        temporary=Path(folder)/'snapshot.sqlite3'
        temporary.touch(mode=0o600)
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=30)) as original:
            with closing(sqlite3.connect(temporary)) as copy:original.backup(copy,pages=128,sleep=0.05)
        with closing(sqlite3.connect(temporary)) as copy:
            if copy.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Integridade do snapshot reprovada.')
        created=False
        try:
            with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as output:
                created=True;output.write(HEADER);writer=EncryptedWriter(output,cipher())
                with temporary.open('rb') as file:
                    while data:=file.read(1024*1024):writer.write_bytes(data)
                writer.finish();output.flush();os.fsync(output.fileno())
            verify(target)
        except Exception:
            if created:target.unlink(missing_ok=True)
            raise


def restore(source,target):
    target=Path(target).resolve()
    if target.exists():raise ValueError('Restauração permitida somente em caminho inexistente.')
    with tempfile.TemporaryDirectory(prefix='vindex-restore-',dir=target.parent) as folder:
        if os.name!='nt':os.chmod(folder,0o700)
        temporary=Path(folder)/'restored.sqlite3';temporary.touch(mode=0o600)
        with Path(source).open('rb') as file,temporary.open('wb') as output:
            if file.read(len(HEADER))!=HEADER:raise ValueError('Formato de snapshot inválido.')
            decrypt_stream(file,output,cipher())
            output.flush();os.fsync(output.fileno())
        with closing(sqlite3.connect(temporary)) as copy:
            if copy.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Integridade do snapshot reprovada.')
            if copy.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Relações do snapshot inconsistentes.')
        # Link atômico falha se alguém criou o destino; jamais sobrescreve dados.
        os.link(temporary,target)
