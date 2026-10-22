from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView


@extend_schema(exclude=True)
class ApiNotFoundView(APIView):
    authentication_classes = []
    permission_classes = []
    renderer_classes = [JSONRenderer]
    def not_found(self, request, *args, **kwargs):
        response = Response({'error': {'code': 'not_found', 'message': 'Endpoint não encontrado.', 'details': {}}}, status=404)
        response['Cache-Control'] = 'no-store, private'
        return response
    get = post = put = patch = delete = head = options = not_found
