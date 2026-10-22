"""Parser e pipeline interno de distribuição DF-e, sem manifestação automática.

A execução real autorizada e sua coordenação global ficam em capture.py.
Nenhum endpoint público aceita um transporte fornecido pelo consumidor.
"""
import base64
import binascii
import gzip
import hashlib
import io
import re
import uuid
import zlib
from dataclasses import dataclass
from datetime import timedelta
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from portal.models import AuditEntry, Company
from portal.sefaz_models import SefazDocument, SefazSyncState
from portal.services.invoices import import_invoice

NFE_NS = 'http://www.portalfiscal.inf.br/nfe'
NS = {'n': NFE_NS}
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_BATCH_BYTES = 20 * 1024 * 1024
MAX_DOCUMENTS = 50
LEASE_SECONDS = 300
HOUR = timedelta(hours=1)


class SefazError(ValueError):
    pass


class SefazNotConfigured(SefazError):
    pass


class SefazBusy(SefazError):
    pass


class SefazRejected(SefazError):
    pass


class NotConfiguredTransport:
    source = 'test'
    is_real = False

    def ensure_configured(self, company, environment):
        raise SefazNotConfigured('Este pipeline interno exige transporte explícito. Habilite a captura de leitura da empresa para usar o conector oficial.')


@dataclass(frozen=True)
class DistributionDocument:
    kind: str
    nsu: str
    schema_name: str
    content_hash: str
    access_key: str
    event_type: str
    xml_content: str


@dataclass(frozen=True)
class DistributionResponse:
    environment: str
    status: str
    last_nsu: str
    max_nsu: str
    responded_at: object
    documents: tuple
    reason: str = ''


def normalize_nsu(value, required=True):
    value = str(value or '').strip()
    if not value and not required:
        return ''
    if not re.fullmatch(r'[0-9]{1,15}', value):
        raise SefazError('O retorno contém um NSU inválido.')
    return value.zfill(15)


def _xml(payload):
    try:
        return ElementTree.fromstring(payload, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ElementTree.ParseError, DefusedXmlException, ValueError):
        raise SefazError('O retorno contém XML inválido ou inseguro.') from None


