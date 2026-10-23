from django.core.management.base import BaseCommand
from portal.models import Invoice,FiscalDocument
from portal.services.fiscal_search import index_document


class Command(BaseCommand):
    help='Preenche índice reconstruível dos XMLs locais. Não consulta serviços fiscais.'
    def add_arguments(self,parser):
        parser.add_argument('--reconstruir',action='store_true')
    def handle(self,*args,**options):
        count=0
        for model in (Invoice,FiscalDocument):
            qs=model.objects.select_related('company').order_by('pk')
            if model is Invoice:qs=qs.filter(is_demo=False)
            if not options['reconstruir']:qs=qs.filter(search_record__isnull=True)
            # Paginação por PK mantém transações curtas, sem cursor de leitura longo.
            last=0
            while True:
                batch=list(qs.filter(pk__gt=last)[:100])
                if not batch:break
                for doc in batch:index_document(doc);count+=1
                last=batch[-1].pk
        self.stdout.write(f'{count} documento(s) indexado(s), sem modificar XMLs ou NSUs.')
