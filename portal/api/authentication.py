import hashlib
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, Throttled

from portal.api_models import ApiCredential


class IntegrationAuthentication(BaseAuthentication):
    @sensitive_variables('raw', 'token', 'secret')
    def authenticate(self, request):
        if getattr(settings, 'API_REQUIRE_HTTPS', not settings.DEBUG) and not request.is_secure():
            raise AuthenticationFailed('HTTPS é obrigatório para a API em produção.')
        raw = get_authorization_header(request)
        if not raw:
            return None
        address = request.META.get('REMOTE_ADDR', 'unknown')
        attempt_key = 'vindex-api-attempt:' + hashlib.sha256(address.encode()).hexdigest()
        cache.add(attempt_key, 0, 60)
        try:
            attempts = cache.incr(attempt_key)
        except ValueError:
            attempts = 1
            cache.set(attempt_key, attempts, 60)
        if attempts > 180:
            raise Throttled(wait=60, detail='Limite de autenticações por endereço atingido. Aguarde um minuto.')
        key = 'vindex-api-auth:' + hashlib.sha256(address.encode()).hexdigest()
        if cache.get(key, 0) >= 30:
            raise Throttled(wait=60, detail='Muitas tentativas de autenticação. Aguarde um minuto.')
        try:
            token = raw.decode('ascii')
        except UnicodeDecodeError:
            token = ''
        match = re.fullmatch(r'Bearer vfx_([a-f0-9]{16})\.([A-Za-z0-9_-]{43})', token)
        credential = None
        if match:
            credential = ApiCredential.objects.select_related('workspace__owner').filter(prefix=match[1]).first()
        if not credential or not credential.verifies(match[2]) or credential.state != 'active' or not credential.workspace.owner.is_active or credential.workspace.access_status!='active':
            cache.add(key, 0, 60)
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, 60)
            raise AuthenticationFailed('Credencial inválida, expirada ou revogada.')
        ApiCredential.objects.filter(pk=credential.pk).update(last_used_at=timezone.now())
        return credential.workspace.owner, credential

    def authenticate_header(self, request):
        return 'Bearer'


class IntegrationAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'portal.api.authentication.IntegrationAuthentication'
    name = 'VindexIntegration'

    def get_security_definition(self, auto_schema):
        return {'type': 'http', 'scheme': 'bearer',
                'description': 'Credencial opaca vfx_<prefixo>.<segredo>, emitida em Integrações/API. Validade, escopos read/write e empresas são validados no servidor.'}