def _document(node):
    schema = node.attrib.get('schema', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,96}\.xsd', schema):
        raise SefazError('O documento não identifica um schema XML válido.')
    nsu = normalize_nsu(node.attrib.get('NSU'), required=False)
    encoded = ''.join((node.text or '').split())
    if len(encoded) > MAX_DOCUMENT_BYTES * 2:
        raise SefazError('Documento compactado acima do limite local.')
    try:
        compressed = base64.b64decode(encoded, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            payload = stream.read(MAX_DOCUMENT_BYTES + 1)
    except (binascii.Error, OSError, EOFError, ValueError, zlib.error):
        raise SefazError('O documento não contém base64/gzip válido.') from None
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise SefazError('Documento descompactado acima do limite de 2 MB.')
    root = _xml(payload)
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise SefazError('O documento deve usar UTF-8.') from None
    if not root.tag.startswith('{' + NFE_NS + '}'):
        raise SefazError('O documento não usa o namespace da NF-e.')
    tag = root.tag.split('}', 1)[1]
    kind = {'resNFe': 'summary', 'nfeProc': 'invoice', 'procEventoNFe': 'event', 'resEvento': 'event_summary'}.get(tag, 'unknown')
    prefixes = {'summary': ('resNFe_',), 'invoice': ('procNFe_',), 'event': ('procEventoNFe_',), 'event_summary': ('resEvento_',)}
    if kind in prefixes and not schema.startswith(prefixes[kind]):
        raise SefazError('O schema informado não corresponde ao tipo do documento.')
    access_key = root.findtext('n:chNFe', '', NS).strip()
    event_type = ''
    if kind == 'invoice':
        info = root.find('n:NFe/n:infNFe', NS)
        access_key = info.attrib.get('Id', '').removeprefix('NFe') if info is not None else ''
    elif kind == 'event':
        # Evento processado só é classificado; não muda a situação fiscal.
        event = root.find('n:evento/n:infEvento', NS)
        response = root.find('n:retEvento/n:infEvento', NS)
        if event is None or response is None:
            raise SefazError('O evento processado não contém os dados e o retorno do evento.')
        access_key = event.findtext('n:chNFe', '', NS).strip()
        if response.findtext('n:chNFe', '', NS).strip() != access_key:
            raise SefazError('A chave do evento difere da chave do retorno.')
        event_type = event.findtext('n:tpEvento', '', NS).strip()
    elif kind == 'event_summary':
        event_type = root.findtext('n:tpEvento', '', NS).strip()
    elif kind == 'unknown':
        access_key = ''
    if kind != 'unknown' and not re.fullmatch(r'[A-Z0-9]{44}', access_key):
        raise SefazError('O documento não contém uma chave de NF-e válida.')
    if event_type and not re.fullmatch(r'[0-9]{6}', event_type):
        raise SefazError('O documento contém um tipo de evento inválido.')
    return DistributionDocument(kind, nsu, schema, hashlib.sha256(payload).hexdigest(), access_key, event_type, text)


def parse_distribution(payload, environment='2'):
    """Lê retorno direto ou envelope SOAP. Não valida assinatura nem XSD completo."""
    if environment not in {'1', '2'}:
        raise SefazError('Ambiente SEFAZ inválido.')
    if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
        raise SefazError('O retorno excede o limite local ou não contém bytes XML.')
    root = _xml(payload)
    returns = [root] if root.tag == '{' + NFE_NS + '}retDistDFeInt' else root.findall('.//n:retDistDFeInt', NS)
    if len(returns) != 1:
        raise SefazError('O XML deve conter exatamente um retorno de distribuição DF-e.')
    root = returns[0]
    value = lambda name: root.findtext('n:' + name, '', NS).strip()
    if value('tpAmb') != environment:
        raise SefazError('O retorno pertence a outro ambiente SEFAZ.')
    status = value('cStat')
    if not re.fullmatch(r'[0-9]{3}', status):
        raise SefazError('O retorno contém uma situação de processamento inválida.')
    required = status in {'137', '138'}
    last = normalize_nsu(value('ultNSU'), required=required)
    maximum = normalize_nsu(value('maxNSU'), required=required)
    if required and last and maximum and int(last) > int(maximum):
        raise SefazError('O último NSU do retorno supera o NSU máximo.')
    try:
        responded_at = parse_datetime(value('dhResp'))
    except ValueError:
        responded_at = None
    if responded_at is None or timezone.is_naive(responded_at):
        raise SefazError('O retorno não contém data/hora com fuso válido.')
    nodes = root.findall('n:loteDistDFeInt/n:docZip', NS)
    if len(nodes) > MAX_DOCUMENTS:
        raise SefazError('O retorno supera o limite de 50 documentos.')
    if status != '138' and nodes:
        raise SefazError('O retorno contém documentos incompatíveis com a situação informada.')
    if status == '138' and not nodes:
        raise SefazError('O retorno informa documentos localizados sem apresentar documentos.')
    documents = []
    batch_size = 0
    for node in nodes:
        doc = _document(node)
        batch_size += len(doc.xml_content.encode('utf-8'))
        if batch_size > MAX_BATCH_BYTES:
            raise SefazError('O lote descompactado supera o limite local de 20 MB.')
        documents.append(doc)
    known = [doc.nsu for doc in documents if doc.nsu]
    if len(set(known)) != len(known) or known != sorted(known):
        raise SefazError('O retorno repete NSU ou apresenta sequência fora de ordem.')
    if last and any(int(nsu) > int(last) for nsu in known):
        raise SefazError('O NSU de um documento supera o cursor do retorno.')
    return DistributionResponse(environment, status, last, maximum, responded_at, tuple(documents), value('xMotivo')[:500])


def distribution_metadata(payload, environment='2'):
    """Extrai evidências do cabeçalho mesmo se um docZip/cursor for inválido.

    Não autoriza importar documentos nem avançar NSU. Campos inválidos ficam
    vazios, e somente um retorno seguro do ambiente solicitado é considerado.
    """
    if environment not in {'1', '2'} or not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
        raise SefazError('Retorno indisponível para extrair metadados seguros.')
    root = _xml(payload)
    returns = [root] if root.tag == '{' + NFE_NS + '}retDistDFeInt' else root.findall('.//n:retDistDFeInt', NS)
    if len(returns) != 1:
        raise SefazError('O retorno não identifica um único cabeçalho de distribuição.')
    value = lambda name: returns[0].findtext('n:' + name, '', NS).strip()
    if value('tpAmb') != environment or not re.fullmatch(r'[0-9]{3}', value('cStat')):
        raise SefazError('O cabeçalho não identifica o ambiente e a situação oficiais.')
    try:
        responded_at = parse_datetime(value('dhResp'))
        if responded_at is not None and timezone.is_naive(responded_at):
            responded_at = None
    except ValueError:
        responded_at = None
    def optional_nsu(name):
        try:
            return normalize_nsu(value(name), required=False)
        except SefazError:
            return ''
    return {'status': value('cStat'), 'reason': value('xMotivo')[:500],
            'responded_at': responded_at, 'last_nsu': optional_nsu('ultNSU'),
            'max_nsu': optional_nsu('maxNSU')}


def _company(workspace, company_id, allowed_companies=None):
    companies = Company.objects.filter(workspace=workspace, pk=company_id)
    if allowed_companies is not None:
        companies = companies.filter(pk__in=allowed_companies)
    company = companies.first()
    if company is None:
        raise SefazError('A empresa não está disponível para este acesso.')
    return company


def _claim(company, environment, source):
    now = timezone.now()
    state, _ = SefazSyncState.objects.get_or_create(company=company, environment=environment, source=source)
    token = uuid.uuid4()
    claimed = SefazSyncState.objects.filter(pk=state.pk).filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now)).filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).update(lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS), last_attempt_at=now)
    if not claimed:
        raise SefazBusy('Esta empresa já tem uma execução em andamento ou deve aguardar o intervalo de consulta.')
    state.refresh_from_db()
    return state, token


