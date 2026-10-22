def add_error_responses(result, generator, request, public):
    """Documenta o envelope real em todas as operações, sem incluir dados dos clientes."""
    error = {'description': 'Erro padronizado. Consulte código, mensagem e detalhes.', 'content': {'application/json': {'schema': {
        'type': 'object', 'required': ['error'], 'properties': {'error': {'type': 'object', 'required': ['code', 'message', 'details'],
            'properties': {'code': {'type': 'string'}, 'message': {'type': 'string'}, 'details': {}}}}}}}}
    for path in result.get('paths', {}).values():
        for method, operation in path.items():
            if method not in ('get', 'post', 'put', 'patch', 'delete', 'head', 'options'):
                continue
            for status in ('400', '401', '403', '404', '405', '409', '413', '415', '429', '500'):
                operation.setdefault('responses', {}).setdefault(status, error)
    return result
