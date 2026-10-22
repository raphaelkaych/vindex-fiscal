from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response

from portal.api.base import IntegrationViewSet
from portal.api.serializers import (CompanySerializer, InvoiceSerializer, InvoiceDetailSerializer, XmlImportSerializer,
    InvoiceImportResultSerializer, InstallmentSerializer, InstallmentWriteSerializer, InstallmentCorrectionSerializer, InstallmentCheckSerializer,
    CertificateMetadataSerializer, BoletoSerializer, BoletoDetailSerializer, BoletoImportSerializer,
    BoletoImportResultSerializer, BoletoAssociateSerializer, BoletoCorrectionSerializer)
from portal.api_models import CredentialCompany
from portal.models import Company, Invoice, Installment, DigitalCertificate, AuditEntry
from portal.boleto_models import Boleto
from portal.services.invoices import import_invoice, InvoiceImportError
from portal.services.installments import save_installment, review_installment
from portal.services.boletos import (import_boleto, associate_boleto, disassociate_boleto, update_boleto,
                                    BoletoImportError, BoletoAssociationError)


COMMON_FILTERS = [
    OpenApiParameter('company', OpenApiTypes.INT, description='ID de uma empresa autorizada.'),
    OpenApiParameter('cnpj', OpenApiTypes.STR, description='CNPJ completo de uma empresa autorizada.'),
    OpenApiParameter('ordering', OpenApiTypes.STR, description='Campos permitidos; prefixo - inverte. Consulte API.md.'),
]
DATE_FILTERS = [OpenApiParameter('from', OpenApiTypes.DATE, description='Início inclusivo (emissão/vencimento conforme recurso).'),
                OpenApiParameter('to', OpenApiTypes.DATE, description='Fim inclusivo.')]
SUPPLIER_FILTERS = [OpenApiParameter('supplier', OpenApiTypes.STR, description='Nome parcial ou CNPJ do fornecedor/beneficiário.'),
                    OpenApiParameter('source', OpenApiTypes.STR, description='Origem exata, conforme recurso.'),
                    OpenApiParameter('review', OpenApiTypes.STR, enum=['pending', 'clear'], description='Pendência de revisão.')]


@extend_schema_view(list=extend_schema(parameters=COMMON_FILTERS + [OpenApiParameter('q', str)]))
class CompanyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, IntegrationViewSet):
    """Empresas autorizadas. Cadastrar um novo CNPJ autoriza esse cadastro para a credencial que o criou."""
    queryset = Company.objects.none()
    serializer_class = CompanySerializer
    company_lookup = ''
    filter_fields = ('q',)
    ordering_fields = ('id', 'legal_name', 'cnpj', 'created_at')
    default_ordering = ('legal_name', 'pk')

    def get_queryset(self):
        qs = self.companies()
        if self.action != 'list':
            return qs
        qs = self.filtered(qs)
        q = self.request.query_params.get('q', '')[:150]
        return qs.filter(Q(legal_name__icontains=q) | Q(trade_name__icontains=q) | Q(cnpj__icontains=q)) if q else qs

    @transaction.atomic
    def perform_create(self, serializer):
        company = serializer.save(workspace=self.request.auth.workspace)
        CredentialCompany.objects.create(credential=self.request.auth, company=company)
        AuditEntry.objects.create(workspace=self.request.auth.workspace, description=f'Empresa cadastrada pela API: {company.display_name}'[:250])


