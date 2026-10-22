from decimal import Decimal
from rest_framework import serializers
from portal.forms import CompanyForm
from portal.models import Company, Invoice, Installment, DigitalCertificate
from portal.boleto_models import Boleto, BoletoEvent


class StrictInputMixin:
    def to_internal_value(self, data):
        if not hasattr(data, 'keys'):
            raise serializers.ValidationError('Envie um objeto com os campos documentados.')
        allowed = {name for name, field in self.fields.items() if not field.read_only}
        extra = set(data.keys()) - allowed
        if extra:
            raise serializers.ValidationError({str(name): 'Campo não permitido.' for name in sorted(extra)})
        return super().to_internal_value(data)


class ExactMoneyField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, (float, bool)):
            raise serializers.ValidationError('Envie o valor como texto decimal, por exemplo "123.45".')
        return super().to_internal_value(data)


class CompanySerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'legal_name', 'trade_name', 'cnpj', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {'cnpj': {'max_length': 18}}
        validators = []

    def validate(self, attrs):
        form = CompanyForm(data=attrs, workspace=self.context['request'].auth.workspace)
        if not form.is_valid():
            raise serializers.ValidationError(form.errors)
        return {key: form.cleaned_data[key] for key in ('legal_name', 'trade_name', 'cnpj')}


class InstallmentSerializer(serializers.ModelSerializer):
    company = serializers.IntegerField(source='invoice.company_id', read_only=True)
    financial_status = serializers.SerializerMethodField()
    class Meta:
        model = Installment
        fields = ['id', 'invoice', 'company', 'number', 'due_on', 'amount', 'checked', 'source', 'original_data', 'review_note', 'updated_at', 'financial_status']
        read_only_fields = fields

    def get_financial_status(self, obj) -> str:
        return 'forecast'


class InvoiceSerializer(serializers.ModelSerializer):
    needs_review = serializers.BooleanField(read_only=True)
    class Meta:
        model = Invoice
        fields = ['id', 'company', 'access_key', 'number', 'series', 'issuer_name', 'issuer_cnpj', 'issued_on', 'total', 'purpose', 'payment_method', 'payment_details', 'billing_details', 'review_notes', 'needs_review', 'source', 'is_demo', 'imported_at']
        read_only_fields = fields


class InvoiceDetailSerializer(InvoiceSerializer):
    payment_evidence=serializers.ListField(child=serializers.DictField(),read_only=True)
    installments = InstallmentSerializer(many=True, read_only=True)
    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ['installments','payment_evidence']


class XmlImportSerializer(StrictInputMixin, serializers.Serializer):
    file = serializers.FileField(help_text='XML completo NF-e modelo 55, UTF-8, até 2 MB.')
    def validate_file(self, file):
        if not file.name.lower().endswith('.xml') or file.size > 2 * 1024 * 1024:
            raise serializers.ValidationError('Envie um XML de NF-e de até 2 MB.')
        return file


class InvoiceImportResultSerializer(serializers.Serializer):
    created = serializers.BooleanField()
    invoice = InvoiceDetailSerializer()


class InstallmentWriteSerializer(StrictInputMixin, serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.none(), required=True)
    number = serializers.CharField(max_length=60)
    due_on = serializers.DateField(allow_null=True, required=False)
    amount = ExactMoneyField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    review_note = serializers.CharField(max_length=2000, required=True, allow_blank=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.auth and 'invoice' in self.fields:
            self.fields['invoice'].queryset = Invoice.objects.filter(company__in=request.auth.allowed_companies)
        if self.instance is not None:
            self.fields.pop('invoice', None)


class InstallmentCorrectionSerializer(InstallmentWriteSerializer):
    invoice = None


class InstallmentCheckSerializer(StrictInputMixin, serializers.Serializer):
    checked = serializers.BooleanField()


class CertificateMetadataSerializer(serializers.ModelSerializer):
    state = serializers.CharField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    class Meta:
        model = DigitalCertificate
        fields = ['id', 'company', 'subject_name', 'holder_cnpj', 'valid_from', 'valid_until', 'uploaded_at', 'state', 'days_remaining', 'is_demo']
        read_only_fields = fields


class BoletoEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoletoEvent
        fields = ['id', 'action', 'source', 'actor_label', 'details', 'created_at']
        read_only_fields = fields


class BoletoSerializer(serializers.ModelSerializer):
    has_pdf = serializers.BooleanField(read_only=True)
    needs_review = serializers.BooleanField(read_only=True)
    financial_status = serializers.CharField(read_only=True)
    invoice = serializers.IntegerField(source='installment.invoice_id', read_only=True, allow_null=True)
    class Meta:
        model = Boleto
        fields = ['id', 'company', 'installment', 'invoice', 'kind', 'barcode', 'digitable_line', 'amount', 'due_on', 'due_candidates', 'beneficiary_name', 'beneficiary_document', 'payer_name', 'payer_document', 'bank_code', 'reference', 'source', 'validation_state', 'review_notes', 'needs_review', 'has_pdf', 'financial_status', 'imported_at', 'updated_at']
        read_only_fields = fields


class BoletoDetailSerializer(BoletoSerializer):
    events = BoletoEventSerializer(many=True, read_only=True)
    class Meta(BoletoSerializer.Meta):
        fields = BoletoSerializer.Meta.fields + ['events']


class BoletoImportSerializer(StrictInputMixin, serializers.Serializer):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.none())
    file = serializers.FileField(required=False, help_text='PDF de até 5 MB; PDF digital usa texto, scan requer revisão/OCR externo.')
    digitable_line = serializers.CharField(max_length=100, required=False, allow_blank=True)
    barcode = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount = ExactMoneyField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'), required=False, allow_null=True)
    due_on = serializers.DateField(required=False, allow_null=True)
    beneficiary_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    beneficiary_document = serializers.CharField(max_length=20, required=False, allow_blank=True)
    payer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    payer_document = serializers.CharField(max_length=20, required=False, allow_blank=True)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.auth:
            self.fields['company'].queryset = request.auth.allowed_companies

    def validate_file(self, file):
        if not file.name.lower().endswith('.pdf') or file.size > 5 * 1024 * 1024:
            raise serializers.ValidationError('Envie um PDF de até 5 MB.')
        return file


class BoletoCorrectionSerializer(BoletoImportSerializer):
    company = None
    file = None

    def __init__(self, *args, **kwargs):
        # Não permite alterar a identidade do cliente/CNPJ nem substituir arquivo na revisão.
        serializers.Serializer.__init__(self, *args, **kwargs)


class BoletoImportResultSerializer(serializers.Serializer):
    created = serializers.BooleanField()
    boleto = BoletoDetailSerializer()


class BoletoAssociateSerializer(StrictInputMixin, serializers.Serializer):
    installment = serializers.PrimaryKeyRelatedField(queryset=Installment.objects.none(), allow_null=True,
                                                    help_text='Parcela da mesma empresa; null desfaz o vínculo.')
    review_reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.auth:
            self.fields['installment'].queryset = Installment.objects.filter(invoice__company__in=request.auth.allowed_companies)


class ApiErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField()


class ErrorEnvelopeSerializer(serializers.Serializer):
    error = ApiErrorSerializer()
