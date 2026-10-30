"""Recheck the root barrier after acquiring the host lease, before any command."""
import json
import os
from pathlib import Path
import sys

PERF_LOCK = Path('/tmp/agents/irl-shield/perf.lock')
QUEUE_KEYS = ('FORCED', 'ATTEMPT', 'RECEIPT', 'LEASE_FD')


def read_queue_context():
    values = {name: os.environ.get('IRL_SHIELD_PERF_QUEUE_' + name) for name in QUEUE_KEYS}
    if all(value is None for value in values.values()):
        return None
    if any(value is None for value in values.values()) or values['FORCED'] not in ('0', '1'):
        raise RuntimeError('Incomplete or invalid performance queue context')
    try:
        attempt, fd = int(values['ATTEMPT']), int(values['LEASE_FD'])
        if attempt < 1 or not Path(values['RECEIPT']).is_absolute():
            raise ValueError('Invalid attempt or receipt')
        inherited, canonical = os.fstat(fd), PERF_LOCK.stat()
        if (inherited.st_dev, inherited.st_ino) != (canonical.st_dev, canonical.st_ino):
            raise RuntimeError('Queue lease descriptor does not identify the canonical perf.lock')
    except (ValueError, OSError) as error:
        raise RuntimeError('Invalid canonical queue lease context') from error
    return {'forced': values['FORCED'] == '1', 'attempt': attempt, 'receipt': values['RECEIPT'],
            'lease_fd': fd, 'inherited_environment': values}


def require_complete(path):
    marker = json.loads(Path(path).read_text())
    if marker.get('complete') is not True:
        raise RuntimeError('Root sustained receipt is not complete; FAST host work must wait')
    return marker


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: python -m bench.fast_lease command [args...]')
    require_complete('/tmp/agents/irl-shield/m1-20261029-ready.json')
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
