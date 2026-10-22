from rest_framework.throttling import SimpleRateThrottle


class IntegrationThrottle(SimpleRateThrottle):
    scope = 'integration'
    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope, '120/min')
    def get_cache_key(self, request, view):
        identity = f'credential-{request.auth.pk}' if request.auth else self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': identity}


class IntegrationWriteThrottle(IntegrationThrottle):
    scope = 'integration_burst'
    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope, '20/min')
    def allow_request(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return super().allow_request(request, view)
