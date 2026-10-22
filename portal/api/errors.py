from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import RequestDataTooBig, TooManyFilesSent
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    if isinstance(exc,(RequestDataTooBig,TooManyFilesSent)):
        return Response({'error':{'code':'too_large','message':'A requisição excede o tamanho ou a quantidade de arquivos permitidos.','details':{}}},status=413)
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(getattr(exc, 'message_dict', None) or exc.messages)
    if isinstance(exc, IntegrityError):
        return Response({'error': {'code': 'conflict', 'message': 'Já existe um registro com estes identificadores.', 'details': {}}}, status=409)
    response = exception_handler(exc, context)
    if response is None:
        # Não propagar payload XML/PDF/JSON ou variáveis locais a uma página DEBUG.
        return Response({'error': {'code': 'internal_error', 'message': 'Não foi possível concluir a operação.', 'details': {}}}, status=500)
    data = response.data
    detail = data.get('detail') if isinstance(data, dict) else None
    codes = {400: 'validation_error', 401: 'authentication_failed', 403: 'permission_denied', 404: 'not_found', 405: 'method_not_allowed', 413: 'too_large', 415: 'unsupported_media_type', 429: 'throttled'}
    response.data = {'error': {'code': codes.get(response.status_code, 'request_error'),
                               'message': str(detail) if detail else 'Confira os dados enviados.',
                               'details': {} if detail else data}}
    return response
