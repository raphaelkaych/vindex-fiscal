"""Inspeção local e cifra. Não verifica cadeia ICP-Brasil nem revogação."""
import re
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from portal.models import DigitalCertificate,AuditEntry
from portal.validators import validate_cnpj
class CertificateError(ValueError): pass

def cipher():
    try: return Fernet(settings.CERTIFICATE_ENCRYPTION_KEY.encode())
    except (ValueError,TypeError,AttributeError):
        raise CertificateError('A proteção de certificados não foi configurada. Execute python iniciar.py --preparar.') from None

def der_text(payload):
    for _ in range(3):
        if len(payload)<2 or payload[0] not in (0x04,0x0c,0x13,0x16): return ''
        length,offset=payload[1],2
        if length&0x80:
            count=length&0x7f
            if not 1<=count<=2 or len(payload)<2+count: return ''
            length=int.from_bytes(payload[2:2+count],'big'); offset+=count
        if len(payload)!=offset+length: return ''
        content=payload[offset:]
        if payload[0]!=0x04: return content.decode('ascii','ignore').strip()
        payload=content
    return ''

@sensitive_variables('password','payload','key')
def inspect_certificate(payload,password,company):
    if len(payload)>1024*1024: raise CertificateError('O certificado excede 1 MB.')
    try: key,cert,extra=pkcs12.load_key_and_certificates(payload,password.encode('utf-8'))
    except (ValueError,TypeError): raise CertificateError('Não foi possível abrir o certificado. Confira o arquivo A1 e a senha.') from None
    if key is None or cert is None: raise CertificateError('O arquivo precisa conter o certificado A1 e sua chave privada.')
    if cert.not_valid_after_utc<=timezone.now(): raise CertificateError('Este certificado está vencido. Envie um certificado válido.')
    if cert.not_valid_before_utc>timezone.now(): raise CertificateError('A validade deste certificado ainda não começou.')
    holder=''
    try:
        san=cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        for item in san:
            if isinstance(item,x509.OtherName) and item.type_id.dotted_string=='2.16.76.1.3.3':
                candidate=der_text(item.value)
                if re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}',candidate): holder=validate_cnpj(candidate)
    except (x509.ExtensionNotFound,ValueError,ValidationError): pass
    if not holder: raise CertificateError('Não foi encontrado um CNPJ válido no campo e-CNPJ do certificado.')
    if holder[:8]!=company.cnpj[:8]: raise CertificateError('O certificado pertence a outra raiz de CNPJ e não pode ser associado a esta empresa.')
    return {'subject_name':cert.subject.rfc4514_string()[:250],'holder_cnpj':holder,'valid_from':cert.not_valid_before_utc,'valid_until':cert.not_valid_after_utc,'fingerprint':cert.fingerprint(hashes.SHA256()).hex()}

@sensitive_variables('password','payload')
def save_certificate(company,payload,password,is_demo=False):
    data=inspect_certificate(payload,password,company)
    box=cipher()
    result,created=DigitalCertificate.objects.update_or_create(company=company,defaults={**data,'encrypted_file':box.encrypt(payload),'encrypted_password':box.encrypt(password.encode()),'is_demo':is_demo})
    AuditEntry.objects.create(workspace=company.workspace,description=f'Certificado {"associado" if created else "renovado"}: {company.display_name}'[:250])
    from portal.services.capture import schedule_company
    schedule_company(company)
    return result
