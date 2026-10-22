from django.contrib.auth.decorators import login_required
from django.shortcuts import render,get_object_or_404
from django.views.decorators.cache import never_cache
from .models import FiscalDelivery,Company
from .views import workspace_for
from .pagination import paginate


@login_required
@never_cache
def pending_documents(request):
    workspace=workspace_for(request)
    rows=FiscalDelivery.objects.filter(connector__company__workspace=workspace).exclude(error='').select_related('connector__company','envelope','document').defer('envelope__xml_content','document__xml_content','document__official_pdf')
    if request.GET.get('company'):
        company=get_object_or_404(Company,workspace=workspace,pk=request.GET['company']) if request.GET['company'].isdecimal() else get_object_or_404(Company,pk=-1)
        rows=rows.filter(connector__company=company)
    return render(request,'portal/pending_documents.html',{'page':paginate(request,rows.order_by('-pk'))})
