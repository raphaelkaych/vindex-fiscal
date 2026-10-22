"""Revalidação local da participação; não altera agenda ou fila compartilhada."""
from portal.models import Company


def capture_block_reason(company):
    row=Company.objects.filter(pk=company.pk).values('deactivated_at','workspace__access_status','workspace__capture_paused','workspace__owner__is_active').first()
    if row is None or row['deactivated_at'] is not None:return 'Empresa desativada. Histórico preservado; reative o cadastro para consultar.'
    if row['workspace__access_status']!='active' or not row['workspace__owner__is_active']:return 'Conta desativada ou aguardando aprovação. Nenhuma consulta fiscal será iniciada por este vínculo.'
    if row['workspace__capture_paused']:return 'Captura pausada pela administração. Histórico e autorizações preservados.'
    return ''
