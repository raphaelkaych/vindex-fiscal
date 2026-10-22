import re
from django.core.exceptions import ValidationError

def normalize_cnpj(value):
    return re.sub(r'[.\-/\s]', '', str(value)).upper()

def validate_cnpj(value):
    cnpj=normalize_cnpj(value)
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}',cnpj) or len(set(cnpj))==1:
        raise ValidationError('Informe um CNPJ válido, com 14 posições.')
    base=[ord(c)-48 for c in cnpj[:12]]
    def digit(numbers,weights):
        remainder=sum(a*b for a,b in zip(numbers,weights))%11
        return 0 if remainder<2 else 11-remainder
    d1=digit(base,[5,4,3,2,9,8,7,6,5,4,3,2])
    d2=digit(base+[d1],[6,5,4,3,2,9,8,7,6,5,4,3,2])
    if cnpj[-2:]!=f'{d1}{d2}':
        raise ValidationError('Os dígitos verificadores do CNPJ não conferem.')
    return cnpj

def format_cnpj(value):
    value=normalize_cnpj(value)
    return f'{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}' if len(value)==14 else value
