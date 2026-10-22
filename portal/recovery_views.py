from django.contrib.auth.views import PasswordResetView
from django.conf import settings
from django.http import HttpResponse
from .views import rate_limited


class RecoveryView(PasswordResetView):
    template_name='portal/recovery.html'
    email_template_name='portal/recovery_email.txt'
    subject_template_name='portal/recovery_subject.txt'
    def dispatch(self,request,*args,**kwargs):
        if rate_limited(request,'password-reset',5):return HttpResponse('Aguarde antes de solicitar outro e-mail.',status=429)
        if not settings.EMAIL_HOST:return HttpResponse('Recuperação por e-mail ainda não configurada. Contate a Vindex. O administrador local pode usar o comando changepassword.',status=503)
        return super().dispatch(request,*args,**kwargs)
