from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from portal.models import Workspace
from portal.services.account_deletion import delete_account
from portal.services.master_lifecycle import references


class Command(BaseCommand):
    help = 'Exclui conta de cliente mediante solicitação explícita, confirmação do nome e executor master com permissão operacional.'

    def add_arguments(self, parser):
        parser.add_argument('--workspace', type=int, required=True)
        parser.add_argument('--executor-email', required=True)
        parser.add_argument('--confirmar-nome', required=True)
        parser.add_argument('--executar', action='store_true')

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username__iexact=options['executor_email'], is_active=True).first()
        if not actor or not actor.has_perm('portal.admin_master') or not actor.has_perm('portal.operate_clients'):
            raise CommandError('Executor precisa de admin_master e operate_clients ativos.')
        workspace = Workspace.objects.filter(pk=options['workspace']).first()
        if workspace is None or workspace.name != options['confirmar_nome']:
            raise CommandError('Cliente ausente ou nome de confirmação divergente.')
        if not options['executar']:
            for row in references(workspace):
                self.stdout.write(f'{row["model"]}: {row["count"]}')
            self.stdout.write('Somente diagnóstico. --executar remove login, empresas, A1 e arquivos privados; preserva filas, consultas oficiais, eventos fiscais e auditoria. Exige solicitação explícita do titular.')
            return
        try:
            delete_account(actor=actor,workspace_id=workspace.pk,confirmation=options['confirmar_nome'])
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from None
        self.stdout.write('Conta e arquivos privados excluídos. Outros clientes, filas, consultas oficiais, eventos fiscais e auditoria foram preservados.')
