"""Build the synthetic source while holding the canonical exclusive host lease."""
from pathlib import Path
import runpy
import sys


def main():
    root = Path(__file__).resolve().parents[2]
    launcher = runpy.run_path(str(root / 'scripts/walk-linux'))
    if sys.argv[1:2] != ['source']:
        raise SystemExit('W8 entry supports: source --output <fresh-directory>')
    with launcher['exclusive_lease']():
        sys.path.insert(0, str(root))
        from tools.demo_renderer.source import main as build
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        build()


if __name__ == '__main__':
    main()
