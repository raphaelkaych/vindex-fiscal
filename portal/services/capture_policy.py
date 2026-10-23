"""Intervalos de rede; o polling local não faz consultas durante a espera."""
from datetime import timedelta
from django.conf import settings


def idle_interval():
    # Nunca permitir configuração abaixo de uma hora mais margem de segurança.
    return timedelta(minutes=max(61,settings.FISCAL_IDLE_INTERVAL_MINUTES))


def page_interval():
    return timedelta(seconds=10)


def consumption_interval(failure_count):
    # Rejeição persistente não deve provocar novas tentativas a cada hora.
    # Nunca reduz a política configurada nem representa prazo oficial adicional.
    factor = 2 ** min(max(0, (failure_count - 1) // 3), 4)
    return max(idle_interval(), min(idle_interval() * factor, timedelta(hours=24)))
