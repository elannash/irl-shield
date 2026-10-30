"""Linux RTMP relay commands: python -m shield.cli login|run|doctor."""
import argparse
import asyncio
from importlib import metadata
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
from urllib.parse import urlsplit


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='Inspect requirements; never qualifies privacy or walking')
    for name in ('login', 'run'):
        command = commands.add_parser(name)
        command.add_argument('--remember', action='store_true', help='Opt in to existing secure OS keyring')
        if name == 'login':
            command.add_argument('--run', action='store_true', help='Keep memory-only login in this process and run')
        command.add_argument('--mock-origin', help='Synthetic HTTP/EventSub server on IPv4 loopback')
        command.add_argument('--local-only', action='store_true', help='No Twitch authentication or EventSub')
        command.add_argument('--twitch-bandwidth-test', action='store_true', help='Explicitly publish to Twitch test ingest')
        command.add_argument('--local-sink', help='Local fake Twitch RTMP /shielded sink; requires --mock-origin')
        command.add_argument('--host', default=os.environ.get('SHIELD_BIND_HOST'),
                             help='Required relay bind: IPv4 loopback or Tailscale 100.64.0.0/10 (or SHIELD_BIND_HOST)')
        command.add_argument('--rtmp-port', type=int, default=19350)
        command.add_argument('--rtsp-port', type=int, default=18554)
        command.add_argument('--srt-port', type=int, default=18890)
        command.add_argument('--model-cache', type=Path, default=Path('models/cache'))
        command.add_argument('--archive', type=Path, help='Opt in to full stream and per-frame evidence')
        command.add_argument('--mediamtx-dir', type=Path, help='Directory with the hash-pinned MediaMTX binary')
        command.add_argument('--seconds', type=float)
        command.add_argument('--phone-setup', action='store_true', help='Show runtime phone credentials on /dev/tty')
        command.add_argument('--hold', action='store_true', help='Start with an independent manual HOLD')
    return root


