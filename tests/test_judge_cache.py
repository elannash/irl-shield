"""Identical pixels hit only when every judge runtime input is unchanged."""
from contextlib import ExitStack
from importlib.metadata import PackageNotFoundError
import os
from subprocess import check_output, CalledProcessError, TimeoutExpired
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from bench.judges import Judges


class Reader:
    def __init__(self, *args, **kwargs):
        self.closed = False

    def read(self, frame):
        return []

    def close(self):
        self.closed = True


class JudgeCache(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.cache = self.root / 'cache'
        self.tessdata = self.root / 'active tessdata'
        self.tessdata.mkdir()
        self.language = self.tessdata / 'eng.traineddata'
        self.language.write_bytes(b'original English language data\n')
        self.versions = {'pytesseract': '0.3.13', 'onnxruntime': '1.31.1',
                         'rapidocr': '3.10.0', 'opencv-python-headless': '4.11.0.86'}
        self.product_version = '27.0\n'
        self.language_listing = None
        stack.enter_context(patch('bench.judges.Vision', Reader))
        self.recognizer = stack.enter_context(patch('bench.onnx_detectors.create_recognizer', side_effect=Reader))
        data = {'text': ['ELM'], 'conf': ['99'], 'left': [1], 'top': [2], 'width': [20], 'height': [10]}
        self.ocr = stack.enter_context(patch('bench.judges.pytesseract.image_to_data', return_value=data))
        self.binary = stack.enter_context(patch('bench.judges.pytesseract.get_tesseract_version', return_value='5.5.4'))
        stack.enter_context(patch('bench.judges.pytesseract.pytesseract.tesseract_cmd', '/configured/bin/tesseract'))
        stack.enter_context(patch('bench.judges.version', side_effect=self.distribution_version))
        stack.enter_context(patch('bench.judges.platform.system', return_value='Linux'))
        self.command = stack.enter_context(patch('bench.judges.subprocess.check_output', side_effect=self.command_output))
        self.pixels = np.zeros((32, 32, 3), np.uint8)

    def distribution_version(self, name):
        if name not in self.versions:
            raise PackageNotFoundError(name)
        return self.versions[name]

    def command_output(self, command, **kwargs):
        if command == ['getconf', 'DARWIN_USER_TEMP_DIR']:
            return '/synthetic/os-temp/\n'
        if command == ['/configured/bin/tesseract', '--list-langs']:
            if self.language_listing is not None:
                return self.language_listing
            return f'List of available languages in "{self.tessdata}" (1):\neng\n'
        if command == ['sw_vers', '-productVersion']:
            return self.product_version
        self.fail(f'Unexpected native command: {command!r}')

    def read_once(self, pixels=None):
        reader = Judges('ppocr-v6-small', self.cache)
        try:
            return reader.read(self.pixels if pixels is None else pixels)
        finally:
            reader.close()

    def test_tesseract_upgrade_misses_cache_but_identical_environment_hits(self):
        first = self.read_once()
        self.assertEqual(self.read_once(), first)
        self.assertEqual(self.ocr.call_count, 1)
        self.binary.return_value = '5.5.5'
        self.read_once()
        self.assertEqual(self.ocr.call_count, 2)

    def test_readiness_bypasses_cache_and_exercises_every_reader(self):
        reader = Judges('ppocr-v6-small', self.cache)
        try:
            reader.read(self.pixels)
            before = set(self.cache.iterdir())
            self.ocr.reset_mock()
            with patch.object(reader.vision, 'read', wraps=reader.vision.read) as vision, \
                    patch.object(reader.paddle, 'read', wraps=reader.paddle.read) as paddle:
                reader.preflight()
                reader.preflight()
                self.assertEqual(self.ocr.call_count, 2)
                self.assertEqual(vision.call_count, 2)
                self.assertEqual(paddle.call_count, 2)
                self.assertEqual(set(self.cache.iterdir()), before)
                paddle.side_effect = RuntimeError('synthetic recognizer unavailable')
                with self.assertRaisesRegex(RuntimeError, 'recognizer unavailable'):
                    reader.preflight()
        finally:
            reader.close()

    def test_darwin_readiness_requires_the_os_temp_directory(self):
        reader = Judges('ppocr-v6-small', self.cache)
        try:
            with patch('bench.judges.platform.system', return_value='Darwin'):
                for value in (None, '/synthetic/wrong-temp/'):
                    with self.subTest(value=value), patch.dict(os.environ):
                        if value is None:
                            os.environ.pop('TMPDIR', None)
                        else:
                            os.environ['TMPDIR'] = value
                        with self.assertRaisesRegex(RuntimeError, 'TMPDIR must equal'):
                            reader.preflight()
                        self.ocr.assert_not_called()
                with patch.dict(os.environ, {'TMPDIR': '/synthetic/os-temp/'}):
                    self.ocr.reset_mock()
                    reader.preflight()
                    self.assertEqual(self.ocr.call_count, 1)
        finally:
            reader.close()

    def test_each_runtime_version_and_macos_product_change_misses_cache(self):
        with patch('bench.judges.platform.system', return_value='Darwin'):
            self.read_once(); self.read_once()
            self.assertEqual(self.ocr.call_count, 1)
            for count, name in enumerate(('pytesseract', 'onnxruntime', 'rapidocr'), 2):
                self.versions[name] += '-upgrade'
                self.read_once()
                self.assertEqual(self.ocr.call_count, count)
            self.product_version = '27.1\n'
            self.read_once()
            self.assertEqual(self.ocr.call_count, 5)

    def test_opencv_distribution_upgrade_alone_misses_cache(self):
        del self.versions['opencv-python-headless']
        for distribution in ('opencv-python-headless', 'opencv-python',
                             'opencv-contrib-python-headless', 'opencv-contrib-python'):
            with self.subTest(distribution=distribution):
                self.cache = self.root / distribution
                self.versions[distribution] = '4.11.0.86'
                self.ocr.reset_mock()
                self.read_once(); self.read_once()
                self.assertEqual(self.ocr.call_count, 1)
                self.versions[distribution] = '4.12.0.88'
                self.read_once()
                self.assertEqual(self.ocr.call_count, 2)
                del self.versions[distribution]

    def test_detector_implementation_and_pixel_shape_are_part_of_cache_identity(self):
        from bench import judges
        for name in judges.CACHE_SOURCES:
            source = self.root / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('original ' + name)
        with patch('bench.judges.__file__', str(self.root / 'bench/judges.py')):
            self.read_once(); self.read_once()
            self.assertEqual(self.ocr.call_count, 1)
            (self.root / 'bench/onnx_detectors.py').write_text('changed judge preprocessing')
            self.read_once()
            self.assertEqual(self.ocr.call_count, 2)
            self.read_once(np.zeros((16, 64, 3), np.uint8))
            self.assertEqual(self.ocr.call_count, 3)
            self.read_once(np.zeros((16, 64, 3), np.int8))
            self.assertEqual(self.ocr.call_count, 4)

    def test_active_english_data_bytes_alone_miss_with_unchanged_binary(self):
        self.read_once(); self.read_once()
        self.assertEqual(self.ocr.call_count, 1)
        historical = {path: path.read_bytes() for path in self.cache.glob('*.json')}
        self.language.write_bytes(b'replacement English language data\n')
        self.read_once()
        self.assertEqual(self.ocr.call_count, 2)
        self.assertEqual({path: path.read_bytes() for path in historical}, historical)
        self.assertEqual(len(list(self.cache.glob('*.json'))), 2)
        self.read_once()
        self.assertEqual(self.ocr.call_count, 2)

    def test_active_data_path_alone_misses_even_with_identical_bytes(self):
        self.read_once(); self.read_once()
        self.assertEqual(self.ocr.call_count, 1)
        other = self.root / 'other tessdata'
        other.mkdir()
        (other / 'eng.traineddata').write_bytes(self.language.read_bytes())
        self.tessdata = other
        self.read_once()
        self.assertEqual(self.ocr.call_count, 2)
        self.read_once()
        self.assertEqual(self.ocr.call_count, 2)

    def test_constructor_failure_closes_started_judges(self):
        vision = Reader()
        self.recognizer.side_effect = RuntimeError('recognizer setup failed')
        with patch('bench.judges.Vision', return_value=vision):
            with self.assertRaisesRegex(RuntimeError, 'recognizer setup failed'):
                Judges('ppocr-v6-small', self.cache)
        self.assertTrue(vision.closed)

        vision, paddle = Reader(), Reader()
        self.recognizer.side_effect = None
        self.recognizer.return_value = paddle
        self.cache.write_text('not a directory')
        with patch('bench.judges.Vision', return_value=vision):
            with self.assertRaises(FileExistsError):
                Judges('ppocr-v6-small', self.cache)
        self.assertTrue(vision.closed)
        self.assertTrue(paddle.closed)

        vision, paddle = Reader(), Reader()
        with patch('bench.judges.Vision', return_value=vision), \
                patch('bench.onnx_detectors.create_recognizer', return_value=paddle):
            reader = Judges('ppocr-v6-small', self.root / 'close-cache')
        with patch.object(vision, 'close', side_effect=RuntimeError('synthetic Vision close failure')):
            with self.assertRaisesRegex(RuntimeError, 'Vision close failure'):
                reader.close()
        self.assertTrue(paddle.closed)

    def test_configured_cli_inherits_prefix_and_reports_canonical_data_path(self):
        executable = self.root / 'configured tesseract'
        executable.write_text(f'''#!{sys.executable}
import os
from pathlib import Path
import sys
assert sys.argv[1:] == ['--list-langs'], 'Only read-only language discovery is allowed'
directory = Path(os.environ.get('TESSDATA_PREFIX', {str(self.tessdata)!r}))
if not directory.exists():
    directory = Path({str(self.tessdata)!r})
print(f'List of available languages in "{{directory}}" (1):')
print('eng')
''')
        executable.chmod(0o700)
        alternate = self.root / 'prefix tessdata'
        alternate.mkdir()
        (alternate / 'eng.traineddata').symlink_to(self.language)
        with patch('bench.judges.pytesseract.pytesseract.tesseract_cmd', str(executable)), \
             patch('bench.judges.subprocess.check_output', wraps=check_output), \
             patch.dict(os.environ, {'TESSDATA_PREFIX': str(alternate)}):
            reader = Judges('ppocr-v6-small', self.cache)
            try:
                data = reader.metadata['cache_identity']['runtime']['tesseract_data']
                self.assertEqual(data['language'], 'eng')
                self.assertEqual(data['path'], str(self.language.resolve()))
                reader.read(self.pixels)
            finally:
                reader.close()
            self.read_once()
            self.assertEqual(self.ocr.call_count, 1)
            self.assertEqual(self.ocr.call_args.kwargs['lang'], 'eng')
            # A native CLI may ignore an invalid prefix and report its compiled default.
            os.environ['TESSDATA_PREFIX'] = str(self.root / 'nonexistent prefix')
            self.read_once()
            self.assertEqual(self.ocr.call_count, 1)

    def test_missing_or_ambiguous_language_data_fails_before_readers_start(self):
        header = f'List of available languages in "{self.tessdata}" (1):\n'
        for listing, error in (('eng\n', RuntimeError),
                               (header + 'eng\n' + header + 'eng\n', RuntimeError),
                               (header + 'fra\n', FileNotFoundError)):
            with self.subTest(listing=listing), patch('bench.judges.Vision') as vision:
                self.language_listing = listing
                with self.assertRaises(error):
                    Judges('ppocr-v6-small', self.cache)
                vision.assert_not_called()
        self.language_listing = None
        self.language.unlink()
        with patch('bench.judges.Vision') as vision:
            with self.assertRaises(FileNotFoundError) as missing:
                Judges('ppocr-v6-small', self.cache)
            self.assertIn('eng.traineddata', str(missing.exception))
            vision.assert_not_called()
        self.language.mkdir()
        with self.assertRaises(IsADirectoryError):
            Judges('ppocr-v6-small', self.cache)
        self.ocr.assert_not_called()
        self.recognizer.assert_not_called()

    def test_discovery_command_errors_preserve_their_cause(self):
        for error in (FileNotFoundError('configured executable missing'),
                      CalledProcessError(1, ['tesseract', '--list-langs']),
                      TimeoutExpired(['tesseract', '--list-langs'], 30)):
            with self.subTest(error=type(error).__name__):
                self.command.side_effect = error
                with self.assertRaisesRegex(RuntimeError, 'discover active Tesseract tessdata') as raised:
                    Judges('ppocr-v6-small', self.cache)
                self.assertIs(raised.exception.__cause__, error)
        self.recognizer.assert_not_called()
        self.ocr.assert_not_called()

    def test_gpu_ort_distribution_upgrade_misses_cache_when_cpu_not_installed(self):
        del self.versions['onnxruntime']
        self.versions['onnxruntime-gpu'] = '1.31.1'
        self.read_once(); self.read_once()
        self.assertEqual(self.ocr.call_count, 1)
        self.versions['onnxruntime-gpu'] = '1.32.0'
        self.read_once()
        self.assertEqual(self.ocr.call_count, 2)
