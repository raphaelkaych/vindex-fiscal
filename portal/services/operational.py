"""Oculta empresas comprovadamente usadas só por demonstrações; não apaga dados."""
from django.db.models import Exists,OuterRef,Q
from portal.models import Company,Invoice,DigitalCertificate,FiscalDocument,SefazCaptureConfig


def operational_companies(workspace=None):
    qs=Company.objects.all()
    if workspace:qs=qs.filter(workspace=workspace)
    qs=qs.annotate(_demo_note=Exists(Invoice.objects.filter(company_id=OuterRef('pk'),is_demo=True)),
        _real_note=Exists(Invoice.objects.filter(company_id=OuterRef('pk'),is_demo=False)),
        _demo_cert=Exists(DigitalCertificate.objects.filter(company_id=OuterRef('pk'),is_demo=True)),
        _real_cert=Exists(DigitalCertificate.objects.filter(company_id=OuterRef('pk'),is_demo=False)),
        _other_doc=Exists(FiscalDocument.objects.filter(company_id=OuterRef('pk'))),
        _capture=Exists(SefazCaptureConfig.objects.filter(company_id=OuterRef('pk'),read_authorized_at__isnull=False)))
    return qs.exclude((Q(_demo_note=True)|Q(_demo_cert=True))&Q(_real_note=False,_real_cert=False,_other_doc=False,_capture=False))
