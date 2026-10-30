"""Restricted relay addresses and runtime-only credentials. No network side effects."""
from dataclasses import dataclass, field
import json
import re
import secrets
from urllib.parse import urlencode


@dataclass(frozen=True)
class RelayAddress:
    host: str = '100.109.49.77'
    rtmp_port: int = 19350
    srt_port: int = 18890

    def __post_init__(self):
        if self.host not in ('100.109.49.77', '127.0.0.1'):
            raise ValueError('Relay listeners require the assigned Tailscale or IPv4 loopback address')
        if any(type(p) is not int or not 1024 <= p <= 65535 for p in (self.rtmp_port, self.srt_port)):
            raise ValueError('Relay requires explicit unprivileged ports')

    def rtmp(self, path, credentials=None):
        if path not in ('camera', 'shielded'):
            raise ValueError('Unknown relay path')
        query = '?' + urlencode({'user': credentials.user, 'pass': credentials.password}) if credentials else ''
        return f'rtmp://{self.host}:{self.rtmp_port}/{path}{query}'

    def srt(self, action, path, credentials=None):
        if action not in ('read', 'publish') or path not in ('camera', 'shielded'):
            raise ValueError('Unknown SRT action or path')
        streamid = f'{action}:{path}'
        if credentials:
            streamid += f':{credentials.user}:{credentials.password}'
        return f'srt://{self.host}:{self.srt_port}?' + urlencode({
            'streamid': streamid, 'pkt_size': 1316, 'mode': 'caller', 'latency': 120000})


@dataclass(frozen=True)
class Credentials:
    user: str = field(repr=False)
    password: str = field(repr=False)

    @classmethod
    def generate(cls):
        return cls('u' + secrets.token_hex(8), secrets.token_urlsafe(32))


def mediamtx_environment(address, phone, internal):
    # No wildcard paths, default anonymous publisher, recording or additional listeners.
    users = [
        {'user': phone.user, 'pass': phone.password, 'ips': [],
         'permissions': [{'action': 'publish', 'path': 'camera'}]},
        {'user': internal.user, 'pass': internal.password, 'ips': [address.host, '127.0.0.1'],
         'permissions': [{'action': 'read', 'path': 'camera'}, {'action': 'publish', 'path': 'shielded'}]},
        {'user': 'any', 'ips': [], 'permissions': [{'action': 'read', 'path': 'shielded'}]},
    ]
    return {
        **{f'MTX_{key}': 'no' for key in ('RTSP', 'HLS', 'WEBRTC', 'MOQ', 'API', 'METRICS', 'PPROF', 'PLAYBACK')},
        'MTX_RTMP': 'yes', 'MTX_RTMPENCRYPTION': 'no', 'MTX_RTMPADDRESS': f'{address.host}:{address.rtmp_port}',
        'MTX_SRT': 'yes', 'MTX_SRTADDRESS': f'{address.host}:{address.srt_port}',
        'MTX_AUTHMETHOD': 'internal', 'MTX_AUTHINTERNALUSERS': json.dumps(users),
        'MTX_LOGLEVEL': 'error', 'MTX_LOGDESTINATIONS': 'stdout',
        'MTX_READTIMEOUT': '3s', 'MTX_WRITETIMEOUT': '3s', 'MTX_WRITEQUEUESIZE': '128',
    }


class TwitchStub:
    """M3 calls set_key in memory. Tonight this has no socket/publish implementation."""
    connected = False

    def __init__(self):
        self._key = None

    @property
    def configured(self):
        return self._key is not None

    def set_key(self, key):
        if key is not None and (not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', key)):
            raise ValueError('Invalid ephemeral stream key')
        self._key = key

    def destination(self):
        if self._key is None:
            raise RuntimeError('No ephemeral stream key')
        return 'rtmp://live.twitch.tv/app/' + self._key + '?bandwidthtest=true'
