"""Prepare lane-owned weights, borrowing only hash-verified read-only judge files."""
import argparse
from pathlib import Path
import shutil

from models.prepare import download, load_manifest, sha256_file, verified_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--judge-source-cache', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, default=Path('.tmp/fast/models'))
    parser.add_argument('--local-fast', type=Path)
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    fast = load_manifest()['artifacts']['fast-tiny']
    destination = args.cache_dir / fast['filename']
    if args.local_fast is not None and not destination.exists():
        if sha256_file(args.local_fast) != fast['sha256']:
            raise ValueError('Local FAST weight SHA-256 mismatch')
        shutil.copyfile(args.local_fast, destination)
    else:
        download('fast-tiny', args.cache_dir)
    verified_path('fast-tiny', args.cache_dir)
    cache = Path('models/cache')
    cache.mkdir(parents=True, exist_ok=True)
    for name in ('ppocr-v5-mobile', 'ppocr-v5-english-rec'):
        source, artifact = verified_path(name, args.judge_source_cache)
        target = cache / artifact['filename']
        if not target.exists():
            target.symlink_to(source)
        verified_path(name, cache)
    print('FAST weights and read-only independent PP judge weights verified')


if __name__ == '__main__':
    main()
