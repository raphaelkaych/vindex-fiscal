from datetime import date

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.renderers import JSONRenderer

from portal.api.authentication import IntegrationAuthentication
from portal.api.errors import api_exception_handler
from portal.api.pagination import IntegrationPagination
from portal.api.permissions import IntegrationScopePermission
from portal.api.throttling import IntegrationThrottle, IntegrationWriteThrottle
from portal.validators import validate_cnpj


class IntegrationViewSet(viewsets.GenericViewSet):
    authentication_classes = [IntegrationAuthentication]
    permission_classes = [IntegrationScopePermission]
    throttle_classes = [IntegrationThrottle, IntegrationWriteThrottle]
    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = IntegrationPagination
    filter_backends = []
    filter_fields = ()
    ordering_fields = ()
    default_ordering = ('pk',)
    company_lookup = 'company'
    date_field = None

    def dispatch(self, request, *args, **kwargs):
        request.sensitive_post_parameters = '__ALL__'
        return super().dispatch(request, *args, **kwargs)

    def get_exception_handler(self):
        return api_exception_handler

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store, private'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    def companies(self):
        if getattr(self, 'swagger_fake_view', False):
            from portal.models import Company
            return Company.objects.none()
        from portal.services.operational import operational_companies
        return self.request.auth.allowed_companies.filter(pk__in=operational_companies().values('pk'))

    def filtered(self, qs):
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        params = self.request.query_params
        allowed = {'company', 'cnpj', 'ordering', 'page', 'page_size', 'format', *self.filter_fields}
        if self.date_field:
            allowed.update(('from', 'to'))
        extras = set(params) - allowed
        if extras:
            raise serializers.ValidationError({key: 'Filtro não permitido.' for key in sorted(extras)})
        if params.get('company'):
            if not params['company'].isdecimal():
                raise serializers.ValidationError({'company': 'Informe o ID numérico da empresa.'})
            company = get_object_or_404(self.companies(), pk=params['company'])
            qs = qs.filter(**{f'{self.company_lookup}_id' if self.company_lookup else 'pk': company.pk})
        if params.get('cnpj'):
            cnpj = validate_cnpj(params['cnpj'])
            company = get_object_or_404(self.companies(), cnpj=cnpj)
            qs = qs.filter(**{f'{self.company_lookup}__cnpj' if self.company_lookup else 'cnpj': company.cnpj})
        dates = {}
        if self.date_field:
            for param, lookup in [('from', 'gte'), ('to', 'lte')]:
                if params.get(param):
                    try:
                        dates[param] = date.fromisoformat(params[param])
                    except ValueError:
                        raise serializers.ValidationError({param: 'Use uma data válida no formato AAAA-MM-DD.'}) from None
                    qs = qs.filter(**{f'{self.date_field}__{lookup}': dates[param]})
            if dates.get('from') and dates.get('to') and dates['from'] > dates['to']:
                raise serializers.ValidationError({'to': 'O fim do período deve ser igual ou posterior ao início.'})
        ordering = params.get('ordering', '')
        if ordering:
            fields = ordering.split(',')
            if len(fields)>10 or any((field[1:] if field.startswith('-') else field) not in self.ordering_fields for field in fields):
                raise serializers.ValidationError({'ordering': 'Ordenação não permitida.'})
            qs = qs.order_by(*fields, 'pk')
        else:
            qs = qs.order_by(*self.default_ordering)
        return qs

    def enum_filter(self, value, choices, name):
        if value and value not in choices:
            raise serializers.ValidationError({name: 'Use uma das opções: ' + ', '.join(choices) + '.'})
        return value
