def app_context(request):
    if not request.user.is_authenticated: return {}
    supervised=getattr(request,'supervised_workspace',None)
    workspace=supervised or getattr(request.user,'workspace',None)
    name=request.user.first_name or request.user.username.split('@')[0]
    from django.conf import settings
    return {'current_workspace':workspace,'supervision_workspace':supervised,'master_area':request.path_info.startswith('/gestao/') and not supervised,'user_display_name':name,'user_initial':name[:1].upper(),'visual_preview':getattr(settings,'VINDEX_VISUAL_PREVIEW',False)}
