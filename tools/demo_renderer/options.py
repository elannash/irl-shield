"""Stdlib-only demo checks shared by the isolated bootstrap and CLI."""
import json
import math
from pathlib import Path


def source_frame_count(manifest):
    if not isinstance(manifest, dict):
        raise ValueError('Demo source manifest must be a JSON object')
    seconds, frames = manifest.get('seconds'), manifest.get('frames')
    if (type(seconds) not in (int, float) or not 10 <= seconds <= 600
            or manifest.get('fps') != 30
            or not isinstance(frames, list)):
        raise ValueError('Demo source requires 10–600 seconds at 30 fps')
    count = round(seconds * 30)
    # JSON floats can approximate a whole-frame duration such as 1801 / 30.
    if not math.isclose(seconds * 30, count, rel_tol=0, abs_tol=1e-7) or len(frames) != count:
        raise ValueError('Demo source frame count differs from its duration')
    return count


def fresh(path):
    path = Path(path).expanduser()
    if path.exists() or path.is_symlink():
        raise ValueError('Demo output paths must be fresh')
    return path.resolve()


def validate_demo(args):
    if args.demo_source is None and args.demo_receipt is None:
        return
    local = args.local_only and not args.twitch_live and args.host == '127.0.0.1'
    attended = args.twitch_live and not args.local_only
    mocked = (bool(getattr(args, 'mock_origin', None)) and not args.local_only
              and not args.twitch_live and getattr(args, 'local_sink', None) is None
              and args.host == '127.0.0.1')
    if (not (local or attended or mocked) or args.twitch_bandwidth_test
            or getattr(args, 'command', 'run') != 'run'
            or getattr(args, 'phone_setup', False)):
        raise ValueError('Demo source requires local-only or mock-controlled loopback, or attended live mode without phone setup')
    if args.demo_source is None or args.demo_receipt is None or args.archive is None or args.seconds is None:
        raise ValueError('Demo source requires source, receipt, fresh archive and bounded duration')
    if args.accurate_rate_hz is not None or args.accurate_box_thresh is not None:
        raise ValueError('Demo source uses the frozen detector defaults')
    if not args.demo_source.expanduser().is_file():
        raise ValueError('Demo source manifest must already exist')
    manifest = json.loads(args.demo_source.expanduser().read_text())
    if source_frame_count(manifest) / 30 + 5 > args.seconds:
        raise ValueError('Demo source requires at least 5 seconds of headroom under --seconds')
    receipt, archive = fresh(args.demo_receipt), fresh(args.archive)
    if receipt == archive or archive in receipt.parents:
        raise ValueError('Demo sender receipt must be outside its relay archive')
