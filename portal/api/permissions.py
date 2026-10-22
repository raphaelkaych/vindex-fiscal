from rest_framework.permissions import BasePermission, SAFE_METHODS
from portal.api_models import ApiCredential


class IntegrationScopePermission(BasePermission):
    message = 'A credencial não possui o escopo necessário para esta operação.'

    def has_permission(self, request, view):
        if not isinstance(request.auth, ApiCredential):
            return False
        scope = 'read' if request.method in SAFE_METHODS else 'write'
        return scope in request.auth.scopes
