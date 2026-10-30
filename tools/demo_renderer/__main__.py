"""python -m tools.demo_renderer --help"""
import argparse
import json
from pathlib import Path
import tempfile

from .evidence import EvidenceError, load_evidence, sha256, require
from .layout import Layout
from .media import encode, pictures


def export(archive, manifest, manifest_hash, evidence_hash, output):
    require(sha256(Path(archive) / 'demo-evidence.json') == evidence_hash, 'Sidecar hash mismatch')
    evidence = load_evidence(archive, manifest, manifest_hash)
    output = Path(output)
    require(output.suffix.lower() == '.mp4', 'Output must be MP4')
    require(not output.exists(), 'Refusing to overwrite export')
    report_path, poster_path = output.with_suffix('.json'), output.with_suffix('.png')
    require(not report_path.exists() and not poster_path.exists(), 'Export companion already exists')
    layout = Layout(evidence)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='demo-render-', dir=output.parent) as temporary:
        temp = Path(temporary) / 'export.mp4'
        poster_index = next((i for i, r in enumerate(evidence.timeline) if r['backward_receipt_ids']), 0)
        def images():
            for i, pair in enumerate(pictures(evidence)):
                image = layout.compose(*pair, i)
                if i == poster_index:
                    image.save(Path(temporary) / 'export.png')
                yield image
        # All output stays private scratch until every decode and identity check succeeds.
        encode(temp, images(),
               [r['source_pts'] for r in evidence.timeline], evidence.provenance['fps'])
        report = {'schema': 'irl-shield-demo-export-v1', 'evidence_kind': evidence.sidecar['evidence_kind'],
                  'execution_mode': evidence.sidecar['execution_mode'], 'audio': 'none',
                  'source_manifest_sha256': manifest_hash, 'evidence_sha256': evidence_hash,
                  'export_sha256': sha256(temp), 'frame_count': len(evidence.rows),
                  'native_performance': None, 'timeline': evidence.timeline,
                  'detections': evidence.sidecar['detections']}
        (Path(temporary) / 'export.json').write_text(json.dumps(report, indent=2)+'\n')
        temp.rename(output)
        (Path(temporary) / 'export.png').rename(poster_path)
        (Path(temporary) / 'export.json').rename(report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description='Export a provenance-pinned synthetic BEFORE alongside archived output.')
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--evidence-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = export(args.archive, args.source_manifest, args.manifest_sha256, args.evidence_sha256, args.output)
    except (EvidenceError, OSError, ValueError) as error:
        parser.exit(2, f'demo-renderer: {error}\n')
    print(json.dumps({'output': str(args.output), 'frames': report['frame_count'],
                      'evidence_kind': report['evidence_kind'], 'execution_mode': report['execution_mode']}))


if __name__ == '__main__':
    main()
