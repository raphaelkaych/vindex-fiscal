import re
from decimal import Decimal,InvalidOperation
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from portal.models import FiscalDocument
from .fiscal_transport import xml_read,validate_xml,CTE,NFSE
from .sefaz import SefazError
from .payment_evidence import extract_payment_data


def classify(payload,service):
    node=xml_read(payload);name=node.tag.rsplit('}',1)[-1]
    if service=='nfse':return 'complete' if node.tag=='{'+NFSE+'}NFSe' else 'event' if node.tag=='{'+NFSE+'}evento' else 'unknown'
    return 'complete' if name=='cteProc' else 'event' if name=='procEventoCTe' else 'summary' if name.lower().startswith('res') else 'unknown'


def import_fiscal(connector,envelope):
    node=xml_read(envelope.xml_content.encode());service=connector.service
    validation_status='schema';details={}
    ns={'n':NFSE if service=='nfse' else CTE}
    get=lambda path:node.findtext(path,'',ns).strip()
    if envelope.kind!='complete':
        if envelope.kind=='event':
            filename=('evento_v'+node.get('versao','1.01')+'.xsd') if service=='nfse' else 'procEventoCTe_v4.00.xsd'
            validate_xml(service,filename,node)
            key=get('.//n:chNFSe') if service=='nfse' else get('.//n:chCTe')
            replacement=node.find('.//n:e105102',ns) if service=='nfse' else None
            cancellation=(node.find('.//n:e101101',ns) is not None or replacement is not None) if service=='nfse' else get('.//n:tpEvento')=='110111'
            if service=='cte':
                returned=node.find('n:retEventoCTe/n:infEvento',ns)
                if returned is None or returned.findtext('n:chCTe','',ns)!=key or returned.findtext('n:tpEvento','',ns)!=get('.//n:tpEvento') or returned.findtext('n:cStat','',ns) not in {'135','136'}:
                    raise SefazError('Evento CT-e sem retorno aceito correspondente. Original preservado; situação não alterada.')
            if cancellation:FiscalDocument.objects.filter(company=connector.company,service=service,environment=connector.environment,access_key=key).update(cancellation_reported=True)
            if replacement is not None:
                FiscalDocument.objects.filter(company=connector.company,service=service,environment=connector.environment,access_key=key).update(substitution_reported=True,substituted_by=replacement.findtext('n:chSubstituta','',ns))
        return None
    if service=='nfse':
        try:validate_xml('nfse','NFSe_v'+node.get('versao','1.01')+'.xsd',node)
        except SefazError:
            from .nfse_compat import partial_profile
            from portal.models import FiscalEnvelope
            import hashlib
            # Perfis parciais só para originais da distribuição já preservados,
            # com prova local de recebimento e hash inalterado.
            if not isinstance(envelope,FiscalEnvelope) or envelope.stream.service!='nfse' or envelope.stream.cnpj!=connector.company.cnpj or envelope.stream.environment!=connector.environment or hashlib.sha256(envelope.xml_content.encode()).hexdigest()!=envelope.content_hash:
                raise SefazError('Compatibilidade parcial exige original preservado da integração autorizada.') from None
            if not envelope.stream.consultations.filter(http_status=200,status='DOCUMENTOS_LOCALIZADOS',completed_at__isnull=False).exists():
                raise SefazError('Recebimento oficial não comprovado para a conferência parcial.')
            details=partial_profile(node);validation_status='partial'
        info=node.find('n:infNFSe',ns)
        if info is None:raise SefazError('NFS-e sem infNFSe.')
        key=info.get('Id','').removeprefix('NFS')
        owner=get('n:infNFSe/n:DPS/n:infDPS/n:toma/n:CNPJ')
        issuer=get('n:infNFSe/n:emit/n:CNPJ');name=get('n:infNFSe/n:emit/n:xNome')
        if owner!=connector.company.cnpj and issuer!=connector.company.cnpj:raise SefazError('NFS-e não identifica esta empresa como emitente ou tomadora. Original preservado.')
        if get('n:infNFSe/n:DPS/n:infDPS/n:tpAmb') not in {'',connector.environment}:raise SefazError('Ambiente declarado na NFS-e divergente.')
        issued=get('n:infNFSe/n:DPS/n:infDPS/n:dhEmi');number=get('n:infNFSe/n:nNFSe')
        amount=get('n:infNFSe/n:DPS/n:infDPS/n:valores/n:vServPrest/n:vServ');role='emitente_tomador' if owner==issuer==connector.company.cnpj else 'emitente' if issuer==connector.company.cnpj else 'tomador'
    else:
        validate_xml('cte','procCTe_v4.00.xsd',node)
        info=node.find('n:CTe/n:infCte',ns)
        if info is None or get('n:CTe/n:infCte/n:ide/n:mod')!='57':raise SefazError('Somente CT-e completo modelo 57 padrão é suportado; original preservado.')
        key=info.get('Id','').removeprefix('CTe')
        if get('n:protCTe/n:infProt/n:chCTe')!=key or get('n:protCTe/n:infProt/n:cStat') not in {'100','150'}:raise SefazError('Protocolo de CT-e ausente ou incompatível.')
        roles=[tag for tag in ['rem','dest','exped','receb','toma4','autXML'] if info.findtext('n:'+tag+'/n:CNPJ','',ns)==connector.company.cnpj]
        if not roles:raise SefazError('CT-e não declara interesse desta empresa nos papéis suportados.')
        role=','.join(roles);issuer=get('n:CTe/n:infCte/n:emit/n:CNPJ');name=get('n:CTe/n:infCte/n:emit/n:xNome')
        issued=get('n:CTe/n:infCte/n:ide/n:dhEmi');number=get('n:CTe/n:infCte/n:ide/n:nCT')
        amount=get('n:CTe/n:infCte/n:vPrest/n:vTPrest')
    try:
        total=Decimal(amount);date=parse_datetime(issued)
        if not total.is_finite() or total<0 or total>=Decimal('10000000000000000') or total!=total.quantize(Decimal('.01')) or date is None or not timezone.is_aware(date):raise ValueError
    except (ValueError,InvalidOperation):raise SefazError('Valor ou data do documento fiscal inválidos.') from None
    if not re.fullmatch(r'[0-9A-Z]{40,64}',key) or not number or not issuer or not name:raise SefazError('Identidade do documento fiscal incompleta.')
    doc,_=FiscalDocument.objects.get_or_create(company=connector.company,service=service,environment=connector.environment,access_key=key,
        defaults=dict(number=number,issuer_name=name,issuer_cnpj=issuer,role=role,issued_at=date,total=total,xml_content=envelope.xml_content,payment_data=extract_payment_data(envelope.xml_content),validation_status=validation_status,validation_details=details))
    if doc.xml_content!=envelope.xml_content:raise SefazError('Identificador já existente com XML diferente; originais preservados para revisão.')
    if doc.validation_status!=validation_status or doc.validation_details!=details:
        doc.validation_status=validation_status;doc.validation_details=details;doc.save(update_fields=['validation_status','validation_details'])
    return doc
