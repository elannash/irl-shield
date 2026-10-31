"""Reuse the launcher's canonical WRITE lease before any native import."""
import os
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
LEASE_ENV = 'IRL_SHIELD_PERF_QUEUE_LEASE_FD'


def inherited_exclusive():
    try:
        fd = int(os.environ[LEASE_ENV])
        if fd < 3:
            raise ValueError()
        # One authority for physical inode and /proc flock identity checks.
        launcher = runpy.run_path(str(ROOT / 'scripts/walk-linux'))
        launcher['verified_fd'](fd, launcher['LOCK_ROOT'] / 'perf.lock')
    except Exception:
        raise RuntimeError('W8 requires the inherited canonical EX lease') from None
    return fd
