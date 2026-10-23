from django.urls import include,path
from django.contrib.auth.views import LogoutView
from . import views
from .installment_views import installment_review
from .danfe_views import danfe_download
from . import fiscal_views
from .pending_views import pending_documents
from .analytics_views import indicators
from .recovery_views import RecoveryView
from .account_views import account_delete
from . import document_search_views
from django.contrib.auth import views as auth_views
urlpatterns=[
    path('saude/',views.health,name='health'),
    path('recuperar-senha/',RecoveryView.as_view(),name='password_reset'),
    path('recuperar-senha/enviado/',auth_views.PasswordResetDoneView.as_view(template_name='portal/recovery.html'),name='password_reset_done'),
    path('recuperar-senha/<uidb64>/<token>/',auth_views.PasswordResetConfirmView.as_view(template_name='portal/recovery.html'),name='password_reset_confirm'),
    path('recuperar-senha/concluido/',auth_views.PasswordResetCompleteView.as_view(template_name='portal/recovery.html'),name='password_reset_complete'),
    path('documentos/',document_search_views.documents,name='fiscal_documents'),
    path('documentos/exportar.xlsx',document_search_views.export_xlsx,name='fiscal_export_xlsx'),
    path('nfse/',fiscal_views.nfse_list,name='nfse_list'),
    path('nfse/<int:pk>/',fiscal_views.document_detail,{'service':'nfse'},name='nfse_detail'),
    path('nfse/<int:pk>/xml/',fiscal_views.document_xml,{'service':'nfse'},name='nfse_xml'),
    path('nfse/<int:pk>/pdf/',fiscal_views.document_pdf,{'service':'nfse'},name='nfse_pdf'),
    path('cte/',fiscal_views.cte_list,name='cte_list'),
    path('cte/<int:pk>/',fiscal_views.document_detail,{'service':'cte'},name='cte_detail'),
    path('cte/<int:pk>/xml/',fiscal_views.document_xml,{'service':'cte'},name='cte_xml'),
    path('cte/<int:pk>/pdf/',fiscal_views.document_pdf,{'service':'cte'},name='cte_pdf'),
    path('documentos/pendentes/',pending_documents,name='pending_documents'),
    path('indicadores/',indicators,name='indicators'),
    path('conectores/documentos/<int:pk>/xml/',fiscal_views.envelope_xml,name='fiscal_envelope_xml'),
    path('documentos/<int:pk>/',fiscal_views.document_detail,name='fiscal_document'),
    path('documentos/<int:pk>/xml/',fiscal_views.document_xml,name='fiscal_xml'),
    path('documentos/<int:pk>/pdf/',fiscal_views.document_pdf,name='fiscal_pdf'),
    path('documentos/<int:pk>/dacte/',fiscal_views.document_pdf),
    path('empresas/<int:company_id>/conectores/',fiscal_views.connectors,name='fiscal_connectors'),
    path('',include('portal.capture_urls')),
    path('integracoes/',include('portal.integration_urls')),
    path('',include('portal.boleto_urls')),
    path('',views.dashboard,name='dashboard'),
    path('entrar/',views.PortalLoginView.as_view(),name='login'),
    path('criar-conta/',views.register,name='register'),
    path('sair/',LogoutView.as_view(),name='logout'),
    path('empresas/',views.companies,name='companies'),
    path('empresas/nova/',views.company_form,name='company_create'),
    path('empresas/<int:pk>/editar/',views.company_form,name='company_edit'),
    path('certificados/',views.certificates,name='certificates'),
    path('empresas/<int:pk>/certificado/',views.certificate_upload,name='certificate_upload'),
    path('empresas/<int:pk>/certificado/remover/',views.certificate_delete,name='certificate_delete'),
    path('notas/',views.invoices,name='invoices'),
    path('notas/importar/',views.import_xml,name='import_xml'),
    path('notas/<int:pk>/',views.invoice_detail,name='invoice_detail'),
    path('notas/<int:pk>/xml/',views.xml_download,name='xml_download'),
    path('notas/<int:pk>/danfe/',danfe_download,name='danfe_download'),
    path('notas/<int:invoice_pk>/parcelas/nova/',installment_review,name='installment_create'),
    path('notas/<int:invoice_pk>/parcelas/<int:pk>/revisar/',installment_review,name='installment_review'),
    path('agenda/',views.agenda,name='agenda'),
    path('parcelas/<int:pk>/conferir/',views.installment_check,name='installment_check'),
    path('perfil/',views.profile,name='profile'),
    path('perfil/senha/',views.ChangePassword.as_view(),name='password_change'),
    path('perfil/excluir/',account_delete,name='account_delete'),
    path('demonstracao/',views.demo,name='demo'),
    path('exemplo.xml',views.example_xml,name='example_xml'),
    path('exportar/',views.export_csv,name='export_csv'),
]
