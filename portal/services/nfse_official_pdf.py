"""Contrato de adaptadores homologados; nenhum endpoint arbitrário é aceito."""
from io import BytesIO
import re
from django.utils import timezone
from .sefaz import SefazError
from .nfse_compat import identify
from .fiscal_transport import xml_read

# Somente código homologado registra adaptadores (município IBGE, ambiente).
# A API ADN DANFSe v1 foi desativada; não há adaptador nacional fictício aqui.
ADAPTERS={}


def public_url(document):
    if document.service=='nfse' and re.fullmatch(r'[0-9]{50}',document.access_key):
        return 'https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave='+document.access_key
    return ''


def capabilities(document):
    return {'official_available':bool(document.official_pdf_source) and document.official_pdf is not None,
        'public_url':public_url(document),'local_kind':'DANFSe recuperado' if document.official_pdf_source and document.official_pdf is not None else 'PDF de conferência' if document.validation_status=='partial' else 'DANFSe gerado pelo Vindex',
        'reason':'API DANFSe do ADN desativada; nenhum conector municipal homologado configurado.' if not ADAPTERS else 'Cobertura depende de município, ambiente e autorizações.'}


def validate_pdf(payload,key):
    if not isinstance(payload,bytes) or not payload.startswith(b'%PDF-') or len(payload)>5*1024*1024:raise SefazError('PDF retornado inválido ou acima de 5 MB.')
    try:
        from pypdf import PdfReader,apply_configuration
        with apply_configuration(zlib_maximum_output_length=1024*1024,stream_decoding_work_maximum_length=4*1024*1024,maximum_declared_stream_length=5*1024*1024):
            reader=PdfReader(BytesIO(payload),strict=True)
            if reader.is_encrypted or not 1<=len(reader.pages)<=10:raise ValueError
            text=''.join(page.extract_text() for page in reader.pages)
        if key not in re.sub(r'\s','',text):raise ValueError
    except Exception:raise SefazError('PDF não permite associação segura à chave desta NFS-e. Original fiscal preservado.') from None
    return payload


def retrieve_if_configured(document):
    """Falha/ausência do PDF nunca desfaz importação ou avança cursor fiscal."""
    if document.service!='nfse' or document.official_pdf is not None:return False
    info=identify(xml_read(document.xml_content.encode()))
    adapter=ADAPTERS.get((info['municipality'],document.environment))
    if adapter is None:return False
    if document.official_pdf_checked_at and (timezone.now()-document.official_pdf_checked_at).total_seconds()<86400:return False
    from portal.models import FiscalConnector,AuditEntry
    from .fiscal_capture import requirements
    config=FiscalConnector.objects.filter(company=document.company,service='nfse',environment=document.environment).first()
    try:
        if config is None:raise SefazError('Conector de leitura não autorizado.')
        requirements(config)
        payload=validate_pdf(adapter.fetch(document.company,document.access_key,document.environment),document.access_key)
    except Exception as error:
        document.official_pdf_checked_at=timezone.now();document.save(update_fields=['official_pdf_checked_at'])
        AuditEntry.objects.create(workspace=document.company.workspace,description='PDF oficial NFS-e indisponível ('+type(error).__name__+'); XML preservado.')
        return False
    document.official_pdf=payload;document.official_pdf_source=str(adapter.source)[:250];document.official_pdf_checked_at=timezone.now()
    document.save(update_fields=['official_pdf','official_pdf_source','official_pdf_checked_at'])
    return True
