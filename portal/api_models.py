"""Credenciais opacas de integração; o segredo nunca é persistido."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables


class ApiCredential(models.Model):
    workspace = models.ForeignKey('portal.Workspace', on_delete=models.CASCADE, related_name='api_credentials')
    name = models.CharField('Nome da integração', max_length=100)
    prefix = models.CharField(max_length=24, unique=True, editable=False)
    secret_hash = models.CharField(max_length=256, editable=False)
    scopes = models.JSONField(default=list)
    companies = models.ManyToManyField('portal.Company', through='portal.CredentialCompany', related_name='api_credentials')
    expires_at = models.DateTimeField('Válida até')
    revoked_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def clean(self):
        if not isinstance(self.scopes, list) or not self.scopes or any(s not in ('read', 'write') for s in self.scopes):
            raise ValidationError({'scopes': 'Escolha os escopos read e/ou write.'})
        if not self.expires_at or self.expires_at <= timezone.now():
            raise ValidationError({'expires_at': 'Informe uma validade futura.'})
        maximum = getattr(settings, 'API_CREDENTIAL_MAX_DAYS', 365)
        if self.expires_at > timezone.now() + timedelta(days=maximum):
            raise ValidationError({'expires_at': f'A validade máxima é de {maximum} dias.'})

    @property
    def state(self):
        if self.revoked_at:
            return 'revoked'
        return 'expired' if self.expires_at <= timezone.now() else 'active'

    @property
    def allowed_companies(self):
        # A dupla restrição protege inclusive contra uma relação incorreta inserida fora desta gestão.
        return self.companies.filter(workspace_id=self.workspace_id)

    @classmethod
    @transaction.atomic
    @sensitive_variables('secret', 'token')
    def issue(cls, *, workspace, name, scopes, companies, expires_at):
        from portal.models import Company, AuditEntry
        ids = {int(getattr(company, 'pk', company)) for company in companies}
        allowed = list(Company.objects.filter(workspace=workspace, pk__in=ids))
        if len(allowed) != len(ids):
            raise ValidationError('Empresa fora do cliente autenticado.')
        secret = secrets.token_urlsafe(32)
        credential = cls(workspace=workspace, name=name, scopes=sorted(set(scopes)),
                         expires_at=expires_at, prefix=secrets.token_hex(8),
                         secret_hash=make_password(secret, hasher='pbkdf2_sha256'))
        credential.full_clean()
        credential.save()
        CredentialCompany.objects.bulk_create([CredentialCompany(credential=credential, company=company) for company in allowed])
        AuditEntry.objects.create(workspace=workspace, description=f'Credencial de API criada: {credential.name}'[:250])
        token = f'vfx_{credential.prefix}.{secret}'
        return credential, token

    @sensitive_variables('secret')
    def verifies(self, secret):
        # check_password usa o PBKDF2 mantido pelo Django e comparação em tempo constante.
        return check_password(secret, self.secret_hash)

    def revoke(self):
        from portal.models import AuditEntry
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=['revoked_at'])
            AuditEntry.objects.create(workspace=self.workspace, description=f'Credencial de API revogada: {self.name}'[:250])


class CredentialCompany(models.Model):
    credential = models.ForeignKey(ApiCredential, on_delete=models.CASCADE)
    company = models.ForeignKey('portal.Company', on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['credential', 'company'], name='unique_api_credential_company')]

    def clean(self):
        if self.credential_id and self.company_id and self.credential.workspace_id != self.company.workspace_id:
            raise ValidationError('A empresa deve pertencer ao cliente da credencial.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
