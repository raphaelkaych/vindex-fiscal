from rest_framework import serializers,mixins
from rest_framework.decorators import action
from django.http import HttpResponse
from portal.models import FiscalDocument,FiscalConnector,FiscalStream,SefazSyncState
from .base import IntegrationViewSet


class FiscalDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model=FiscalDocument
        fields=['id','company','service','environment','access_key','number','issuer_name','issuer_cnpj','role','issued_at','imported_at','total','cancellation_reported','substitution_reported','substituted_by','validation_status','validation_details','payment_data']
        read_only_fields=fields


class FiscalDocumentViewSet(mixins.ListModelMixin,mixins.RetrieveModelMixin,IntegrationViewSet):
    """Registros NFS-e/CT-e; validation_status distingue schema e importação parcial."""
    queryset=FiscalDocument.objects.none()
    serializer_class=FiscalDocumentSerializer
    filter_fields=('service','environment','validation_status')
    ordering_fields=('issued_at','imported_at','total','id')
    date_field='issued_at'
    def get_queryset(self):
        qs=FiscalDocument.objects.filter(company__in=self.companies()).select_related('company').defer('xml_content','official_pdf')
        if self.action=='list':
            qs=self.filtered(qs)
            for field,choices in [('service',('nfse','cte')),('environment',('1','2')),('validation_status',('schema','partial'))]:
                value=self.request.query_params.get(field)
                if value:qs=qs.filter(**{field:self.enum_filter(value,choices,field)})
        return qs
    @action(detail=True,methods=['get'])
    def xml(self,request,pk=None):
        doc=self.get_object();response=HttpResponse(doc.xml_content,content_type='application/xml; charset=utf-8')
        response['Content-Disposition']=f'attachment; filename="{doc.service}-{doc.access_key}.xml"'
        return response


class ConnectorSerializer(serializers.ModelSerializer):
    state=serializers.SerializerMethodField()
    class Meta:
        model=FiscalConnector
        fields=['id','company','service','environment','enabled','authorized_at','uf_author','last_error','state']
        read_only_fields=fields
    def get_state(self,obj)->dict:
        from portal.services.fiscal_capture import requirements
        from portal.services.sefaz import SefazError
        try:requirements(obj)
        except SefazError as error:return {'status':'configuration_pending','reason':str(error)}
        stream=FiscalStream.objects.filter(cnpj=obj.company.cnpj,service=obj.service,environment=obj.environment).first()
        return {field:getattr(stream,field) for field in ['cursor','max_cursor','last_status','last_reason','last_attempt_at','last_accepted_at','next_attempt_at']} if stream else {'status':'not_started'}


class ConnectorViewSet(mixins.ListModelMixin,mixins.RetrieveModelMixin,IntegrationViewSet):
    """Estado dos conectores autorizados; nenhuma consulta/evento pode ser disparado pela API."""
    queryset=FiscalConnector.objects.none()
    serializer_class=ConnectorSerializer
    ordering_fields=('id','service')
    def get_queryset(self):
        qs=FiscalConnector.objects.filter(company__in=self.companies()).select_related('company')
        return self.filtered(qs) if self.action=='list' else qs


class NfeCaptureSerializer(serializers.ModelSerializer):
    class Meta:
        model=SefazSyncState
        fields=['id','company','environment','source','last_nsu','max_nsu','last_status','last_reason','official_response_at','last_attempt_at','next_attempt_at','last_counts','last_error']
        read_only_fields=fields


class NfeCaptureViewSet(mixins.ListModelMixin,mixins.RetrieveModelMixin,IntegrationViewSet):
    queryset=SefazSyncState.objects.none()
    serializer_class=NfeCaptureSerializer
    ordering_fields=('id',)
    def get_queryset(self):
        qs=SefazSyncState.objects.filter(company__in=self.companies(),source='sefaz')
        return self.filtered(qs) if self.action=='list' else qs