@extend_schema_view(list=extend_schema(parameters=COMMON_FILTERS + DATE_FILTERS + SUPPLIER_FILTERS + [OpenApiParameter('q', str)]))
class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, IntegrationViewSet):
    """NF-e modelo 55 importadas. XML não comprova liquidação nem consulta atual à SEFAZ."""
    queryset = Invoice.objects.none()
    serializer_class = InvoiceSerializer
    date_field = 'issued_on'
    filter_fields = ('q', 'supplier', 'source', 'review')
    ordering_fields = ('id', 'issued_on', 'total', 'number', 'imported_at')
    default_ordering = ('-issued_on', '-pk')

    def get_serializer_class(self):
        return InvoiceDetailSerializer if self.action == 'retrieve' else self.serializer_class

    def get_queryset(self):
        qs = Invoice.objects.filter(company__in=self.companies(),is_demo=False).select_related('company').prefetch_related('installments')
        if self.action != 'list':
            return qs
        qs = self.filtered(qs)
        params = self.request.query_params
        if params.get('q'):
            q = params['q'][:150]
            qs = qs.filter(Q(number__icontains=q) | Q(access_key__icontains=q) | Q(issuer_name__icontains=q))
        if params.get('supplier'):
            q = params['supplier'][:200]
            qs = qs.filter(Q(issuer_name__icontains=q) | Q(issuer_cnpj__icontains=q))
        if params.get('source'):
            value = self.enum_filter(params['source'], ['xml', 'api_xml', 'sefaz', 'demo'], 'source')
            qs = qs.filter(source=value)
        review = self.enum_filter(params.get('review'), ['pending', 'clear'], 'review')
        if review == 'pending':
            qs = qs.exclude(review_notes='')
        elif review == 'clear':
            qs = qs.filter(review_notes='')
        return qs

    @extend_schema(request={'multipart/form-data': XmlImportSerializer}, responses={201: InvoiceImportResultSerializer, 200: InvoiceImportResultSerializer})
    @action(detail=False, methods=['post'], url_path='importar', parser_classes=[MultiPartParser, FormParser])
    def import_xml(self, request):
        """Importação idempotente por empresa e chave. Não aceita eventos, resumos, CT-e ou NFS-e."""
        serializer = XmlImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invoice, created = import_invoice(request.auth.workspace, serializer.validated_data['file'].read(),
                                             allowed_companies=self.companies(), source='api_xml')
        except InvoiceImportError as exc:
            raise serializers.ValidationError({'file': str(exc)}) from None
        return Response({'created': created, 'invoice': InvoiceDetailSerializer(invoice).data}, status=201 if created else 200)

    @extend_schema(responses={(200, 'application/xml'): OpenApiTypes.BINARY})
    @action(detail=True, methods=['get'], url_path='xml')
    def xml(self, request, pk=None):
        invoice = self.get_object()
        response = HttpResponse(invoice.xml_content, content_type='application/xml; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="nfe-{invoice.access_key}.xml"'
        return response


@extend_schema_view(list=extend_schema(parameters=COMMON_FILTERS + DATE_FILTERS + [
    OpenApiParameter('supplier', str), OpenApiParameter('source', str, enum=['xml', 'manual']),
    OpenApiParameter('checked', str, enum=['true', 'false']), OpenApiParameter('invoice', int),
    OpenApiParameter('state', str, enum=['past_due_date', 'upcoming', 'undated']),
]))
class InstallmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, IntegrationViewSet):
    """Previsões financeiras. Conferência e vencimento não significam pagamento ou inadimplência."""
    queryset = Installment.objects.none()
    serializer_class = InstallmentSerializer
    company_lookup = 'invoice__company'
    date_field = 'due_on'
    filter_fields = ('supplier', 'source', 'checked', 'invoice', 'state')
    ordering_fields = ('id', 'due_on', 'amount', 'number')
    default_ordering = ('due_on', 'pk')

    def get_queryset(self):
        qs = Installment.objects.filter(invoice__company__in=self.companies(),invoice__is_demo=False).select_related('invoice__company')
        if self.action != 'list':
            return qs
        qs = self.filtered(qs)
        params = self.request.query_params
        if params.get('supplier'):
            q = params['supplier'][:200]
            qs = qs.filter(Q(invoice__issuer_name__icontains=q) | Q(invoice__issuer_cnpj__icontains=q))
        if params.get('source'):
            qs = qs.filter(source=self.enum_filter(params['source'], ['xml', 'manual'], 'source'))
        checked = self.enum_filter(params.get('checked'), ['true', 'false'], 'checked')
        if checked:
            qs = qs.filter(checked=checked == 'true')
        if params.get('invoice'):
            if not params['invoice'].isdecimal():
                raise serializers.ValidationError({'invoice': 'Informe um ID numérico.'})
            qs = qs.filter(invoice_id=params['invoice'])
        state = self.enum_filter(params.get('state'), ['past_due_date', 'upcoming', 'undated'], 'state')
        if state == 'past_due_date':
            qs = qs.filter(due_on__lt=timezone.localdate())
        elif state == 'upcoming':
            qs = qs.filter(due_on__gte=timezone.localdate())
        elif state == 'undated':
            qs = qs.filter(due_on__isnull=True)
        return qs

    @extend_schema(request=InstallmentWriteSerializer, responses={201: InstallmentSerializer})
    def create(self, request):
        serializer = InstallmentWriteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        invoice = data.pop('invoice')
        item = save_installment(request.auth.workspace, invoice, data, allowed_companies=self.companies(), actor=request.auth, source='manual')
        return Response(InstallmentSerializer(item).data, status=201)

    @extend_schema(request=InstallmentCorrectionSerializer, responses={200: InstallmentSerializer})
    def partial_update(self, request, pk=None):
        item = self.get_object()
        serializer = InstallmentWriteSerializer(item, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get('review_note'):
            raise serializers.ValidationError({'review_note': 'Explique a correção para preservar a auditoria.'})
        item = save_installment(request.auth.workspace, item.invoice, dict(serializer.validated_data), installment=item,
                                allowed_companies=self.companies(), actor=request.auth, source='manual')
        return Response(InstallmentSerializer(item).data)

    @extend_schema(request=InstallmentCheckSerializer, responses={200: InstallmentSerializer})
    @action(detail=True, methods=['post'], url_path='conferir')
    def check(self, request, pk=None):
        item = self.get_object()
        serializer = InstallmentCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = review_installment(request.auth.workspace, item, serializer.validated_data['checked'],
                                  actor=request.auth, allowed_companies=self.companies())
        return Response(InstallmentSerializer(item).data)


@extend_schema_view(list=extend_schema(parameters=COMMON_FILTERS))
class CertificateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, IntegrationViewSet):
    """Somente metadados. Nenhum endpoint retorna PFX/P12, senha, chave privada ou chave de cifra."""
    queryset = DigitalCertificate.objects.none()
    serializer_class = CertificateMetadataSerializer
    ordering_fields = ('id', 'valid_until', 'uploaded_at')
    def get_queryset(self):
        qs = DigitalCertificate.objects.filter(company__in=self.companies(),is_demo=False).defer('encrypted_file', 'encrypted_password')
        return self.filtered(qs) if self.action == 'list' else qs


