"""Mesmo portal, escopo explícito na URL e supervisão administrativa em leitura."""
import re
from functools import lru_cache
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, render
from django.urls import include, path
from django.utils.cache import add_never_cache_headers
from django.utils.deprecation import MiddlewareMixin
from .models import Workspace, MasterAudit

PREFIX = re.compile(r'^/gestao/clientes/([1-9][0-9]*)/painel(?:/|$)')
READ_VIEWS = frozenset({
    'dashboard', 'companies', 'certificates', 'invoices', 'invoice_detail',
    'xml_download', 'danfe_download', 'agenda', 'export_csv', 'boletos',
    'boleto_detail', 'boleto_download', 'capture_list', 'capture_detail',
    'capture_document', 'capture_document_download', 'fiscal_documents',
    'fiscal_document', 'fiscal_xml', 'fiscal_pdf', 'fiscal_envelope_xml',
    'fiscal_connectors', 'integration_list','pending_documents','indicators',
})


@lru_cache(maxsize=128)
def scoped_urls(workspace_id):
    # Prefixo literal faz todos os {% url %} existentes manterem o cliente.
    # Não há variável de sessão/global indicando "cliente atual".
    from config.urls import master_urls
    from . import views
    from django.contrib.auth.views import LogoutView
    return (
        path(f'gestao/clientes/{workspace_id}/painel/', include('portal.urls')),
        path('gestao/', include(master_urls)),
        path('api/v1/', include('portal.api.urls')),
        path('perfil/', views.profile, name='profile'),
        path('sair/', LogoutView.as_view(), name='logout'),
    )


class SupervisionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        match = PREFIX.match(request.path_info)
        if not match:
            return
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.has_perm('portal.admin_master'):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        request.supervised_workspace = get_object_or_404(
            Workspace.objects.select_related('owner'), pk=int(match[1]))
        request.urlconf = scoped_urls(request.supervised_workspace.pk)

    def process_view(self, request, view_func, view_args, view_kwargs):
        workspace = getattr(request, 'supervised_workspace', None)
        if workspace is None:
            return
        name = request.resolver_match.url_name
        if request.method not in {'GET', 'HEAD'} or name not in READ_VIEWS:
            return render(request, 'portal/supervision_blocked.html', status=403)
        MasterAudit.objects.create(actor=request.user, workspace=workspace,
            action='client_panel_read', details=f'Tela {name}'[:250])

    def process_response(self, request, response):
        if getattr(request, 'supervised_workspace', None) is not None:
            add_never_cache_headers(response)
            response['Referrer-Policy'] = 'same-origin'
        return response
