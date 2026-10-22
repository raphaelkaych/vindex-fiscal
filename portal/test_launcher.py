"""Supervisão local sem iniciar servidor ou worker reais."""
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
import iniciar


class LauncherTests(SimpleTestCase):
    @patch('iniciar.capture_is_running',side_effect=[False,True])
    @patch('iniciar.stop_child')
    @patch('iniciar.time.sleep')
    @patch('iniciar.start_child')
    def test_does_not_respawn_exited_child_when_another_worker_is_active(self,start,sleep,stop,running):
        first,server=MagicMock(),MagicMock();start.side_effect=[first,server]
        first.poll.return_value=0;server.poll.side_effect=[None,0];server.returncode=0
        iniciar.serve_with_capture()
        self.assertEqual(start.call_count,2);sleep.assert_called_once_with(.5)
    @patch('iniciar.capture_is_running', return_value=False)
    @patch('iniciar.stop_child')
    @patch('iniciar.time.sleep')
    @patch('iniciar.start_child')
    def test_starts_web_and_worker_and_closes_both(self,start,sleep,stop,running):
        worker,server=MagicMock(),MagicMock()
        start.side_effect=[worker,server]
        server.poll.side_effect=[None,0];server.returncode=0
        worker.poll.return_value=None
        iniciar.serve_with_capture()
        self.assertIn('capturar_sefaz',start.call_args_list[0].args[0])
        self.assertIn('runserver',start.call_args_list[1].args[0])
        self.assertEqual(stop.call_args_list[0].args[0],worker)
        self.assertEqual(stop.call_args_list[1].args[0],server)

    @patch('iniciar.capture_is_running', return_value=False)
    @patch('iniciar.stop_child')
    @patch('iniciar.time.sleep')
    @patch('iniciar.start_child')
    def test_restarts_worker_without_restarting_web(self,start,sleep,stop,running):
        first,server,replacement=MagicMock(),MagicMock(),MagicMock()
        start.side_effect=[first,server,replacement]
        first.poll.return_value=1
        server.poll.side_effect=[None,0];server.returncode=0
        iniciar.serve_with_capture()
        self.assertEqual(start.call_count,3)
        self.assertIn('capturar_sefaz',start.call_args_list[2].args[0])
        self.assertEqual(stop.call_args_list[0].args[0],replacement)

    @patch('iniciar.capture_is_running', return_value=True)
    @patch('iniciar.stop_child')
    @patch('iniciar.start_child')
    def test_reuses_capture_already_started_by_windows(self,start,stop,running):
        server=MagicMock();server.poll.return_value=0;server.returncode=0
        start.return_value=server
        iniciar.serve_with_capture()
        start.assert_called_once()
        self.assertIn('runserver',start.call_args.args[0])
        stop.assert_called_once_with(server)
