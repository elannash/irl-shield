"""Relay auth/config contracts; scripts/m2-native proves real socket enforcement."""
import json
import unittest

from relay.security import Credentials, RelayAddress, TwitchDestination, mediamtx_environment


class Security(unittest.TestCase):
    def test_restricted_listeners_and_path_permissions(self):
        for host in ('0.0.0.0', '::', '::1', '100.63.255.255', '100.128.0.0', 'localhost', '8.8.8.8'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                RelayAddress(host)
        for host in ('127.0.0.1', '127.255.255.254', '100.64.0.0', '100.127.255.255', '100.80.90.100'):
            self.assertEqual(RelayAddress(host).host, host)
        address = RelayAddress('127.0.0.1', 19350, 18890)
        phone, internal = Credentials.generate(), Credentials.generate()
        self.assertTrue(phone.password != internal.password)
        self.assertTrue(phone.password not in repr(phone))
        self.assertTrue(phone.user not in repr(phone))
        env = mediamtx_environment(address, phone, internal)
        self.assertEqual(env['MTX_RTMPADDRESS'], '127.0.0.1:19350')
        self.assertEqual(env['MTX_SRTADDRESS'], '127.0.0.1:18890')
        users = json.loads(env['MTX_AUTHINTERNALUSERS'])
        permissions = {u['user']: u['permissions'] for u in users}
        self.assertTrue(permissions.get(phone.user) == [{'action': 'publish', 'path': 'camera'}])
        self.assertEqual(permissions['any'], [{'action': 'read', 'path': 'shielded'}])
        self.assertTrue(permissions.get(internal.user) == [
            {'action': 'read', 'path': 'camera'}, {'action': 'publish', 'path': 'shielded'}])
        self.assertEqual(env['MTX_RTSP'], 'yes')
        self.assertEqual(env['MTX_RTSPADDRESS'], '127.0.0.1:18554')
        for field in ('MTX_HLS', 'MTX_WEBRTC', 'MTX_MOQ', 'MTX_API',
                      'MTX_METRICS', 'MTX_PPROF', 'MTX_PLAYBACK'):
            self.assertEqual(env[field], 'no')

    def test_twitch_callback_is_memory_only_and_forces_bandwidth_test(self):
        stub = TwitchDestination()
        secret = 'synthetic-key-never-log'
        stub.set_key(secret)
        self.assertTrue(stub.configured)
        self.assertTrue(stub.destination() == 'rtmps://live.twitch.tv:443/app/' + secret + '?bandwidthtest=true')
        self.assertTrue(secret not in repr(stub))
        stub.set_key(None)
        self.assertFalse(stub.configured)
        with self.assertRaises(ValueError):
            stub.set_key('unsafe?bandwidthtest=false')


if __name__ == '__main__':
    unittest.main()


class OperatorBind(unittest.TestCase):
    def test_cli_requires_explicit_bind_and_allows_environment_choice(self):
        from unittest.mock import patch
        from shield.cli import parser, validate
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                validate(parser().parse_args(['run', '--local-only']))
            validate(parser().parse_args(['run', '--local-only', '--host', '127.0.0.1']))
        with patch.dict('os.environ', {'SHIELD_BIND_HOST': '100.80.90.100'}, clear=True):
            args = parser().parse_args(['run', '--local-only'])
            validate(args)
            self.assertEqual(args.host, '100.80.90.100')

    def test_doctor_reports_detected_ip_and_explicit_absence(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from shield.cli import doctor
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='100.80.90.100\n')):
            self.assertEqual(doctor()['tailscale_ipv4'], '100.80.90.100')
        with patch('subprocess.run', side_effect=FileNotFoundError):
            self.assertEqual(doctor()['tailscale_ipv4'], 'unavailable')
