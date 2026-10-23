"""Configuração e evidências privadas da distribuição DF-e por empresa."""
from django.conf import settings
from django.db import models
from django.db.models import Q


class SefazSyncState(models.Model):
    ENVIRONMENTS = [('1', 'Produção'), ('2', 'Homologação')]
    SOURCES = [('test', 'Teste sintético'), ('manual', 'Resposta importada manualmente'), ('sefaz', 'Serviço oficial SEFAZ')]
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='sefaz_states')
    environment = models.CharField(max_length=1, choices=ENVIRONMENTS, default='2')
    source = models.CharField(max_length=8, choices=SOURCES, default='test')
    last_nsu = models.CharField(max_length=15, default='000000000000000')
    max_nsu = models.CharField(max_length=15, default='000000000000000')
    reported_nsu = models.CharField(max_length=15, blank=True)
    last_status = models.CharField(max_length=3, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_response_at = models.DateTimeField(null=True, blank=True)
    last_real_success_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    last_reason = models.CharField(max_length=500, blank=True)
    official_response_at = models.DateTimeField(null=True, blank=True)
    last_counts = models.JSONField(default=dict, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'environment', 'source'], name='unique_sefaz_state_company_env_source')]


class SefazDocument(models.Model):
    KINDS = [('summary', 'Resumo NF-e'), ('invoice', 'XML completo NF-e'), ('event', 'Evento NF-e'), ('event_summary', 'Resumo de evento'), ('unknown', 'Tipo sem tratamento')]
    state = models.ForeignKey(SefazSyncState, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=16, choices=KINDS)
    nsu = models.CharField(max_length=15, blank=True)
    content_hash = models.CharField(max_length=64)
    schema_name = models.CharField(max_length=100)
    access_key = models.CharField(max_length=44, blank=True)
    event_type = models.CharField(max_length=6, blank=True)
    xml_content = models.TextField()
    invoice = models.ForeignKey('Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='distribution_documents')
    stream_document = models.ForeignKey('SefazStreamDocument', on_delete=models.SET_NULL, null=True, blank=True, related_name='deliveries')
    processing_error = models.CharField(max_length=500, blank=True)
    last_processing_attempt_at = models.DateTimeField(null=True, blank=True)
    next_processing_attempt_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['state', 'content_hash'], name='unique_sefaz_document_content'),
            models.UniqueConstraint(fields=['state', 'nsu'], condition=~Q(nsu=''), name='unique_sefaz_document_known_nsu'),
        ]


class SefazCaptureConfig(models.Model):
    company = models.OneToOneField('Company', on_delete=models.CASCADE, related_name='capture_config')
    enabled = models.BooleanField(default=False)
    environment = models.CharField(max_length=1, choices=SefazSyncState.ENVIRONMENTS, default='1')
    uf_author = models.CharField(max_length=2, blank=True)
    read_authorized_at = models.DateTimeField(null=True, blank=True)
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    science_authorized_at = models.DateTimeField(null=True, blank=True)
    science_authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=40, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SefazDistributionStream(models.Model):
    """Cursor/limites do consumidor CNPJ, compartilhados só no serviço interno.

    A mesma pessoa jurídica pode autorizar clientes diferentes. Nunca deve haver
    dois consumidores distNSU concorrentes para o mesmo CNPJ e ambiente.
    """
    cnpj = models.CharField(max_length=14)
    environment = models.CharField(max_length=1, choices=SefazSyncState.ENVIRONMENTS)
    source = models.CharField(max_length=8, choices=SefazSyncState.SOURCES, default='sefaz')
    last_nsu = models.CharField(max_length=15, default='000000000000000')
    max_nsu = models.CharField(max_length=15, default='000000000000000')
    reported_nsu = models.CharField(max_length=15, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    blocked_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True, editable=False)
    lease_until = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_response_at = models.DateTimeField(null=True, blank=True)
    official_response_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=3, blank=True)
    last_reason = models.CharField(max_length=500, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['cnpj', 'environment', 'source'], name='unique_sefaz_stream_cnpj_env_source')]


class SefazStreamDocument(models.Model):
    """Caixa de entrada durável; entregas de cada cliente ficam em SefazDocument."""
    stream = models.ForeignKey(SefazDistributionStream, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=16, choices=SefazDocument.KINDS)
    nsu = models.CharField(max_length=15, blank=True)
    content_hash = models.CharField(max_length=64)
    schema_name = models.CharField(max_length=100)
    access_key = models.CharField(max_length=44, blank=True)
    event_type = models.CharField(max_length=6, blank=True)
    xml_content = models.TextField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['stream', 'content_hash'], name='unique_sefaz_stream_document_content'),
            models.UniqueConstraint(fields=['stream', 'nsu'], condition=~Q(nsu=''), name='unique_sefaz_stream_document_nsu'),
        ]


class SefazConsultation(models.Model):
    state = models.ForeignKey(SefazSyncState, on_delete=models.SET_NULL, null=True, related_name='consultations')
    stream = models.ForeignKey(SefazDistributionStream, on_delete=models.PROTECT, null=True, related_name='consultations')
    requested_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    official_response_at = models.DateTimeField(null=True, blank=True)
    requested_nsu = models.CharField(max_length=15)
    query_kind = models.CharField(max_length=9, default='distNSU', db_default='distNSU', choices=[('distNSU', 'Distribuição'), ('consNSU', 'Recuperação por NSU'), ('consChNFe', 'Recuperação por chave')])
    requested_key = models.CharField(max_length=44, blank=True, db_default='')
    key_recovery = models.ForeignKey('SefazKeyRecovery', on_delete=models.PROTECT, null=True, blank=True, related_name='consultations')
    resume_from_nsu = models.CharField(max_length=15, blank=True, db_default='')
    recovery = models.ForeignKey('SefazNsuRecovery', on_delete=models.PROTECT, null=True, blank=True, related_name='consultations')
    reported_nsu = models.CharField(max_length=15, blank=True)
    max_nsu = models.CharField(max_length=15, blank=True)
    status = models.CharField(max_length=3, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    counts = models.JSONField(default=dict)
    error_code = models.CharField(max_length=40, blank=True)
    error = models.CharField(max_length=500, blank=True)
    response_xml = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ['-requested_at', '-pk']


class SefazNsuRecovery(models.Model):
    """Intervalo ainda não recebido; nunca se confunde com cursor de distribuição."""
    stream = models.ForeignKey(SefazDistributionStream, on_delete=models.PROTECT, related_name='recoveries')
    first_nsu = models.CharField(max_length=15)
    last_nsu = models.CharField(max_length=15)
    next_nsu = models.CharField(max_length=15)
    recovered_count = models.PositiveIntegerField(default=0)
    unavailable_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['stream', 'first_nsu', 'last_nsu'], name='unique_sefaz_recovery_range')]


class SefazKeyRecovery(models.Model):
    """Consulta pontual motivada por referência em CT-e do próprio cliente."""
    stream = models.ForeignKey(SefazDistributionStream, on_delete=models.PROTECT, related_name='key_recoveries')
    company = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, related_name='nfe_key_recoveries')
    evidence = models.ForeignKey('FiscalDocument', on_delete=models.SET_NULL, null=True, related_name='nfe_key_recoveries')
    access_key = models.CharField(max_length=44)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=3, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    result = models.CharField(max_length=20, default='pending', choices=[('pending', 'Agendada'), ('xml', 'XML recebido'), ('summary', 'Somente resumo'), ('unavailable', 'Sem documento disponível'), ('rejected', 'Consulta rejeitada')])
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['stream', 'access_key'], name='unique_sefaz_recovery_key')]
