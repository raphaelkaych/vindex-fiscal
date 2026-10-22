from django import forms
from decimal import Decimal

class InstallmentReviewForm(forms.Form):
    number=forms.CharField(label='Identificador da parcela',max_length=60)
    amount=forms.DecimalField(label='Valor previsto',max_digits=18,decimal_places=2,min_value=Decimal('.01'))
    due_on=forms.DateField(label='Vencimento informado',required=False,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    review_note=forms.CharField(label='Origem ou motivo da revisão',max_length=2000,widget=forms.Textarea(attrs={'rows':3}),help_text='Indique o documento ou a confirmação do fornecedor. Não informa pagamento ao banco.')
