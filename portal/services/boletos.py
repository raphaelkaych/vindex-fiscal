"""Análise local de cobranças; validação matemática não autentica na rede bancária.

Layouts e decisões conservadoras documentados em docs/BOLETOS.md.
O pagador e o escopo são conferidos em todos os pontos de escrita.
"""
import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from portal.models import Company, Installment, AuditEntry
from portal.boleto_models import Boleto, BoletoEvent
from portal.validators import validate_cnpj, normalize_cnpj

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_PAGE_CONTENT_BYTES = 1024 * 1024
EDITABLE_FIELDS = ('digitable_line','barcode','amount','due_on','beneficiary_name',
    'beneficiary_document','payer_name','payer_document','reference')


class BoletoImportError(ValueError): pass
class BoletoAssociationError(ValueError): pass


def mod10(value):
    total = sum(sum(divmod(int(c) * (2 if i % 2 == 0 else 1),10)) for i,c in enumerate(reversed(value)))
    return (10 - total % 10) % 10


def mod11(value, collection=False):
    remainder = sum(int(c) * (i % 8 + 2) for i,c in enumerate(reversed(value))) % 11
    if collection:
        return 0 if remainder in (0,1) else 11 - remainder
    result = 11 - remainder
    return 1 if result in (0,10,11) else result


def _digits(value):
    value = str(value or '').strip()
    if not re.fullmatch(r'[0-9.\s-]+', value):
        raise BoletoImportError('A linha/código deve conter somente números e sua formatação.')
    return re.sub(r'[.\s-]','',value)


def validate_code(value):
    """Normaliza 44/47/48 posições, valida todos DVs e retorna dados verificáveis.

    Datas candidatas nunca são convertidas em um vencimento definitivo.
    """
    number = _digits(value)
    line = ''
    if len(number) == 47:
        if number[0] == '8':
            raise BoletoImportError('Arrecadação exige linha de 48 posições ou código de barras de 44.')
        for part, dv in ((number[:9],number[9]),(number[10:20],number[20]),(number[21:31],number[31])):
            if mod10(part) != int(dv):
                raise BoletoImportError('Os dígitos verificadores da linha digitável não conferem.')
        line = number
        number = number[:4] + number[32] + number[33:] + number[4:9] + number[10:20] + number[21:31]
    elif len(number) == 48:
        if number[0] != '8' or number[2] not in '6789':
            raise BoletoImportError('A linha de arrecadação não segue o formato reconhecido.')
        calculate = mod10 if number[2] in '67' else lambda p: mod11(p,collection=True)
        for offset in range(0,48,12):
            if calculate(number[offset:offset+11]) != int(number[offset+11]):
                raise BoletoImportError('Os dígitos verificadores dos blocos de arrecadação não conferem.')
        line = number
        number = ''.join(number[i:i+11] for i in range(0,48,12))
    elif len(number) != 44:
        raise BoletoImportError('Informe 47 dígitos de cobrança, 48 de arrecadação ou 44 do código de barras.')
    if len(set(number)) == 1:
        raise BoletoImportError('Código de barras inválido.')
    result = {'barcode':number,'due_candidates':[],'amount':None,'amount_candidate':None,'bank_code':'','warnings':[]}
    if number[0] == '8':
        if number[1] not in '12345679' or number[2] not in '6789':
            raise BoletoImportError('Segmento ou identificador de valor da arrecadação não suportado.')
        calculate = mod10 if number[2] in '67' else lambda p: mod11(p,collection=True)
        if calculate(number[:3]+number[4:]) != int(number[3]):
            raise BoletoImportError('O dígito geral do código de arrecadação não confere.')
        result['kind'] = 'collection'
        if not line:
            line = ''.join(number[i:i+11]+str(calculate(number[i:i+11])) for i in range(0,44,11))
        if number[2] in '68' and int(number[4:15]):
            result['amount'] = Decimal(number[4:15])/100
        else:
            result['warnings'].append('O código não declara valor efetivo em reais; confira o documento.')
        result['warnings'].append('Vencimento de arrecadação depende do documento/layout do emissor; não foi inferido do campo livre.')
    else:
        if number[3] != '9' or number[:3] == '000':
            raise BoletoImportError('Somente cobrança bancária em reais (moeda 9) é suportada.')
        if mod11(number[:4]+number[5:]) != int(number[4]):
            raise BoletoImportError('O dígito geral do código de barras não confere.')
        result.update(kind='charge', bank_code=number[:3])
        if not line:
            fields = (number[:4]+number[19:24],number[24:34],number[34:44])
            line = ''.join(p+str(mod10(p)) for p in fields)+number[4]+number[5:19]
        factor = int(number[5:9])
        # Valores acima de 10 posições podem invadir o fator (manual BB, Anexo IV).
        # 0000..0999 também não fornecem uma data universal segura.
        if factor >= 1000:
            result['due_candidates'] = [(date(1997,10,7)+timedelta(days=factor)).isoformat(),
                (date(2025,2,22)+timedelta(days=factor-1000)).isoformat()]
            result['warnings'].append('O fator de vencimento tem ciclos anterior e posterior a 22/02/2025; informe a data do documento para confirmar.')
            if int(number[9:19]): result['amount_candidate'] = Decimal(number[9:19])/100
        else:
            result['warnings'].append('Fator ausente/especial: valor e vencimento exigem informação explícita; valores altos podem ocupar o fator.')
    result['digitable_line'] = line
    return result


