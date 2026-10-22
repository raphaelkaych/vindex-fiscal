from django.views.debug import SafeExceptionReporterFilter


class SecretRedactingFilter(SafeExceptionReporterFilter):
    """Defesa adicional: cabeçalho Bearer nunca entra no relatório de erro."""
    def get_safe_request_meta(self, request):
        result = super().get_safe_request_meta(request)
        if 'HTTP_AUTHORIZATION' in result:
            result['HTTP_AUTHORIZATION'] = self.cleansed_substitute
        return result

    def get_post_parameters(self, request):
        if request.path.startswith('/api/'):
            return {key: self.cleansed_substitute for key in request.POST}
        return super().get_post_parameters(request)

    def cleanse_setting(self, key, value):
        # Redis pode usar uma URL com senha em LOCATION; não depende do nome da chave.
        if key in {'CACHES','DATABASES'}:
            return self.cleansed_substitute
        return super().cleanse_setting(key,value)

    def get_traceback_frame_variables(self,request,tb_frame):
        # Relatórios de exceção em produção não devem transportar XMLs fiscais,
        # documentos ou objetos de identidade abertos nos serviços.
        module=tb_frame.f_globals.get('__name__','')
        if self.is_active(request) and module.startswith('portal.services.'):
            return [(name,self.cleansed_substitute) for name in tb_frame.f_locals]
        return super().get_traceback_frame_variables(request,tb_frame)
