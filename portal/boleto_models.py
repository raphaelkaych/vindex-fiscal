"""Documentos de cobrança privados. Nenhum campo representa liquidação bancária."""
from django.core.exceptions import ValidationError
from django.db import models


class Boleto(models.Model):
    company = models.ForeignKey('portal.Company', on_delete=models.CASCADE, related_name='boletos')
    installment = models.OneToOneField('portal.Installment', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='boleto')
    private_pdf = models.BinaryField(editable=False, null=True, blank=True)
    pdf_sha256 = models.CharField(max_length=64, null=True, blank=True, editable=False)
    barcode = models.CharField('Código de barras', max_length=44, null=True, blank=True)
    digitable_line = models.CharField('Linha digitável', max_length=48, blank=True)
    kind = models.CharField(max_length=16, choices=[('charge','Cobrança bancária'),
        ('collection','Arrecadação'),('unknown','A identificar')], default='unknown')
    amount = models.DecimalField('Valor declarado', max_digits=18, decimal_places=2, null=True, blank=True)
    due_on = models.DateField('Vencimento declarado', null=True, blank=True)
    due_candidates = models.JSONField(default=list, blank=True)
    beneficiary_name = models.CharField('Beneficiário', max_length=200, blank=True)
    beneficiary_document = models.CharField('CPF/CNPJ do beneficiário', max_length=14, blank=True)
    payer_name = models.CharField('Pagador', max_length=200, blank=True)
    payer_document = models.CharField('CPF/CNPJ do pagador', max_length=14, blank=True)
    bank_code = models.CharField('Código do banco', max_length=3, blank=True)
    reference = models.CharField('Identificação do documento', max_length=100, blank=True)
    source = models.CharField('Origem', max_length=12, choices=[('manual','Dados informados'),
        ('pdf','Importação de PDF'),('api','API Vindex')], default='manual')
    extraction_method = models.CharField(max_length=12, choices=[('manual','Dados informados'),
        ('pdf_text','Texto do PDF'),('none','Sem texto legível')], default='manual')
    validation_state = models.CharField(max_length=12, choices=[('validated','Dígitos conferidos'),
        ('pending','A revisar')], default='pending')
    review_notes = models.TextField(blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_on', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['company','barcode'], name='unique_boleto_company_barcode'),
            models.UniqueConstraint(fields=['company','pdf_sha256'], name='unique_boleto_company_pdf'),
        ]

    @property
    def has_pdf(self): return bool(self.pdf_sha256)
    @property
    def needs_review(self): return bool(self.review_notes) or self.validation_state != 'validated'
    @property
    def financial_status(self): return 'unknown'

    def clean(self):
        if self.installment_id and self.installment.invoice.company_id != self.company_id:
            raise ValidationError('A parcela e o boleto precisam pertencer à mesma empresa.')

    def __str__(self): return self.reference or f'Boleto {self.pk}'


class BoletoEvent(models.Model):
    boleto = models.ForeignKey(Boleto, on_delete=models.CASCADE, related_name='events')
    action = models.CharField(max_length=30)
    source = models.CharField(max_length=30)
    actor_label = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at','-pk']

    @property
    def action_label(self):
        return {'importado':'Importação','arquivo_anexado':'PDF anexado','revisado':'Revisão dos dados',
            'associado':'Associação à parcela','desassociado':'Vínculo removido'}.get(self.action,self.action)

    @property
    def source_label(self):
        return {'manual':'Área autenticada','pdf':'Importação de PDF','api':'API Vindex'}.get(self.source,'Serviço local')

    @property
    def display_changes(self):
        labels={'barcode':'Código de barras','digitable_line':'Linha digitável','amount':'Valor declarado',
            'due_on':'Vencimento declarado','beneficiary_name':'Beneficiário',
            'beneficiary_document':'CPF/CNPJ do beneficiário','payer_name':'Pagador',
            'payer_document':'CPF/CNPJ do pagador','reference':'Identificação',
            'kind':'Tipo de documento','bank_code':'Código do banco','validation_state':'Conferência dos dígitos'}
        def readable(value):
            return {'None':'Não informado','':'Não informado','validated':'Dígitos conferidos',
                'pending':'A revisar','charge':'Cobrança bancária','collection':'Arrecadação','unknown':'A identificar'}.get(str(value),str(value))
        return [{'label':labels[key],'before':readable(change.get('before')),'after':readable(change.get('after'))}
            for key,change in self.details.get('changes',{}).items() if key in labels]