@extend_schema_view(list=extend_schema(parameters=COMMON_FILTERS + DATE_FILTERS + SUPPLIER_FILTERS + [
    OpenApiParameter('validation_state', str, enum=['validated', 'pending']),
    OpenApiParameter('linked', str, enum=['true', 'false']), OpenApiParameter('invoice', int),
]))
class BoletoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, IntegrationViewSet):
    """Boletos locais. Dígitos verificados não comprovam autenticidade ou liquidação bancária."""
    queryset = Boleto.objects.none()
    serializer_class = BoletoSerializer
    date_field = 'due_on'
    filter_fields = ('supplier', 'source', 'review', 'validation_state', 'linked', 'invoice')
    ordering_fields = ('id', 'due_on', 'amount', 'imported_at')
    default_ordering = ('-imported_at', '-pk')

    def get_serializer_class(self):
        return BoletoDetailSerializer if self.action == 'retrieve' else self.serializer_class

    def get_queryset(self):
        qs = Boleto.objects.filter(company__in=self.companies()).select_related('installment__invoice').defer('private_pdf').prefetch_related('events')
        if self.action != 'list':
            return qs
        qs = self.filtered(qs)
        params = self.request.query_params
        if params.get('supplier'):
            q = params['supplier'][:200]
            qs = qs.filter(Q(beneficiary_name__icontains=q) | Q(beneficiary_document__icontains=q))
        if params.get('source'):
            qs = qs.filter(source=self.enum_filter(params['source'], ['pdf', 'manual', 'api'], 'source'))
        if params.get('validation_state'):
            qs = qs.filter(validation_state=self.enum_filter(params['validation_state'], ['validated', 'pending'], 'validation_state'))
        linked = self.enum_filter(params.get('linked'), ['true', 'false'], 'linked')
        if linked:
            qs = qs.filter(installment__isnull=linked == 'false')
        review = self.enum_filter(params.get('review'), ['pending', 'clear'], 'review')
        if review == 'pending':
            qs = qs.filter(Q(validation_state='pending') | ~Q(review_notes=''))
        elif review == 'clear':
            qs = qs.filter(validation_state='validated', review_notes='')
        if params.get('invoice'):
            if not params['invoice'].isdecimal():
                raise serializers.ValidationError({'invoice': 'Informe um ID numérico.'})
            qs = qs.filter(installment__invoice_id=params['invoice'])
        return qs

    @extend_schema(request={'application/json': BoletoImportSerializer, 'multipart/form-data': BoletoImportSerializer},
                   responses={201: BoletoImportResultSerializer, 200: BoletoImportResultSerializer})
    @action(detail=False, methods=['post'], url_path='importar')
    def import_document(self, request):
        serializer = BoletoImportSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        file = data.pop('file', None)
        data['source'] = 'api'
        try:
            boleto, created = import_boleto(request.auth.workspace, data, payload=file.read() if file else None,
                                            allowed_companies=self.companies(), actor=request.auth)
        except BoletoImportError as exc:
            raise serializers.ValidationError({'document': str(exc)}) from None
        return Response({'created': created, 'boleto': BoletoDetailSerializer(boleto).data}, status=201 if created else 200)

    @extend_schema(responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=True, methods=['get'], url_path='arquivo')
    def document(self, request, pk=None):
        boleto = self.get_object()
        if not boleto.has_pdf:
            raise Http404
        response = HttpResponse(bytes(boleto.private_pdf), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="boleto-{boleto.pk}.pdf"'
        return response

    @extend_schema(request=BoletoCorrectionSerializer, responses={200: BoletoDetailSerializer})
    def partial_update(self, request, pk=None):
        boleto = self.get_object()
        serializer = BoletoCorrectionSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            boleto = update_boleto(request.auth.workspace, boleto, dict(serializer.validated_data),
                                    actor=request.auth, source='api', allowed_companies=self.companies())
        except BoletoImportError as exc:
            raise serializers.ValidationError({'document': str(exc)}) from None
        return Response(BoletoDetailSerializer(boleto).data)

    @extend_schema(request=BoletoAssociateSerializer, responses={200: BoletoDetailSerializer})
    @action(detail=True, methods=['post'], url_path='associar')
    def associate(self, request, pk=None):
        boleto = self.get_object()
        serializer = BoletoAssociateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        try:
            if serializer.validated_data['installment'] is None:
                boleto = disassociate_boleto(request.auth.workspace, boleto, allowed_companies=self.companies(), actor=request.auth, source='api')
            else:
                boleto = associate_boleto(request.auth.workspace, boleto, serializer.validated_data['installment'],
                                           allowed_companies=self.companies(), actor=request.auth, source='api',
                                           review_reason=serializer.validated_data.get('review_reason', ''))
        except BoletoAssociationError as exc:
            raise serializers.ValidationError({'association': str(exc)}) from None
        return Response(BoletoDetailSerializer(boleto).data)