def _document(value):
    value = normalize_cnpj(value or '')
    if not value: return ''
    if len(value) == 14:
        try: return validate_cnpj(value)
        except ValidationError as exc: raise BoletoImportError('CNPJ informado no boleto inválido.') from exc
    if not re.fullmatch(r'[0-9]{11}',value) or len(set(value)) == 1:
        raise BoletoImportError('Informe CPF ou CNPJ válido, ou deixe o campo vazio para revisão.')
    for length in (9,10):
        d = (sum(int(c)*w for c,w in zip(value[:length],range(length+1,1,-1)))*10)%11
        if int(value[length]) != (0 if d == 10 else d):
            raise BoletoImportError('CPF informado no boleto inválido.')
    return value


def _amount(value):
    if value in (None,''): return None
    try:
        if isinstance(value,float): raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result <= 0 or result >= Decimal('10000000000000000') or result != result.quantize(Decimal('.01')):
            raise InvalidOperation
        return result
    except (ValueError,TypeError,InvalidOperation) as exc:
        raise BoletoImportError('Informe valor positivo com até duas casas decimais, sem arredondamento.') from exc


def _date(value):
    if value in (None,''): return None
    if isinstance(value,datetime): raise BoletoImportError('Informe apenas uma data de vencimento, sem horário.')
    if isinstance(value,date): return value
    try: return date.fromisoformat(str(value))
    except (ValueError,TypeError) as exc: raise BoletoImportError('Vencimento deve ser uma data válida no formato AAAA-MM-DD.') from exc


def scoped_company(workspace, value, allowed_companies=None):
    try: company_id = value.pk if isinstance(value,Company) else int(value)
    except (ValueError,TypeError,AttributeError) as exc: raise BoletoImportError('Escolha uma empresa autorizada.') from exc
    companies = Company.objects.filter(workspace=workspace)
    if allowed_companies is not None:
        companies = companies.filter(pk__in=[getattr(item,'pk',item) for item in allowed_companies])
    try: return companies.get(pk=company_id)
    except Company.DoesNotExist as exc: raise BoletoImportError('Empresa inexistente ou fora do acesso autorizado.') from exc


