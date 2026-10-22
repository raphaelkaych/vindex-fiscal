"""Ciência por documento, somente após POST com autorização fiscal específica.

Não confirma a operação e nunca é chamada pelo worker de distribuição.
"""
import base64
import hashlib
from datetime import timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.debug import sensitive_variables
from lxml import etree

from portal.models import AuditEntry, Company
from portal.sefaz_manifest_models import SefazScienceRequest
from portal.sefaz_models import SefazDocument
from portal.services.sefaz import NFE_NS, SefazError, NS
from portal.services.sefaz_schema import validate_message
from portal.services.sefaz_transport import SOAP_NS, load_identity, official_post

EVENT_NS = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4'
EVENT_ENDPOINTS = {
    '1': ('www.nfe.fazenda.gov.br', '/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx'),
    '2': ('hom1.nfe.fazenda.gov.br', '/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx'),
}
DS = 'http://www.w3.org/2000/09/xmldsig#'
C14N = 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'


def _canonical(node):
    return etree.tostring(node, method='c14n', exclusive=False, with_comments=False)


@sensitive_variables()
def science_message(company, environment, access_key, now=None):
    from cryptography.hazmat.primitives.serialization import Encoding
    key, cert, chain = load_identity(company)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise SefazError('A assinatura de manifestação NF-e exige chave RSA no certificado A1.')
    now = now or timezone.now()
    root = etree.Element(f'{{{NFE_NS}}}envEvento', nsmap={None: NFE_NS}, versao='1.00')
    etree.SubElement(root, f'{{{NFE_NS}}}idLote').text = str(int(now.timestamp() * 1000000))[-15:]
    event = etree.SubElement(root, f'{{{NFE_NS}}}evento', versao='1.00')
    identifier = 'ID210210' + access_key + '01'
    info = etree.SubElement(event, f'{{{NFE_NS}}}infEvento', Id=identifier)
    for name, value in [('cOrgao', '91'), ('tpAmb', environment), ('CNPJ', company.cnpj),
                        ('chNFe', access_key), ('dhEvento', timezone.localtime(now).isoformat(timespec='seconds')),
                        ('tpEvento', '210210'), ('nSeqEvento', '1'), ('verEvento', '1.00')]:
        etree.SubElement(info, f'{{{NFE_NS}}}{name}').text = value
    detail = etree.SubElement(info, f'{{{NFE_NS}}}detEvento', versao='1.00')
    etree.SubElement(detail, f'{{{NFE_NS}}}descEvento').text = 'Ciencia da Operacao'
    signature = etree.SubElement(event, f'{{{DS}}}Signature', nsmap={'ds': DS})
    signed_info = etree.SubElement(signature, f'{{{DS}}}SignedInfo')
    etree.SubElement(signed_info, f'{{{DS}}}CanonicalizationMethod', Algorithm=C14N)
    etree.SubElement(signed_info, f'{{{DS}}}SignatureMethod', Algorithm=DS + 'rsa-sha1')
    reference = etree.SubElement(signed_info, f'{{{DS}}}Reference', URI='#' + identifier)
    transforms = etree.SubElement(reference, f'{{{DS}}}Transforms')
    etree.SubElement(transforms, f'{{{DS}}}Transform', Algorithm=DS + 'enveloped-signature')
    etree.SubElement(transforms, f'{{{DS}}}Transform', Algorithm=C14N)
    etree.SubElement(reference, f'{{{DS}}}DigestMethod', Algorithm=DS + 'sha1')
    etree.SubElement(reference, f'{{{DS}}}DigestValue').text = base64.b64encode(hashlib.sha1(_canonical(info)).digest()).decode('ascii')
    etree.SubElement(signature, f'{{{DS}}}SignatureValue').text = base64.b64encode(
        key.sign(_canonical(signed_info), padding.PKCS1v15(), hashes.SHA1())).decode('ascii')
    key_info = etree.SubElement(signature, f'{{{DS}}}KeyInfo')
    x509_data = etree.SubElement(key_info, f'{{{DS}}}X509Data')
    etree.SubElement(x509_data, f'{{{DS}}}X509Certificate').text = base64.b64encode(cert.public_bytes(Encoding.DER)).decode('ascii')
    xml = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    validate_message(xml, 'envEvento_v1.00.xsd', 'envEvento')
    validate_message(etree.tostring(detail), 'e210210_v1.00.xsd', 'detEvento')
    # Envelopar após assinar não deve introduzir namespaces no conteúdo assinado.
    # Serialização explícita evita herdar prefixos SOAP na C14N inclusiva.
    payload = (f'<Envelope xmlns="{SOAP_NS}"><Body>'
               f'<nfeDadosMsg xmlns="{EVENT_NS}">'.encode('utf-8') + xml.split(b'?>', 1)[1] +
               b'</nfeDadosMsg></Body></Envelope>')
    return xml, payload


