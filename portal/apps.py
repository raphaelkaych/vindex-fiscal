from django.apps import AppConfig
class PortalConfig(AppConfig):
    default_auto_field='django.db.models.BigAutoField'
    name='portal'
    verbose_name='Vindex Fiscal'
    def ready(self):
        from .services.fiscal_search import register_signals
        register_signals()
