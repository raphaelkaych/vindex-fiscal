"""OOXML tipado: identificadores e conteúdo de XML nunca viram fórmulas."""
from datetime import date,datetime
from decimal import Decimal
from io import BytesIO
import re
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape,quoteattr
from django.db.models import Count,Sum
from django.db.models.functions import TruncMonth

MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
STATUS={'stored':'Armazenado; situação atual não consultada','partial':'Parcial; revisar','cancelled':'Cancelamento recebido','substituted':'Substituição recebida'}

def column(index):
    result=''
    while index:index,rem=divmod(index-1,26);result=chr(65+rem)+result
    return result

def cell(value,ref,header=False):
    if value is None:return f'<c r="{ref}"/>'
    if isinstance(value,datetime):value=value.date()
    if isinstance(value,date):return f'<c r="{ref}" s="2"><v>{(value-date(1899,12,30)).days}</v></c>'
    if isinstance(value,Decimal) and len(''.join(str(d) for d in value.as_tuple().digits).rstrip('0'))>15:
        value=format(value,'f')
    if isinstance(value,(int,Decimal)):return f'<c r="{ref}" s="{3 if isinstance(value,Decimal) else 0}"><v>{value}</v></c>'
    value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value))[:32767]
    return f'<c r="{ref}" s="{1 if header else 0}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'

def workbook(sheets):
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        overrides=''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+overrides+'</Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{MAIN}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>' for i,(name,*_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{MAIN}"><numFmts count="2"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/><numFmt numFmtId="165" formatCode="#,##0.00########"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0756FF"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i,(name,headers,rows) in enumerate(sheets,1):
            with z.open(f'xl/worksheets/sheet{i}.xml','w') as sheet:
                def write(value):sheet.write(value.encode())
                write(f'<worksheet xmlns="{MAIN}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>')
                for c,h in enumerate(headers,1):
                    width=54 if 'Descrição' in h or 'Chave' in h else 38 if 'Nome' in h or 'Situação' in h else 26 if 'CNPJ' in h else 24
                    write(f'<col min="{c}" max="{c}" width="{width}" customWidth="1"/>')
                write('</cols><sheetData>');count=0
                from itertools import chain
                for count,row in enumerate(chain([headers],rows),1):
                    write(f'<row r="{count}"'+(' ht="32" customHeight="1"' if count==1 else '')+'>')
                    for c,value in enumerate(row,1):write(cell(value,f'{column(c)}{count}',count==1))
                    write('</row>')
                write(f'</sheetData><autoFilter ref="A1:{column(len(headers))}{max(1,count)}"/></worksheet>')
    return output.getvalue()

def fiscal_workbook(records,items,filters):
    def documents():
        for r in records.select_related('company').order_by('issued_on','pk').iterator(chunk_size=500):
            yield [r.kind.upper(),r.environment or 'Não informado',r.company.display_name,r.company.cnpj,r.number,r.series,r.access_key,r.issuer_name,r.issuer_cnpj,r.recipient_cnpj,r.issued_on,r.total,STATUS[r.status],r.diagnostic]
    def details():
        for item in items.select_related('record__company').order_by('record_id','position').iterator(chunk_size=500):
            r=item.record
            yield [r.kind.upper(),r.environment or 'Não informado',r.company.display_name,r.company.cnpj,r.number,r.series,r.access_key,r.issuer_name,r.issuer_cnpj,r.issued_on,item.position,item.description,item.code,item.ncm,item.cfop,item.unit,item.quantity,item.unit_price,item.total]
    def grouped(fields):
        for row in records.order_by().values('kind','environment',*fields).annotate(documents=Count('pk'),amount=Sum('total')).order_by('kind',*fields):
            yield [row['kind'].upper(),row['environment'] or 'Não informado',*[row[f] for f in fields],row['documents'],row['amount']]
    period=records.annotate(month=TruncMonth('issued_on'))
    notes=[['Fonte','XMLs privados armazenados no Vindex Fiscal; mesmos filtros da pesquisa.'],['Valores','Valores declarados; incluem cancelados/parciais quando selecionados. Não indicam pagamento.'],['Itens','Somente campos presentes no XML. Vazios não significam zero. CT-e descreve carga; não infere itens/quantidades.'],['Resumos','Não contêm itens; permanecem na captura, fora deste relatório.'],['Tipos','NF-e 55, NFS-e nacional e CT-e 57. NFC-e 65 não possui importador/conector.']]
    allowed=['company','type','issuer_cnpj','issuer','recipient_cnpj','number','series','key','start','end','minimum','maximum','status','product','code','ncm','cfop','environment']
    labels=['Empresa (ID)','Tipo','CNPJ do emitente','Nome do emitente','CNPJ destinatário / tomador','Número','Série','Chave de acesso','Emissão inicial','Emissão final','Valor mínimo','Valor máximo','Situação','Produto / serviço','Código','NCM','CFOP','Ambiente']
    notes.append(['Precisão','Valores com mais de 15 algarismos significativos são exportados como texto para preservar a precisão.'])
    notes.extend([label,filters[key]] for key,label in zip(allowed,labels) if filters.get(key))
    return workbook([
        ('Documentos',['Tipo','Ambiente','Nome da empresa','CNPJ da empresa','Número','Série','Chave de acesso','Nome do emitente','CNPJ do emitente','CNPJ destinatário / tomador','Emissão','Valor declarado (R$)','Situação informada','Limitação de leitura'],documents()),
        ('Itens encontrados',['Tipo','Ambiente','Nome da empresa','CNPJ da empresa','Número','Série','Chave de acesso','Nome do fornecedor','CNPJ fornecedor','Emissão','Item','Descrição','Código','NCM','CFOP','Unidade','Quantidade','Valor unitário (R$)','Valor do item (R$)'],details()),
        ('Por fornecedor',['Tipo','Ambiente','CNPJ fornecedor','Nome do fornecedor','Documentos','Valor declarado (R$)'],grouped(['issuer_cnpj','issuer_name'])),
        ('Por empresa',['Tipo','Ambiente','CNPJ da empresa','Nome da empresa','Documentos','Valor declarado (R$)'],grouped(['company__cnpj','company__legal_name'])),
        ('Por período',['Tipo','Ambiente','Mês de emissão','Documentos','Valor declarado (R$)'],([r['kind'].upper(),r['environment'] or 'Não informado',r['month'].strftime('%Y-%m'),r['documents'],r['amount']] for r in period.order_by().values('kind','environment','month').annotate(documents=Count('pk'),amount=Sum('total')).order_by('month','kind','environment'))),
        ('Critérios',['Campo','Descrição'],notes),
    ])
