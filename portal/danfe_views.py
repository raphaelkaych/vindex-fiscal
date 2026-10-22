"""Downloads auxiliares privados: o escopo é sempre o Workspace autenticado."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from .models import Invoice
from .services.danfe import DanfeError, generate_danfe
from .views import workspace_for


@login_required
@require_safe
@never_cache
def danfe_download(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related('company'), pk=pk,is_demo=False,
                               company__workspace=workspace_for(request))
    try:
        data = generate_danfe(invoice)
    except DanfeError as error:
        return render(request, 'portal/danfe_unavailable.html', {'invoice': invoice, 'reason': str(error)}, status=422)
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="danfe-{invoice.access_key}.pdf"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