def _event(boleto, action, source, actor, details=None):
    # Identificação interna, nunca repr(request), cabeçalhos ou segredo de credencial.
    actor_id = getattr(actor,'pk',None)
    BoletoEvent.objects.create(boleto=boleto,action=action,source=str(source)[:30],
        actor_label=f'{actor.__class__.__name__}:{actor_id}' if actor_id else '',details=details or {})
    AuditEntry.objects.create(workspace=boleto.company.workspace,
        description=f'Boleto {boleto.pk}: {action} · empresa {boleto.company_id} · origem {source}'[:250])


def extract_pdf(payload):
    """PDF digital limitado; scans ficam privados e pendentes, sem OCR simulado."""
    if not isinstance(payload,(bytes,bytearray)) or not payload or len(payload) > MAX_PDF_BYTES:
        raise BoletoImportError('Envie um PDF de até 5 MB.')
    if not payload.startswith(b'%PDF-'):
        raise BoletoImportError('O arquivo enviado não é um PDF reconhecido.')
    try:
        from pypdf import PdfReader, apply_configuration
        # Limites por contexto, inclusive ANTES da descompressão; não altera outras requisições.
        with apply_configuration(maximum_declared_stream_length=MAX_PDF_BYTES,
            zlib_maximum_output_length=MAX_PAGE_CONTENT_BYTES,
            lzw_maximum_output_length=MAX_PAGE_CONTENT_BYTES,
            run_length_maximum_output_length=MAX_PAGE_CONTENT_BYTES,
            brotli_maximum_output_length=MAX_PAGE_CONTENT_BYTES,
            array_based_stream_maximum_output_length=MAX_PAGE_CONTENT_BYTES,
            stream_decoding_work_maximum_length=4*MAX_PAGE_CONTENT_BYTES,
            stream_parsing_work_maximum_count=100000, array_maximum_element_count=20000,
            dictionary_maximum_element_count=10000, page_tree_maximum_entries=1000,
            page_tree_maximum_depth=20, xform_maximum_invocations_per_extraction=100,
            jbig2dec_binary=None):
            reader = PdfReader(BytesIO(payload), strict=True)
            if reader.is_encrypted: raise BoletoImportError('PDF protegido por senha não pode ser analisado; envie uma cópia sem senha.')
            if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
                raise BoletoImportError('O PDF deve conter de 1 a 10 páginas.')
            texts=[]
            for page in reader.pages:
                stream = page.get_contents()
                if stream and len(stream.get_data()) > MAX_PAGE_CONTENT_BYTES:
                    raise BoletoImportError('O PDF excede o limite de conteúdo por página; envie um arquivo mais simples.')
                texts.append((page.extract_text() or '')[:100000])
            text='\n'.join(texts)
    except BoletoImportError: raise
    except ImportError as exc: raise BoletoImportError('Leitor PDF indisponível. Execute py iniciar.py --preparar.') from exc
    except Exception as exc:
        # Não inclui mensagem do parser: pode conter texto privado do documento.
        raise BoletoImportError('Não foi possível ler este PDF. Envie uma cópia válida ou informe a linha digitável.') from exc
    data = {'extraction_method':'pdf_text' if text.strip() else 'none'}
    warnings = ['Dados extraídos de PDF exigem revisão visual; texto do arquivo não comprova autenticidade nem pagamento.']
    candidates = set()
    # Campos com separadores conhecidos; não agrega dígitos de partes desconexas.
    patterns = (r'(?<![0-9])[0-9]{5}\.?[0-9]{5}\s+[0-9]{5}\.?[0-9]{6}\s+[0-9]{5}\.?[0-9]{6}\s+[0-9]\s+[0-9]{14}(?![0-9])',
        r'(?<![0-9])(?:[0-9]{11}[- ]?[0-9]\s+){3}[0-9]{11}[- ]?[0-9](?![0-9])',
        r'(?<![0-9])[0-9]{44,48}(?![0-9])')
    for pattern in patterns:
        for match in re.finditer(pattern,text):
            try: candidates.add(validate_code(match.group())['barcode'])
            except BoletoImportError: continue
    if len(candidates) == 1: data['barcode'] = candidates.pop()
    elif len(candidates) > 1:
        warnings.append('O PDF contém múltiplos códigos válidos; informe explicitamente qual cobrança importar.')
    else: warnings.append('Linha digitável não identificada. Informe os dados para revisão; OCR não está disponível nesta instalação.')
    # Somente rótulos explícitos na mesma linha. Layouts de colunas não são inferidos.
    labels = {
        'beneficiary_name':r'(?im)^\s*(?:Nome do benefici[aá]rio|Benefici[aá]rio)\s*:\s*([^\n\r]{1,200})$',
        'payer_name':r'(?im)^\s*(?:Nome do pagador|Pagador)\s*:\s*([^\n\r]{1,200})$',
        'beneficiary_document':r'(?im)^\s*(?:CPF/CNPJ|CNPJ|CPF) do benefici[aá]rio\s*:\s*([A-Z0-9./ -]{11,20})$',
        'payer_document':r'(?im)^\s*(?:CPF/CNPJ|CNPJ|CPF) do pagador\s*:\s*([A-Z0-9./ -]{11,20})$',
        'due_on':r'(?im)^\s*(?:Data de vencimento|Vencimento)\s*:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})\s*$',
        'amount':r'(?im)^\s*(?:Valor do documento|Valor nominal)\s*:\s*(?:R\$\s*)?([0-9.]+,[0-9]{2})\s*$',
        'reference':r'(?im)^\s*(?:N[uú]mero do documento|Identifica[cç][aã]o)\s*:\s*([^\n\r]{1,100})$',
    }
    for field,pattern in labels.items():
        values = {m.strip() for m in re.findall(pattern,text)}
        if len(values) != 1: continue
        value = values.pop()
        try:
            if field == 'due_on': value = datetime.strptime(value,'%d/%m/%Y').date()
            elif field == 'amount': value = _amount(value.replace('.','').replace(',','.'))
            elif field.endswith('_document'): value = _document(value)
        except (ValueError,BoletoImportError):
            warnings.append('Há um campo rotulado inválido no PDF; revise o documento.')
            continue
        data[field] = value
    return data,warnings


