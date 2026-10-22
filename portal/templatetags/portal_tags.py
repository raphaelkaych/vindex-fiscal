from decimal import Decimal
from django import template
from django.utils.safestring import mark_safe
from portal.validators import format_cnpj
register=template.Library()
@register.filter
def signature_label(value):
    return {'invalid':'Divergência na verificação criptográfica','unverified':'Não foi possível verificar','absent':'Assinatura ausente',
        'certificate_outside_declared_processing_validity':'Certificado de assinatura fora da validade na data de processamento declarada',
        'verified_embedded_key':'Integridade conferida com chave embutida; cadeia e revogação não verificadas','invalid_reference':'Referência assinada incompatível',
        'not_checked':'Não conferida'}.get(value,'Não conferida')
@register.filter
def brl(value):
    try: value=f'{Decimal(value):,.2f}'
    except (ValueError,TypeError,ArithmeticError): return 'R$ 0,00'
    return 'R$ '+value.replace(',','_').replace('.',',').replace('_','.')
register.filter('cnpj',format_cnpj)
@register.simple_tag
def icon(name):
    shapes={
        'truck':'<path d="M3 5h11v12H3zM14 9h4l3 4v4h-7M7 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4M18 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4"/>',
        'chart':'<path d="M4 3v18h17M8 16v-4M13 16V7M18 16v-7"/>',
        'layers':'<path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
        'grid':'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        'building':'<path d="M4 21V5l8-2v18M12 8h8v13M2 21h20M7 7h2M7 11h2M7 15h2M15 11h2M15 15h2M7 19h2M15 19h2"/>',
        'file':'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/>',
        'shield':'<path d="m12 3 8 4v5c0 5-8 9-8 9s-8-4-8-9V7zM8 12l3 3 5-6"/>',
        'calendar':'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2"/>',
        'upload':'<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
        'download':'<path d="M12 3v13m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
        'arrow':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
        'plus':'<path d="M12 5v14M5 12h14"/>',
        'search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
        'user':'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
        'logout':'<path d="M10 3H5v18h5M9 12h12m-4-4 4 4-4 4"/>',
        'clock':'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
        'check':'<path d="m5 12 4 4L20 5"/>',
        'info':'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.1"/>',
        'lock':'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
        'menu':'<path d="M4 6h16M4 12h16M4 18h16"/>',
        'spark':'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
        'edit':'<path d="m15 5 4 4M4 20l5-1L21 7l-4-4L5 15z"/>',
    }
    return mark_safe('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+shapes.get(name,shapes['file'])+'</svg>')
