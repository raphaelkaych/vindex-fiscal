"""Leitura local de NFS-e nacional para tela/PDF. Não consulta nem modifica XML."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from .fiscal_transport import NFSE, xml_read, validate_xml
from .sefaz import SefazError

NS = {'n': NFSE}
DPS = 'DPS/infDPS/'
MUN = DPS + 'valores/trib/tribMun/'
FED = DPS + 'valores/trib/tribFed/'


def read_nfse(document, *, validate=False):
    if document.service != 'nfse':
        raise SefazError('Este documento não é uma NFS-e nacional.')
    root = xml_read(document.xml_content.encode())
    version = root.get('versao', '')
    info = root.find('n:infNFSe', NS)
    if (root.tag != '{' + NFSE + '}NFSe' or version not in {'1.00', '1.01'}
            or info is None or not re.fullmatch(r'[0-9]{50}', document.access_key)
            or info.get('Id') != 'NFS' + document.access_key):
        raise SefazError('O XML não corresponde a uma NFS-e nacional suportada. Baixe o original para conferência.')
    if validate:
        if document.validation_status == 'partial':
            from .nfse_compat import partial_profile
            partial_profile(root)
        else:
            validate_xml('nfse', f'NFSe_v{version}.xsd', root)
    return info


def value(info, path, default=''):
    node = info.find('/'.join('n:' + part for part in path.split('/')), NS)
    return node.text.strip() if node is not None and node.text else default


def money(text):
    if not text:
        return 'Não informado'
    try:
        number = Decimal(text)
        if not number.is_finite():
            return text
        return 'R$ ' + format(number, ',.2f').replace(',', '_').replace('.', ',').replace('_', '.')
    except InvalidOperation:
        return text


def date_text(text):
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.strftime('%d/%m/%Y %H:%M:%S') if 'T' in text else parsed.strftime('%d/%m/%Y')
    except ValueError:
        return text


def document_id(text):
    if re.fullmatch(r'\d{14}', text):
        return f'{text[:2]}.{text[2:5]}.{text[5:8]}/{text[8:12]}-{text[12:]}'
    if re.fullmatch(r'\d{11}', text):
        return f'{text[:3]}.{text[3:6]}.{text[6:9]}-{text[9:]}'
    return text


def display(info, path, mapping=None):
    text = value(info, path)
    return (mapping or {}).get(text, text) or 'Não informado'


def parties(info):
    result = []
    for title, path in [('Prestador / fornecedor', DPS+'prest'), ('Tomador / adquirente', DPS+'toma'),
                        ('Destinatário da operação', DPS+'IBSCBS/dest'), ('Intermediário da operação', DPS+'interm')]:
        if info.find('/'.join('n:'+part for part in path.split('/')), NS) is None:
            if 'Prestador' in title:
                path = 'emit'
            else:
                result.append({'title': title, 'missing': True, 'rows': []})
                continue
        get = lambda field: value(info, path+'/'+field) or (value(info,'emit/'+field) if path==DPS+'prest' else '')
        address = ', '.join(filter(None, [get('end/'+x) for x in ['xLgr','nro','xCpl','xBairro']]))
        if path == 'emit' or (path==DPS+'prest' and not address):
            address = ', '.join(filter(None, [get('enderNac/'+x) for x in ['xLgr','nro','xCpl','xBairro']]))
        locality = get('end/endNac/cMun') or get('enderNac/cMun') or get('end/endExt/xCidade')
        postal = get('end/endNac/CEP') or get('enderNac/CEP') or get('end/endExt/cEndPost')
        result.append({'title':title, 'missing':False, 'rows':[
            [('CNPJ / CPF / NIF', document_id(get('CNPJ') or get('CPF') or get('NIF'))),
             ('Inscrição municipal', get('IM')), ('Telefone', get('fone'))],
            [('Nome / nome empresarial', get('xNome') or (value(info,'emit/xNome') if path.endswith('/prest') else '')),
             ('Localidade (código IBGE / exterior)', locality), ('CEP / código postal', postal)],
            [('Endereço', address), ('E-mail', get('email'))],
        ]})
    return result


def sections(info):
    """Campos literais e códigos conhecidos; ausências nunca viram zero."""
    def row(label, path, kind='text', mapping=None):
        raw = value(info,path)
        text = money(raw) if kind=='money' else date_text(raw) if kind=='date' else (mapping or {}).get(raw,raw)
        return (label,text or 'Não informado')
    return [
        {'title':'Identificação da NFS-e','rows':[
            [row('Número da NFS-e','nNFSe'),row('Competência',DPS+'dCompet','date'),row('Emissão da DPS',DPS+'dhEmi','date')],
            [row('Número da DPS',DPS+'nDPS'),row('Série da DPS',DPS+'serie'),row('Simples Nacional (código)',DPS+'prest/regTrib/opSimpNac'),row('Regime de apuração SN (código)',DPS+'prest/regTrib/regApTribSN')],
        ]},
        {'title':'Serviço prestado','rows':[
            [row('Tributação nacional',DPS+'serv/cServ/cTribNac'),row('Tributação municipal',DPS+'serv/cServ/cTribMun'),row('Código NBS',DPS+'serv/cServ/cNBS'),row('Local da prestação','xLocPrestacao')],
            [row('Descrição da tributação','xTribNac'),row('Descrição municipal','xTribMun')],
            [row('Descrição do serviço',DPS+'serv/cServ/xDescServ')],
        ]},
        {'title':'Tributação municipal (ISSQN)','rows':[
            [row('Tipo de tributação',MUN+'tribISSQN',mapping={'1':'Operação tributável','2':'Imunidade','3':'Exportação de serviço','4':'Não incidência'}),row('Local da incidência','xLocIncid'),row('Regime especial',DPS+'prest/regTrib/regEspTrib')],
            [row('Base de cálculo','valores/vBC','money'),row('Alíquota aplicada (%)','valores/pAliqAplic'),row('Retenção ISSQN',MUN+'tpRetISSQN',mapping={'1':'Não retido','2':'Retido pelo tomador','3':'Retido pelo intermediário'}),row('ISSQN apurado','valores/vISSQN','money')],
            [row('Imunidade (código)',MUN+'tpImunidade'),row('Exigibilidade suspensa',MUN+'exigSusp/tpSusp'),row('Processo',MUN+'exigSusp/nProcesso'),row('Benefício municipal','valores/tpBM')],
            [row('Cálculo do benefício','valores/vCalcBM','money'),row('Deduções / reduções','valores/vCalcDR','money'),row('Desconto incondicionado',DPS+'valores/vDescCondIncond/vDescIncond','money')],
        ]},
        {'title':'Tributação federal (exceto CBS)','rows':[
            [row('IRRF retido',FED+'vRetIRRF','money'),row('Previdência retida',FED+'vRetCP','money'),row('CSLL retida',FED+'vRetCSLL','money')],
            [row('PIS informado no XML',FED+'piscofins/vPis','money'),row('COFINS informado no XML',FED+'piscofins/vCofins','money'),row('Retenção PIS/COFINS',FED+'piscofins/tpRetPisCofins',mapping={'1':'Retidos','2':'Não retidos'})],
        ]},
        {'title':'Valor total da NFS-e','rows':[
            [row('Valor do serviço',DPS+'valores/vServPrest/vServ','money'),row('Desconto incondicionado',DPS+'valores/vDescCondIncond/vDescIncond','money'),row('Desconto condicionado',DPS+'valores/vDescCondIncond/vDescCond','money')],
            [row('Total de retenções','valores/vTotalRet','money'),row('Valor líquido','valores/vLiq','money'),row('Valor final (vTotNF)','IBSCBS/totCIBS/vTotNF','money')],
        ]},
        {'title':'Informações complementares','rows':[
            [row('Informações do serviço',DPS+'serv/infoCompl/xInfComp')],
            [row('Informações da administração','xOutInf')],
        ]},
    ]


def extra_fields(info, path):
    node = info.find('/'.join('n:'+part for part in path.split('/')), NS)
    if node is None:
        return []
    rows = []
    def walk(current, prefix=''):
        for child in current:
            if not isinstance(child.tag,str) or not child.tag.startswith('{'+NFSE+'}'):
                continue
            name=child.tag.rsplit('}',1)[-1]
            if len(child):
                walk(child,prefix+name+'/')
            elif child.text and child.text.strip():
                rows.append((prefix+name,child.text.strip()))
    walk(node)
    return rows
