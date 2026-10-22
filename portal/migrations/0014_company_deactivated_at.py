from django.db import migrations,models


class Migration(migrations.Migration):
    dependencies=[('portal','0013_processing_backfill')]
    operations=[migrations.AddField(model_name='company',name='deactivated_at',field=models.DateTimeField(blank=True,editable=False,null=True))]
