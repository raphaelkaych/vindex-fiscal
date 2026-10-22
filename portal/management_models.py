from django.conf import settings
from django.db import models


class MasterAudit(models.Model):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    workspace=models.ForeignKey('Workspace',on_delete=models.PROTECT,null=True)
    action=models.CharField(max_length=60)
    details=models.CharField(max_length=200,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-pk']
