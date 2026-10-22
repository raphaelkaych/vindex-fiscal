"""Perfis limitados de compatibilidade. Originais e assinatura não são alterados."""
import base64
from copy import deepcopy
from pathlib import Path
from lxml import etree as XML
from django.utils.dateparse import parse_datetime
from .sefaz import SefazError
from .fiscal_transport import NFSE, schema

REVISION='nfse-20261021-3'
NS={'n':NFSE,'ds':'http://www.w3.org/2000/09/xmldsig#'}


def identify(root):
    namespace=XML.QName(root).namespace or ''
    name=XML.QName(root).localname
    return {'pattern':'nacional' if namespace==NFSE else 'abrasf' if 'abrasf' in namespace.lower() or name=='CompNfse' else 'desconhecido',
        'root':name,'namespace':namespace[:150],'version':root.get('versao','')[:20],
        'municipality':root.findtext('.//n:emit/n:enderNac/n:cMun','',NS) or root.findtext('.//n:locPrest/n:cLocPrestacao','',NS),
        'environment':root.findtext('.//n:tpAmb','',NS),'revision':REVISION}


def signature_status(root):
    # Apenas integridade criptográfica com a chave embutida. Não é cadeia ICP,
    # revogação ou confirmação da situação fiscal. SHA1 restrito à leitura legada.
    try:
        from cryptography import x509
        from signxml import XMLVerifier,SignatureConfiguration,SignatureMethod,DigestAlgorithm
        signature=root.find('ds:Signature',NS)
        if signature is None:return 'absent'
        cert=x509.load_der_x509_certificate(base64.b64decode(signature.findtext('ds:KeyInfo/ds:X509Data/ds:X509Certificate',namespaces=NS),validate=False))
        when=parse_datetime(root.findtext('n:infNFSe/n:dhProc','',NS))
        if when is not None and when.tzinfo and not cert.not_valid_before_utc<=when<=cert.not_valid_after_utc:
            return 'certificate_outside_declared_processing_validity'
        config=SignatureConfiguration(location='./',signature_methods=frozenset([SignatureMethod.RSA_SHA1,SignatureMethod.RSA_SHA256]),
            digest_algorithms=frozenset([DigestAlgorithm.SHA1,DigestAlgorithm.SHA256]),verification_time=when)
        result=XMLVerifier().verify(root,x509_cert=cert,expect_config=config,id_attribute='Id')
        info=root.find('n:infNFSe',NS)
        if info is None or result.signed_xml.tag!=info.tag or result.signed_xml.get('Id')!=info.get('Id'):return 'invalid_reference'
        return 'verified_embedded_key'
    except Exception as error:
        # Nunca ecoar mensagens da biblioteca: podem conter nome/certificado.
        return 'invalid' if type(error).__name__ in {'InvalidSignature','InvalidDigest'} else 'unverified'


def partial_profile(root):
    """Só aceita cópia estruturalmente válida após duas adaptações enumeradas.

    Não declara o original conforme ao XSD: o resultado permanece PARCIAL.
    Nenhum nó da árvore original é movido, removido ou regravado.
    """
    if root.tag!='{'+NFSE+'}NFSe' or root.get('versao')!='1.00':
        raise SefazError('Padrão/versão sem perfil de compatibilidade. Original preservado.')
    shadow=deepcopy(root);changes=[]
    for tax in shadow.findall('.//n:DPS/n:infDPS/n:valores/n:trib/n:tribMun',NS):
        if [XML.QName(x).localname for x in tax]==['tribISSQN','tpRetISSQN','pAliq']:
            rate=tax[-1];tax.remove(rate);tax.insert(1,rate);changes.append('pAliq_order')
    info=shadow.find('n:infNFSe',NS)
    extras=info.findall('n:xOutInf',NS) if info is not None else []
    if len(extras)==1 and info.index(extras[0])+1<len(info) and info[info.index(extras[0])+1].tag=='{'+NFSE+'}DPS':
        # Tipo TSDesc2000 oficial, validado separadamente sem remover restrições.
        types=Path(__file__).parent/'schemas'/'nfse'/'tiposSimples_v1.00.xsd'
        source=f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="{NFSE}" xmlns:n="{NFSE}" elementFormDefault="qualified"><xs:include schemaLocation="{types.as_uri()}"/><xs:element name="xOutInf" type="n:TSDesc2000"/></xs:schema>'
        if not XML.XMLSchema(XML.fromstring(source.encode())).validate(extras[0]):raise SefazError('Informação complementar fora dos limites do tipo oficial.')
        info.remove(extras[0]);changes.append('xOutInf_extension')
    if not changes or not schema('nfse','NFSe_v1.00.xsd').validate(shadow):
        raise SefazError('Diferença estrutural fora dos perfis restritos. Original preservado.')
    details=identify(root)
    details.update({'profile':changes,'signature':signature_status(root),'original_schema_valid':False,'financial_eligible':False,
        'reason':'Estrutura compatível em conferência parcial; original não conforme ao XSD. Assinatura não certifica validade fiscal.'})
    return details