def validate(args):
    if args.command == 'run' or args.command == 'login' and args.run:
        from relay.security import RelayAddress
        RelayAddress(args.host, args.rtmp_port, args.srt_port, args.rtsp_port)
    if args.command == 'login' and args.local_only:
        raise ValueError('Login requires Twitch authorization')
    if args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0):
        raise ValueError('Run duration must be positive and finite')
    if args.mock_origin:
        from shield.twitch.http import TwitchHTTP
        TwitchHTTP(None, mock_origin=args.mock_origin)
    if args.local_sink:
        parsed = urlsplit(args.local_sink)
        if (not args.mock_origin or args.twitch_bandwidth_test or parsed.scheme != 'rtmp'
                or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path != '/shielded'
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Fake sink requires mock controls and IPv4 loopback RTMP /shielded')
    if args.twitch_bandwidth_test and (args.local_only or args.mock_origin):
        raise ValueError('Twitch egress requires real owner authorization')
    if args.mock_origin and args.remember:
        raise ValueError('Synthetic credentials cannot use the owner OS keyring')
    if args.local_only and (args.mock_origin or args.remember or args.local_sink):
        raise ValueError('Local-only mode cannot use Twitch controls or credentials')


def tailscale_ipv4():
    import ipaddress
    try:
        result = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                address = ipaddress.IPv4Address(line.strip())
                if address in ipaddress.IPv4Network('100.64.0.0/10'):
                    return str(address)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass  # An absent/disabled Tailscale is an explicit doctor result.
    return 'unavailable'


def doctor():
    packages = {}
    for name in ('numpy', 'opencv-python-headless', 'av', 'onnxruntime-gpu', 'twitchAPI', 'aiohttp'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    from relay.mediamtx import verified_binary
    try:
        verified_binary()
        media = 'hash-verified'
    except (OSError, RuntimeError):
        media = 'missing-or-invalid; run scripts/m2-tools'
    return {'tailscale_ipv4': tailscale_ipv4(), 'platform': sys.platform, 'packages': packages, 'mediamtx': media,
            'cuda': 'not exercised', 'nvenc': 'not exercised',
            'rtmp': 'implemented; native qualification separate', 'srt': 'UNQUALIFIED; do not use for walking',
            'privacy': 'UNQUALIFIED; independent Q gate required',
            'cadence': 'not measured by doctor', 'av_offset': 'not measured by doctor',
            'credentials': 'memory-only by default; --remember opts into OS keyring',
            'ready': False}


def terminal_setup(address, phone):
    with open('/dev/tty', 'w') as terminal:
        if not terminal.isatty():
            raise RuntimeError('Owner terminal required')
        terminal.write('Phone RTMP URL (private): ' + address.rtmp('camera', phone) + '\n')
        terminal.write('OBS RTMP input: ' + address.rtmp('shielded') + '\n')
        terminal.flush()


async def execute(args):
    from aiohttp import ClientSession
    from shield.app.session import TwitchControls, login
    from shield.twitch.http import TwitchHTTP
    validate(args)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    cancel, stopped = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    def stop():
        cancel.set()
        stopped.set()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop)
    try:
        async with ClientSession() as network:
            http = TwitchHTTP(network, mock_origin=args.mock_origin)
            session = None
            if not args.local_only:
                session = await login(http, os.environ.get('TWITCH_CLIENT_ID', 'synthetic-client' if args.mock_origin else ''),
                                      os.environ.get('TWITCH_BROADCASTER_ID', '1' if args.mock_origin else ''), cancel,
                                      remember=args.remember, **({'present': lambda _: None} if args.mock_origin else {}))
            if args.command == 'login' and not args.run:
                print('Login validated. Memory-only session ends here; use login --run or --remember to continue.')
                return
            from relay.mediamtx import MediaMTX, verified_binary
            from relay.runtime import make_engine, run
            from relay.security import Credentials, RelayAddress
            address = RelayAddress(args.host, args.rtmp_port, args.srt_port, args.rtsp_port)
            phone, internal = Credentials.generate(), Credentials.generate()
            controls = TwitchControls(session, http, stopped, mock_origin=args.mock_origin) if session else None
            if controls:
                await controls.prepare()
            current = None
            def register(control):
                nonlocal current
                current = control
                if args.hold:
                    control.hold(True)
                if controls:
                    controls.register(control)
            def manual(active):
                if current is not None:
                    current.hold(active)
            for signum, active in ((signal.SIGUSR1, True), (signal.SIGUSR2, False)):
                loop.add_signal_handler(signum, manual, active)
            try:
                binary = verified_binary(args.mediamtx_dir) if args.mediamtx_dir else verified_binary()
                with MediaMTX(address, phone, internal, binary=binary):
                    if args.phone_setup:
                        terminal_setup(address, phone)
                    engine = await asyncio.to_thread(make_engine, args.model_cache)
                    work = asyncio.create_task(asyncio.to_thread(run, engine, address, phone, internal,
                        args.archive, stopped, args.seconds, control_ready=register,
                        publish_twitch=args.twitch_bandwidth_test, local_sink=args.local_sink))
                    try:
                        await asyncio.shield(work)
                    finally:
                        stopped.set()
                        await work
                if controls and controls.failure:
                    raise RuntimeError('EventSub startup failed')
            finally:
                if controls:
                    await controls.close()
                if current:
                    current.set_stream_key(None)
                for signum in (signal.SIGUSR1, signal.SIGUSR2):
                    loop.remove_signal_handler(signum)
    finally:
        stopped.set()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    if args.command == 'doctor':
        print(json.dumps(doctor(), indent=2))
        return 0
    if (args.command == 'run' or args.command == 'login' and args.run) and not args.host:
        arguments.error('--host is required: use IPv4 loopback (127.0.0.0/8) or a Tailscale address '
                        '(100.64.0.0/10), or set SHIELD_BIND_HOST. Run shield doctor '
                        '(python -m shield.cli doctor) to find the address.')
    try:
        asyncio.run(execute(args))
    except (Exception, asyncio.CancelledError):
        print('Shield stopped with an error; credentialed upstream diagnostics suppressed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
