"""Local, selected-policy resource checks; no downloads or model execution.

The frozen policy pins dependencies and executables, while models/manifest.json
owns model payload identity. A cache path is a runtime binding, never a policy
override. Callers hold the host EX lease through validation and rendering.
"""
from contextlib import contextmanager
import hashlib
from importlib import metadata
from importlib import import_module
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_file(directory, name):
    root = Path(directory).resolve(strict=True)
    path = root / name
    if (not isinstance(name, str) or not name or Path(name).is_absolute()
            or '..' in Path(name).parts or not path.resolve().is_relative_to(root)):
        raise ValueError('Heldout resource escapes its bound cache')
    if not path.is_file():
        raise FileNotFoundError('Missing heldout resource: ' + str(path))
    return path.resolve(strict=True)


def payload(path, pin):
    sha = pin.get('sha256')
    size = pin.get('bytes')
    if (not isinstance(sha, str) or len(sha) != 64
            or any(c not in '0123456789abcdef' for c in sha)
            or type(size) is not int or size <= 0):
        raise ValueError('Heldout resource requires pinned SHA-256 and positive byte count')
    if Path(path).stat().st_size != size or digest(path) != sha:
        raise ValueError('Heldout resource payload differs: ' + str(path))
    return {'path': str(Path(path).resolve()), 'sha256': sha, 'bytes': size}


def selected_models(config, manifest):
    from bench.independence import resolve_fast_candidate
    candidate, options = config['candidate'], config['options']
    fast = resolve_fast_candidate(candidate, options)
    names = set() if fast is None else {candidate, fast}
    names -= {'unmasked', 'slate'}
    # Vision has a native resource contract which this Linux renderer cannot
    # prove. Unknown future detector names fail in the family registry first.
    if names - manifest['artifacts'].keys():
        raise ValueError('V3 resource adapter is unavailable for the selected detector')
    if any(manifest['artifacts'][name].get('task') != 'det' for name in names):
        raise ValueError('V3 selected detector requires a detection model resource')
    return names


def required_distributions(config, models):
    names = {'numpy', 'opencv-python-headless', 'psutil'}
    if models:
        names.update(('rapidocr', 'omegaconf', 'pyclipper', 'shapely'))
        options = config['options']
        cuda = 'cuda' in selected_providers(config, models)
        names.add('onnxruntime-gpu' if cuda else 'onnxruntime')
        if options.get('static_model'):
            names.add('onnx')
    return names


def selected_providers(config, models):
    from bench.independence import resolve_fast_candidate
    options = config['options']
    return {options.get(key, 'cpu') for model, key in (
        (config['candidate'], 'provider'), (resolve_fast_candidate(config['candidate'], options), 'fast_provider'))
        if model in models}


def dependency_check(names):
    modules = {'opencv-python-headless': 'cv2', 'onnxruntime-gpu': 'onnxruntime'}
    for name in sorted(names):
        import_module(modules.get(name, name))


def provider_check(config, models):
    if not models:
        return []
    import onnxruntime as ort
    lookup = {'cpu': 'CPUExecutionProvider', 'cuda': 'CUDAExecutionProvider', 'coreml': 'CoreMLExecutionProvider'}
    requested = selected_providers(config, models)
    if requested - lookup.keys():
        raise ValueError('Unsupported heldout execution provider')
    required = {lookup[name] for name in requested}
    if required - set(ort.get_available_providers()):
        raise ValueError('Selected heldout execution provider is unavailable')
    return sorted(required)


def encoder_check(config, executable):
    encoder = config['options'].get('encoder', 'h264_nvenc')
    if encoder not in {'h264_nvenc', 'h264_videotoolbox', 'libx264'}:
        raise ValueError('Unsupported quality encoder')
    listing = subprocess.check_output([executable, '-hide_banner', '-encoders'],
                                      text=True, stderr=subprocess.STDOUT, timeout=30)
    if not any(len(parts) >= 2 and parts[1] == encoder for parts in map(str.split, listing.splitlines())):
        raise ValueError('Selected heldout encoder is unavailable: ' + encoder)
    return encoder


