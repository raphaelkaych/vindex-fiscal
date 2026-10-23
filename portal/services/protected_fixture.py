"""JSONL cifrado em blocos Fernet autenticados, ordenados e com fechamento.

Cada bloco vincula identificador aleatório do arquivo, índice e tipo. O bloco
final autentica SHA256 do fluxo inteiro. Não é compressão nem arquivo ZIP.
"""
import hashlib,os,struct

MAGIC=b'VINDEX-FIXTURE-2\n'
CHUNK=1024*1024
MAX_FRAME=2*1024*1024


class EncryptedWriter:
    def __init__(self,file,cipher):
        self.file=file;self.cipher=cipher;self.identifier=os.urandom(16);self.index=0;self.buffer=b'';self.digest=hashlib.sha256()
        file.write(MAGIC)
    def frame(self,kind,data):
        token=self.cipher.encrypt(self.identifier+struct.pack('!Q',self.index)+kind+data)
        self.file.write(struct.pack('!I',len(token)));self.file.write(token);self.index+=1
    def write(self,text):
        self.write_bytes(text.encode('utf-8'))
        return len(text)
    def write_bytes(self,data):
        self.digest.update(data);self.buffer+=data
        while len(self.buffer)>=CHUNK:self.frame(b'D',self.buffer[:CHUNK]);self.buffer=self.buffer[CHUNK:]
        return len(data)
    def flush(self):self.file.flush()
    def finish(self):
        if self.buffer:self.frame(b'D',self.buffer);self.buffer=b''
        self.frame(b'E',self.digest.digest());self.file.flush()


def decrypt_stream(source,target,cipher):
    if source.read(len(MAGIC))!=MAGIC:raise ValueError('Formato de backup desconhecido.')
    index=0;identifier=None;digest=hashlib.sha256()
    while True:
        length=source.read(4)
        if len(length)!=4:raise ValueError('Backup truncado.')
        size=struct.unpack('!I',length)[0]
        if not 100<=size<=MAX_FRAME:raise ValueError('Bloco fora dos limites.')
        token=source.read(size)
        if len(token)!=size:raise ValueError('Bloco truncado.')
        data=cipher.decrypt(token)
        if len(data)<25:raise ValueError('Bloco incompleto.')
        if identifier is None:identifier=data[:16]
        if data[:16]!=identifier or struct.unpack('!Q',data[16:24])[0]!=index:raise ValueError('Ordem/identidade de blocos divergente.')
        kind=data[24:25];payload=data[25:];index+=1
        if kind==b'E':
            if payload!=digest.digest() or source.read(1):raise ValueError('Fechamento do backup inválido.')
            return
        if kind!=b'D' or len(payload)>CHUNK:raise ValueError('Tipo/tamanho do bloco inválido.')
        digest.update(payload);target.write(payload)
