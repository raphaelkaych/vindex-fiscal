"""Verificação de configuração, sem imprimir segredos nem consultar o fisco."""
import json
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from portal.services.capture_runtime import capture_runtime_status


class Command(BaseCommand):
    help='Lista bloqueios de configuração para implantação; não homologa infraestrutura externa.'
    def add_arguments(self,parser):
        parser.add_argument('--estrito',action='store_true')
        parser.add_argument('--json',action='store_true')
    def handle(self,*args,**options):
        hosts=settings.ALLOWED_HOSTS
        checks={
            'DEBUG desativado':not settings.DEBUG,
            'Domínio explícito, sem curingas ou exemplos':bool(hosts) and '*' not in hosts and any('.' in h and h not in {'127.0.0.1','localhost','[::1]'} and not any(x in h for x in ['example','seu-dominio','testserver']) for h in hosts),
            'PostgreSQL configurado':settings.DATABASES['default']['ENGINE'].endswith('postgresql'),
            'Cache compartilhado Redis configurado':'redis' in settings.CACHES['default']['BACKEND'].lower(),
            'HTTPS e cookies seguros':settings.SECURE_SSL_REDIRECT and settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
            'Origens CSRF HTTPS explícitas':bool(settings.CSRF_TRUSTED_ORIGINS) and all(s.startswith('https://') and '*' not in s for s in settings.CSRF_TRUSTED_ORIGINS),
            'SMTP e remetente configurados':bool(settings.EMAIL_HOST and settings.DEFAULT_FROM_EMAIL and settings.EMAIL_HOST_USER),
            'Cadastro sujeito a aprovação ou fechado':settings.REGISTRATION_MODE in {'approval','closed'},
            'Processo de captura com sinal recente':capture_runtime_status()['active'],
        }
        result={'configuration_complete':all(checks.values()),'checks':checks,'external_validation_required':['DNS/HTTPS público e proxy','Conexão PostgreSQL/Redis/SMTP','Backup privado, restauração e preservação da chave dos A1','Reinício supervisionado e monitoramento','Teste de carga e segunda empresa real com nova emissão']}
        if options['json']:self.stdout.write(json.dumps(result,ensure_ascii=False,indent=2))
        else:
            for name,passed in checks.items():self.stdout.write(('OK: ' if passed else 'PENDENTE: ')+name)
            self.stdout.write('Configuração não equivale a homologação. Valide infraestrutura, recuperação e operação real antes da publicação ampla.')
        if options['estrito'] and not result['configuration_complete']:raise CommandError('Configuração de produção incompleta. Nenhum segredo foi exibido e nenhuma consulta fiscal foi disparada.')
