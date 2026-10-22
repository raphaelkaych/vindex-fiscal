"""Previsões informadas por pessoa autorizada. Nenhuma operação bancária."""
from datetime import date
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from portal.models import Invoice, Installment, AuditEntry, InstallmentRevision


@transaction.atomic
def save_installment(workspace, invoice, data, installment=None, allowed_companies=None, actor=None, source='manual'):
    allowed=Invoice.objects.filter(pk=invoice.pk,company__workspace=workspace)
    if allowed_companies is not None: allowed=allowed.filter(company_id__in=allowed_companies)
    invoice=allowed.select_for_update().first()
    if invoice is None: raise ValidationError('Documento não disponível para este acesso.')
    if set(data)-{'number','amount','due_on','review_note'}: raise ValidationError('Existem campos de previsão não permitidos.')
    if installment is not None:
        installment=Installment.objects.select_for_update().filter(pk=installment.pk,invoice=invoice).first()
        if installment is None: raise ValidationError('Parcela não disponível neste documento.')
    number=str(data.get('number', installment.number if installment else '')).strip()
    note=str(data.get('review_note','')).strip()
    if not number or len(number)>60: raise ValidationError({'number':'Informe o identificador da parcela, até 60 caracteres.'})
    if not note or len(note)>2000: raise ValidationError({'review_note':'Descreva a origem ou o motivo da revisão, até 2.000 caracteres.'})
    try:
        amount=Decimal(str(data.get('amount',installment.amount if installment else '')))
        if not amount.is_finite() or amount<=0 or amount>=Decimal('10000000000000000') or amount!=amount.quantize(Decimal('.01')): raise ValueError
    except (ValueError,InvalidOperation): raise ValidationError({'amount':'Informe um valor positivo com até duas casas decimais.'}) from None
    due=data.get('due_on',installment.due_on if installment else None)
    if due in ('',None): due=None
    elif not isinstance(due,date):
        try: due=date.fromisoformat(str(due))
        except ValueError: raise ValidationError({'due_on':'Informe uma data válida no formato AAAA-MM-DD.'}) from None
    before=None
    if installment:
        if (amount!=installment.amount or due!=installment.due_on or number!=installment.number) and hasattr(installment,'boleto'):
            raise ValidationError('Desvincule o boleto antes de alterar valor, vencimento ou identificação da parcela e confira a associação novamente.')
        before={'number':installment.number,'amount':str(installment.amount),'due_on':installment.due_on.isoformat() if installment.due_on else None}
    if installment is None: installment=Installment(invoice=invoice)
    installment.number=number
    installment.amount=amount
    installment.due_on=due
    installment.review_note=note
    installment.source='manual'
    installment.checked=False
    try:
        with transaction.atomic(): installment.save()
    except IntegrityError: raise ValidationError({'number':'Já existe uma parcela com este identificador na nota.'}) from None
    InstallmentRevision.objects.create(installment=installment,before=before or {},
        after={'number':number,'amount':str(amount),'due_on':due.isoformat() if due else None},reason=note,actor=str(actor or '')[:100])
    actor_text=f' por {actor}' if actor else ''
    AuditEntry.objects.create(workspace=workspace,description=(f'Previsão {installment.pk} {"revisada" if before else "informada"}{actor_text}; NF-e {invoice.number}. Origem manual. '+(f'Antes: {before}. ' if before else '')+f'Depois: {number}, {amount}, {due}. Motivo: {note}')[:250])
    return installment


@transaction.atomic
def review_installment(workspace,installment,checked,actor=None,allowed_companies=None):
    qs=Installment.objects.select_for_update().filter(pk=installment.pk,invoice__company__workspace=workspace)
    if allowed_companies is not None: qs=qs.filter(invoice__company_id__in=allowed_companies)
    item=qs.first()
    if item is None: raise ValidationError('Parcela não disponível para este acesso.')
    if not isinstance(checked,bool): raise ValidationError('O estado de conferência deve ser verdadeiro ou falso.')
    item.checked=checked
    item.save(update_fields=['checked','updated_at'])
    AuditEntry.objects.create(workspace=workspace,description=f'Conferência da previsão {item.pk}: {"conferida" if checked else "a conferir"}. Nenhum pagamento confirmado. Responsável: {actor or "usuário"}.'[:250])
    return item
