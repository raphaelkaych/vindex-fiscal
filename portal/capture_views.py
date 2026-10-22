from .pagination import paginate
"""Painel privado da captura. Os POSTs de configuração apenas agendam leitura."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count,Max,Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .capture_forms import CaptureEnableForm, ScienceAuthorizationForm
from .models import Company
from .sefaz_models import SefazCaptureConfig, SefazDistributionStream, SefazDocument, SefazSyncState
from .services.capture import configure_capture
from .services.capture_runtime import capture_runtime_status
from .services.sefaz import SefazError
from .views import workspace_for


def _state(company, config):
    return SefazSyncState.objects.filter(company=company, source='sefaz',
        environment=config.environment if config else '1').first()


def _shared_metadata(company,config):
    """Só metadados da fila comum; nenhuma caixa/histórico de outro Workspace."""
    certificate=getattr(company,'certificate',None)
    now=timezone.now()
    if not (company.is_active and company.workspace.access_status=='active' and config and config.read_authorized_at and certificate and not certificate.is_demo
            and certificate.valid_from<=now<certificate.valid_until
            and certificate.holder_cnpj[:8]==company.cnpj[:8]):return {}
    return SefazDistributionStream.objects.filter(cnpj=company.cnpj,environment=config.environment,
        source='sefaz').values('last_attempt_at','lease_until','next_attempt_at','last_status',
            'last_reason','last_response_at','official_response_at','reported_nsu').first() or {}


def _activity(company,config,state):
    """Observação de leitura. Não corrige banco, cursor, espera ou agendamento."""
    shared=_shared_metadata(company,config)
    attempts=state.consultations.all() if state else None
    summary=attempts.aggregate(attempt=Max('requested_at'),success=Max('completed_at',filter=Q(status__in=['137','138']))) if state else {}
    last_attempt=max((d for d in [getattr(state,'last_attempt_at',None),shared.get('last_attempt_at'),summary.get('attempt')] if d),default=None)
    last_success=summary.get('success') or getattr(state,'last_real_success_at',None)
    latest_error=attempts.filter(Q(status__gt='')|Q(error__gt='')).exclude(status__in=['137','138']).order_by('-requested_at').values('requested_at','status','reason','error').first() if state else None
    status=getattr(state,'last_status','')
    response_at=getattr(state,'last_response_at',None)
    if shared.get('last_response_at') and (not response_at or shared['last_response_at']>=response_at):
        status=shared['last_status'];response_at=shared['last_response_at']
    official_error=bool(status and status not in {'137','138'} and response_at)
    local_error=getattr(state,'last_error','')
    config_error=getattr(config,'last_error','')
    stale_config=bool(config_error and ((getattr(config,'last_error_code','').startswith('sefaz_') and not official_error and status in {'137','138'})
        or (last_success and config.last_checked_at and last_success>config.last_checked_at and not local_error)))
    history=latest_error if latest_error and last_success and latest_error['requested_at']<last_success else None
    imported=state.documents.filter(invoice__isnull=False).aggregate(at=Max('invoice__imported_at'))['at'] if state else None
    return {'shared':shared,'last_attempt':last_attempt,'last_success':last_success,'last_import':imported,
        'official_error':official_error,'local_error':local_error,'config_error':'' if stale_config else config_error,
        'historical_error':history,'historical_config_error':config_error if stale_config else '',
        'last_status':status,'waiting':bool((shared.get('next_attempt_at') or getattr(state,'next_attempt_at',None)) and (shared.get('next_attempt_at') or state.next_attempt_at)>timezone.now())}


def _status(company, config, state, runtime=None,activity=None):
    if not company.is_active:return 'Empresa desativada', 'neutral'
    if company.workspace.access_status!='active':return 'Captura bloqueada pela conta', 'warning'
    if company.workspace.capture_paused:return 'Captura pausada pela administração', 'warning'
    """O rótulo descreve o estado local; sucesso exige resposta oficial armazenada."""
    if not config or not config.enabled:
        return 'Pausada' if config and config.read_authorized_at else 'Depende de autorização', 'neutral'
    if not config.read_authorized_at:
        return 'Depende de autorização', 'warning'
    # O lease pertence ao consumidor compartilhado CNPJ/ambiente. Ler somente
    # esta metainformação nunca dá acesso à caixa de documentos de outro cliente.
    now = timezone.now()
    certificate = getattr(company, 'certificate', None)
    can_show_shared_activity = (certificate and not certificate.is_demo and
        certificate.valid_from <= now < certificate.valid_until and
        certificate.holder_cnpj[:8] == company.cnpj[:8])
    shared=activity['shared'] if activity is not None else _shared_metadata(company,config)
    lease=shared.get('lease_until') if can_show_shared_activity else None
    if lease and lease > now:
        return 'Consultando a SEFAZ', 'neutral'
    if activity is not None and activity['official_error'] and activity['waiting'] and not activity['local_error'] and (not activity['config_error'] or config.last_error_code.startswith('sefaz_')):
        return 'Aguardando intervalo · SEFAZ '+activity['last_status'], 'warning'
    has_error=(activity['config_error'] or activity['local_error'] or activity['official_error']) if activity is not None else (config.last_error or (state and state.last_error))
    if has_error:
        return 'Requer atenção', 'danger'
    if not hasattr(company, 'certificate'):
        return 'Certificado necessário', 'warning'
    if company.certificate.state == 'expired':
        return 'Certificado vencido', 'danger'
    runtime = runtime if runtime is not None else capture_runtime_status()
    if not runtime['active']:
        return 'Processo de captura parado', 'warning'
    if state and state.next_attempt_at and state.next_attempt_at > now:
        return 'Aguardando próxima consulta', 'neutral'
    return 'Ativa · consulta agendada', 'success'


@login_required
@never_cache
def capture_list(request):
    from .services.operational import operational_companies
    companies = operational_companies(workspace_for(request)).select_related('workspace','certificate', 'capture_config').defer('certificate__encrypted_file','certificate__encrypted_password')
    rows = []
    runtime = capture_runtime_status()
    for company in companies:
        config = getattr(company, 'capture_config', None)
        state = _state(company, config)
        status, tone = _status(company, config, state, runtime)
        rows.append({'company': company, 'config': config, 'state': state, 'status': status, 'tone': tone})
    return render(request, 'portal/capture_list.html', {'rows': rows, 'capture_runtime': runtime})


@login_required
@never_cache
def capture_detail(request, pk):
    workspace = workspace_for(request)
    company = get_object_or_404(Company.objects.select_related('workspace','certificate').defer('certificate__encrypted_file','certificate__encrypted_password'), pk=pk, workspace=workspace)
    config = SefazCaptureConfig.objects.filter(company=company).first()
    form = CaptureEnableForm(request.POST or None, initial={'uf_author': config.uf_author if config else ''})
    if request.method == 'POST' and form.is_valid():
        try:
            configured = configure_capture(workspace, company.pk, enabled=True, environment='1', actor=request.user,
                authorize_read=form.cleaned_data['authorize_read'], uf_author=form.cleaned_data['uf_author'])
        except (SefazError, ValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            if configured.last_error:
                messages.warning(request, 'Autorização de leitura salva. Resolva o impedimento indicado abaixo para iniciar a captura.')
            else:
                messages.success(request, 'Captura habilitada e agendada. O resultado oficial aparecerá aqui após a execução, respeitando o intervalo da SEFAZ.')
            return redirect('capture_detail', pk=company.pk)
    state = _state(company, config)
    documents = SefazDocument.objects.filter(state=state).defer('xml_content') if state else SefazDocument.objects.none()
    counts = {item['kind']: item['count'] for item in documents.values('kind').annotate(count=Count('pk'))}
    runtime = capture_runtime_status()
    activity=_activity(company,config,state)
    status, tone = _status(company, config, state, runtime,activity)
    return render(request, 'portal/capture_detail.html', {'company': company, 'config': config, 'state': state,
        'form': form, 'status': status, 'tone': tone, 'counts': counts, 'capture_runtime': runtime,'activity':activity,
        'imported_count': documents.filter(invoice__isnull=False).values('invoice').distinct().count(),
        'consultations': state.consultations.defer('response_xml')[:20] if state else [],
        'page': paginate(request,documents.order_by('-received_at', '-pk'),20)})


@login_required
@require_POST
@never_cache
def capture_disable(request, pk):
    workspace = workspace_for(request)
    company = get_object_or_404(Company, pk=pk, workspace=workspace)
    try:
        config = SefazCaptureConfig.objects.filter(company=company).first()
        configure_capture(workspace, company.pk, enabled=False, actor=request.user,
            environment=config.environment if config else '1', uf_author=config.uf_author if config else '')
    except (SefazError, ValidationError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, 'Captura pausada. O progresso, os documentos e o histórico foram preservados.')
    return redirect('capture_detail', pk=company.pk)


def _document_for(request, pk):
    return get_object_or_404(SefazDocument.objects.select_related('state__company', 'invoice'),
        pk=pk, state__company__workspace=workspace_for(request), state__source='sefaz')


@login_required
@never_cache
def capture_document(request, pk):
    document = _document_for(request, pk)
    return render(request, 'portal/capture_document.html', {'document': document,
        'company': document.state.company, 'science_form': ScienceAuthorizationForm(),
        'science_requested': document.science_requests.exists()})


@login_required
@never_cache
def capture_document_download(request, pk):
    document = _document_for(request, pk)
    response = HttpResponse(document.xml_content, content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="sefaz-{document.pk}-{document.kind}.xml"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_POST
@never_cache
def capture_science(request, pk):
    document = _document_for(request, pk)
    if document.kind != 'summary' or document.state.environment != '1':
        messages.error(request, 'A Ciência da Emissão desta tela exige um resumo de NF-e de produção.')
        return redirect('capture_document', pk=document.pk)
    form = ScienceAuthorizationForm(request.POST)
    if form.is_valid():
        from .services.sefaz_manifest import send_science
        try:
            result = send_science(workspace_for(request), document.state.company_id, document.pk,
                actor=request.user, authorized=True)
        except (SefazError, ValidationError) as exc:
            form.add_error(None, str(exc))
        else:
            if result.status == 'accepted':
                messages.success(request, 'Ciência da Emissão registrada pela SEFAZ. A captura periódica aguardará os documentos disponibilizados, respeitando o intervalo de consulta.')
            else:
                messages.warning(request, 'Envio registrado. Consulte o código e o motivo oficial abaixo. O sistema não reenviará o evento automaticamente.')
            return redirect('capture_document', pk=document.pk)
    return render(request, 'portal/capture_document.html', {'document': document,
        'company': document.state.company, 'science_form': form,
        'science_requested': document.science_requests.exists()})
