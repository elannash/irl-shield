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

from shield.app.live import LiveModeError


def parser():
    root = argparse.ArgumentParser(description=__doc__ + ' Default detectors: PP-OCRv5-mobile in both lanes.')
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='Inspect requirements; never qualifies privacy or walking')
    for name in ('login', 'run'):
        command = commands.add_parser(name)
        command.add_argument('--remember', action='store_true', help='Opt in to existing secure OS keyring')
        if name == 'login':
            command.add_argument('--run', action='store_true', help='Keep memory-only login in this process and run')
        command.add_argument('--mock-origin', help='Synthetic HTTP/EventSub server on IPv4 loopback')
        command.add_argument('--local-only', action='store_true', help='No Twitch authentication or EventSub')
        publication = command.add_mutually_exclusive_group()
        publication.add_argument('--twitch-bandwidth-test', action='store_true', help='Explicitly publish to Twitch test ingest')
        publication.add_argument('--twitch-live', action='store_true', help='Publish live to naie after fresh authorization and terminal confirmation')
        command.add_argument('--local-sink', help='Local fake Twitch RTMP /shielded sink; requires --mock-origin')
        command.add_argument('--host', default=os.environ.get('SHIELD_BIND_HOST'),
                             help='Required relay bind: IPv4 loopback or Tailscale 100.64.0.0/10 (or SHIELD_BIND_HOST)')
        command.add_argument('--rtmp-port', type=int, default=19350)
        command.add_argument('--rtsp-port', type=int, default=18554)
        command.add_argument('--srt-port', type=int, default=18890)
        command.add_argument('--model-cache', type=Path, default=Path('models/cache'))
        command.add_argument('--cpu', action='store_true', help='Use ONNX CPU for both lanes and libx264 encoding')
        command.add_argument('--delay-seconds', type=float, help='Presentation delay, 0.5..10 seconds inclusive (privacy floor 0.5); default 1, or 2.5 with --cpu')
        command.add_argument('--accurate-rate-hz', type=float, help='Experimental accurate detector cadence; default 4 Hz')
        command.add_argument('--accurate-box-thresh', type=float, help='Experimental accurate-only box confidence floor; default 0.5')
        command.add_argument('--archive', type=Path, help='Opt in to full stream and per-frame evidence')
        command.add_argument('--demo-source', type=Path, help='Prepared local-only loopback input manifest')
        command.add_argument('--demo-receipt', type=Path, help='Fresh sender receipt; requires demo source and archive')
        command.add_argument('--mediamtx-dir', type=Path, help='Directory with the hash-pinned MediaMTX binary')
        command.add_argument('--seconds', type=float)
        command.add_argument('--phone-setup', action='store_true', help='Show runtime phone credentials on /dev/tty')
        command.add_argument('--dashboard', action='store_true', help='Serve private phone controls; also enabled by --phone-setup')
        command.add_argument('--dashboard-port', type=int, default=0, help='Private dashboard port; default chooses a free port')
        command.add_argument('--skin', default='patch', choices=('frosted', 'bar', 'signed', 'patch'))
        command.add_argument('--frosted-desaturation', type=float, default=0.0, help='Optional coarse-color desaturation, 0 to 1')
        command.add_argument('--hold', action='store_true', help='Start with an independent manual HOLD')
    return root


