from django.contrib import admin
from django.urls import include, path
from portal import master_views,master_management
master_urls=[path('',master_views.management,name='master_home'),path('clientes/<int:workspace_id>/',master_views.supervise,name='master_client'),path('clientes/<int:workspace_id>/acao/',master_views.client_action,name='master_action'),path('clientes/<int:workspace_id>/notas/<int:pk>/xml/',master_views.supervised_xml,name='master_xml')]
master_urls += [path('clientes/<int:workspace_id>/gerenciar/',master_management.account_manage,name='master_account_manage'),path('clientes/<int:workspace_id>/empresas/<int:company_id>/gerenciar/',master_management.company_manage,name='master_company_manage')]
urlpatterns=[path('gestao/',include(master_urls))]
master_urls.append(path('clientes/<int:workspace_id>/documentos/<int:pk>/xml/',master_views.supervised_fiscal,name='master_fiscal_xml'))
master_urls.append(path('clientes/<int:workspace_id>/documentos/<str:kind>/<int:pk>/',master_views.supervised_document,name='master_document'))
# A supervisão por URL é atendida pelo middleware antes da resolução normal.
# Este nome também mantém os links compatíveis com o reverse do Django.
master_urls.append(path('clientes/<int:workspace_id>/painel/',master_views.supervise,name='master_panel'))
urlpatterns += [path('gestao-interna/',admin.site.urls),path('api/v1/',include('portal.api.urls')),path('',include('portal.urls'))]
