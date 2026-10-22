from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, render, redirect
from portal.models import Invoice, Installment
from portal.views import workspace_for
from portal.installment_forms import InstallmentReviewForm
from portal.services.installments import save_installment

@login_required
def installment_review(request, invoice_pk, pk=None):
    workspace=workspace_for(request)
    invoice=get_object_or_404(Invoice,pk=invoice_pk,company__workspace=workspace)
    item=get_object_or_404(Installment,pk=pk,invoice=invoice) if pk else None
    initial={key:getattr(item,key) for key in ('number','amount','due_on','review_note')} if item else {}
    form=InstallmentReviewForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        try: save_installment(workspace,invoice,form.cleaned_data,installment=item,actor=request.user.pk)
        except ValidationError as exc: form.add_error(None,'; '.join(exc.messages))
        else:
            messages.success(request,'Previsão registrada para conferência. Nenhum pagamento foi realizado ou confirmado.')
            return redirect('invoice_detail',pk=invoice.pk)
    return render(request,'portal/installment_form.html',{'invoice':invoice,'form':form,'item':item})
