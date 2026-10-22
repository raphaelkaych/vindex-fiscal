"""Consentimentos explícitos para consultas e eventos: nunca contém segredos A1."""
from django import forms
from .forms import CertificateForm


UF_CHOICES = [('', 'Não informar (opcional)'), ('12', 'AC'), ('27', 'AL'),
    ('16', 'AP'), ('13', 'AM'), ('29', 'BA'), ('23', 'CE'), ('53', 'DF'), ('32', 'ES'),
    ('52', 'GO'), ('21', 'MA'), ('51', 'MT'), ('50', 'MS'), ('31', 'MG'), ('15', 'PA'),
    ('25', 'PB'), ('41', 'PR'), ('26', 'PE'), ('22', 'PI'), ('33', 'RJ'), ('24', 'RN'),
    ('43', 'RS'), ('11', 'RO'), ('14', 'RR'), ('42', 'SC'), ('35', 'SP'), ('28', 'SE'), ('17', 'TO')]


class CaptureEnableForm(forms.Form):
    uf_author = forms.ChoiceField(label='UF do estabelecimento', choices=UF_CHOICES,
        required=False, help_text='Opcional no serviço de distribuição. Se informada, deve ser a UF deste CNPJ.')
    authorize_read = forms.BooleanField(label='Autorizo o Vindex Fiscal a consultar automaticamente os documentos deste CNPJ na SEFAZ, em produção.',
        help_text='Somente consultas de leitura. Nenhuma manifestação fiscal será enviada por esta autorização.')


class CaptureCertificateForm(CertificateForm):
    enable_nfse=forms.BooleanField(required=False,label='Autorizar captura automática de NFS-e nacional / ADN em produção.',help_text='Somente leitura dos serviços compartilhados com o ADN. Não envia eventos.')
    enable_cte=forms.BooleanField(required=False,label='Autorizar captura automática de CT-e modelo 57 em produção.',help_text='Somente leitura. Informe abaixo a UF deste estabelecimento.')
    enable_capture = forms.BooleanField(required=False, label='Habilitar a captura automática de NF-e recebidas em produção.',
        help_text='Autorizo consultas periódicas de leitura para esta empresa. Desmarcar esta opção na renovação pausa a captura. Eventos fiscais exigem autorização separada por documento.')
    uf_author = forms.ChoiceField(label='UF do estabelecimento para a captura', choices=UF_CHOICES,
        required=False, help_text='Opcional no serviço de distribuição. A senha do certificado nunca será exibida novamente.')
    def clean(self):
        data=super().clean()
        if data.get('enable_cte') and not data.get('uf_author'):self.add_error('uf_author','A UF é obrigatória para capturar CT-e.')
        return data


class ScienceAuthorizationForm(forms.Form):
    authorized = forms.BooleanField(label='Autorizo o envio de Ciência da Emissão exclusivamente para a NF-e identificada nesta página.',
        help_text='Li os efeitos e os prazos indicados abaixo. Esta autorização não confirma a operação comercial.')
