from django.urls import path
from . import capture_views as views

urlpatterns = [
    path('captura/', views.capture_list, name='capture_list'),
    path('empresas/<int:pk>/captura/', views.capture_detail, name='capture_detail'),
    path('empresas/<int:pk>/captura/pausar/', views.capture_disable, name='capture_disable'),
    path('captura/documentos/<int:pk>/', views.capture_document, name='capture_document'),
    path('captura/documentos/<int:pk>/xml/', views.capture_document_download, name='capture_document_download'),
    path('captura/documentos/<int:pk>/ciencia/', views.capture_science, name='capture_science'),
]
