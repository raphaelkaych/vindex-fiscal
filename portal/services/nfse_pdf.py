"""PDF privado baseado no modelo nacional; parciais permanecem conferência."""
import re
from .fiscal_transport import xml_read, validate_xml, NFSE
from .sefaz import SefazError


def generate_nfse_pdf(document):
    if document.service != 'nfse':
        raise SefazError('Este PDF atende somente NFS-e nacional.')
    if getattr(document,'official_pdf',None) is not None and getattr(document,'official_pdf_source',''):
        from .nfse_official_pdf import validate_pdf
        return validate_pdf(bytes(document.official_pdf),document.access_key)
    root = xml_read(document.xml_content.encode())
    version = root.get('versao', '')
    if version not in {'1.00', '1.01'}:
        raise SefazError('Versão de NFS-e ainda não suportada para PDF. Baixe o XML.')
    if getattr(document,'validation_status','schema')=='partial':
        from .nfse_compat import partial_profile
        partial_profile(root)
    else:validate_xml('nfse', f'NFSe_v{version}.xsd', root)
    info = root.find(f'{{{NFSE}}}infNFSe')
    if (info is None or not re.fullmatch(r'[0-9]{50}', document.access_key)
            or info.get('Id') != 'NFS' + document.access_key):
        raise SefazError('O XML não corresponde à NFS-e solicitada.')
    try:
        from .nfse_danfse import render_danfse
        result = render_danfse(document, info)
        if not result.startswith(b'%PDF-') or len(result) > 20 * 1024 * 1024:
            raise ValueError
        return result
    except SefazError:
        raise
    except Exception:
        raise SefazError('Não foi possível representar fielmente esta NFS-e em PDF. O XML original está disponível.') from None
