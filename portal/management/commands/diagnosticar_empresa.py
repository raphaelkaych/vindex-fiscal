from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from portal.models import Company,DigitalCertificate
from portal.services.sefaz_transport import load_identity
from portal.services.sefaz import SefazError


class Command(BaseCommand):
    help='Diagnóstico local, sem consultas fiscais nem cadastro artificial.'
    def add_arguments(self,parser):
        parser.add_argument('--empresa',type=int,required=True)
    def handle(self,*args,**options):
        company=Company.objects.filter(pk=options['empresa']).first()
        if not company:raise CommandError('Empresa não cadastrada.')
        try:load_identity(company)
        except SefazError as e:raise CommandError(str(e)) from None
        self.stdout.write('A1 acessível, vigente e com raiz de CNPJ compatível. Isso não comprova aceitação remota.')
        config=getattr(company,'capture_config',None)
        self.stdout.write('NF-e: '+('leitura habilitada' if config and config.enabled and config.read_authorized_at else 'autorização/habilitação pendente'))
        for config in company.fiscal_connectors.all():
            self.stdout.write(f'{config.service}, ambiente {config.environment}: '+('leitura habilitada' if config.enabled and config.authorized_at else 'desativado'))
        self.stdout.write('Confira os conectores na empresa. CT-e exige UF. Nenhuma consulta foi executada pelo diagnóstico.')
