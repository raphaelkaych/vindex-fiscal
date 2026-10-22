"""Leitura tipada e local de CT-e 57 v4.00; sem rede ou alteração do XML."""
import re
from urllib.parse import urlsplit,parse_qs
from .fiscal_transport import CTE,xml_read,validate_xml
from .nfse_presentation import money,date_text,document_id
from .sefaz import SefazError

NS={'n':CTE}
MODALS={'01':'Rodoviário','02':'Aéreo','03':'Aquaviário','04':'Ferroviário','05':'Dutoviário','06':'Multimodal'}
ROLES={'emit':'Emitente','rem':'Remetente','dest':'Destinatário','exped':'Expedidor','receb':'Recebedor','toma4':'Tomador','autXML':'Autorizado no XML'}


def field(node,path,default=''):
    return node.findtext('/'.join('n:'+part for part in path.split('/')),default,NS).strip()


def read_cte(document,*,validate=False):
    if document.service!='cte':raise SefazError('Este documento não é um CT-e modelo 57.')
    root=xml_read(document.xml_content.encode())
    info=root.find('n:CTe/n:infCte',NS)
    if (root.tag!='{'+CTE+'}cteProc' or root.get('versao')!='4.00' or info is None
            or info.get('versao')!='4.00' or not re.fullmatch(r'[0-9]{44}',document.access_key)
            or info.get('Id')!='CTe'+document.access_key or field(info,'ide/mod')!='57'):
        raise SefazError('XML não corresponde a um CT-e completo modelo 57, versão 4.00. O original está disponível.')
    if (field(root,'protCTe/infProt/chCTe')!=document.access_key
            or field(root,'protCTe/infProt/cStat') not in {'100','150'}
            or not field(root,'protCTe/infProt/nProt')):
        raise SefazError('Protocolo de autorização do CT-e ausente ou incompatível. Baixe o XML original.')
    if field(info,'ide/tpAmb')!=document.environment:
        raise SefazError('Ambiente do CT-e divergente do cadastro do documento. Baixe o XML original.')
    if validate:validate_xml('cte','procCTe_v4.00.xsd',root)
    return root,info


def qr_url(root,key,environment):
    """Somente o endereço declarado no XML, com chave e ambiente correspondentes."""
    url=field(root,'CTe/infCTeSupl/qrCodCTe')
    if not url:return ''
    try:parsed=urlsplit(url)
    except ValueError:raise SefazError('Endereço de QR Code inválido. XML original preservado.') from None
    query=parse_qs(parsed.query)
    if (parsed.scheme not in {'http','https'} or not (parsed.hostname or '').endswith('.gov.br')
            or parsed.username or parsed.password or query.get('chCTe')!=[key]
            or query.get('tpAmb')!=[environment]):
        raise SefazError('QR Code do CT-e não corresponde à chave, ao ambiente ou a um portal governamental. XML preservado.')
    return url


def party_rows(info):
    parties=[('Transportador / emitente','emit','enderEmit'),('Remetente','rem','enderReme'),
             ('Destinatário','dest','enderDest'),('Expedidor','exped','enderExped'),('Recebedor','receb','enderReceb')]
    taker=field(info,'ide/toma3/toma')
    lookup={'0':('rem','enderReme'),'1':('exped','enderExped'),'2':('receb','enderReceb'),'3':('dest','enderDest')}
    if taker in lookup:parties.append(('Tomador do serviço',*lookup[taker]))
    elif info.find('n:ide/n:toma4',NS) is not None:parties.append(('Tomador do serviço','ide/toma4','enderToma'))
    result=[]
    for title,path,address_tag in parties:
        node=info.find('/'.join('n:'+part for part in path.split('/')),NS)
        if node is None:
            result.append({'title':title,'missing':True,'rows':[]});continue
        get=lambda name:field(node,name)
        address=', '.join(filter(None,[get(address_tag+'/'+name) for name in ['xLgr','nro','xCpl','xBairro']]))
        result.append({'title':title,'missing':False,'rows':[
            [('Nome / razão social',get('xNome')),('CNPJ / CPF',document_id(get('CNPJ') or get('CPF'))),('Inscrição estadual',get('IE'))],
            [('Endereço',address),('Município / UF',' / '.join(filter(None,[get(address_tag+'/xMun'),get(address_tag+'/UF')]))),('CEP',get(address_tag+'/CEP'))],
            [('Telefone',get('fone') or get(address_tag+'/fone')),('E-mail',get('email'))],
        ]})
    return result


