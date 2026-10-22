from django.conf import settings
from django.db import models

SERVICES=[('nfse','NFS-e nacional / ADN'),('cte','CT-e modelo 57')]


class FiscalConnector(models.Model):
    company=models.ForeignKey('Company',on_delete=models.CASCADE,related_name='fiscal_connectors')
    service=models.CharField(max_length=8,choices=SERVICES)
    environment=models.CharField(max_length=1,default='1',choices=[('1','Produção'),('2','Homologação')])
    enabled=models.BooleanField(default=False)
    authorized_at=models.DateTimeField(null=True)
    authorized_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    uf_author=models.CharField(max_length=2,blank=True)
    last_error=models.CharField(max_length=500,blank=True)
    last_checked_at=models.DateTimeField(null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['company','service','environment'],name='unique_fiscal_connector')]


class FiscalStream(models.Model):
    cnpj=models.CharField(max_length=14)
    service=models.CharField(max_length=8,choices=SERVICES)
    environment=models.CharField(max_length=1)
    cursor=models.CharField(max_length=20,default='0')
    max_cursor=models.CharField(max_length=20,blank=True)
    next_attempt_at=models.DateTimeField(null=True)
    lease_token=models.UUIDField(null=True)
    lease_until=models.DateTimeField(null=True)
    last_attempt_at=models.DateTimeField(null=True)
    last_accepted_at=models.DateTimeField(null=True)
    last_status=models.CharField(max_length=80,blank=True)
    last_reason=models.CharField(max_length=500,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['cnpj','service','environment'],name='unique_fiscal_stream')]


class FiscalConsultation(models.Model):
    stream=models.ForeignKey(FiscalStream,on_delete=models.PROTECT,related_name='consultations')
    requested_at=models.DateTimeField(auto_now_add=True)
    completed_at=models.DateTimeField(null=True)
    cursor_sent=models.CharField(max_length=20)
    cursor_received=models.CharField(max_length=20,blank=True)
    status=models.CharField(max_length=80,blank=True)
    reason=models.CharField(max_length=500,blank=True)
    http_status=models.PositiveIntegerField(null=True)
    response_content=models.TextField(blank=True,editable=False)
    error=models.CharField(max_length=500,blank=True)
    counts=models.JSONField(default=dict)
    class Meta:ordering=['-pk']


class FiscalEnvelope(models.Model):
    stream=models.ForeignKey(FiscalStream,on_delete=models.PROTECT,related_name='envelopes')
    nsu=models.CharField(max_length=20)
    schema_name=models.CharField(max_length=100,blank=True)
    xml_content=models.TextField()
    content_hash=models.CharField(max_length=64)
    kind=models.CharField(max_length=16,default='unknown')
    received_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['stream','nsu'],name='unique_fiscal_envelope_nsu')]


class FiscalDocument(models.Model):
    company=models.ForeignKey('Company',on_delete=models.CASCADE,related_name='fiscal_documents')
    service=models.CharField(max_length=8,choices=SERVICES)
    environment=models.CharField(max_length=1,default='1')
    access_key=models.CharField(max_length=64)
    number=models.CharField(max_length=30)
    issuer_name=models.CharField(max_length=200)
    issuer_cnpj=models.CharField(max_length=14)
    role=models.CharField(max_length=30)
    issued_at=models.DateTimeField()
    total=models.DecimalField(max_digits=18,decimal_places=2)
    xml_content=models.TextField()
    imported_at=models.DateTimeField(auto_now_add=True)
    cancellation_reported=models.BooleanField(default=False)
    payment_data=models.JSONField(default=list)
    validation_status=models.CharField(max_length=16,default='schema',choices=[('schema','Schema validado'),('partial','Importação parcial — revisar')])
    validation_details=models.JSONField(default=dict)
    substitution_reported=models.BooleanField(default=False)
    substituted_by=models.CharField(max_length=64,blank=True)
    official_pdf=models.BinaryField(null=True,editable=False)
    official_pdf_source=models.CharField(max_length=250,blank=True)
    official_pdf_checked_at=models.DateTimeField(null=True)
    class Meta:
        ordering=['-issued_at','-pk']
        constraints=[models.UniqueConstraint(fields=['company','service','environment','access_key'],name='unique_fiscal_document_key')]


class FiscalDelivery(models.Model):
    connector=models.ForeignKey(FiscalConnector,on_delete=models.PROTECT,related_name='deliveries')
    envelope=models.ForeignKey(FiscalEnvelope,on_delete=models.PROTECT,related_name='deliveries')
    document=models.ForeignKey(FiscalDocument,on_delete=models.SET_NULL,null=True)
    error=models.CharField(max_length=500,blank=True)
    next_retry_at=models.DateTimeField(null=True)
    processing_status=models.CharField(max_length=20,default='pending')
    diagnostics=models.JSONField(default=dict)
    processor_revision=models.CharField(max_length=40,blank=True)
    last_processed_at=models.DateTimeField(null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['connector','envelope'],name='unique_fiscal_delivery')]