def send_science(workspace, company_id, document_id, actor=None, authorized=False):
    if not authorized or actor is None or actor.pk != workspace.owner_id:
        raise SefazError('Autorize especificamente a Ciência da Emissão desta nota na aplicação.')
    company = Company.objects.filter(pk=company_id, workspace=workspace).first()
    document = SefazDocument.objects.filter(pk=document_id, state__company=company,
                                           state__source='sefaz', kind='summary').select_related('state').first() if company else None
    if document is None:
        raise SefazError('Resumo oficial não disponível para esta empresa e acesso.')
    from portal.sefaz_models import SefazCaptureConfig
    config = SefazCaptureConfig.objects.filter(company=company, enabled=True,
                                             read_authorized_at__isnull=False).first()
    if config is None or config.environment != document.state.environment:
        raise SefazError('Habilite a captura e autorize a leitura neste ambiente antes de manifestar.')
    if document.state.documents.filter(kind='invoice', access_key=document.access_key).exists():
        raise SefazError('O XML completo já foi recebido; a Ciência não é necessária para obtê-lo.')
    # Verifica prazo documentado de Ciência, quando o resumo fornece a emissão.
    # Prazo legal conta da autorização. Sem a data de autorização no resumo,
    # a SEFAZ decide a aceitação; a interface não inventa um prazo restante.
    signed_xml, payload = science_message(company, config.environment, document.access_key)
    try:
        with transaction.atomic():
            request = SefazScienceRequest.objects.create(company=company, document=document,
                environment=config.environment, access_key=document.access_key,
                cnpj=company.cnpj, authorized_by=actor, signed_xml=signed_xml.decode('utf-8'), status='sent')
            AuditEntry.objects.create(workspace=workspace, description=f'Autorizada Ciência da Emissão, chave {document.access_key}, empresa {company.display_name}'[:250])
    except IntegrityError:
        raise SefazError('A Ciência desta nota já foi solicitada. Confira o resultado registrado; não houve reenvio automático.') from None
    host, path = EVENT_ENDPOINTS[config.environment]
    try:
        response = official_post(company, host, path, EVENT_NS + '/nfeRecepcaoEventoNF', payload)
        root = validate_message(response, 'retEnvEvento_v1.00.xsd', 'retEnvEvento')
        if root.findtext(f'{{{NFE_NS}}}tpAmb') != config.environment or root.findtext(f'{{{NFE_NS}}}cOrgao') != '91':
            raise SefazError('Resposta de manifestação pertence a outro ambiente ou órgão.')
        entries = root.findall(f'{{{NFE_NS}}}retEvento/{{{NFE_NS}}}infEvento')
        batch_code = root.findtext(f'{{{NFE_NS}}}cStat', '')
        if batch_code == '128' and len(entries) == 1:
            entry = entries[0]
            if entry.findtext(f'{{{NFE_NS}}}chNFe') != document.access_key or entry.findtext(f'{{{NFE_NS}}}tpEvento') != '210210':
                raise SefazError('Resposta de manifestação não corresponde à chave e ao evento autorizados.')
            if entry.findtext(f'{{{NFE_NS}}}tpAmb') != config.environment or entry.findtext(f'{{{NFE_NS}}}cOrgao') != '91' or entry.findtext(f'{{{NFE_NS}}}nSeqEvento') != '1':
                raise SefazError('Resposta de manifestação não corresponde ao ambiente, órgão e sequência autorizados.')
        elif batch_code != '128':
            entry = root
        else:
            raise SefazError('Resposta oficial de manifestação sem resultado individual único.')
        code = entry.findtext(f'{{{NFE_NS}}}cStat', '')
        reason = entry.findtext(f'{{{NFE_NS}}}xMotivo', '')
        response_at = parse_datetime(entry.findtext(f'{{{NFE_NS}}}dhRegEvento', ''))
        request.response_code = code
        request.response_reason = reason[:500]
        request.response_at = response_at or timezone.now()
        request.protocol = entry.findtext(f'{{{NFE_NS}}}nProt', '')[:20]
        if code in {'135', '136'} and not request.protocol:
            raise SefazError('Resposta de registro da Ciência sem protocolo oficial. Revise o resultado antes de reenviar.')
        request.response_xml = response.decode('utf-8')
        # 573 duplicidade não prova que ESTE envio foi registrado: manter rejeição.
        request.status = 'accepted' if code in {'135', '136'} else 'rejected'
        request.save()
        AuditEntry.objects.create(workspace=workspace, description=f'Retorno Ciência da Emissão: {code}, empresa {company.display_name}'[:250])
        return request
    except SefazError as error:
        request.status = 'uncertain'
        request.response_reason = str(error)[:500]
        request.save(update_fields=['status', 'response_reason'])
        raise
    except Exception:
        request.status = 'uncertain'
        request.response_reason = 'Falha ao processar retorno. Revise o registro oficial antes de reenviar.'
        request.save(update_fields=['status', 'response_reason'])
        raise SefazError(request.response_reason) from None
