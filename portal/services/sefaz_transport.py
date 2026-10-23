"""Transporte oficial DF-e: mTLS com A1 privado e TLS sempre verificado.

Não faz manifestação nem altera preferências. Nenhum segredo é registrado.
"""
import csv
import http.client
import io
import os
import re
import secrets
import socket
import ssl
import subprocess
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path
from lxml import etree as XML

from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption, Encoding, PrivateFormat, pkcs12,
)
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from portal.models import DigitalCertificate
from portal.services.certificates import CertificateError, cipher, inspect_certificate
from portal.services.sefaz import MAX_RESPONSE_BYTES, NFE_NS, SefazError, SefazNotConfigured

ENDPOINTS = {
    '1': ('www1.nfe.fazenda.gov.br', '/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx'),
    '2': ('hom1.nfe.fazenda.gov.br', '/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx'),
}
DISTRIBUTION_NS = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe'
SOAP_NS = 'http://www.w3.org/2003/05/soap-envelope'


@sensitive_variables()
def load_identity(company):
    """Abre o armazenamento existente apenas em memória e revalida cada uso."""
    from .company_status import capture_block_reason
    reason=capture_block_reason(company)
    if reason:raise SefazNotConfigured(reason)
    try:
        stored = DigitalCertificate.objects.get(company=company)
    except DigitalCertificate.DoesNotExist:
        raise SefazNotConfigured('Certificado A1 ausente. Vincule um certificado válido desta empresa.') from None
    if stored.is_demo:
        raise SefazNotConfigured('Certificado de demonstração não pode consultar o serviço oficial.')
    try:
        box = cipher()
        payload = box.decrypt(bytes(stored.encrypted_file))
        password = box.decrypt(bytes(stored.encrypted_password)).decode('utf-8')
        # Certificados BER ainda aceitos pelo OpenSSL são tratados sem ecoar payload.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            inspect_certificate(payload, password, company)
            key, cert, chain = pkcs12.load_key_and_certificates(payload, password.encode('utf-8'))
    except CertificateError as exc:
        raise SefazNotConfigured(str(exc)) from None
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        raise SefazNotConfigured('Não foi possível abrir o A1 protegido. Confira a chave de cifra do ambiente ou vincule novamente o certificado.') from None
    return key, cert, chain or []


def server_context():
    # Inclui as autoridades confiáveis do Windows, sem substituir a validação.
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    extra_ca = getattr(settings, 'SEFAZ_EXTRA_CA_FILE', '')
    if extra_ca:
        try:
            context.load_verify_locations(cafile=extra_ca)
        except (OSError, ssl.SSLError):
            raise SefazNotConfigured('O arquivo adicional de autoridades TLS não pôde ser carregado.') from None
    return context


def _private_directory(path):
    if os.name != 'nt':
        os.chmod(path, 0o700)
        return
    # Antes de escrever: remove herança e concede acesso apenas ao usuário atual.
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                                  capture_output=True, text=True, check=True, creationflags=flags)
        sid = next(csv.reader(io.StringIO(identity.stdout)))[-1].strip()
        if not re.fullmatch(r'S-1-[0-9-]+', sid):
            raise ValueError
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:(OI)(CI)F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, creationflags=flags)
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
        raise SefazNotConfigured('Não foi possível proteger o diretório temporário de autenticação TLS.') from None


@contextmanager
@sensitive_variables()
def identity_context(company):
    key, cert, chain = load_identity(company)
    context = server_context()
    password = secrets.token_urlsafe(48).encode('ascii')
    # SSLContext precisa de arquivo. A chave temporária é cifrada com senha efêmera,
    # em diretório privado, removido antes da conexão. A senha existe só em memória.
    with tempfile.TemporaryDirectory(prefix='vindex-tls-') as directory:
        _private_directory(directory)
        filename = Path(directory) / 'identity.pem'
        data = cert.public_bytes(Encoding.PEM)
        data += b''.join(item.public_bytes(Encoding.PEM) for item in chain)
        data += key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, BestAvailableEncryption(password))
        descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        try:
            context.load_cert_chain(str(filename), password=password)
        except (OSError, ssl.SSLError):
            raise SefazNotConfigured('O A1 não pôde ser preparado para autenticação TLS.') from None
    yield context


