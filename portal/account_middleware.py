from django.http import HttpResponseForbidden


class AccountStatusMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if request.user.is_authenticated and not request.path.startswith(('/api/','/gestao/','/sair/','/perfil/senha/','/perfil/excluir/')):
            workspace=getattr(request.user,'workspace',None)
            if workspace and workspace.access_status!='active' and not request.user.has_perm('portal.admin_master'):
                return HttpResponseForbidden('Acesso aguardando aprovação ou suspenso. Contate a administração Vindex. Seus documentos estão preservados.')
        return self.get_response(request)
