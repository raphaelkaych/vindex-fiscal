from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone
from portal.api_models import ApiCredential


class ApiCredentialForm(forms.Form):
    name = forms.CharField(label='Nome da integração', max_length=100)
    scopes = forms.MultipleChoiceField(label='Permissões', choices=[('read', 'Leitura'), ('write', 'Gravação')], widget=forms.CheckboxSelectMultiple, initial=['read'])
    companies = forms.ModelMultipleChoiceField(label='Empresas autorizadas', queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
                                               help_text='Sem empresas selecionadas, a credencial não acessa nenhuma empresa existente. Gravação permite cadastrar uma empresa e autorizar esse novo cadastro para a própria credencial.')
    expires_at = forms.DateTimeField(label='Válida até', input_formats=['%Y-%m-%dT%H:%M'], widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))

    def __init__(self, *args, workspace, **kwargs):
        self.workspace = workspace
        super().__init__(*args, **kwargs)
        self.fields['companies'].queryset = workspace.companies.all()
        self.fields['expires_at'].initial = timezone.localtime(timezone.now() + timedelta(days=getattr(settings, 'API_CREDENTIAL_DEFAULT_DAYS', 90)))
        self.fields['expires_at'].help_text = f"Escolha uma data futura em até {getattr(settings, 'API_CREDENTIAL_MAX_DAYS', 365)} dias."

    def clean(self):
        data = super().clean()
        if data.get('expires_at') and data.get('scopes'):
            candidate = ApiCredential(workspace=self.workspace, name=data.get('name', ''), scopes=data['scopes'], expires_at=data['expires_at'])
            candidate.clean()
        return data

    def issue(self):
        return ApiCredential.issue(workspace=self.workspace, **self.cleaned_data)