def validate(args):
    from tools.demo_renderer.options import validate_demo
    validate_demo(args)
    if args.delay_seconds is not None and (not math.isfinite(args.delay_seconds) or not .5 <= args.delay_seconds <= 10):
        raise ValueError('delay_seconds must be finite and between 0.5 (privacy floor) and 10 seconds inclusive')
    if args.command == 'login' and not args.run and (args.cpu or args.delay_seconds is not None):
        raise ValueError('CPU and presentation delay options require run or login --run')
    if args.accurate_rate_hz is not None and (not math.isfinite(args.accurate_rate_hz)
                                             or not 0 < args.accurate_rate_hz <= 30):
        raise ValueError('accurate_rate_hz must be positive, finite and at most 30')
    if args.accurate_box_thresh is not None and (not math.isfinite(args.accurate_box_thresh)
                                                or not 0 <= args.accurate_box_thresh <= 1):
        raise ValueError('accurate_box_thresh must be finite and between 0 and 1')
    if args.command == 'run' or args.command == 'login' and args.run:
        from relay.security import RelayAddress
        RelayAddress(args.host, args.rtmp_port, args.srt_port, args.rtsp_port)
    if args.command == 'login' and args.local_only:
        raise ValueError('Login requires Twitch authorization')
    if args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0):
        raise ValueError('Run duration must be positive and finite')
    if (not math.isfinite(args.frosted_desaturation) or not 0 <= args.frosted_desaturation <= 1
            or not 0 <= args.dashboard_port <= 65535):
        raise ValueError('Invalid dashboard port or frosted desaturation')
    if args.mock_origin:
        from shield.twitch.http import TwitchHTTP
        TwitchHTTP(None, mock_origin=args.mock_origin)
    if args.local_sink:
        parsed = urlsplit(args.local_sink)
        if (not args.mock_origin or args.twitch_bandwidth_test or args.twitch_live or parsed.scheme != 'rtmp'
                or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path != '/shielded'
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Fake sink requires mock controls and IPv4 loopback RTMP /shielded')
    if (args.twitch_bandwidth_test or args.twitch_live) and (args.local_only or args.mock_origin):
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
    from shield.app.live import authorize_live
    from shield.app.session import TwitchControls, login
    from shield.twitch.http import TwitchHTTP
    validate(args)
    phone_input = None
    local_demo = args.demo_source is not None and not args.twitch_live
    if args.demo_source is not None:
        from tools.demo_renderer.sender import Sender, source_manifest
        source_manifest(args.demo_source)
        args.demo_receipt.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        args.archive = args.archive.expanduser().resolve()
        args.archive.mkdir(parents=True, exist_ok=False)
        def phone_input(address, phone):
            return Sender(args.demo_source, address, phone, args.demo_receipt, local_only=local_demo)
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
            approval = await authorize_live(session, http) if args.twitch_live else None
            from relay.mediamtx import MediaMTX, verified_binary
            from relay.runtime import make_engine, run
            from relay.security import Credentials, RelayAddress
            address = RelayAddress(args.host, args.rtmp_port, args.srt_port, args.rtsp_port)
            phone, internal = Credentials.generate(), Credentials.generate()
            from shield.app.appearance import Appearance
            appearance = Appearance(skin=args.skin, desaturation=args.frosted_desaturation)
            controls = TwitchControls(session, http, stopped, mock_origin=args.mock_origin,
                                      skin_chat=appearance.chat) if session else None
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
            def dashboard_manual(active):
                if current is None:
                    raise RuntimeError('Relay control is not ready')
                current.hold(active)
            for signum, active in ((signal.SIGUSR1, True), (signal.SIGUSR2, False)):
                loop.add_signal_handler(signum, manual, active)
            try:
                binary = verified_binary(args.mediamtx_dir) if args.mediamtx_dir else verified_binary()
                with MediaMTX(address, phone, internal, binary=binary, archive=args.archive):
                    if args.phone_setup:
                        terminal_setup(address, phone)
                    detector_options = {}
                    if args.cpu:
                        detector_options.update(provider='cpu', delay_seconds=2.5)
                    if args.delay_seconds is not None:
                        detector_options['delay_seconds'] = args.delay_seconds
                    if args.accurate_rate_hz is not None:
                        detector_options['accurate_rate_hz'] = args.accurate_rate_hz
                    if args.accurate_box_thresh is not None:
                        detector_options['accurate_box_thresh'] = args.accurate_box_thresh
                    if phone_input is None:
                        engine = await asyncio.to_thread(make_engine, args.model_cache, appearance=appearance,
                                                         **detector_options)
                    else:
                        initializing = asyncio.create_task(asyncio.to_thread(make_engine, args.model_cache,
                            appearance=appearance, **detector_options))
                        try:
                            engine = await asyncio.shield(initializing)
                        except asyncio.CancelledError:
                            # A cancelled to_thread await does not stop model
                            # construction; reap its result before leaving MTX.
                            engine = await initializing
                            await asyncio.to_thread(engine.close)
                            raise
                    appearance.engine = engine
                    work = dashboard = None
                    try:
                        if args.dashboard or args.phone_setup:
                            from shield.dashboard import DashboardServer, PairingData
                            dashboard_factory = DashboardServer
                            if local_demo:
                                from tools.demo_renderer.rehearsal import local_dashboard
                                dashboard_factory = local_dashboard
                            dashboard = dashboard_factory(host=args.host, port=args.dashboard_port,
                                get_public_snapshot=appearance.snapshot, set_manual_hold=dashboard_manual,
                                pairing=PairingData(address.rtmp('camera', phone),
                                                    address.srt('publish', 'camera', phone)))
                            await dashboard.start()
                        input_options = {'phone_input': phone_input} if phone_input is not None else {}
                        if args.cpu:
                            input_options['encoder'] = 'libx264'
                        work = asyncio.create_task(asyncio.to_thread(run, engine, address, phone, internal,
                            args.archive, stopped, args.seconds, control_ready=register,
                            publish_twitch=(args.twitch_bandwidth_test or args.twitch_live),
                            twitch_live=args.twitch_live, live_approval=approval,
                            local_sink=args.local_sink, appearance=appearance, **input_options))
                        await asyncio.shield(work)
                        if local_demo:
                            from tools.demo_renderer.rehearsal import check_archive
                            check_archive(args.archive, args.demo_receipt)
                    finally:
                        stopped.set()
                        try:
                            if dashboard is not None:
                                await dashboard.close()
                        finally:
                            if work is not None:
                                await work
                            else:
                                await asyncio.to_thread(engine.close)
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
    except LiveModeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (Exception, asyncio.CancelledError):
        print('Shield stopped with an error; credentialed upstream diagnostics suppressed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
