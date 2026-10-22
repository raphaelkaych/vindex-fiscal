from datetime import timedelta
from django.test import SimpleTestCase,override_settings
from portal.services.capture_policy import idle_interval


class CapturePolicyTests(SimpleTestCase):
    def test_default_de_duas_horas(self):
        self.assertEqual(idle_interval(),timedelta(hours=2))

    @override_settings(FISCAL_IDLE_INTERVAL_MINUTES=180)
    def test_intervalo_maior_e_respeitado(self):
        self.assertEqual(idle_interval(),timedelta(hours=3))

    @override_settings(FISCAL_IDLE_INTERVAL_MINUTES=5)
    def test_configuracao_nao_pode_reduzir_minimo_com_margem(self):
        self.assertEqual(idle_interval(),timedelta(minutes=61))
