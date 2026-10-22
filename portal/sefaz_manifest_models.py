"""Autorizações individuais de Ciência da Emissão e evidência da resposta."""
from django.conf import settings
from django.db import models


class SefazScienceRequest(models.Model):
    company = models.ForeignKey('Company', on_delete=models.CASCADE, related_name='science_requests')
    document = models.ForeignKey('SefazDocument', on_delete=models.PROTECT, related_name='science_requests')
    environment = models.CharField(max_length=1)
    cnpj = models.CharField(max_length=14, default='')
    access_key = models.CharField(max_length=44)
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    authorized_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', 'Autorizado'), ('sent', 'Enviado'), ('accepted', 'Registrado na SEFAZ'),
        ('rejected', 'Rejeitado'), ('uncertain', 'Resultado desconhecido: revisar antes de reenviar'),
    ])
    response_code = models.CharField(max_length=3, blank=True)
    response_reason = models.CharField(max_length=500, blank=True)
    response_at = models.DateTimeField(null=True, blank=True)
    protocol = models.CharField(max_length=20, blank=True)
    signed_xml = models.TextField(blank=True, editable=False)
    response_xml = models.TextField(blank=True, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'environment', 'access_key'], name='unique_science_company_env_key'),
            models.UniqueConstraint(fields=['cnpj', 'environment', 'access_key'], name='unique_science_cnpj_env_key'),
        ]