def derived_requirements(config, manifest, dataset):
    if not config['options'].get('static_model') or not selected_models(config, manifest):
        return {}
    # Use the renderer's actual preprocessing on synthetic shape-only pixels.
    # No source media is opened and no detector or model session is constructed.
    import numpy as np
    from rapidocr.ch_ppocr_det.utils import DetPreProcess
    from bench.independence import resolve_fast_candidate
    options = config['options']
    result = {}
    for clip in dataset['clips']:
        height, width = clip['height'], clip['width']
        if type(height) is not int or type(width) is not int or min(height, width) < 32:
            raise ValueError('Static heldout resources require frozen clip dimensions')
        for lane, model in (('fast', resolve_fast_candidate(config['candidate'], options)),
                            ('accurate', config['candidate'])):
            if model not in manifest['artifacts']:
                continue
            lane_width = options.get(lane + '_width', 640 if lane == 'fast' else 1280) or width
            scale = lane_width / width
            small = np.zeros((int(height * scale), int(width * scale), 3), np.uint8)
            limit = options.get('fast_limit_side_len', 640) if lane == 'fast' else options.get('limit_side_len', 960)
            tensor = DetPreProcess(limit, 'max')(small)
            if tensor is None:
                raise ValueError('Static heldout preprocessing shape failed')
            h, w = map(int, tensor.shape[2:])
            derivation = {'recipe': 'ppocr-static-io-and-shape-inference-v1',
                          'source_sha256': manifest['artifacts'][model]['sha256'],
                          'height': h, 'width': w, 'onnx_version': metadata.version('onnx')}
            key = hashlib.sha256(json.dumps(derivation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            result['det-static-' + key + '.onnx'] = derivation
    return result


def preflight(root, config, dataset, model_cache):
    """Return the actual binding without persistent output or reservation state."""
    if model_cache is None:
        raise ValueError('Fresh heldout v3 requires an explicit --model-cache')
    cache = Path(model_cache).expanduser().resolve(strict=True)
    if not cache.is_dir():
        raise ValueError('Heldout model cache must be an existing directory')
    contract = config.get('resources', {})
    if (type(contract.get('schema_version')) is not int or contract['schema_version'] != 1 or set(contract) != {
            'schema_version', 'model_manifest_sha256', 'distributions', 'executables',
            'derived_models', 'option_files', 'minimum_free_bytes'}):
        raise ValueError('Fresh heldout v3 requires its pinned resource contract')
    manifest_path = Path(root) / 'models/manifest.json'
    if digest(manifest_path) != contract['model_manifest_sha256']:
        raise ValueError('Heldout model manifest differs from frozen resource contract')
    manifest = json.loads(manifest_path.read_text())
    models = selected_models(config, manifest)
    # Reserved local OCR/GGUF bindings cannot claim availability before their
    # real consumer exists. A future adapter must derive and consume these exact
    # option bindings; accepting arbitrary extra files would hide missing ones.
    if contract['option_files'] or any(key in config['options'] for key in ('local_ocr_model', 'gguf_model')):
        raise ValueError('Selected local OCR/GGUF resource adapter is not implemented')
    required = required_distributions(config, models)
    if set(contract['distributions']) != required:
        raise ValueError('Heldout dependency pins must match the selected policy exactly')
    for name, version in contract['distributions'].items():
        if not isinstance(version, str) or not version or metadata.version(name) != version:
            raise ValueError('Heldout dependency differs from frozen resource contract: ' + name)
    dependency_check(required)
    # Co-installed CPU/GPU wheels can resolve the wrong native runtime.
    alternate = 'onnxruntime' if 'onnxruntime-gpu' in required else 'onnxruntime-gpu'
    if models:
        try:
            metadata.version(alternate)
        except metadata.PackageNotFoundError:
            pass
        else:
            raise ValueError('Conflicting heldout ONNX Runtime distributions')
    if set(contract['executables']) != {'ffmpeg', 'ffprobe'}:
        raise ValueError('Heldout resources require exactly ffmpeg and ffprobe pins')
    executables = {}
    for name, pin in contract['executables'].items():
        path = shutil.which(name)
        if path is None:
            raise FileNotFoundError('Missing heldout executable: ' + name)
        executables[name] = payload(path, pin)
    files = {name: payload(checked_file(cache, manifest['artifacts'][name]['filename']),
                           manifest['artifacts'][name]) for name in sorted(models)}
    derived = derived_requirements(config, manifest, dataset)
    if set(contract['derived_models']) != set(derived):
        raise ValueError('Heldout derived model pins must match selected shapes exactly')
    for name, derivation in derived.items():
        pin = contract['derived_models'][name]
        if pin.get('derivation') != derivation:
            raise ValueError('Heldout derived model recipe differs: ' + name)
        files[name] = payload(checked_file(cache, name), pin)
    minimum = contract['minimum_free_bytes']
    if type(minimum) is not int or minimum <= 0:
        raise ValueError('Heldout resources require a positive output free-space reservation')
    providers = provider_check(config, models)
    if 'CoreMLExecutionProvider' in providers:
        writable_destination(cache / 'coreml-compiled/preflight', 1)
    return {'model_cache': str(cache), 'files': files, 'executables': executables,
            'distributions': dict(contract['distributions']), 'providers': providers,
            'encoder': encoder_check(config, executables['ffmpeg']['path']),
            'minimum_free_bytes': minimum}


def writable_destination(path, minimum_free_bytes):
    """Exercise write/fsync in the existing ancestor before reserving a start."""
    path = Path(path).resolve()
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    if (not parent.is_dir() or not parent.stat().st_mode & 0o222
            or not os.access(parent, os.W_OK | os.X_OK)):
        raise ValueError('Heldout output/state ancestor is not writable: ' + str(parent))
    if shutil.disk_usage(parent).free < minimum_free_bytes:
        raise ValueError('Insufficient heldout output/state free space: ' + str(parent))
    with tempfile.TemporaryFile(dir=parent) as stream:
        stream.write(b'heldout preflight\n')
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def model_cache_binding(binding):
    """Bind the cache used by _session, static derivation and CoreML compilation.

    The legacy lane factory filters cache_dir out of options. Scope its actual
    module default under the caller's EX lease rather than pretending an ignored
    option reaches that factory. All prior defaults are restored even on failure.
    """
    if not binding['files']:
        yield
        return
    from bench import onnx_detectors
    previous = onnx_detectors.DEFAULT_CACHE
    onnx_detectors.DEFAULT_CACHE = Path(binding['model_cache'])
    try:
        yield
    finally:
        onnx_detectors.DEFAULT_CACHE = previous
