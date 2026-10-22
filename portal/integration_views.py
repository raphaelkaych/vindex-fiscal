from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_POST

from portal.api_models import ApiCredential
from portal.integration_forms import ApiCredentialForm
from portal.views import workspace_for, rate_limited


@login_required
@never_cache
def integration_list(request):
    credentials = ApiCredential.objects.filter(workspace=workspace_for(request)).prefetch_related('companies')
    return render(request, 'portal/integrations.html', {'credentials': credentials})


@login_required
@never_cache
@sensitive_post_parameters()
@sensitive_variables('token')
def integration_create(request):
    workspace = workspace_for(request)
    form = ApiCredentialForm(request.POST or None, workspace=workspace)
    if rate_limited(request, 'api-credential-create', 15):
        return render(request, 'portal/limit.html', status=429)
    if request.method == 'POST' and form.is_valid():
        credential, token = form.issue()
        response = render(request, 'portal/integration_created.html', {'credential': credential, 'token': token})
        response['Cache-Control'] = 'no-store, private, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Referrer-Policy'] = 'no-referrer'
        return response
    return render(request, 'portal/integration_form.html', {'form': form})


@login_required
@never_cache
@require_POST
def integration_revoke(request, pk):
    credential = get_object_or_404(ApiCredential, pk=pk, workspace=workspace_for(request))
    credential.revoke()
    messages.success(request, 'Credencial revogada. Requisições futuras com este segredo serão recusadas.')
    return redirect('integration_list')
