"""Contratos oficiais: CT-e SOAP 1.2 e ADN Contribuintes REST mTLS."""
import base64,gzip,io,json,http.client,re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from lxml import etree as XML
from django.utils.dateparse import parse_datetime
from .sefaz_transport import identity_context,official_post,SOAP_NS
from .sefaz import SefazError

CTE='http://www.portalfiscal.inf.br/cte'
NFSE='http://www.sped.fazenda.gov.br/nfse'
MAX_RESPONSE=12*1024*1024


def xml_read(payload):
    if len(payload)>2*1024*1024:raise SefazError('Documento excede o limite local de 2 MB.')
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():raise SefazError('DTD/entidades não são permitidas.')
    try:return XML.fromstring(payload,XML.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
    except XML.XMLSyntaxError:raise SefazError('XML fiscal inválido.') from None


@lru_cache(maxsize=40)
def schema(service,filename):
    if service not in {'nfse','nfse_legacy','cte'} or not re.fullmatch(r'[A-Za-z0-9_.-]+\.xsd',filename):raise SefazError('Identificação de schema inválida.')
    path=Path(__file__).parent/'schemas'/service/filename
    if not path.is_file():raise SefazError('Schema oficial ainda não suportado: '+filename[:80])
    document=XML.parse(str(path),XML.XMLParser(resolve_entities=False,no_network=True))
    if service=='nfse' and filename.startswith(('NFSe_','evento_')):
        # O pacote oficial 20260209 usa ^/$ (âncoras PCRE) no TSSerieDPS.
        # XSD 1.0 interpreta esses caracteres literalmente. Resolver localmente
        # só esse padrão, mantendo o arquivo oficial intacto e a regra 1–5 dígitos.
        class NfseResolver(XML.Resolver):
            def resolve(self,url,pubid,context):
                if Path(url).name=='tiposSimples_v1.01.xsd':
                    original=(path.parent/'tiposSimples_v1.01.xsd').read_bytes()
                    fixed=original.replace(b'^0{0,4}\\d{1,5}$',b'[0-9]{1,5}')
                    return self.resolve_string(fixed,context,base_url=str(path.parent/'tiposSimples_v1.01.xsd'))
        parser=XML.XMLParser(resolve_entities=False,no_network=True);parser.resolvers.add(NfseResolver())
        document=XML.parse(str(path),parser)
    return XML.XMLSchema(document)


def validate_xml(service,filename,node):
    if schema(service,filename).validate(node):return
    # Documentos nacionais 1.00 anteriores à revisão corrente mantêm o layout
    # histórico oficial. Não alterar versão ou conteúdo para fazê-los passar.
    if service=='nfse' and filename in {'NFSe_v1.00.xsd','evento_v1.00.xsd'} and schema('nfse_legacy',filename).validate(node):return
    raise SefazError('Documento não corresponde ao schema oficial '+filename[:80]+'. Original preservado para revisão.')


def unzip(value):
    try:
        compressed=base64.b64decode(value,validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as file:result=file.read(2*1024*1024+1)
        xml_read(result);return result
    except SefazError:raise
    except Exception:raise SefazError('Documento compactado inválido.') from None


def official_get(company,host,path):
    with identity_context(company) as context:
        connection=http.client.HTTPSConnection(host,context=context,timeout=45)
        try:
            connection.request('GET',path,headers={'Accept':'application/json','User-Agent':'VindexFiscal/1.0'})
            response=connection.getresponse();body=response.read(MAX_RESPONSE+1)
            if len(body)>MAX_RESPONSE:raise SefazError('Resposta excede 12 MB.')
            return response.status,body
        except SefazError:raise
        except Exception as error:raise SefazError('Falha de rede/TLS no ADN ('+type(error).__name__+'). Nenhum sucesso foi presumido.') from None
        finally:connection.close()


@dataclass
class Batch:
    status:str
    reason:str
    cursor:str
    maximum:str
    accepted:bool
    end:bool
    documents:list
    official_at:object=None


class CteTransport:
    def fetch(self,connector,cursor):
        if not connector.uf_author:raise SefazError('Informe a UF do autor para CT-e.')
        ns=CTE+'/wsdl/CTeDistribuicaoDFe'
        root=XML.Element('{'+SOAP_NS+'}Envelope',nsmap={'s':SOAP_NS});body=XML.SubElement(root,'{'+SOAP_NS+'}Body')
        method=XML.SubElement(body,'{'+ns+'}cteDistDFeInteresse',nsmap={None:ns})
        msg=XML.SubElement(method,'{'+ns+'}cteDadosMsg')
        request=XML.SubElement(msg,'{'+CTE+'}distDFeInt',versao='1.00',nsmap={None:CTE})
        for name,value in [('tpAmb',connector.environment),('cUFAutor',connector.uf_author),('CNPJ',connector.company.cnpj)]:XML.SubElement(request,'{'+CTE+'}'+name).text=value
        query=XML.SubElement(request,'{'+CTE+'}distNSU');XML.SubElement(query,'{'+CTE+'}ultNSU').text=cursor.zfill(15)
        validate_xml('cte','distDFeInt_v1.00.xsd',request)
        host='www1.cte.fazenda.gov.br' if connector.environment=='1' else 'hom1.cte.fazenda.gov.br'
        return 200,official_post(connector.company,host,'/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx',ns+'/cteDistDFeInteresse',XML.tostring(root,encoding='utf-8',xml_declaration=True))

    def parse(self,payload,environment,cursor):
        # Envelope pode exceder o limite de um documento individual.
        if len(payload)>MAX_RESPONSE or b'<!DOCTYPE' in payload.upper():raise SefazError('Envelope CT-e inválido.')
        root=XML.fromstring(payload,XML.XMLParser(resolve_entities=False,no_network=True));ns={'c':CTE}
        node=root if root.tag=='{'+CTE+'}retDistDFeInt' else root.find('.//c:retDistDFeInt',ns)
        if node is None:raise SefazError('Retorno CT-e não contém retDistDFeInt.')
        validate_xml('cte','retDistDFeInt_v1.00.xsd',node)
        get=lambda name:node.findtext('c:'+name,'',ns)
        if get('tpAmb')!=environment:raise SefazError('Ambiente CT-e divergente.')
        status=get('cStat');accepted=status in {'137','138'};last=get('ultNSU') or cursor;maximum=get('maxNSU')
        documents=[]
        for d in node.findall('c:loteDistDFeInt/c:docZip',ns):
            documents.append((d.get('NSU'),d.get('schema'),unzip(''.join((d.text or '').split()))))
        if len(documents)>50 or sum(len(x[2]) for x in documents)>20*1024*1024:raise SefazError('Lote CT-e excede limites locais.')
        if accepted and (int(last)<int(cursor) or maximum and int(last)>int(maximum)):raise SefazError('NSU CT-e inconsistente; progresso preservado.')
        if status=='138' and not documents:raise SefazError('CT-e informa documentos sem conteúdo.')
        return Batch(status,get('xMotivo'),last,maximum,accepted,status!='138' or last==maximum,documents,parse_datetime(get('dhResp')))


class NfseTransport:
    def fetch(self,connector,cursor):
        host='adn.nfse.gov.br' if connector.environment=='1' else 'adn.producaorestrita.nfse.gov.br'
        return official_get(connector.company,host,f'/contribuintes/DFe/{int(cursor)}?cnpjConsulta={connector.company.cnpj}&lote=true')

    def parse(self,payload,environment,cursor):
        try:data=json.loads(payload)
        except (ValueError,UnicodeError):raise SefazError('ADN não retornou JSON válido.') from None
        expected='PRODUCAO' if environment=='1' else 'HOMOLOGACAO'
        if data.get('TipoAmbiente')!=expected:raise SefazError('Ambiente ADN ausente ou divergente.')
        status=data.get('StatusProcessamento','');accepted=status in {'DOCUMENTOS_LOCALIZADOS','NENHUM_DOCUMENTO_LOCALIZADO'}
        reasons=data.get('Erros') or data.get('Alertas') or []
        reason='; '.join(str(x.get('Codigo',''))+' '+str(x.get('Descricao','')) for x in reasons)[:500] or status
        items=data.get('LoteDFe') or []
        if not isinstance(items,list) or len(items)>1000:raise SefazError('Lote ADN inválido ou excessivo.')
        documents=[];last=int(cursor)
        for item in items:
            nsu=item.get('NSU')
            if type(nsu) is not int or nsu<0 or nsu>9223372036854775807:raise SefazError('NSU ADN inválido.')
            documents.append((str(nsu),str(item.get('TipoDocumento','')),unzip(item.get('ArquivoXml') or '')));last=max(last,nsu)
        if sum(len(x[2]) for x in documents)>20*1024*1024:raise SefazError('Lote ADN descompactado excessivo.')
        if status=='DOCUMENTOS_LOCALIZADOS' and not items:raise SefazError('ADN informa documentos sem conteúdo.')
        return Batch(status,reason,str(last),'',accepted,not items or last==int(cursor),documents,parse_datetime(data.get('DataHoraProcessamento','')))
