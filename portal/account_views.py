from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .models import Invoice, FiscalDocument
from .services.account_deletion import delete_account
from .views import workspace_for, rate_limited


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label='Sua senha atual', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    confirmation = forms.CharField(label='Nome exato do cliente ou grupo', max_length=120)
    acknowledged = forms.BooleanField(label='Quero excluir meu acesso, certificados e arquivos privados. Entendo que a ação é definitiva e que as evidências fiscais compartilhadas e de auditoria serão preservadas.')

    def __init__(self, *args, user, workspace, **kwargs):
        self.user = user
        self.workspace = workspace
        super().__init__(*args, **kwargs)
        self.fields['confirmation'].help_text = format_html('Digite: {}', workspace.name)

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data['password']):
            raise forms.ValidationError('Senha atual incorreta.')
        return self.cleaned_data['password']

    def clean_confirmation(self):
        if self.cleaned_data['confirmation'] != self.workspace.name:
            raise forms.ValidationError('O nome informado não corresponde ao seu cliente.')
        return self.cleaned_data['confirmation']


@login_required
@never_cache
@require_http_methods(['GET', 'HEAD', 'POST'])
@sensitive_post_parameters('password')
def account_delete(request):
    workspace = workspace_for(request)
    if request.method == 'POST' and rate_limited(request, 'account-delete'):
        return HttpResponse('Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.', status=429)
    form = DeleteAccountForm(request.POST if request.method == 'POST' else None, user=request.user, workspace=workspace)
    if request.method == 'POST' and form.is_valid():
        try:
            delete_account(actor=request.user, workspace_id=workspace.pk, confirmation=form.cleaned_data['confirmation'])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            logout(request)
            messages.success(request, 'Sua conta e seus arquivos privados foram excluídos. As evidências fiscais compartilhadas e os registros de auditoria foram preservados.')
            return redirect('login')
    return render(request, 'portal/account_delete.html', {'form': form,
        'invoice_count': Invoice.objects.filter(company__workspace=workspace).count(),
        'fiscal_count': FiscalDocument.objects.filter(company__workspace=workspace).count()})
