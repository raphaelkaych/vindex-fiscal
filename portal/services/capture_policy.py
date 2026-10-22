"""Intervalos de rede; o polling local não faz consultas durante a espera."""
from datetime import timedelta
from django.conf import settings


def idle_interval():
    # Nunca permitir configuração abaixo de uma hora mais margem de segurança.
    return timedelta(minutes=max(61,settings.FISCAL_IDLE_INTERVAL_MINUTES))


def page_interval():
    return timedelta(seconds=10)
