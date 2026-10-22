from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand,CommandError
from django.core.validators import validate_email
from django.db import transaction
from portal.models import MasterAudit


class Command(BaseCommand):
    help='Cria ou concede acesso master explicitamente; senha oculta, sem argumento de senha.'
    @transaction.atomic
    def handle(self,*args,**options):
        email=input('E-mail/login do master: ').strip().lower()
        try:validate_email(email)
        except ValidationError:raise CommandError('E-mail inválido.') from None
        users=get_user_model().objects.filter(username__iexact=email)
        by_email=get_user_model().objects.filter(email__iexact=email)
        ids=set(users.values_list('pk',flat=True))|set(by_email.values_list('pk',flat=True))
        if len(ids)>1:raise CommandError('Há contas diferentes com esse login/e-mail. Resolva a duplicidade antes da concessão.')
        user=get_user_model().objects.get(pk=ids.pop()) if ids else get_user_model()(username=email,email=email)
        if user.pk and input('Conta existente. Digite CONCEDER para atribuir privilégios master, usar este e-mail como login e definir nova senha: ')!='CONCEDER':
            raise CommandError('Nenhuma alteração realizada.')
        user.username=email;user.email=email
        first=getpass('Nova senha (não aparece ao digitar): ');second=getpass('Repita a senha: ')
        if first!=second:raise CommandError('As senhas não conferem.')
        try:validate_password(first,user)
        except ValidationError as e:raise CommandError(' '.join(e.messages)) from None
        user.set_password(first);user.is_active=True;user.save()
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='portal',codename__in=['admin_master','operate_clients']))
        MasterAudit.objects.create(actor=user,action='master_granted',details='Comando local interativo; senha não registrada.')
        self.stdout.write(self.style.SUCCESS('Master configurado. Entre em /entrar/ e acesse /gestao/.'))
