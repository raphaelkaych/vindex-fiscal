from .pagination import paginate
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import BadRequest
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from portal.models import Company
from portal.boleto_models import Boleto
from portal.boleto_forms import BoletoDataForm, BoletoImportForm, BoletoAssociationForm
from portal.services.boletos import (import_boleto, associate_boleto, disassociate_boleto,
    update_boleto, BoletoImportError, BoletoAssociationError)
from portal.views import workspace_for


@login_required
def boletos(request):
    workspace=workspace_for(request)
    items=Boleto.objects.filter(company__workspace=workspace).select_related('company','installment__invoice').defer('private_pdf')
    selected=None
    if request.GET.get('company'):
        selected=get_object_or_404(Company,pk=request.GET['company'],workspace=workspace) if request.GET['company'].isdigit() else None
        if selected is None: raise BadRequest('Empresa inválida.')
        items=items.filter(company=selected)
    if request.GET.get('supplier'): items=items.filter(beneficiary_name__icontains=request.GET['supplier'][:200])
    if request.GET.get('source') in ('pdf','manual','api'): items=items.filter(source=request.GET['source'])
    if request.GET.get('review')=='pending': items=items.exclude(review_notes='')
    if request.GET.get('association')=='pending': items=items.filter(installment__isnull=True)
    for parameter,lookup in (('from','due_on__gte'),('to','due_on__lte')):
        if request.GET.get(parameter):
            try: value=date.fromisoformat(request.GET[parameter])
            except ValueError as exc: raise BadRequest('Data de filtro inválida.') from exc
            items=items.filter(**{lookup:value})
    query=request.GET.copy();query.pop('page',None)
    return render(request,'portal/boletos.html',{'page':paginate(request,items,20),
        'companies':workspace.companies.all(),'selected_company':selected,'query_string':query.urlencode()})


@login_required
def boleto_import(request):
    workspace=workspace_for(request)
    form=BoletoImportForm(request.POST or None,request.FILES or None,workspace=workspace)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);file=data.pop('file',None)
        try: boleto,created=import_boleto(workspace,data,payload=file.read() if file else None,actor=request.user)
        except BoletoImportError as exc: form.add_error(None,str(exc))
        else:
            messages.success(request,'Boleto importado para análise. Nenhuma parcela ou pagamento foi criado.' if created else 'Este boleto já estava cadastrado. Nenhuma duplicidade foi criada.')
            return redirect('boleto_detail',pk=boleto.pk)
    return render(request,'portal/boleto_import.html',{'form':form})


@login_required
def boleto_detail(request,pk):
    item=get_object_or_404(Boleto.objects.select_related('company','installment__invoice'),pk=pk,company__workspace=workspace_for(request))
    return render(request,'portal/boleto_detail.html',{'boleto':item,'events':item.events.all()[:30]})


@login_required
def boleto_review(request,pk):
    workspace=workspace_for(request)
    item=get_object_or_404(Boleto,pk=pk,company__workspace=workspace)
    initial={name:getattr(item,name) for name in BoletoDataForm.base_fields}
    form=BoletoDataForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        try: update_boleto(workspace,item,form.cleaned_data,actor=request.user)
        except BoletoImportError as exc: form.add_error(None,str(exc))
        else:
            messages.success(request,'Revisão registrada com origem e histórico. O pagamento permanece não consultado.')
            return redirect('boleto_detail',pk=item.pk)
    return render(request,'portal/boleto_review.html',{'form':form,'boleto':item})


@login_required
def boleto_associate(request,pk):
    workspace=workspace_for(request)
    item=get_object_or_404(Boleto,pk=pk,company__workspace=workspace)
    form=BoletoAssociationForm(request.POST or None,boleto=item)
    if request.method=='POST' and form.is_valid():
        try: associate_boleto(workspace,item,form.cleaned_data['installment'],actor=request.user,review_reason=form.cleaned_data['review_reason'])
        except BoletoAssociationError as exc: form.add_error(None,str(exc))
        else:
            messages.success(request,'Vínculo confirmado. A parcela existente foi preservada, sem gerar outra obrigação.')
            return redirect('boleto_detail',pk=item.pk)
    return render(request,'portal/boleto_associate.html',{'form':form,'boleto':item})


@login_required
@require_POST
def boleto_disassociate(request,pk):
    item=get_object_or_404(Boleto,pk=pk,company__workspace=workspace_for(request))
    disassociate_boleto(workspace_for(request),item,actor=request.user)
    messages.success(request,'Vínculo removido. A parcela e o documento foram preservados.')
    return redirect('boleto_detail',pk=item.pk)


@login_required
def boleto_download(request,pk):
    item=get_object_or_404(Boleto,pk=pk,company__workspace=workspace_for(request),private_pdf__isnull=False)
    response=HttpResponse(bytes(item.private_pdf),content_type='application/pdf')
    response['Content-Disposition']=f'attachment; filename="boleto-{item.pk}.pdf"'
    response['X-Content-Type-Options']='nosniff'
    response['Cache-Control']='private, no-store'
    response['Content-Security-Policy']='sandbox'
    return response
