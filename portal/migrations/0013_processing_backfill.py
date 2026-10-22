from django.db import migrations


def populate(apps,schema_editor):
    Delivery=apps.get_model('portal','FiscalDelivery')
    Delivery.objects.filter(processing_status='pending',error='',document__validation_status='schema').update(processing_status='validated')
    Delivery.objects.filter(processing_status='pending',error='',document__isnull=True,envelope__kind='event').update(processing_status='event')
    Delivery.objects.filter(processing_status='pending',error='',envelope__kind='unknown').update(processing_status='unsupported',error='Padrão ainda sem importador. Original preservado para revisão.')


class Migration(migrations.Migration):
    dependencies=[('portal','0012_fiscal_processing_states')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]
