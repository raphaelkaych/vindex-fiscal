"""Índice reconstruível de campos declarados nos XMLs privados."""
from django.db import models
from django.db.models import Q


class FiscalSearchRecord(models.Model):
    company=models.ForeignKey('Company',on_delete=models.CASCADE)
    invoice=models.OneToOneField('Invoice',on_delete=models.CASCADE,null=True,related_name='search_record')
    document=models.OneToOneField('FiscalDocument',on_delete=models.CASCADE,null=True,related_name='search_record')
    kind=models.CharField(max_length=4)
    environment=models.CharField(max_length=1,blank=True)
    access_key=models.CharField(max_length=64,db_index=True)
    number=models.CharField(max_length=30,db_index=True)
    series=models.CharField(max_length=30,blank=True,db_index=True)
    issuer_name=models.CharField(max_length=200,blank=True)
    issuer_search=models.CharField(max_length=250,blank=True,db_default='')
    issuer_cnpj=models.CharField(max_length=14,blank=True,db_index=True)
    recipient_cnpj=models.CharField(max_length=14,blank=True,db_index=True)
    issued_on=models.DateField(db_index=True)
    imported_at=models.DateTimeField()
    total=models.DecimalField(max_digits=18,decimal_places=2)
    status=models.CharField(max_length=20,default='stored')
    diagnostic=models.CharField(max_length=200,blank=True)
    xml_hash=models.CharField(max_length=64)
    class Meta:
        indexes=[models.Index(fields=['company','kind','issued_on'],name='fiscal_search_scope')]
        constraints=[models.CheckConstraint(condition=(Q(invoice__isnull=False,document__isnull=True)|Q(invoice__isnull=True,document__isnull=False)),name='search_one_source')]
    @property
    def doc_id(self):return self.invoice_id or self.document_id
    @property
    def doc_type(self):return self.kind


class FiscalSearchItem(models.Model):
    record=models.ForeignKey(FiscalSearchRecord,on_delete=models.CASCADE,related_name='items')
    position=models.PositiveIntegerField()
    description=models.TextField(blank=True)
    search_text=models.TextField(blank=True,db_default='')
    code=models.CharField(max_length=100,blank=True,db_index=True)
    ncm=models.CharField(max_length=8,blank=True,db_index=True)
    cfop=models.CharField(max_length=4,blank=True,db_index=True)
    unit=models.CharField(max_length=20,blank=True)
    quantity=models.DecimalField(max_digits=30,decimal_places=10,null=True)
    unit_price=models.DecimalField(max_digits=30,decimal_places=10,null=True)
    total=models.DecimalField(max_digits=18,decimal_places=2,null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['record','position'],name='search_item_position')]
