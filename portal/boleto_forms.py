from django import forms
from portal.models import Company, Installment
from portal.services.boletos import MAX_PDF_BYTES


class BoletoDataForm(forms.Form):
    digitable_line = forms.CharField(label='Linha digitável ou código de barras', max_length=80, required=False,
        help_text='47 posições de cobrança, 48 de arrecadação ou 44 do código de barras. Os números não autenticam o boleto no banco.')
    beneficiary_name = forms.CharField(label='Beneficiário', max_length=200, required=False)
    beneficiary_document = forms.CharField(label='CPF/CNPJ do beneficiário', max_length=20, required=False)
    payer_name = forms.CharField(label='Pagador', max_length=200, required=False)
    payer_document = forms.CharField(label='CNPJ do pagador', max_length=20, required=False,
        help_text='Quando informado, deve coincidir exatamente com o CNPJ da empresa selecionada.')
    amount = forms.DecimalField(label='Valor declarado (R$)', max_digits=18, decimal_places=2,
        min_value=0.01, required=False, localize=True)
    due_on = forms.DateField(label='Vencimento declarado', required=False,
        widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'), input_formats=['%Y-%m-%d','%d/%m/%Y'],
        help_text='Informe a data do documento. O fator do código possui ciclos e não escolhe a data automaticamente.')
    reference = forms.CharField(label='Identificação do documento', max_length=100, required=False)


class BoletoImportForm(BoletoDataForm):
    company = forms.ModelChoiceField(label='Empresa / CNPJ pagador', queryset=Company.objects.none(), empty_label='Selecione a empresa')
    file = forms.FileField(label='PDF do boleto (até 5 MB)', required=False,
        widget=forms.FileInput(attrs={'accept':'.pdf,application/pdf'}),
        help_text='PDF digital: leitura de texto. Imagem/scan: revisão manual; OCR não está configurado.')

    def __init__(self,*args,workspace,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=Company.objects.filter(workspace=workspace)
        self.order_fields(['company','file',*BoletoDataForm.base_fields])

    def clean_file(self):
        file=self.cleaned_data.get('file')
        if file and (file.size>MAX_PDF_BYTES or not file.name.lower().endswith('.pdf')):
            raise forms.ValidationError('Envie um arquivo .pdf de até 5 MB.')
        return file

    def clean(self):
        data=super().clean()
        if not data.get('file') and not data.get('digitable_line'):
            raise forms.ValidationError('Envie o PDF ou informe a linha digitável/código de barras.')
        return data


class BoletoAssociationForm(forms.Form):
    installment=forms.ModelChoiceField(label='Parcela da mesma empresa',queryset=Installment.objects.none(),empty_label='Selecione uma parcela')
    review_reason=forms.CharField(label='Justificativa de revisão',max_length=1000,required=False,
        widget=forms.Textarea(attrs={'rows':3}),help_text='Obrigatória se valor, vencimento ou beneficiário divergirem/não estiverem confirmados. Considere cessões ou intermediários.')
    confirmed=forms.BooleanField(label='Conferi o documento e confirmo este vínculo. Esta ação não confirma pagamento.')
    def __init__(self,*args,boleto,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['installment'].queryset=Installment.objects.filter(invoice__company=boleto.company).select_related('invoice').order_by('-invoice__issued_on','number')
        self.fields['installment'].label_from_instance=lambda part: f'NF-e {part.invoice.number} · parcela {part.number} · {part.due_on or "data a definir"} · R$ {part.amount}'
