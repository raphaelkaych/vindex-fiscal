"""Validação dos envelopes DF-e por schemas oficiais locais, sem rede."""
from functools import lru_cache
from pathlib import Path
from lxml import etree
from portal.services.sefaz import NFE_NS, SefazError

SCHEMAS = Path(__file__).with_name('schemas') / 'sefaz'


@lru_cache(maxsize=16)
def schema(name):
    allowed = {'distDFeInt_v1.01.xsd', 'retDistDFeInt_v1.01.xsd',
               'envEvento_v1.00.xsd', 'retEnvEvento_v1.00.xsd', 'e210210_v1.00.xsd'}
    if name not in allowed:
        raise SefazError('Schema SEFAZ não permitido.')
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return etree.XMLSchema(etree.parse(str(SCHEMAS / name), parser))


def validate_message(payload, name, root_name):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(payload, parser)
        if root.getroottree().docinfo.doctype:
            raise SefazError('DTD não permitido na comunicação oficial.')
        nodes = [root] if root.tag == f'{{{NFE_NS}}}{root_name}' else root.findall(f'.//{{{NFE_NS}}}{root_name}')
        if len(nodes) != 1:
            raise SefazError(f'O serviço não apresentou um único {root_name}; confira o envelope SOAP.')
        validator = schema(name)
        if not validator.validate(nodes[0]):
            # O log lxml pode conter valores fiscais: não o copie para mensagens.
            raise SefazError(f'A mensagem {root_name} não atende ao schema oficial {name}. Nenhum cursor foi avançado.')
    except (etree.XMLSyntaxError, etree.XMLSchemaError, OSError):
        raise SefazError(f'Não foi possível validar a mensagem pelo schema oficial {name}.') from None
    return nodes[0]