def _prepare(company,data,pdf_warnings=None):
    result={}
    warnings=list(pdf_warnings or [])
    for name in ('beneficiary_name','payer_name','reference'):
        value = str(data.get(name) or '').strip()
        limit=100 if name == 'reference' else 200
        if len(value) > limit: raise BoletoImportError(f'Campo {name} excede o tamanho permitido.')
        result[name]=value
    for name in ('beneficiary_document','payer_document'): result[name] = _document(data.get(name))
    if result['payer_document'] and result['payer_document'] != company.cnpj:
        raise BoletoImportError('O CPF/CNPJ do pagador difere do CNPJ da empresa selecionada. Escolha o CNPJ correto.')
    code=data.get('digitable_line') or data.get('barcode')
    code_data=validate_code(code) if code else {}
    if data.get('digitable_line') and data.get('barcode'):
        if code_data['barcode'] != validate_code(data['barcode'])['barcode']:
            raise BoletoImportError('A linha digitável e o código de barras representam cobranças diferentes.')
    result.update({key:code_data.get(key,default) for key,default in (
        ('barcode',None),('digitable_line',''),('kind','unknown'),('bank_code',''),('due_candidates',[]))})
    result['amount'] = _amount(data.get('amount'))
    result['due_on'] = _date(data.get('due_on'))
    if code_data.get('amount'):
        if result['amount'] is not None and result['amount'] != code_data['amount']:
            warnings.append('Valor informado diverge do valor codificado. Os dados declarados foram preservados para análise.')
        elif result['amount'] is None: result['amount'] = code_data['amount']
    candidate=code_data.get('amount_candidate')
    if candidate:
        if result['amount'] is None:
            candidate_label=f'{candidate:.2f}'.replace('.',',')
            warnings.append(f'O trecho usual do código sugere R$ {candidate_label}, apenas um candidato. Cobranças acima de R$ 99.999.999,99 podem ocupar também o fator. Informe o valor explícito do documento; nenhum valor foi preenchido automaticamente.')
        elif result['amount'] != candidate:
            warnings.append('Valor declarado difere do trecho usual de dez posições do código; valores altos podem ocupar também o fator. Confira o documento e o emissor.')
    candidates=result['due_candidates']
    if result['due_on'] and candidates:
        if result['due_on'].isoformat() not in candidates:
            warnings.append('Vencimento informado diverge das datas candidatas do fator. Revise documento e emissor.')
        else:
            code_data['warnings']=[w for w in code_data['warnings'] if not w.startswith('O fator de vencimento')]
    warnings.extend(code_data.get('warnings',[]))
    for field,label in (('payer_document','CPF/CNPJ do pagador'),('beneficiary_name','Beneficiário'),
        ('beneficiary_document','CPF/CNPJ do beneficiário'),('amount','Valor'),('due_on','Vencimento')):
        if not result[field]: warnings.append(f'{label} não confirmado; complete na revisão.')
    if not code: warnings.append('Código/linha não identificados: validação matemática pendente.')
    result['validation_state']='validated' if code else 'pending'
    result['review_notes']='\n'.join(dict.fromkeys(warnings))
    return result