def _retry(state, token):
    # Mensagens de exceção do transporte não são registradas: podem conter segredos.
    fresh = SefazSyncState.objects.filter(pk=state.pk, lease_token=token).first()
    if fresh is None:
        return
    delay = min(3600, 60 * (2 ** min(fresh.failure_count, 6)))
    SefazSyncState.objects.filter(pk=state.pk, lease_token=token).update(lease_token=None, lease_until=None, failure_count=F('failure_count') + 1, next_attempt_at=timezone.now() + timedelta(seconds=delay))


def run_distribution(workspace, company_id, transport=None, environment='2', allowed_companies=None):
    """Executa uma página com transporte interno; o padrão nunca faz consulta real.

    Transporte futuro deve fornecer ensure_configured(company,environment) e
    fetch(company,environment,last_nsu), source e is_real. Testes não podem declarar
    última sincronização real. Não existe transporte de rede nesta entrega.
    """
    if environment not in {'1', '2'}:
        raise SefazError('Ambiente SEFAZ inválido.')
    company = _company(workspace, company_id, allowed_companies)
    transport = transport or NotConfiguredTransport()
    source = getattr(transport, 'source', 'test')
    real = getattr(transport, 'is_real', False) is True
    if source not in {'test', 'manual', 'sefaz'} or real != (source == 'sefaz'):
        raise SefazError('A origem do transporte não corresponde à evidência de consulta real.')
    try:
        transport.ensure_configured(company, environment)
    except SefazError:
        raise
    except Exception:
        raise SefazNotConfigured('O transporte não pôde ser validado. Nenhuma consulta foi iniciada.') from None
    state, token = _claim(company, environment, source)
    try:
        response = parse_distribution(transport.fetch(company, environment, state.last_nsu), environment)
        now = timezone.now()
        rejected = response.status not in {'137', '138'}
        with transaction.atomic():
            current = SefazSyncState.objects.select_for_update().get(pk=state.pk)
            if current.lease_token != token or not current.lease_until or current.lease_until <= now:
                raise SefazBusy('A execução perdeu sua reserva. O cursor não foi alterado.')
            if not rejected and int(response.last_nsu) < int(current.last_nsu):
                raise SefazError('O retorno retrocede o cursor de distribuição. Revise o estado antes de continuar.')
            imported = 0
            for doc in response.documents:
                existing_nsu = current.documents.filter(nsu=doc.nsu).first() if doc.nsu else None
                if existing_nsu and existing_nsu.content_hash != doc.content_hash:
                    raise SefazError('O mesmo NSU foi recebido com conteúdo diferente. É necessária revisão.')
                defaults = {'kind': doc.kind, 'nsu': doc.nsu, 'schema_name': doc.schema_name, 'access_key': doc.access_key, 'event_type': doc.event_type, 'xml_content': doc.xml_content}
                stored, created = SefazDocument.objects.get_or_create(state=current, content_hash=doc.content_hash, defaults=defaults)
                if not created and doc.nsu and stored.nsu and stored.nsu != doc.nsu:
                    raise SefazError('O mesmo conteúdo foi recebido com NSU divergente. É necessária revisão.')
                if not created and doc.nsu and not stored.nsu:
                    stored.nsu = doc.nsu
                    stored.save(update_fields=['nsu'])
                if created and doc.kind == 'invoice':
                    invoice, new = import_invoice(workspace, doc.xml_content.encode('utf-8'), allowed_companies=[company.pk], is_demo=source == 'test', source='sefaz' if real else 'xml')
                    stored.invoice = invoice
                    stored.save(update_fields=['invoice'])
                    imported += int(new)
            current.reported_nsu = response.last_nsu
            current.last_status = response.status
            current.last_response_at = now
            if response.max_nsu and not rejected:
                current.max_nsu = response.max_nsu
            # Na rejeição 656, a SEFAZ pode informar cursor de outro consumidor.
            # Guardamos reported_nsu para revisão sem pular documentos locais.
            if not rejected:
                current.last_nsu = response.last_nsu
                current.failure_count = 0
                if real:
                    current.last_real_success_at = now
            else:
                current.failure_count += 1
            end = not rejected and response.last_nsu and response.last_nsu == response.max_nsu
            if response.status in {'137', '656'} or end:
                current.next_attempt_at = now + HOUR
            elif rejected:
                current.next_attempt_at = now + timedelta(seconds=min(3600, 60 * (2 ** min(current.failure_count - 1, 6))))
            else:
                current.next_attempt_at = None
            current.lease_token = None
            current.lease_until = None
            current.save()
            if not rejected:
                label = {'test': 'Teste sintético do pipeline SEFAZ', 'manual': 'Resposta SEFAZ importada manualmente', 'sefaz': 'Distribuição oficial SEFAZ'}[source]
                AuditEntry.objects.create(workspace=workspace, description=f'{label}: {len(response.documents)} documento(s), {imported} NF-e nova(s), empresa {company.display_name}'[:250])
        if rejected:
            raise SefazRejected(f'A distribuição foi rejeitada com código {response.status}. Aguarde o intervalo e revise a configuração.')
        current.refresh_from_db()
        return current
    except SefazRejected:
        raise
    except Exception as error:
        _retry(state, token)
        if isinstance(error, (SefazError, ValidationError)):
            raise
        raise SefazError('A execução falhou. Nenhum sucesso foi registrado; aguarde a retentativa e revise a configuração.') from None
