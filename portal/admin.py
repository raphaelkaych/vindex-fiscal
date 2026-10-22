from django.contrib import admin
from .models import Workspace,Company,Invoice,Installment,AuditEntry
# Certificados e senhas cifrados não são expostos no painel administrativo.
for model in [Workspace,Company,Invoice,Installment,AuditEntry]: admin.site.register(model)
admin.site.site_header='Vindex Fiscal · Gestão interna'