@transaction.atomic
def import_boleto(workspace,data,payload=None,allowed_companies=None,actor=None):
    data=dict(data)
    company=scoped_company(workspace,data.get('company') or data.get('company_id'),allowed_companies)
    Company.objects.select_for_update().get(pk=company.pk)
    supplied={key:data[key] for key in EDITABLE_FIELDS if data.get(key) not in (None,'')}
    warnings=[]
    pdf_hash=None
    extraction_method='manual'
    if payload is not None:
        extracted,warnings=extract_pdf(payload)
        pdf_hash=hashlib.sha256(payload).hexdigest()
        extraction_method=extracted.pop('extraction_method')
        if extracted.get('payer_document') and extracted['payer_document'] != company.cnpj:
            raise BoletoImportError('O CNPJ pagador identificado no PDF difere da empresa selecionada. Confira o arquivo e escolha o CNPJ correto.')
        supplied_code=supplied.get('digitable_line') or supplied.get('barcode')
        if supplied_code and extracted.get('barcode') and validate_code(supplied_code)['barcode'] != extracted['barcode']:
            raise BoletoImportError('O código informado difere da única cobrança reconhecida no PDF. Confira o arquivo antes de importar.')
        for key,value in extracted.items():
            if key not in supplied: data[key]=value
            elif str(supplied[key]) != str(value):
                warnings.append(f'Campo {key} informado manualmente substituiu texto extraído; confira a divergência.')
    elif not (data.get('digitable_line') or data.get('barcode')):
        raise BoletoImportError('Informe linha digitável/código de barras ou envie um PDF para revisão.')
    values=_prepare(company,data,warnings)
    source=data.get('source') or ('pdf' if payload is not None else 'manual')
    if source not in ('manual','pdf','api'): raise BoletoImportError('Origem de importação inválida.')
    identity=Q()
    if values['barcode']: identity |= Q(barcode=values['barcode'])
    if pdf_hash: identity |= Q(pdf_sha256=pdf_hash)
    existing=list(Boleto.objects.select_for_update().filter(identity,company=company)) if identity else []
    if len(existing) > 1:
        raise BoletoImportError('Código e arquivo apontam para registros diferentes; revise os documentos existentes.')
    if existing:
        item=existing[0]
        if item.barcode and values['barcode'] and item.barcode != values['barcode']:
            raise BoletoImportError('Este PDF já foi importado com outro código. Corrija o registro na revisão.')
        for key in supplied:
            if key in ('barcode','digitable_line'): continue
            if getattr(item,key) != values[key]:
                raise BoletoImportError('Boleto já cadastrado com dados diferentes. Abra a revisão para corrigir e preservar a auditoria.')
        if payload is not None and not item.has_pdf:
            item.private_pdf=bytes(payload);item.pdf_sha256=pdf_hash
            item.save(update_fields=['private_pdf','pdf_sha256','updated_at'])
            _event(item,'arquivo_anexado',source,actor,{'sha256':pdf_hash,'extraction_warnings':warnings})
        return item,False
    try:
        with transaction.atomic():
            item=Boleto.objects.create(company=company,private_pdf=bytes(payload) if payload is not None else None,
                pdf_sha256=pdf_hash,source=source,extraction_method=extraction_method,**values)
    except IntegrityError as exc:
        existing=Boleto.objects.filter(identity,company=company).first()
        if existing: return existing,False
        raise BoletoImportError('Importação concorrente em conflito. Recarregue a lista e confira o boleto.') from exc
    _event(item,'importado',source,actor,{'extraction_method':extraction_method,'has_pdf':payload is not None,
        'review_notes':item.review_notes,'extraction_warnings':warnings})
    return item,True


