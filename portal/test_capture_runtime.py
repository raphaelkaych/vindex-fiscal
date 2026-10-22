"""Sinal de execução local; pasta temporária de teste, sem rede e sem banco."""
import json
import os
import tempfile
import threading
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command
from django.db import OperationalError,InterfaceError
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from portal.services import capture_runtime as runtime


class CaptureRuntimeTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='vindex-runtime-test-')
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(BASE_DIR=Path(self.directory.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def test_missing_heartbeat_does_not_announce_running_worker(self):
        self.assertFalse(runtime.capture_runtime_status()['active'])
        self.assertEqual(runtime.capture_runtime_status()['reason'], 'missing')

    def test_database_failure_does_not_stop_continuous_queue_or_expose_exception(self):
        from portal.management.commands.capturar_sefaz import Command
        for failure in (OperationalError,InterfaceError):
            with self.subTest(failure=failure):
                out=StringIO();err=StringIO();command=Command(stdout=out,stderr=err)
                with patch('portal.management.commands.capturar_sefaz.run_due',side_effect=[failure('SEGREDO_NAO_EXIBIR'),[]]) as run,patch('portal.services.fiscal_capture.run_due_connectors') as connectors,patch('portal.management.commands.capturar_sefaz.time.sleep',side_effect=[None,KeyboardInterrupt]):
                    command._run({'once':False,'limit':20,'company':None,'interval':15})
                self.assertEqual(run.call_count,2);connectors.assert_called_once()
                self.assertIn('Acesso ao banco',err.getvalue())
                self.assertNotIn('SEGREDO_NAO_EXIBIR',err.getvalue()+out.getvalue())

    def test_single_cycle_database_failure_is_reported_as_failure(self):
        from portal.management.commands.capturar_sefaz import Command
        with patch('portal.management.commands.capturar_sefaz.run_due',side_effect=OperationalError('SEGREDO_NAO_EXIBIR')):
            with self.assertRaises(CommandError) as caught:
                Command(stderr=StringIO())._run({'once':True,'limit':20,'company':None,'interval':15})
        self.assertNotIn('SEGREDO_NAO_EXIBIR',str(caught.exception))

    def test_atomic_heartbeat_contains_only_pid_and_timestamp(self):
        with patch.object(runtime.time, 'time', return_value=1_800_000_000):
            self.assertTrue(runtime.write_heartbeat())
            self.assertTrue(runtime.capture_runtime_status()['active'])
        value = json.loads(runtime.heartbeat_path().read_text())
        self.assertEqual(set(value), {'pid', 'updated_at'})
        self.assertEqual(value['pid'], os.getpid())
        self.assertEqual(list(runtime.heartbeat_path().parent.glob('*.tmp')), [])

    def test_heartbeat_expires_after_ninety_seconds(self):
        with patch.object(runtime.time, 'time', return_value=1_800_000_000):
            runtime.write_heartbeat()
        with patch.object(runtime.time, 'time', return_value=1_800_000_089):
            self.assertTrue(runtime.capture_runtime_status()['active'])
        with patch.object(runtime.time, 'time', return_value=1_800_000_090):
            state = runtime.capture_runtime_status()
            self.assertFalse(state['active'])
            self.assertEqual(state['reason'], 'stale')
            self.assertIsNotNone(state['last_seen'])

    def test_invalid_or_future_heartbeat_does_not_announce_running_worker(self):
        runtime.heartbeat_path().parent.mkdir()
        for value in ['INVALIDO', '{}', '[]', '{"pid":true,"updated_at":12}',
                      '{"pid":12,"updated_at":true}', '{"pid":12,"updated_at":NaN}',
                      '{"pid":12,"updated_at":9999999999999}', 'x' * 513]:
            with self.subTest(value=value):
                runtime.heartbeat_path().write_text(value)
                self.assertFalse(runtime.capture_runtime_status()['active'])
                self.assertEqual(runtime.capture_runtime_status()['reason'], 'invalid')

    def test_failed_write_does_not_interrupt_worker_or_leave_temporary_file(self):
        with patch.object(runtime.os, 'replace', side_effect=PermissionError):
            self.assertFalse(runtime.write_heartbeat())
        self.assertEqual(list(runtime.heartbeat_path().parent.glob('*.tmp')), [])

    def test_context_marks_running_and_removes_own_signal_on_exit(self):
        with runtime.worker_heartbeat():
            self.assertTrue(runtime.capture_runtime_status()['active'])
        self.assertFalse(runtime.heartbeat_path().exists())

    def test_background_heartbeat_continues_during_busy_work(self):
        refreshed = threading.Event()
        original = runtime.write_heartbeat
        calls = []
        def record():
            calls.append(True)
            original()
            if len(calls) > 1:
                refreshed.set()
        with patch.object(runtime, 'HEARTBEAT_INTERVAL', .01), patch.object(runtime, 'write_heartbeat', side_effect=record):
            with runtime.worker_heartbeat():
                self.assertTrue(refreshed.wait(timeout=1), 'A atualização deve continuar sem depender do loop fiscal.')
        self.assertFalse(runtime.heartbeat_path().exists())

    def test_own_shutdown_does_not_remove_another_worker_signal(self):
        runtime.heartbeat_path().parent.mkdir()
        runtime.heartbeat_path().write_text(json.dumps({'pid': os.getpid()+100, 'updated_at': 0}))
        runtime._clear_own_heartbeat()
        self.assertTrue(runtime.heartbeat_path().exists())

    def test_once_command_never_marks_continuous_worker_active(self):
        with (patch('portal.management.commands.capturar_sefaz.run_due', return_value=[]) as due,
              patch('portal.services.fiscal_capture.run_due_connectors') as extra_due,
              patch('portal.management.commands.capturar_sefaz.close_old_connections')):
            call_command('capturar_sefaz', once=True, stdout=StringIO())
        due.assert_called_once()
        extra_due.assert_called_once()
        self.assertFalse(runtime.heartbeat_path().exists())

    def test_worker_lock_prevents_duplicate_queue_and_releases_for_restart(self):
        with runtime.capture_worker_lock() as first:
            self.assertTrue(first)
            with patch('portal.management.commands.capturar_sefaz.run_due') as due:
                call_command('capturar_sefaz',stdout=StringIO())
                due.assert_not_called()
            self.assertFalse(runtime.heartbeat_path().exists())
        with runtime.capture_worker_lock() as restarted:self.assertTrue(restarted)

    def test_continuous_command_signals_before_first_queue_pass(self):
        def due(**kwargs):
            self.assertTrue(runtime.capture_runtime_status()['active'])
            raise KeyboardInterrupt
        with (patch('portal.management.commands.capturar_sefaz.run_due', side_effect=due),
              patch('portal.management.commands.capturar_sefaz.close_old_connections')):
            call_command('capturar_sefaz', stdout=StringIO())
        self.assertFalse(runtime.heartbeat_path().exists())
