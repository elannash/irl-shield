"""Fail clearly before starting a persistent Mac OCR judge process."""
import hashlib
import importlib
import os
from pathlib import Path
import platform
import sys


def check_environment(root, expected_python, tesseract):
    root, expected_python, tesseract = map(Path, (root, expected_python, tesseract))
    if platform.system() != 'Darwin' or sys.version_info[:2] != (3, 11):
        raise RuntimeError('Synthetic skin OCR requires the scheduled macOS CPython3.11 SDK')
    if os.path.abspath(sys.executable) != str(expected_python):
        raise RuntimeError('OCR interpreter differs from the immutable queue packet')
    prefix = expected_python.parent.parent
    if Path(sys.prefix) != prefix or os.environ.get('PYTHONPATH'):
        raise RuntimeError('OCR needs the isolated SDK without PYTHONPATH overlays')
    cfg = (prefix/'pyvenv.cfg').read_text().lower().replace(' ', '')
    if 'include-system-site-packages=false' not in cfg:
        raise RuntimeError('OCR SDK permits system site packages')
    for item in sys.path:
        if 'site-packages' in Path(item).parts and not Path(item).is_relative_to(prefix):
            raise RuntimeError('OCR has a site-packages overlay outside the pinned SDK')
    modules = {}
    for name in ('numpy', 'cv2', 'onnxruntime', 'rapidocr', 'omegaconf', 'pytesseract', 'psutil'):
        try:
            module = importlib.import_module(name)
        except ImportError as error:
            raise RuntimeError(f'OCR SDK dependency missing: {name}') from error
        location = Path(module.__file__)
        if not location.is_relative_to(prefix):
            raise RuntimeError(f'OCR dependency is outside the pinned SDK: {name}')
        modules[name] = {'path': str(location), 'version': getattr(module, '__version__', 'not exposed')}
    import cv2
    import onnxruntime as ort
    import pytesseract
    cv2.setNumThreads(1)
    providers = ort.get_available_providers()
    if 'CPUExecutionProvider' not in providers:
        raise RuntimeError('Independent Paddle judge requires CPUExecutionProvider; no provider fallback')
    if not tesseract.is_file() or not os.access(tesseract, os.X_OK):
        raise RuntimeError('Packet Tesseract executable is unavailable')
    pytesseract.pytesseract.tesseract_cmd = str(tesseract)
    bridge = root/'.build/vision-bridge'
    if not bridge.is_file() or not os.access(bridge, os.X_OK):
        raise RuntimeError('Dedicated W5 mirror has no executable persistent Vision bridge')
    from models.prepare import DEFAULT_CACHE, verified_path
    cache = root/'models/cache'
    if DEFAULT_CACHE != cache or cache.resolve() != cache:
        raise RuntimeError('OCR model cache must be owned inside the dedicated W5 mirror')
    artifacts = {}
    for name in ('ppocr-v5-mobile', 'ppocr-v5-english-rec'):
        path, entry = verified_path(name, cache)
        if path.parent != cache or path.is_symlink():
            raise RuntimeError('OCR models must be local files inside the W5 cache')
        artifacts[name] = {'path': str(path), 'sha256': entry['sha256'], 'license': entry['license']}
    return {'python': sys.executable, 'prefix': str(prefix), 'modules': modules,
            'available_providers': providers, 'requested_independent_provider': 'CPUExecutionProvider',
            'model_artifacts': artifacts, 'tesseract': str(tesseract),
            'vision_bridge_sha256': hashlib.sha256(bridge.read_bytes()).hexdigest(),
            'model_manifest_sha256': hashlib.sha256((root/'models/manifest.json').read_bytes()).hexdigest()}
