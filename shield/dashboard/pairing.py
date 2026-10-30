"""RAM-only Moblin imports, per the upstream documented custom URL format."""
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote, urlsplit
import ipaddress
import json


def private_address(host):
    try:
        if type(host) is not str:
            raise ValueError
        address = ipaddress.ip_address(host)
    except (ValueError, TypeError):
        raise ValueError('Expected a literal loopback or Tailscale address') from None
    if address.is_loopback or (address.version == 4 and address in ipaddress.ip_network('100.64.0.0/10')):
        return str(address)
    raise ValueError('Expected a literal loopback or Tailscale address')


def _stream_url(value, schemes):
    try:
        if type(value) is not str or len(value) > 768 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError
        parsed = urlsplit(value)
        if (parsed.scheme not in schemes or not parsed.hostname or parsed.fragment
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        private_address(parsed.hostname)
        if parsed.port is None or not 1 <= parsed.port <= 65535:
            raise ValueError
        if parsed.scheme in ('rtmp', 'rtmps') and (not parsed.path.strip('/') or value.endswith('/') or '/' in parsed.query):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Invalid private stream configuration') from None
    return value


@dataclass(frozen=True, repr=False)
class PairingData:
    """Supply only local ingest credentials, never a Twitch destination/key.

    SRT remains unqualified until root has native phone/relay receipts.
    """
    rtmp_url: str
    srt_url: str | None = None
    srt_qualified: bool = False

    def __post_init__(self):
        _stream_url(self.rtmp_url, ('rtmp', 'rtmps'))
        if self.srt_url is not None:
            _stream_url(self.srt_url, ('srt',))
        if type(self.srt_qualified) is not bool or (self.srt_qualified and self.srt_url is None):
            raise ValueError('Invalid SRT qualification')

    def import_url(self, protocol='rtmp'):
        if protocol not in ('rtmp', 'srt') or (protocol == 'srt' and self.srt_url is None):
            raise ValueError('Pairing protocol unavailable')
        url = self.rtmp_url if protocol == 'rtmp' else self.srt_url
        payload = {'streams': [{'name': 'IRL Shield', 'url': url, 'selected': True}]}
        # Encode the outer JSON once; encoding the stream URL itself changes its key.
        return 'moblin://?' + quote(json.dumps(payload, separators=(',', ':')), safe='')

    def qr_png(self, protocol='rtmp'):
        import qrcode
        from qrcode.image.pil import PilImage
        from qrcode.exceptions import DataOverflowError
        try:
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
            qr.add_data(self.import_url(protocol))
            qr.make(fit=True)
            stream = BytesIO()
            qr.make_image(image_factory=PilImage).save(stream, format='PNG')
            return stream.getvalue()
        except DataOverflowError:
            raise ValueError('Pairing configuration is too large') from None

    def private_payload(self):
        return {'rtmp_url': self.rtmp_url, 'rtmp_import': self.import_url(),
                'srt_url': self.srt_url,
                'srt_import': self.import_url('srt') if self.srt_url is not None else None,
                'srt_status': 'qualified' if self.srt_qualified else 'unqualified'}
