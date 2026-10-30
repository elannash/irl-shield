"""Foreground queue entrypoint: validates lease, accounts test calls, retains result."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import runpy
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from relay.soak import require_queue_lease


def main():
    scenario, *arguments = sys.argv[1:]
    lease = require_queue_lease()
    ledger = Path('out/integration/test-calls.log')
    with open('.tmp/integration/test-budget.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        calls = sum(line.startswith('2026-') for line in ledger.read_text().splitlines())
        if calls >= 32:
            raise RuntimeError('Integration 32-invocation budget exhausted')
        with ledger.open('a') as output:
            output.write(datetime.now(timezone.utc).isoformat() + ' queue-' + scenario + '\n')
    if scenario == 'native':
        sys.argv = ['native.py', *arguments]
        runpy.run_path('tests/integration/native.py', run_name='__main__')
    elif scenario == 'gate':
        out = Path(arguments[0])
        out.mkdir(parents=True, exist_ok=False)
        env = dict(os.environ, SHIELD_PYTHON=sys.executable,
                   SHIELD_GATE_RECEIPT=str(out / 'python.json'))
        result = subprocess.run(['scripts/check'], env=env).returncode
        (out / 'receipt.json').write_text(json.dumps({'scenario': scenario, 'exit': result,
            'lease': lease, 'forced': os.environ.get('IRL_SHIELD_PERF_QUEUE_FORCED') == '1',
            'scope': 'scripts/check: unified Python3.11 main+M2+M3+integration+compile',
            'cli': 'NOT RUN BY DESIGN (local-only boundary)'}, indent=2) + '\n')
        return result
    else:
        raise ValueError('Unknown integration queue scenario')


if __name__ == '__main__':
    raise SystemExit(main())
