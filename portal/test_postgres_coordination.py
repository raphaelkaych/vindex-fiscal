"""Ensaios reais de transações em PostgreSQL descartável; sem transporte fiscal.

SQLite não comprova FOR UPDATE/concorrência PostgreSQL. A classe é ignorada
explicitamente até a homologação dispor desse backend.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection,connections
from django.test import TransactionTestCase
from portal.models import SefazDistributionStream,FiscalStream
from portal.services.capture import _claim,_store_response
from portal.services.sefaz import SefazBusy,parse_distribution
from portal.test_sefaz import response


@skipUnless(connection.vendor=='postgresql','Exige PostgreSQL real de homologação; SQLite não valida esse comportamento.')
class PostgreSQLCoordinationTests(TransactionTestCase):
    def setUp(self):
        self.stream=SefazDistributionStream.objects.create(cnpj='00000003000125',environment='2',source='test',last_nsu='000000000000001')

    def test_independent_connections_cannot_claim_same_identity_concurrently(self):
        barrier=Barrier(2)
        def claim():
            try:
                stream=SefazDistributionStream.objects.get(pk=self.stream.pk)
                barrier.wait(timeout=10)
                try:_claim(stream);return 'claimed'
                except SefazBusy:return 'busy'
            finally:connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
        self.assertCountEqual(results,['claimed','busy'])

    def test_new_connection_resumes_committed_cursor_not_old_python_snapshot(self):
        stale=SefazDistributionStream.objects.get(pk=self.stream.pk)
        token=_claim(self.stream)
        _store_response(self.stream,token,parse_distribution(response([],last='2',maximum='3',environment='2'),'2'))
        def claim_after_restart():
            try:
                _claim(stale)
                return stale.last_nsu
            finally:connections['default'].close()
        with ThreadPoolExecutor(max_workers=1) as pool:cursor=pool.submit(claim_after_restart).result(timeout=10)
        self.assertEqual(cursor,'000000000000002')

    def test_typed_stream_unique_identity_survives_parallel_creation(self):
        barrier=Barrier(2)
        def create():
            try:
                barrier.wait(timeout=10)
                return FiscalStream.objects.get_or_create(cnpj='00000003000125',service='nfse',environment='2')[0].pk
            finally:connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:create(),range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(FiscalStream.objects.count(),1)
