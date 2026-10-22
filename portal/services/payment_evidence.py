"""Extrai evidências do documento; nunca consulta bancos nem cria pagamentos."""
import re
from .fiscal_transport import xml_read
from .sefaz import SefazError


STRUCTURED={
 'nFat':'Número da fatura','vOrig':'Fatura: valor original','vDesc':'Desconto declarado','vLiq':'Valor líquido declarado',
 'nDup':'Identificador da parcela','dVenc':'Vencimento da parcela','vDup':'Valor da parcela',
 'tPag':'Código do meio de pagamento','xPag':'Descrição do pagamento','indPag':'Condição de pagamento',
 'vPag':'Pagamento declarado (não comprova liquidação)','dPag':'Data de pagamento declarada (não comprova liquidação)',
 'vTroco':'Troco declarado','vNF':'Total bruto NF-e','vTPrest':'Total da prestação','vRec':'Valor a receber declarado',
 'vServ':'Valor dos serviços','vTotalRet':'Total de retenções','vRetPIS':'Retenção PIS','vRetCOFINS':'Retenção COFINS',
 'vRetCSLL':'Retenção CSLL','vIRRF':'IRRF','vRetINSS':'Retenção INSS','vISSQN':'ISSQN declarado',
 'vRetCP':'Retenção previdenciária','vRetIRRF':'IRRF retido',
}


def extract_payment_data(payload):
    try:root=xml_read(payload if isinstance(payload,bytes) else payload.encode())
    except SefazError:return []
    result=[]
    def add(label,value,path,method='structured',excerpt=''):
        result.append(dict(label=label,value=value[:2000],source=path,method=method,
                           review='Conferir com o documento' if method=='structured' else 'Revisão necessária',excerpt=excerpt[:2000]))
    def walk(node,path=''):
        name=node.tag.rsplit('}',1)[-1] if isinstance(node.tag,str) else ''
        path=path+'/'+name;value=(node.text or '').strip()
        if value and name in STRUCTURED:add(STRUCTURED[name],value,path)
        if value and name in {'infCpl','infAdFisco','xObs','xInfComp','xDescServ','xOutInf'}:
            # Somente campos rotulados. Texto de cartão/adquirente não é conta do fornecedor.
            patterns=[('Chave Pix declarada',r'\bchave\s*pix\s*[:=]\s*([^\s;,]+)'),
                      ('Banco declarado',r'\bbanco\s*[:=]\s*([^;\n]{1,80})'),
                      ('Agência declarada',r'\bag[eê]ncia\s*[:=]\s*([0-9Xx.-]{1,15})'),
                      ('Conta declarada',r'\bconta(?:\s+corrente)?\s*[:=]\s*([0-9Xx.-]{1,30})'),
                      ('Beneficiário declarado',r'\bbenefici[aá]rio\s*[:=]\s*([^;\n]{1,120})'),
                      ('CPF/CNPJ do beneficiário declarado',r'\b(?:cpf|cnpj)\s+do\s+benefici[aá]rio\s*[:=]\s*([0-9./-]{11,18})'),
                      ('Instrução de pagamento',r'\binstru[cç][aã]o\s+de\s+pagamento\s*[:=]\s*([^;\n]{1,500})'),
                      ('Pix copia e cola declarado',r'\bpix\s+copia\s+e\s+cola\s*[:=]\s*(000201[0-9A-Za-z@./:+ -]{20,1000})')]
            for label,pattern in patterns:
                for found in re.finditer(pattern,value,re.I):
                    candidate=found[1].rstrip('.')
                    if label=='Chave Pix declarada' and not (re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',candidate) or re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',candidate) or re.fullmatch(r'\+?[0-9]{10,14}',candidate)):
                        continue
                    add(label,candidate,path,'labeled_text',value)
            for found in re.finditer(r'\b(?:linha\s+digit[aá]vel|c[oó]digo\s+de\s+barras)\s*[:=]\s*([0-9 .-]{44,80})',value,re.I):
                candidate=re.sub(r'\D','',found[1])
                try:
                    from .boletos import validate_code
                    validate_code(candidate)
                except ValueError:continue
                add('Código de cobrança declarado (dígitos conferidos; titularidade não validada)',candidate,path,'labeled_text',value)
        for child in node:walk(child,path)
    walk(root)
    return result
