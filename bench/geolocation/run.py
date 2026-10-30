"""Queued, offline Mac MPS inference. Importing this module loads no ML SDK."""
import argparse
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import time

from .protocol import read_json, registration, sha256, verify_plan, write_new


def verify_environment(path):
    receipt = read_json(path)
    if receipt['status'] != 'license_verified':
        raise ValueError('Optional environment license closure is not verified')
    installed = {d.metadata['Name'].lower().replace('_', '-'): d.version
                 for d in metadata.distributions()}
    approved = receipt['distributions']
    if set(installed) != set(approved):
        raise ValueError('Environment distributions changed since license review')
    for name, version in installed.items():
        record = approved[name]
        if (record['version'] != version or not record['license_source']
                or record['license'] not in ('MIT', 'BSD-2-Clause', 'BSD-3-Clause',
                    'Apache-2.0', 'ISC', 'PSF-2.0', 'HPND', 'MPL-2.0', 'Zlib')):
            raise ValueError('Environment license/version not approved: ' + name)
    if installed.get('geoclip') != '1.3.0':
        raise ValueError('This adapter requires the reviewed GeoCLIP 1.3.0 API')
    return receipt


def verify_model_assets(manifest, release, backbone):
    for folder, artifacts in ((release, manifest['geoclip']['artifacts']),
                              (backbone, manifest['backbone']['artifacts'])):
        for artifact in artifacts:
            if sha256(Path(folder) / artifact['file']) != artifact['sha256']:
                raise ValueError('Model artifact differs from license manifest: ' + artifact['file'])


def run(args):
    if platform.system() != 'Darwin' or args.device != 'mps':
        raise RuntimeError('Model execution is restricted to the queued Mac MPS slot')
    # Queue authorization is supplied by the conductor, never inferred here.
    if not os.environ.get('W9_EX_SLOT_RECEIPT'):
        raise RuntimeError('Missing conductor EX slot receipt reference')
    for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE'):
        if os.environ.get(name) != '1':
            raise RuntimeError(name + '=1 is required; input images must stay local')
    data = registration(args.preregistration)
    plan = verify_plan(args.plan, args.preregistration, args.root)
    manifest = read_json(args.model_manifest)
    if sha256(args.model_manifest) != data['model_manifest_sha256']:
        raise ValueError('Model selection changed after preregistration')
    verify_environment(args.environment_receipt)
    verify_model_assets(manifest, args.release, args.backbone)
    # Optional imports happen only after host, license, scope and input guards.
    import torch
    import torch.nn.functional as functional
    from PIL import Image
    from geoclip import GeoCLIP
    from geoclip.model._hub import load_geoclip_weights, read_gallery, read_release

    torch.set_num_threads(2)
    if not torch.backends.mps.is_available():
        raise RuntimeError('MPS is unavailable; CPU/CUDA fallback is forbidden')
    if Path(args.output).exists():
        raise FileExistsError('Prediction receipt already exists; retain prior attempts')
    result = {'schema_version': 1, 'plan_sha256': sha256(args.plan),
              'model_manifest_sha256': sha256(args.model_manifest),
              'environment_receipt_sha256': sha256(args.environment_receipt),
              'ex_slot_receipt': os.environ['W9_EX_SLOT_RECEIPT'],
              'device': 'mps', 'rows': [], 'setup_seconds': None, 'status': 'starting'}
    # This file is append-only. An interrupted run retains its started/error rows.
    journal_path = Path(args.output + '.jsonl')
    with journal_path.open('x') as journal:
        def event(value):
            journal.write(json.dumps(value, allow_nan=False) + '\n')
            journal.flush()

        event({'event': 'start', **result})
        try:
            started = time.perf_counter()
            torch.manual_seed(0)
            release, config, weights = read_release(args.release, 'geoclip-geolocation')
            model = GeoCLIP(from_pretrained=False, clip_path=str(Path(args.backbone).resolve()))
            model.gps_gallery = read_gallery(release, config)
            load_geoclip_weights(model, weights)
            model = model.eval().to('mps')
            # Encode the fixed gallery in bounded batches on the M1 Pro.
            with torch.inference_mode():
                features = torch.cat([functional.normalize(model.location_encoder(chunk), dim=1)
                                      for chunk in model.gps_gallery.split(512)])
            torch.mps.synchronize()
            result['setup_seconds'] = time.perf_counter() - started
            gallery = model.gps_gallery.cpu().tolist()
            pairs = {p['id']: p for p in plan['pairs']['pairs']}
            for sample in data['samples']:
                pair = pairs[sample['id']]
                for arm in ('raw', 'shielded'):
                    row = {'id': sample['id'], 'arm': arm, 'frame_sha256': pair[arm]['sha256']}
                    event({'event': 'prediction_start', **row})
                    started = time.perf_counter()
                    try:
                        path = Path(args.root) / pair[arm]['path']
                        if sha256(path) != pair[arm]['sha256']:
                            raise ValueError('Frame changed since input freeze')
                        with Image.open(path) as image:
                            pixels = model.image_encoder.preprocess_image(image.convert('RGB')).to('mps')
                        with torch.inference_mode():
                            embedding = functional.normalize(model.image_encoder(pixels), dim=1)
                            scores = (embedding @ features.T).squeeze(0).cpu()
                        if not bool(torch.isfinite(scores).all()):
                            raise ValueError('Non-finite model output')
                        # Stable sorting preserves gallery order for equal scores.
                        ranked = torch.argsort(scores, descending=True, stable=True).tolist()
                        candidates, seen = [], set()
                        for index in ranked:
                            point = gallery[index]
                            if tuple(point) in seen:
                                continue
                            candidates.append(point)
                            seen.add(tuple(point))
                            if len(candidates) == max(data['top_k']):
                                break
                        if len(candidates) != max(data['top_k']):
                            raise ValueError('Candidate bank has too few unique coordinates')
                        torch.mps.synchronize()
                        row.update(status='ok', candidates=candidates,
                                   seconds=time.perf_counter() - started)
                    except Exception as error:
                        row.update(status='failed', error_type=type(error).__name__,
                                   error=str(error), seconds=None)
                    result['rows'].append(row)
                    event({'event': 'prediction_end', **row})
            result['status'] = 'complete' if all(r['status'] == 'ok' for r in result['rows']) else 'incomplete'
        except Exception as error:
            result.update(status='failed', error_type=type(error).__name__, error=str(error))
            event({'event': 'setup_or_run_failed', **result})
            raise
        finally:
            write_new(args.output, result)
    return 0 if result['status'] == 'complete' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preregistration', required=True)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--model-manifest', required=True)
    parser.add_argument('--environment-receipt', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--backbone', required=True)
    parser.add_argument('--device', choices=('mps',), required=True)
    parser.add_argument('--output', required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
