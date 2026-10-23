from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from .validators import format_cnpj

class Workspace(models.Model):
    owner=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='workspace')
    name=models.CharField('Nome do cliente',max_length=120)
    phone=models.CharField('Telefone',max_length=30,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    access_status=models.CharField(max_length=12,default='active',choices=[('active','Ativo'),('pending','Aguardando aprovação'),('suspended','Acesso suspenso')])
    capture_paused=models.BooleanField(default=False)
    class Meta:
        permissions=[('admin_master','Administrar gestão master Vindex'),('operate_clients','Alterar situação operacional de clientes')]
    def __str__(self): return self.name

class Company(models.Model):
    workspace=models.ForeignKey(Workspace,on_delete=models.CASCADE,related_name='companies')
    legal_name=models.CharField('Razão social',max_length=180)
    trade_name=models.CharField('Nome de exibição',max_length=100,blank=True)
    cnpj=models.CharField('CNPJ',max_length=14)
    created_at=models.DateTimeField(auto_now_add=True)
    deactivated_at=models.DateTimeField(null=True,blank=True,editable=False)
    class Meta:
        ordering=['legal_name']
        constraints=[models.UniqueConstraint(fields=['workspace','cnpj'],name='unique_company_per_workspace')]
    @property
    def display_name(self): return self.trade_name or self.legal_name
    @property
    def is_active(self): return self.deactivated_at is None
    @property
    def formatted_cnpj(self): return format_cnpj(self.cnpj)
    def __str__(self): return self.display_name

class DigitalCertificate(models.Model):
    company=models.OneToOneField(Company,on_delete=models.CASCADE,related_name='certificate')
    encrypted_file=models.BinaryField(editable=False)
    encrypted_password=models.BinaryField(editable=False)
    subject_name=models.CharField(max_length=250)
    holder_cnpj=models.CharField(max_length=14)
    valid_from=models.DateTimeField()
    valid_until=models.DateTimeField()
    fingerprint=models.CharField(max_length=64)
    uploaded_at=models.DateTimeField(auto_now=True)
    is_demo=models.BooleanField(default=False)
    @property
    def days_remaining(self): return (self.valid_until.date()-timezone.localdate()).days
    @property
    def state(self):
        if self.valid_until<=timezone.now(): return 'expired'
        return 'expiring' if self.days_remaining<=30 else 'active'

class Invoice(models.Model):
    company=models.ForeignKey(Company,on_delete=models.CASCADE,related_name='invoices')
    access_key=models.CharField(max_length=44)
    number=models.CharField(max_length=15)
    series=models.CharField(max_length=6)
    issuer_name=models.CharField(max_length=200)
    issuer_cnpj=models.CharField(max_length=14)
    issued_on=models.DateField()
    total=models.DecimalField(max_digits=18,decimal_places=2)
    purpose=models.CharField(max_length=2,default='1')
    payment_method=models.CharField(max_length=80,blank=True)
    payment_details=models.JSONField(default=list,blank=True)
    billing_details=models.JSONField(default=dict,blank=True)
    source=models.CharField(max_length=20,default='xml',choices=[('xml','Importação XML'),('api_xml','API · XML'),('sefaz','Distribuição SEFAZ'),('demo','Demonstração')])
    review_notes=models.TextField(blank=True)
    xml_content=models.TextField()
    imported_at=models.DateTimeField(auto_now_add=True)
    is_demo=models.BooleanField(default=False)
    class Meta:
        ordering=['-issued_on','-pk']
        constraints=[models.UniqueConstraint(fields=['company','access_key'],name='unique_invoice_company_key')]
    @property
    def needs_review(self): return bool(self.review_notes)
    @cached_property
    def payment_evidence(self):
        from .services.payment_evidence import extract_payment_data
        return extract_payment_data(self.xml_content)
    @cached_property
    def danfe_status(self):
        from .services.danfe import availability
        return availability(self)
    @property
    def short_key(self): return f'{self.access_key[:6]}…{self.access_key[-8:]}'
    def __str__(self): return f'NF-e {self.number}'

class Installment(models.Model):
    invoice=models.ForeignKey(Invoice,on_delete=models.CASCADE,related_name='installments')
    number=models.CharField(max_length=60)
    due_on=models.DateField(null=True,blank=True)
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    checked=models.BooleanField(default=False)
    source=models.CharField(max_length=12,default='xml',choices=[('xml','Duplicata do XML'),('manual','Revisão manual')])
    original_data=models.JSONField(default=dict,blank=True)
    review_note=models.TextField(blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=['due_on','pk']
        constraints=[models.UniqueConstraint(fields=['invoice','number'],name='unique_invoice_installment')]
    @property
    def is_overdue(self): return bool(self.due_on and self.due_on<timezone.localdate())

class AuditEntry(models.Model):
    workspace=models.ForeignKey(Workspace,on_delete=models.CASCADE,related_name='events')
    description=models.CharField(max_length=250)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']

class InstallmentRevision(models.Model):
    installment=models.ForeignKey(Installment,on_delete=models.CASCADE,related_name='revisions')
    before=models.JSONField(default=dict)
    after=models.JSONField(default=dict)
    reason=models.TextField()
    actor=models.CharField(max_length=100,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at','-pk']

# Módulos de domínio mantêm a mesma aplicação/migrações e usam relações por nome.
from .boleto_models import Boleto, BoletoEvent
from .api_models import ApiCredential, CredentialCompany
from .sefaz_models import (SefazSyncState, SefazDocument, SefazCaptureConfig,
    SefazDistributionStream, SefazStreamDocument, SefazConsultation, SefazNsuRecovery, SefazKeyRecovery)
from .sefaz_manifest_models import SefazScienceRequest
from .management_models import MasterAudit
from .fiscal_models import FiscalConnector,FiscalStream,FiscalConsultation,FiscalEnvelope,FiscalDocument,FiscalDelivery
from .search_models import FiscalSearchRecord,FiscalSearchItem
