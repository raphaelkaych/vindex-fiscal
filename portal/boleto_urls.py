from django.urls import path
from . import boleto_views as views

urlpatterns=[
    path('boletos/',views.boletos,name='boletos'),
    path('boletos/importar/',views.boleto_import,name='boleto_import'),
    path('boletos/<int:pk>/',views.boleto_detail,name='boleto_detail'),
    path('boletos/<int:pk>/revisar/',views.boleto_review,name='boleto_review'),
    path('boletos/<int:pk>/associar/',views.boleto_associate,name='boleto_associate'),
    path('boletos/<int:pk>/desassociar/',views.boleto_disassociate,name='boleto_disassociate'),
    path('boletos/<int:pk>/arquivo/',views.boleto_download,name='boleto_download'),
]
