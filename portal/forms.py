from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Company, Workspace
from .validators import validate_cnpj

class RegisterForm(UserCreationForm):
    full_name=forms.CharField(label='Seu nome',max_length=150)
    email=forms.EmailField(label='E-mail',max_length=150)
    workspace_name=forms.CharField(label='Nome do cliente ou grupo empresarial',max_length=120)
    class Meta:
        model=User
        fields=['full_name','email','workspace_name','password1','password2']
    def clean_email(self):
        email=self.cleaned_data['email'].strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError('Já existe uma conta com este e-mail.')
        return email
    def save(self,commit=True):
        user=super().save(commit=False)
        user.username=self.cleaned_data['email']
        user.email=self.cleaned_data['email']
        user.first_name=self.cleaned_data['full_name']
        if commit:
            user.save()
            Workspace.objects.create(owner=user,name=self.cleaned_data['workspace_name'])
        return user

class LoginForm(AuthenticationForm):
    username=forms.EmailField(label='E-mail',max_length=150,widget=forms.EmailInput(attrs={'autocomplete':'username'}))
    def clean_username(self): return self.cleaned_data['username'].strip().lower()

class CompanyForm(forms.ModelForm):
    cnpj=forms.CharField(label="CNPJ",max_length=18)
    class Meta:
        model=Company
        fields=['legal_name','trade_name','cnpj']
    def __init__(self,*args,workspace,**kwargs):
        self.workspace=workspace
        super().__init__(*args,**kwargs)
        self.fields['cnpj'].max_length=18
        self.fields['cnpj'].widget.attrs['maxlength']=18
        self.fields['trade_name'].help_text='Opcional. É o nome que aparecerá nos painéis.'
    def clean_cnpj(self):
        cnpj=validate_cnpj(self.cleaned_data['cnpj'])
        if Company.objects.filter(workspace=self.workspace,cnpj=cnpj).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Este CNPJ já está cadastrado no seu painel.')
        if self.instance.pk and cnpj!=self.instance.cnpj:
            raise forms.ValidationError('Cadastre outra empresa para um CNPJ diferente; o CNPJ identifica o histórico existente.')
        return cnpj

class CertificateForm(forms.Form):
    file=forms.FileField(label='Certificado digital A1',widget=forms.FileInput(attrs={'accept':'.pfx,.p12'}))
    password=forms.CharField(label='Senha do certificado',max_length=256,strip=False,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    authorized=forms.BooleanField(label='Tenho autorização para utilizar este certificado na consulta dos documentos desta empresa.')
    def clean_file(self):
        file=self.cleaned_data['file']
        if not file.name.lower().endswith(('.pfx','.p12')):
            raise forms.ValidationError('Envie um arquivo .pfx ou .p12.')
        if file.size>1024*1024: raise forms.ValidationError('O certificado deve ter no máximo 1 MB.')
        return file

class MultipleInput(forms.ClearableFileInput): allow_multiple_selected=True
class MultipleFiles(forms.FileField):
    def clean(self,data,initial=None):
        items=data if isinstance(data,(list,tuple)) else [data]
        if len(items)>5: raise forms.ValidationError('Selecione até cinco XMLs por importação.')
        files=[super(MultipleFiles,self).clean(item,initial) for item in items]
        for item in files:
            if not item.name.lower().endswith('.xml'): raise forms.ValidationError('A importação aceita somente arquivos XML de NF-e.')
            if item.size>2*1024*1024: raise forms.ValidationError('Cada XML deve ter no máximo 2 MB.')
        return files
class ImportForm(forms.Form):
    files=MultipleFiles(label='Arquivos XML',widget=MultipleInput(attrs={'accept':'.xml','data-file-input':''}))
class ProfileForm(forms.ModelForm):
    full_name=forms.CharField(label='Seu nome',max_length=150)
    class Meta:
        model=Workspace
        fields=['full_name','name','phone']