def sections(root,info):
    def row(label,path,kind='',mapping=None):
        raw=field(info,path)
        text=money(raw) if kind=='money' else date_text(raw) if kind=='date' else (mapping or {}).get(raw,raw)
        return label,text or 'Não informado no XML'
    quantities=[]
    for node in info.findall('n:infCTeNorm/n:infCarga/n:infQ',NS):
        unit=field(node,'cUnid')
        quantities.append((' / '.join(filter(None,[field(node,'tpMed'),{'00':'m³','01':'kg','02':'tonelada','03':'unidade','04':'litro','05':'MMBTU'}.get(unit,'Unidade '+unit)])),field(node,'qCarga')))
    components=[(field(node,'xNome') or 'Componente',money(field(node,'vComp'))) for node in info.findall('n:vPrest/n:Comp',NS)]
    tax_fields=[]
    tax=info.find('n:imp/n:ICMS',NS)
    labels={'CST':'Situação tributária (CST)','vBC':'Base de cálculo','pICMS':'Alíquota ICMS (%)','vICMS':'Valor ICMS','pRedBC':'Redução da base (%)','vCred':'Crédito','vBCSTRet':'Base ICMS ST retido','vICMSSTRet':'ICMS ST retido','pICMSSTRet':'Alíquota ST (%)','indSN':'Indicador Simples Nacional'}
    if tax is not None:
        for node in tax.iter():
            name=node.tag.rsplit('}',1)[-1] if isinstance(node.tag,str) else ''
            if len(node)==0 and node.text:
                tax_fields.append((labels.get(name,name),money(node.text) if name.startswith('v') else node.text))
    result=[
        {'title':'Identificação e percurso','rows':[
            [row('Número','ide/nCT'),row('Série','ide/serie'),row('Emissão','ide/dhEmi','date')],
            [row('Modal','ide/modal',mapping=MODALS),row('Tipo de CT-e','ide/tpCTe',mapping={'0':'Normal','1':'Complemento de valores','2':'Anulação','3':'Substituto'}),row('Tipo de serviço','ide/tpServ',mapping={'0':'Normal','1':'Subcontratação','2':'Redespacho','3':'Redespacho intermediário','4':'Vinculado a multimodal'})],
            [row('CFOP','ide/CFOP'),row('Natureza da operação','ide/natOp')],
            [('Origem',' / '.join(filter(None,[field(info,'ide/xMunIni'),field(info,'ide/UFIni')]))),('Destino',' / '.join(filter(None,[field(info,'ide/xMunFim'),field(info,'ide/UFFim')])))]
        ]},
        {'title':'Valores da prestação','rows':[[row('Valor total do serviço','vPrest/vTPrest','money'),row('Valor a receber declarado','vPrest/vRec','money')],components]},
        {'title':'Carga transportada','rows':[[row('Produto predominante','infCTeNorm/infCarga/proPred'),row('Outras características','infCTeNorm/infCarga/xOutCat'),row('Valor da carga','infCTeNorm/infCarga/vCarga','money')],quantities]},
        {'title':'Tributação ICMS','rows':[tax_fields]},
        {'title':'Informações do modal','rows':[[row('RNTRC','infCTeNorm/infModal/rodo/RNTRC')]]},
        {'title':'Observações','rows':[[row('Observações da prestação','compl/xObs')]]},
        {'title':'Autorização recebida','rows':[[('Protocolo',field(root,'protCTe/infProt/nProt')),('Data da autorização',date_text(field(root,'protCTe/infProt/dhRecbto'))),('Código / motivo',' / '.join(filter(None,[field(root,'protCTe/infProt/cStat'),field(root,'protCTe/infProt/xMotivo')])))] ]},
    ]
    return result


def extra_fields(info,path):
    node=info.find('/'.join('n:'+part for part in path.split('/')),NS)
    result=[]
    if node is None:return result
    def walk(current,prefix=''):
        for child in current:
            if not isinstance(child.tag,str):continue
            name=child.tag.rsplit('}',1)[-1]
            if len(child):walk(child,prefix+name+'/')
            elif child.text and child.text.strip():result.append((prefix+name,child.text.strip()))
    walk(node)
    return result


def references(info):
    result=[]
    for node in info.findall('n:infCTeNorm/n:infDoc/*',NS):
        kind=node.tag.rsplit('}',1)[-1]
        result.append({'kind':{'infNFe':'NF-e','infNF':'Nota fiscal','infOutros':'Outro documento'}.get(kind,kind),
            'key':field(node,'chave'),'number':field(node,'nDoc') or field(node,'nDocFisc'),'series':field(node,'serie')})
    for path,title in [('infCteComp/chCTe','CT-e complementado'),('infCTeNorm/infCteSub/chCte','CT-e substituído')]:
        for node in info.findall('/'.join('n:'+part for part in path.split('/')),NS):
            key=(node.text or '').strip()
            if key:result.append({'kind':title,'key':key,'number':'','series':''})
    return result
