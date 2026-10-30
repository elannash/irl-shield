"""Relay auth/config contracts; scripts/m2-native proves real socket enforcement."""
import json
import unittest

from relay.security import Credentials, RelayAddress, TwitchStub, mediamtx_environment


class Security(unittest.TestCase):
    def test_restricted_listeners_and_path_permissions(self):
        for host in ('0.0.0.0', '::', '::1', '100.80.90.100', 'localhost', '8.8.8.8'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                RelayAddress(host)
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
        stub = TwitchStub()
        secret = 'synthetic-key-never-log'
        stub.set_key(secret)
        self.assertTrue(stub.configured)
        self.assertTrue(stub.destination() == 'rtmp://live.twitch.tv/app/' + secret + '?bandwidthtest=true')
        self.assertTrue(secret not in repr(stub))
        self.assertFalse(stub.connected)
        stub.set_key(None)
        self.assertFalse(stub.configured)
        with self.assertRaises(ValueError):
            stub.set_key('unsafe?bandwidthtest=false')


if __name__ == '__main__':
    unittest.main()
