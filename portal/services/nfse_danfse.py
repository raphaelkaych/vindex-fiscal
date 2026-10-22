"""Composição A4 local baseada no modelo DANFSe v2.0 da NT 008 v1.02.

O PDF não atesta assinatura, situação atual ou pagamento. Não há acesso de rede.
"""
from pathlib import Path
from .nfse_presentation import value, display, date_text, parties, sections, extra_fields, DPS
from .sefaz import SefazError


def render_danfse(document, info):
    from fpdf import FPDF
    from fpdf.enums import MethodReturnValue, WrapMode
    from brazilfiscalreport.generate_qrcode import make_qr_code_image
    pdf=FPDF(format='A4')
    pdf.core_fonts_encoding='windows-1252'
    pdf.set_margins(3,3,3)
    pdf.set_auto_page_break(False)
    fonts=Path('C:/Windows/Fonts')
    # Fontes proprietárias são usadas da instalação, nunca redistribuídas.
    if (fonts/'arialbd.ttf').exists() and (fonts/'micross.ttf').exists():
        pdf.add_font('Body','',str(fonts/'micross.ttf'))
        pdf.add_font('Body','B',str(fonts/'arialbd.ttf'))
        family='Body'
    else:
        family='Helvetica'
    partial=getattr(document,'validation_status','schema')=='partial'
    pdf.set_title('NFS-e - '+('PDF de conferência' if partial else 'DANFSe gerado pelo Vindex'))
    pdf.set_creator('Vindex Fiscal')
    pdf.add_page()
    pdf.set_draw_color(55)
    pdf.set_line_width(.176)

    def text(x,y,w,h,content,size=7,bold=False,align='L'):
        content=str(content or 'Não informado').replace('\t',' ').replace('\r','')
        pdf.set_font(family,'B' if bold else '',size)
        lines=pdf.multi_cell(w,3,content,dry_run=True,output=MethodReturnValue.LINES,wrapmode=WrapMode.CHAR)
        limit=max(1,int(h/3))
        if len(lines)>limit:
            lines=lines[:limit];last=lines[-1]
            while last and pdf.get_string_width(last+'...')>w-2:last=last[:-1]
            lines[-1]=last+'...'
        pdf.set_xy(x,y)
        pdf.multi_cell(w,3,'\n'.join(lines),align=align,new_x='LMARGIN',new_y='NEXT')

    y=3
    compact=all(not party['missing'] for party in parties(info))
    title_height=4 if compact else 4.5
    def title(label):
        nonlocal y
        pdf.set_fill_color(242)
        pdf.rect(3,y,204,title_height,style='DF')
        text(4,y+.6,202,3,label.upper(),7,True)
        y+=title_height

    def row(cells,height=None,width=204):
        nonlocal y
        height=height or (7 if compact else 8)
        width=width/len(cells)
        for index,(label,content) in enumerate(cells):
            x=3+index*width
            pdf.rect(x,y,width,height)
            text(x+1,y+.4,width-2,3,label,6,True)
            text(x+1,y+3.6,width-2,height-3.6,content)
        y+=height

    pdf.set_fill_color(242)
    pdf.rect(3,3,204,12,style='DF')
    logo=Path(__file__).resolve().parents[2]/'static/portal/nfse-logo-oficial.png'
    pdf.image(str(logo),x=5,y=4.8,w=43,keep_aspect_ratio=True)
    text(54,4,99,3,'DANFSe v2.0' if not partial else 'NFS-e | CONFERÊNCIA',9,True,'C')
    text(54,7.3,99,3,'Documento Auxiliar da NFS-e',9,True,'C')
    if document.environment=='2':
        pdf.set_text_color(190,0,0)
        text(54,10.6,99,3,'NFS-e SEM VALIDADE JURÍDICA',9,True,'C')
        pdf.set_text_color(0)
    municipality=' / '.join(filter(None,[value(info,'xLocEmi'),value(info,'emit/enderNac/UF')]))
    text(155,4,50,3,municipality,8)
    text(155,7.4,50,3,'Ambiente gerador: '+(value(info,'ambGer') or 'Não informado'),6)
    text(155,10.5,50,3,'Ambiente: '+('Homologação' if document.environment=='2' else 'Produção'),6)
    y=15
    warning=[]
    if partial:warning.append('IMPORTAÇÃO PARCIAL - REVISAR ESTRUTURA E ASSINATURA')
    if getattr(document,'substitution_reported',False):warning.append('SUBSTITUIÇÃO RECEBIDA')
    elif document.cancellation_reported:warning.append('CANCELAMENTO RECEBIDO')
    if warning:
        pdf.set_text_color(165,20,20)
        text(4,y,202,7,' | '.join(warning),8,True)
        pdf.set_text_color(0)
        y+=7
    start=y
    pdf.rect(3,start,153,26)
    text(4,start+.5,151,3,'CHAVE DE ACESSO DA NFS-e',7,True)
    text(4,start+4,151,4,document.access_key,8)
    labels=[('NÚMERO DA NFS-e','nNFSe'),('COMPETÊNCIA',DPS+'dCompet'),('EMISSÃO DA NFS-e','dhProc'),
            ('NÚMERO DA DPS',DPS+'nDPS'),('SÉRIE DA DPS',DPS+'serie'),('EMISSÃO DA DPS',DPS+'dhEmi')]
    for i,(label,path) in enumerate(labels):
        x=4+(i%3)*51;top=start+9+(i//3)*8
        text(x,top,49,3,label,6,True)
        text(x,top+3.2,49,4,date_text(value(info,path)))
    url='https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave='+document.access_key
    # Coluna reservada de 51 x 34 mm: QR quadrado centralizado, margem
    # branca de quatro módulos e legenda separada dos campos à esquerda.
    pdf.rect(156,start,51,34)
    pdf.image(make_qr_code_image(url,box_size=6,border=4),x=170.5,y=start+.5,w=22,h=22,link=url)
    text(157,start+24,49,9,'A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR ou pela consulta da chave de acesso no portal nacional da NFS-e.',6)
    y=start+26
    row([('Emitente da NFS-e',display(info,DPS+'tpEmit',{'1':'Prestador','2':'Tomador','3':'Intermediário'})),
         ('Situação no XML (código)',value(info,'cStat')),('Finalidade (código)',value(info,DPS+'IBSCBS/finNFSe'))],width=153)
    for party in parties(info):
        title(party['title'])
        if party['missing']:
            text(4,y+.6,202,3,'Não identificado na NFS-e');y+=4
        else:
            for cells in party['rows']:row(cells)
    for section in sections(info):
        if section['title'] in {'Identificação da NFS-e','Informações complementares'}:continue
        title(section['title'])
        for cells in section['rows']:row(cells,(8 if compact else 14) if cells[0][0]=='Descrição do serviço' else None)
    ibs=extra_fields(info,'IBSCBS')+extra_fields(info,DPS+'IBSCBS')
    title('Tributação IBS / CBS - dados do XML')
    text(4,y+.6,202,9,' | '.join(label+': '+val for label,val in ibs) or 'Não informado no XML');y+=10
    title('Informações complementares')
    complements=[value(info,'xOutInf'),value(info,DPS+'serv/infoCompl/xInfComp')]
    if getattr(document,'substituted_by',''):complements.append('Chave substituta: '+document.substituted_by)
    text(4,y+.6,202,9,' | '.join(filter(None,complements)) or 'Não informado no XML');y+=10
    if y>285:
        raise SefazError('Este XML exige uma composição ainda não suportada em uma página. Baixe o XML original.')
    pdf.set_line_width(.35)
    pdf.rect(3,3,204,282)
    text(4,286,202,8,'Gerado pelo Vindex a partir do XML | Modelo baseado na NT 008 v1.02 | Não substitui o XML original. Situação atual e pagamento não consultados. Campos extensos podem ser abreviados.',6)
    return bytes(pdf.output())
