"""Selected local resources, using synthetic payloads and external discovery fakes."""
import hashlib
import json
from importlib import metadata
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bench import heldout_resources as resources


class ResourceFixture:
    """Provide tiny owned files; never consult a user's model cache or HOME."""
    def provision_resources(self, root):
        self.model_cache = root / 'models/cache'
        self.model_cache.mkdir(parents=True)
        artifacts = {}
        for name in ('ppocr-v6-tiny', 'ppocr-v6-small', 'ppocr-v5-server'):
            data = ('synthetic model: ' + name).encode()
            pin = {'filename': name + '.onnx', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'task': 'det'}
            artifacts[name] = pin
            # Unselected server deliberately has no payload.
            if name != 'ppocr-v5-server':
                (self.model_cache / pin['filename']).write_bytes(data)
        manifest = root / 'models/manifest.json'
        manifest.write_text(json.dumps({'schema_version': 1, 'artifacts': artifacts}) + '\n')
        self.versions = {name: 'synthetic-1' for name in (
            'numpy', 'opencv-python-headless', 'psutil', 'onnxruntime',
            'rapidocr', 'omegaconf', 'pyclipper', 'shapely')}
        self.executables = {}
        pins = {}
        for name in ('ffmpeg', 'ffprobe'):
            path = root / 'tools' / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('#!/bin/sh\nexit 91\n# synthetic ' + name + '\n')
            path.chmod(0o755)
            self.executables[name] = str(path)
            pins[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
        self.resource_contract = {'schema_version': 1, 'model_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'distributions': dict(self.versions), 'executables': pins, 'derived_models': {},
            'minimum_free_bytes': 1}
        def version(name):
            if name not in self.versions:
                raise metadata.PackageNotFoundError(name)
            return self.versions[name]
        self.real_provider_check = resources.provider_check
        self.real_encoder_check = resources.encoder_check
        for override in (
                patch.object(resources, 'metadata', SimpleNamespace(version=version, PackageNotFoundError=metadata.PackageNotFoundError)),
                patch.object(resources.shutil, 'which', side_effect=lambda name: self.executables.get(name)),
                patch.object(resources, 'import_module', return_value=SimpleNamespace()),
                patch.object(resources, 'provider_check', return_value=['CPUExecutionProvider']),
                patch.object(resources, 'encoder_check', side_effect=lambda config, executable: 'libx264')):
            override.start()
            self.addCleanup(override.stop)
        return self.resource_contract


class HeldoutResources(ResourceFixture, unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        contract = self.provision_resources(self.root)
        self.config = {'candidate': 'ppocr-v6-small', 'options': {'encoder': 'libx264'}, 'resources': contract}
        self.dataset = {'clips': [{'id': 'synthetic', 'width': 64, 'height': 64}]}

    def preflight(self, **changes):
        args = dict(root=self.root, config=self.config, dataset=self.dataset, model_cache=self.model_cache)
        return resources.preflight(**{**args, **changes})

    def test_only_selected_models_are_required_and_pinned(self):
        binding = self.preflight()
        self.assertEqual(set(binding['files']), {'ppocr-v6-tiny', 'ppocr-v6-small'})
        self.assertEqual(binding['model_cache'], str(self.model_cache.resolve()))
        for name, row in binding['files'].items():
            self.assertEqual(row['path'], str(self.model_cache / (name + '.onnx')))
            self.assertEqual(row['sha256'], hashlib.sha256(('synthetic model: ' + name).encode()).hexdigest())
        self.assertFalse((self.model_cache / 'ppocr-v5-server.onnx').exists())
        self.config['candidate'] = 'ppocr-v5-server'
        with self.assertRaisesRegex(FileNotFoundError, 'Missing heldout resource'):
            self.preflight()

    def test_resource_pins_and_cache_containment_cannot_be_rebound(self):
        original = json.dumps(self.config)
        for fault, message in (('manifest', 'model manifest differs'), ('dependency', 'dependency differs'),
                               ('executable', 'resource payload differs'), ('derived', 'derived model pins must match')):
            with self.subTest(fault=fault):
                self.config = json.loads(original)
                contract = self.config['resources']
                if fault == 'manifest':
                    contract['model_manifest_sha256'] = '0' * 64
                elif fault == 'dependency':
                    contract['distributions']['numpy'] = 'wrong-version'
                elif fault == 'executable':
                    contract['executables']['ffmpeg']['sha256'] = '0' * 64
                else:
                    contract['derived_models']['unselected.onnx'] = {}
                with self.assertRaisesRegex(ValueError, message):
                    self.preflight()
        self.config = json.loads(original)
        tiny = self.model_cache / 'ppocr-v6-tiny.onnx'
        outside = self.root / 'outside-cache.onnx'
        tiny.rename(outside)
        tiny.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'resource escapes its bound cache'):
            self.preflight()

    def test_missing_native_provider_and_conflicting_runtime_refuse(self):
        self.config['options']['provider'] = 'cuda'
        del self.versions['onnxruntime']
        self.versions['onnxruntime-gpu'] = 'synthetic-1'
        self.resource_contract['distributions'] = dict(self.versions)
        with patch.object(resources, 'provider_check', self.real_provider_check), \
                patch.dict(sys.modules, {'onnxruntime': SimpleNamespace(get_available_providers=lambda: ['CPUExecutionProvider'])}):
            with self.assertRaisesRegex(ValueError, 'execution provider is unavailable'):
                self.preflight()
        self.versions['onnxruntime'] = 'synthetic-1'
        with self.assertRaisesRegex(ValueError, 'Conflicting heldout ONNX'):
            self.preflight()

    def test_unrecognized_resource_fields_are_rejected(self):
        self.config['resources']['unsupported_resource'] = {}
        with self.assertRaisesRegex(ValueError, 'requires its pinned resource contract'):
            self.preflight()

    def test_static_shape_resources_are_required_before_model_sessions(self):
        self.config['options'].update(static_model=True, fast_width=64, accurate_width=64,
                                      fast_limit_side_len=64, limit_side_len=64)
        self.versions['onnx'] = 'synthetic-onnx'
        self.resource_contract['distributions'] = dict(self.versions)
        with self.assertRaisesRegex(ValueError, 'derived model pins must match selected shapes exactly'):
            self.preflight()
        # A worked 64x64 preprocessing result, pinned by the documented recipe.
        manifest = json.loads((self.root / 'models/manifest.json').read_text())
        for name in ('ppocr-v6-small', 'ppocr-v6-tiny'):
            derivation = {'recipe': 'ppocr-static-io-and-shape-inference-v1',
                'source_sha256': manifest['artifacts'][name]['sha256'],
                'height': 64, 'width': 64, 'onnx_version': 'synthetic-onnx'}
            key = hashlib.sha256(json.dumps(derivation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            data = ('synthetic derived ' + name).encode()
            filename = 'det-static-' + key + '.onnx'
            self.resource_contract['derived_models'][filename] = {
                'derivation': derivation, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            (self.model_cache / filename).write_bytes(data)
        self.assertEqual(len(self.preflight()['files']), 4)
        (self.model_cache / filename).write_bytes(b'x' * len(data))
        with self.assertRaisesRegex(ValueError, 'resource payload differs'):
            self.preflight()

    def test_encoder_listing_must_contain_selected_encoder(self):
        with patch.object(resources.subprocess, 'check_output', return_value=' V..... libx264 synthetic\n') as command:
            self.assertEqual(self.real_encoder_check(self.config, '/synthetic/ffmpeg'), 'libx264')
            self.assertEqual(command.call_args.args[0], ['/synthetic/ffmpeg', '-hide_banner', '-encoders'])
        with patch.object(resources.subprocess, 'check_output', return_value=' V..... unrelated synthetic\n'):
            with self.assertRaisesRegex(ValueError, 'encoder is unavailable: libx264'):
                self.real_encoder_check(self.config, '/synthetic/ffmpeg')
