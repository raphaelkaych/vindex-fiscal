import logging


class PrivateErrorFilter(logging.Filter):
    """Registra ocorrência/tipo sem copiar XML, POST, headers ou traceback fiscal."""
    def filter(self,record):
        if record.exc_info:
            kind=record.exc_info[0].__name__ if record.exc_info[0] else 'Erro'
            record.msg='Falha no servidor (%s). Confira o estado e a auditoria privada.'
            record.args=(kind,);record.exc_info=None;record.exc_text=None;record.stack_info=None
        return True
