"""Preserve independent judges' complete raw evidence; clearance stays external."""
import json
from pathlib import Path
import shutil

from .source import sha256

JUDGES = ('tesseract-5-psm11', 'vision-accurate', 'ppocr-independent')


def retain_raw(output, source_manifest, judges, human_logo_eye=None):
    """Retain root-reviewed, credential-free raw judge JSON artifacts.

    Each raw artifact includes every frame/control observation, confidence,
    unknown, empty result and error before canonical filtering. Opaque bytes
    survive even if the engine's result schema changes.
    """
    if set(judges) - set(JUDGES):
        raise ValueError('Unexpected branding judge')
    output = Path(output)
    if output.exists():
        raise ValueError('Use a fresh raw branding directory')
    prepared = {}
    for name, path in judges.items():
        path = Path(path)
        raw = json.loads(path.read_text())
        if raw['judge'] != name or raw['source_manifest_sha256'] != sha256(source_manifest):
            raise ValueError('Branding source/judge binding mismatch')
        if raw['collection_stage'] != 'raw-before-filters' or not isinstance(raw['observations'], list):
            raise ValueError('Branding requires unfiltered observations')
        prepared[name] = path
    output.mkdir(parents=True)
    files = {}
    for name, path in prepared.items():
        target = output / (name + '.json')
        shutil.copyfile(path, target)
        files[name] = {'file': target.name, 'sha256': sha256(target)}
    eye = None
    if human_logo_eye is not None:
        target = output / 'human-logo-eye.json'
        shutil.copyfile(human_logo_eye, target)
        eye = {'file': target.name, 'sha256': sha256(target)}
    result = {'schema': 'irl-shield-w8-branding-raw-v1', 'status': 'NOT CLEARED',
              'source_manifest_sha256': sha256(source_manifest), 'judges': files,
              'missing_judges': sorted(set(JUDGES) - set(files)), 'human_logo_eye': eye,
              'canonical_clearance': None,
              'note': 'Raw retention is not coverage, independence or logo clearance. Root must bind current collectors.'}
    (output / 'index.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
