"""Fail before a test opens or resolves the real performance lease."""
import os
from pathlib import Path
import sys

GLOBAL_PERF_LOCK = '/tmp/agents/irl-shield/perf.lock'
MESSAGE = 'Global performance lock is forbidden in tests; pass a temporary lock_root'
_installed = False


def _reject(value):
    if isinstance(value, (str, bytes, os.PathLike)):
        name = os.path.abspath(os.fsdecode(value))
        if name == GLOBAL_PERF_LOCK or os.path.realpath(name) == GLOBAL_PERF_LOCK:
            raise AssertionError(MESSAGE)


def install_lock_guard():
    global _installed
    if _installed:
        return
    original_resolve, original_stat = Path.resolve, Path.stat

    def resolve(path, *args, **kwargs):
        _reject(path)
        result = original_resolve(path, *args, **kwargs)
        _reject(result)
        return result

    def stat(path, *args, **kwargs):
        _reject(path)
        return original_stat(path, *args, **kwargs)

    def audit(event, args):
        if event == 'open':
            _reject(args[0])
        elif event == 'fcntl.flock':
            try:
                target = os.readlink('/proc/self/fd/' + str(args[0]))
            except OSError:
                return
            _reject(target.removesuffix(' (deleted)'))
        elif event == 'subprocess.Popen':
            argv = args[1]
            if isinstance(argv, (list, tuple)):
                for value in argv:
                    _reject(value)
                    if isinstance(value, str) and GLOBAL_PERF_LOCK in value:
                        raise AssertionError(MESSAGE)
                # Production host-lock intentionally has no test escape flag.
                script = Path(__file__).resolve().parents[1] / 'scripts/host-lock'
                if any(isinstance(value, str) and os.path.abspath(value) == str(script) for value in argv):
                    raise AssertionError(MESSAGE)

    Path.resolve, Path.stat = resolve, stat
    sys.addaudithook(audit)
    _installed = True
