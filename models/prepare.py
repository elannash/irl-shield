#!/usr/bin/env python3
"""Download the reviewed, hash-pinned OCR artifacts; inference stays offline."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = ROOT / "cache"


def load_manifest():
    return json.loads((ROOT / "manifest.json").read_text())


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_path(name, cache_dir=DEFAULT_CACHE):
    artifact = load_manifest()["artifacts"][name]
    path = Path(cache_dir).expanduser().resolve() / artifact["filename"]
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {name}: {path}. Run python models/prepare.py {name} first."
        )
    actual = sha256_file(path)
    if actual != artifact["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {path}: {actual}")
    return path, artifact


def download(name, cache_dir):
    artifact = load_manifest()["artifacts"][name]
    cache_dir = Path(cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / artifact["filename"]
    if destination.exists():
        verified_path(name, cache_dir)
        return destination

    # A unique temporary name allows separate setup processes to share the cache.
    handle, temporary = tempfile.mkstemp(prefix=artifact["filename"] + ".", dir=cache_dir)
    try:
        with os.fdopen(handle, "wb") as output:
            request = urllib.request.Request(
                artifact["url"], headers={"User-Agent": "IRL-Shield-model-prepare/1"}
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(chunk)
        actual = sha256_file(temporary)
        if actual != artifact["sha256"]:
            raise ValueError(f"SHA-256 mismatch downloading {name}: {actual}")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def main():
    artifacts = load_manifest()["artifacts"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="Artifact IDs; default: all manifest artifacts")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--verify-only", action="store_true", help="Check local files without network")
    args = parser.parse_args()
    names = args.names or list(artifacts)
    unknown = set(names) - artifacts.keys()
    if unknown:
        parser.error(f"Unknown artifacts: {', '.join(sorted(unknown))}")
    for name in names:
        if args.verify_only:
            path, artifact = verified_path(name, args.cache_dir)
        else:
            path = download(name, args.cache_dir)
            artifact = artifacts[name]
        print(json.dumps({"name": name, "path": str(path), "sha256": artifact["sha256"], "bytes": path.stat().st_size}))


if __name__ == "__main__":
    main()
