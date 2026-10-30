"""Inventory installed distribution license notices without exporting credentials."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for distribution in sorted(distributions(), key=lambda item: item.metadata['Name'].lower()):
        metadata = distribution.metadata
        notices = []
        for path in distribution.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in path.parts):
                file = Path(distribution.locate_file(path))
                if file.is_file():
                    notices.append({'path': str(file), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
        rows.append({'name': metadata['Name'], 'version': distribution.version,
                     'license_expression': metadata.get('License-Expression'),
                     'license_classifiers': [value for value in metadata.get_all('Classifier', [])
                                             if value.startswith('License')],
                     'license_metadata': metadata.get('License'),
                     'project_urls': metadata.get_all('Project-URL', []), 'notices': notices})
    args.output.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'inventory': str(args.output), 'distributions': len(rows)}))


if __name__ == '__main__':
    main()