def _scoped_boleto(workspace,boleto,allowed_companies=None):
    pk=getattr(boleto,'pk',boleto)
    try: item=Boleto.objects.select_for_update().select_related('company','installment__invoice').get(pk=pk,company__workspace=workspace)
    except (Boleto.DoesNotExist,ValueError,TypeError) as exc: raise BoletoImportError('Boleto inexistente ou fora do acesso autorizado.') from exc
    scoped_company(workspace,item.company,allowed_companies)
    return item


def association_warnings(boleto,installment):
    result=[]
    if not boleto.payer_document: result.append('CPF/CNPJ do pagador não confirmado')
    if not boleto.amount or boleto.amount != installment.amount: result.append('valor diferente ou não confirmado')
    if not boleto.due_on or not installment.due_on or boleto.due_on != installment.due_on:
        result.append('vencimento diferente ou não confirmado')
    if not boleto.beneficiary_document or boleto.beneficiary_document != installment.invoice.issuer_cnpj:
        result.append('beneficiário diferente do fornecedor ou não confirmado; pode existir cessão/intermediário')
    return result


@transaction.atomic
def associate_boleto(workspace,boleto,installment,actor=None,source='manual',allowed_companies=None,review_reason=''):
    try:
        item=_scoped_boleto(workspace,boleto,allowed_companies)
        installment_id=getattr(installment,'pk',installment)
        part=Installment.objects.select_for_update().select_related('invoice__company').get(
            pk=installment_id,invoice__company__workspace=workspace)
        scoped_company(workspace,part.invoice.company,allowed_companies)
    except (BoletoImportError,Installment.DoesNotExist,ValueError,TypeError) as exc:
        raise BoletoAssociationError('Boleto ou parcela inexistente ou fora do acesso autorizado.') from exc
    if part.invoice.company_id != item.company_id:
        raise BoletoAssociationError('Associe somente boleto e parcela da mesma empresa/CNPJ.')
    if item.installment_id == part.pk: return item
    if item.installment_id:
        raise BoletoAssociationError('O boleto já está associado. Desfaça o vínculo antes de selecionar outra parcela.')
    if Boleto.objects.filter(installment=part).exclude(pk=item.pk).exists():
        raise BoletoAssociationError('A parcela já possui boleto. Não foi criada uma segunda obrigação.')
    warnings=association_warnings(item,part)
    review_reason=str(review_reason or '').strip()
    if len(review_reason)>1000: raise BoletoAssociationError('A justificativa deve ter no máximo 1000 caracteres.')
    if warnings and len(review_reason)<10:
        raise BoletoAssociationError('Associação exige revisão: '+ '; '.join(warnings)+'. Informe justificativa com pelo menos 10 caracteres.')
    item.installment=part
    if warnings:
        item.review_notes='\n'.join(filter(None,[item.review_notes,'Associação com divergências revisadas: '+'; '.join(warnings)]))
    try:
        with transaction.atomic(): item.save(update_fields=['installment','review_notes','updated_at'])
    except IntegrityError as exc: raise BoletoAssociationError('A parcela já possui boleto associado. Recarregue os dados.') from exc
    _event(item,'associado',source,actor,{'installment_id':part.pk,'invoice_id':part.invoice_id,
        'installment_number':part.number,'invoice_number':part.invoice.number,
        'warnings':warnings,'review_reason':review_reason})
    return item


