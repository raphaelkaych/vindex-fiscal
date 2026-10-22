from django.urls import path
from portal import integration_views as views

urlpatterns = [
    path('', views.integration_list, name='integration_list'),
    path('nova/', views.integration_create, name='integration_create'),
    path('<int:pk>/revogar/', views.integration_revoke, name='integration_revoke'),
]