def distribution_request(cnpj, environment, last_nsu, uf_author='', *, query_kind='distNSU'):
    if environment not in ENDPOINTS or not re.fullmatch(r'[0-9A-Z]{12}[0-9]{2}', cnpj):
        raise SefazError('Ambiente ou CNPJ inválido para a consulta oficial.')
    if query_kind == 'consChNFe':
        from .sefaz_key_recovery import validate_key
        validate_key(last_nsu)
    elif not re.fullmatch(r'[0-9]{15}', last_nsu):
        raise SefazError('O cursor de distribuição deve conter 15 dígitos.')
    envelope = XML.Element(f'{{{SOAP_NS}}}Envelope', nsmap={'s': SOAP_NS})
    body = XML.SubElement(envelope, f'{{{SOAP_NS}}}Body')
    method = XML.SubElement(body, f'{{{DISTRIBUTION_NS}}}nfeDistDFeInteresse', nsmap={None: DISTRIBUTION_NS})
    message = XML.SubElement(method, f'{{{DISTRIBUTION_NS}}}nfeDadosMsg')
    request = XML.SubElement(message, f'{{{NFE_NS}}}distDFeInt', {'versao': '1.01'}, nsmap={None: NFE_NS})
    XML.SubElement(request, f'{{{NFE_NS}}}tpAmb').text = environment
    if uf_author:
        if uf_author not in {'11','12','13','14','15','16','17','21','22','23','24','25','26','27','28','29','31','32','33','35','41','42','43','50','51','52','53'}:
            raise SefazError('UF do autor inválida.')
        XML.SubElement(request, f'{{{NFE_NS}}}cUFAutor').text = uf_author
    XML.SubElement(request, f'{{{NFE_NS}}}CNPJ').text = cnpj
    if query_kind not in {'distNSU', 'consNSU', 'consChNFe'}:
        raise SefazError('Modalidade de consulta oficial inválida.')
    query = XML.SubElement(request, f'{{{NFE_NS}}}{query_kind}')
    field = {'distNSU': 'ultNSU', 'consNSU': 'NSU', 'consChNFe': 'chNFe'}[query_kind]
    XML.SubElement(query, f'{{{NFE_NS}}}{field}').text = last_nsu
    return XML.tostring(envelope, encoding='utf-8', xml_declaration=True)


@sensitive_variables()
def official_post(company, host, path, action, payload):
    """URL fixa do governo, sem redirecionamentos, com timeout e limite de bytes."""
    with identity_context(company) as context:
        connection = http.client.HTTPSConnection(host, timeout=45, context=context)
        try:
            connection.request('POST', path, body=payload, headers={
                'Content-Type': f'application/soap+xml; charset=utf-8; action="{action}"',
                'Accept': 'application/soap+xml, application/xml',
                'User-Agent': 'VindexFiscal/1.0',
                'Connection': 'close',
            })
            response = connection.getresponse()
            result = response.read(MAX_RESPONSE_BYTES + 1)
            if len(result) > MAX_RESPONSE_BYTES:
                raise SefazError('Resposta HTTP da SEFAZ excedeu o limite local de 12 MB.')
            if response.status != 200:
                raise SefazError(f'HTTP {response.status} retornado pelo serviço oficial {host}. Nenhum sucesso fiscal foi registrado.')
            return result
        except ssl.SSLCertVerificationError as exc:
            # verify_message é texto de diagnóstico do OpenSSL, não contém A1.
            message = re.sub(r'[^\w .:()\-/]', '', exc.verify_message)[:200]
            raise SefazError(f'Falha na validação TLS do servidor oficial: {message} (verify_code={exc.verify_code}). Atualize a cadeia confiável; a validação não foi desativada.') from None
        except ssl.SSLError as exc:
            reason = re.sub(r'[^A-Z0-9_]', '', str(getattr(exc, 'reason', 'TLS_ERROR')))[:100]
            raise SefazError(f'Falha de autenticação/TLS com a SEFAZ: {reason}. Confira a aceitação e a cadeia do A1.') from None
        except (TimeoutError, socket.timeout):
            raise SefazError('Timeout de 45 segundos na conexão oficial. O resultado é desconhecido; aguarde a próxima tentativa.') from None
        except (OSError, http.client.HTTPException) as exc:
            code = getattr(exc, 'winerror', None) or getattr(exc, 'errno', None)
            raise SefazError(f'Falha de rede com o serviço oficial ({type(exc).__name__}, código {code}).') from None
        finally:
            connection.close()


class SefazTransport:
    source = 'sefaz'
    is_real = True

    def ensure_configured(self, company, environment):
        if environment not in ENDPOINTS:
            raise SefazNotConfigured('Ambiente SEFAZ inválido.')
        load_identity(company)
        server_context()

    def fetch(self, company, environment, last_nsu):
        return self._fetch(company, environment, last_nsu, 'distNSU')

    def fetch_nsu(self, company, environment, nsu):
        return self._fetch(company, environment, nsu, 'consNSU')

    def fetch_key(self, company, environment, access_key):
        return self._fetch(company, environment, access_key, 'consChNFe')

    def _fetch(self, company, environment, last_nsu, query_kind):
        from portal.services.sefaz_schema import validate_message
        config = getattr(company, 'capture_config', None)
        request = distribution_request(company.cnpj, environment, last_nsu,
                                       getattr(config, 'uf_author', ''), query_kind=query_kind)
        host, path = ENDPOINTS[environment]
        validate_message(request, 'distDFeInt_v1.01.xsd', 'distDFeInt')
        response = official_post(company, host, path,
                                 DISTRIBUTION_NS + '/nfeDistDFeInteresse', request)
        return response

    def validate_response(self, response, *, query_kind='distNSU'):
        from portal.services.sefaz_schema import validate_message
        validate_message(response, 'retDistDFeInt_v1.01.xsd', 'retDistDFeInt', query_kind=query_kind)