@transaction.atomic
def disassociate_boleto(workspace,boleto,actor=None,source='manual',allowed_companies=None):
    item=_scoped_boleto(workspace,boleto,allowed_companies)
    if item.installment_id:
        old=item.installment_id
        number=item.installment.number
        invoice_number=item.installment.invoice.number
        item.installment=None;item.save(update_fields=['installment','updated_at'])
        _event(item,'desassociado',source,actor,{'installment_id':old,'installment_number':number,'invoice_number':invoice_number})
    return item


@transaction.atomic
def update_boleto(workspace,boleto,data,actor=None,source='manual',allowed_companies=None):
    item=_scoped_boleto(workspace,boleto,allowed_companies)
    previous_review_notes=item.review_notes
    merged={key:getattr(item,key) for key in EDITABLE_FIELDS}
    merged.update({key:value for key,value in data.items() if key in EDITABLE_FIELDS})
    # Permite corrigir somente uma representação sem manter a antiga contraditória.
    if 'digitable_line' in data and 'barcode' not in data: merged['barcode']=None
    if 'barcode' in data and 'digitable_line' not in data: merged['digitable_line']=''
    if not item.has_pdf and not (merged.get('digitable_line') or merged.get('barcode')):
        raise BoletoImportError('Mantenha o código/linha de um boleto sem PDF para preservar sua identificação.')
    warnings=[]
    if item.has_pdf:
        # Incertezas sobre o arquivo original continuam verdadeiras mesmo ao editar um nome.
        # Preservadas em eventos, sem nova leitura do documento ou necessidade de migração.
        for details in item.events.filter(action__in=['importado','arquivo_anexado']).values_list('details',flat=True):
            warnings.extend(details.get('extraction_warnings',[]))
        warnings.append('Documento PDF preservado; revisão manual registrada.')
    values=_prepare(item.company,merged,warnings)
    changes={key:{'before':str(getattr(item,key)),'after':str(value)} for key,value in values.items()
        if key not in ('review_notes','due_candidates') and getattr(item,key) != value}
    if item.installment_id:
        for key,value in values.items(): setattr(item,key,value)
        if association_warnings(item,item.installment):
            raise BoletoImportError('Desfaça o vínculo antes de alterar dados que divergem da parcela; depois associe com justificativa.')
    for key,value in values.items(): setattr(item,key,value)
    try:
        with transaction.atomic(): item.save(update_fields=list(values)+['updated_at'])
    except IntegrityError as exc: raise BoletoImportError('Este código já pertence a outro boleto da empresa.') from exc
    # A revisão pode resolver avisos, mas o histórico conserva o antes/depois.
    _event(item,'revisado',source,actor,{'changes':changes,'review_notes_before':previous_review_notes,
        'review_notes_after':item.review_notes})
    return item


class DDAConnectorUnavailable(RuntimeError): pass


class UnconfiguredDDAConnector:
    """Contrato para futuro provedor contratado; não simula solicitações ou resultados."""
    status='configuration_pending'
    def fetch(self,company):
        raise DDAConnectorUnavailable('DDA não configurado. Exige instituição/provedor, adesão do pagador, contrato e credenciais autorizadas. Use importação local.')
