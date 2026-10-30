"""Content-addressed evidence seals. Keep the returned digest outside the directory."""
import hashlib
import json
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def seal(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError('Evidence cannot contain symlinks')
    if (directory / 'seal.json').exists():
        raise ValueError('Evidence already sealed; create a new attempt directory')
    entries = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('Evidence cannot contain symlinks')
        if path.is_file():
            entries[path.relative_to(directory).as_posix()] = {
                'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
    body = (json.dumps({'version': 1, 'files': entries}, sort_keys=True, indent=2) + '\n').encode()
    with (directory / 'seal.json').open('xb') as output:
        output.write(body)
    for name in (*entries, 'seal.json'):
        (directory / name).chmod(0o444)
    return hashlib.sha256(body).hexdigest()


def verify(directory, expected_sha256):
    directory = Path(directory)
    if directory.is_symlink() or (directory / 'seal.json').is_symlink():
        raise ValueError('Evidence cannot contain symlinks')
    if sha256_file(directory / 'seal.json') != expected_sha256:
        raise ValueError('Seal digest mismatch')
    manifest = json.loads((directory / 'seal.json').read_text())
    if manifest.get('version') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Evidence seal schema mismatch')
    actual = set()
    for path in directory.rglob('*'):
        if path.is_symlink():
            raise ValueError('Evidence cannot contain symlinks')
        if path.is_file() and path != directory / 'seal.json':
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(manifest['files']):
        raise ValueError('Evidence inventory mismatch')
    for name, entry in manifest['files'].items():
        path = directory / name
        if (path.stat().st_size != entry['bytes'] or sha256_file(path) != entry['sha256']):
            raise ValueError('Evidence content mismatch: ' + name)
    return manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--expected-sha256', required=True,
                        help='Digest retained outside the evidence directory at capture time')
    args = parser.parse_args()
    verify(args.directory, args.expected_sha256)
    print('Evidence seal verified')


if __name__ == '__main__':
    main()
