from django.urls import path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from rest_framework.routers import SimpleRouter
from portal.api.views import CompanyViewSet, InvoiceViewSet, InstallmentViewSet, CertificateViewSet, BoletoViewSet
from portal.api.not_found import ApiNotFoundView

router = SimpleRouter()
from .fiscal import FiscalDocumentViewSet,ConnectorViewSet,NfeCaptureViewSet
router.register('documentos-fiscais',FiscalDocumentViewSet,basename='api-fiscal-document')
router.register('conectores',ConnectorViewSet,basename='api-fiscal-connector')
router.register('capturas-nfe',NfeCaptureViewSet,basename='api-nfe-capture')
router.register('empresas', CompanyViewSet, basename='api-company')
router.register('notas', InvoiceViewSet, basename='api-invoice')
router.register('parcelas', InstallmentViewSet, basename='api-installment')
router.register('certificados', CertificateViewSet, basename='api-certificate')
router.register('boletos', BoletoViewSet, basename='api-boleto')

public = {'permission_classes': [AllowAny], 'authentication_classes': []}
urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(**public), name='api-schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api-schema', **public), name='api-swagger'),
    path('redoc/', SpectacularRedocView.as_view(url_name='api-schema', **public), name='api-redoc'),
] + router.urls + [re_path(r'^.*$', ApiNotFoundView.as_view(), name='api-not-found')]
