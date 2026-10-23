"""Validação dos envelopes DF-e por schemas oficiais locais, sem rede."""
from functools import lru_cache
from pathlib import Path
from lxml import etree
from portal.services.sefaz import NFE_NS, SefazError

SCHEMAS = Path(__file__).with_name('schemas') / 'sefaz'


@lru_cache(maxsize=16)
def schema(name, *, query_kind='distNSU'):
    allowed = {'distDFeInt_v1.01.xsd', 'retDistDFeInt_v1.01.xsd',
               'envEvento_v1.00.xsd', 'retEnvEvento_v1.00.xsd', 'e210210_v1.00.xsd'}
    if name not in allowed:
        raise SefazError('Schema SEFAZ não permitido.')
    if query_kind not in {'distNSU', 'consNSU', 'consChNFe'}:
        raise SefazError('Modalidade de validação SEFAZ inválida.')
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    definition = etree.parse(str(SCHEMAS / name), parser)
    if name == 'retDistDFeInt_v1.01.xsd' and query_kind == 'consChNFe':
        # Compatibilidade restrita com a resposta real do AN 1.7.8: na busca
        # por chave, o retorno 138 omite ultNSU/maxNSU. O XSD publicado ainda
        # os exige. Manter o arquivo oficial intacto e derivar em memória só
        # essa cardinalidade; não inventar cursores nem relaxar distNSU.
        namespaces = {'xs': 'http://www.w3.org/2001/XMLSchema'}
        for field in ('ultNSU', 'maxNSU'):
            definition.find(f'.//xs:element[@name="{field}"]', namespaces).set('minOccurs', '0')
    return etree.XMLSchema(definition)


def validate_message(payload, name, root_name, *, query_kind='distNSU'):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(payload, parser)
        if root.getroottree().docinfo.doctype:
            raise SefazError('DTD não permitido na comunicação oficial.')
        nodes = [root] if root.tag == f'{{{NFE_NS}}}{root_name}' else root.findall(f'.//{{{NFE_NS}}}{root_name}')
        if len(nodes) != 1:
            raise SefazError(f'O serviço não apresentou um único {root_name}; confira o envelope SOAP.')
        validator = schema(name, query_kind=query_kind)
        if not validator.validate(nodes[0]):
            # O log lxml pode conter valores fiscais: não o copie para mensagens.
            raise SefazError(f'A mensagem {root_name} não atende ao schema oficial {name}. Nenhum cursor foi avançado.')
    except (etree.XMLSyntaxError, etree.XMLSchemaError, OSError):
        raise SefazError(f'Não foi possível validar a mensagem pelo schema oficial {name}.') from None
    return nodes[0]
