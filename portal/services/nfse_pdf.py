"""PDF de conferência privado. Não é o DANFSe v2.0 da NT 008."""
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
        from fpdf import FPDF
        pdf = FPDF(format='A4')
        pdf.core_fonts_encoding = 'windows-1252'
        pdf.set_margins(14, 14, 14)
        pdf.set_auto_page_break(True, 16)
        pdf.set_title('NFS-e - espelho do XML')
        pdf.set_creator('Vindex Fiscal')
        pdf.add_page()

        def line(text, bold=False, size=9):
            pdf.set_font('Helvetica', 'B' if bold else '', size)
            pdf.multi_cell(0, 5, text, new_x='LMARGIN', new_y='NEXT')

        line('NFS-e | PDF de conferência', True, 16)
        line('Espelho gerado do XML recebido. Não substitui o XML nem o DANFSe oficial.')
        line('Situação fiscal atual e pagamento não consultados.')
        if getattr(document,'validation_status','schema')=='partial':
            line('IMPORTAÇÃO PARCIAL — ESTRUTURA E ASSINATURA EXIGEM REVISÃO', True)
        if document.environment == '2':
            line('HOMOLOGAÇÃO - SEM VALIDADE JURÍDICA', True)
        if document.cancellation_reported:
            line('EVENTO DE CANCELAMENTO RECEBIDO', True)
        line('Chave de acesso: ' + document.access_key, True)
        for title, path in [
            ('Número', 'nNFSe'), ('Processamento', 'dhProc'),
            ('Competência', 'DPS/infDPS/dCompet'),
            ('Emissão da DPS', 'DPS/infDPS/dhEmi'),
            ('Prestador', 'emit/xNome'), ('CNPJ do prestador', 'emit/CNPJ'),
            ('Tomador', 'DPS/infDPS/toma/xNome'),
            ('CNPJ do tomador', 'DPS/infDPS/toma/CNPJ'),
            ('Serviço', 'DPS/infDPS/serv/cServ/xDescServ'),
            ('Valor do serviço (R$)', 'DPS/infDPS/valores/vServPrest/vServ'),
            ('Valor líquido (R$)', 'valores/vLiq')]:
            node = info.find('/'.join('{' + NFSE + '}' + p for p in path.split('/')))
            line(title + ': ' + (node.text if node is not None and node.text else 'Não informado no XML'))
        line('Consulta pública da chave:', True)
        url = 'https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=' + document.access_key
        pdf.set_font('Helvetica', '', 8)
        pdf.multi_cell(0, 5, 'Abrir consulta no Portal Nacional NFS-e', link=url, new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)
        line('Campos do documento original', True, 12)
        line('Caminhos e valores literais do XML; sem cálculos ou arredondamentos. Assinatura digital disponível no XML original.')

        def fields(node, path='infNFSe'):
            if not isinstance(node.tag, str) or not node.tag.startswith('{' + NFSE + '}'):
                return
            children = list(node)
            if not children and node.text and node.text.strip():
                line(path, True, 8)
                line(node.text, size=9)
            for child in children:
                if isinstance(child.tag, str):
                    fields(child, path + '/' + child.tag.rsplit('}', 1)[-1])
        fields(info)
        result = bytes(pdf.output())
        if not result.startswith(b'%PDF-') or len(result) > 20 * 1024 * 1024:
            raise ValueError
        return result
    except Exception:
        raise SefazError('Não foi possível representar fielmente esta NFS-e em PDF. O XML original está disponível.') from None
