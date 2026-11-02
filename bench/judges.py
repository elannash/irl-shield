"""Independent OCR union with explicit, cached input/output evidence."""
from contextlib import ExitStack
import hashlib
import json
import os
import platform
import re
import subprocess
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import cv2
import pytesseract
from pytesseract import Output

from bench.vision import Vision


CACHE_SOURCES=('bench/judges.py','bench/vision.py','bench/onnx_detectors.py',
               'Sources/VisionBridge/main.swift','models/manifest.json')


def tesseract_data_identity():
    command=[pytesseract.pytesseract.tesseract_cmd,'--list-langs']
    try:
        listing=subprocess.check_output(command,text=True,stderr=subprocess.STDOUT,timeout=30)
    except (OSError,subprocess.SubprocessError) as error:
        raise RuntimeError(f'Could not discover active Tesseract tessdata using {command!r}') from error
    directories=re.findall(r'^List of available languages in "(.+)" \(\d+\):$',listing,re.MULTILINE)
    if len(directories)!=1:
        raise RuntimeError('Tesseract --list-langs did not report exactly one active tessdata directory')
    directory=Path(directories[0])
    if 'eng' not in listing.splitlines():
        raise FileNotFoundError(f'Tesseract did not list eng in active tessdata directory {directory}')
    language=(directory/'eng.traineddata').resolve(strict=True)
    return {'language':'eng','path':str(language),'sha256':hashlib.sha256(language.read_bytes()).hexdigest()}


def runtime_identity():
    try:
        ort_version=version('onnxruntime')
    except PackageNotFoundError:
        ort_version=version('onnxruntime-gpu')
    opencv_versions={}
    for name in ('opencv-python-headless','opencv-python',
                 'opencv-contrib-python-headless','opencv-contrib-python'):
        try:
            opencv_versions[name]=version(name)
        except PackageNotFoundError:
            continue
    if not opencv_versions:
        raise PackageNotFoundError('No installed OpenCV distribution found')
    return {'tesseract_binary':str(pytesseract.get_tesseract_version()),
            'tesseract_data':tesseract_data_identity(),
            'pytesseract':version('pytesseract'),'onnxruntime':ort_version,
            'rapidocr':version('rapidocr'),'opencv':opencv_versions,
            'macos_product_version':subprocess.check_output(['sw_vers','-productVersion'],text=True).strip()
                if platform.system()=='Darwin' else None}


def cache_identity():
    root=Path(__file__).resolve().parents[1]
    identity={'schema_version':3,'runtime':runtime_identity(),
              'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in CACHE_SOURCES}}
    signature=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).digest()
    return signature,identity


class Judges:
    def __init__(self, detector, cache):
        self.signature,identity=cache_identity()
        self.metadata={'cache_signature':self.signature.hex(),'cache_identity':identity}
        with ExitStack() as resources:
            self.vision = Vision('vision-accurate')
            resources.callback(self.vision.close)
            from bench.onnx_detectors import create_recognizer
            self.paddle = create_recognizer({})
            if self.paddle:
                resources.callback(self.paddle.close)
            self.cache = Path(cache)
            self.cache.mkdir(parents=True, exist_ok=True)
            self.names = ['tesseract-5-psm11', 'vision-accurate'] + (['ppocr-independent'] if self.paddle else [])
            resources.pop_all()

    def preflight(self):
        """Exercise every reader on synthetic pixels without consulting the cache."""
        if set(self.names) != {'tesseract-5-psm11', 'vision-accurate', 'ppocr-independent'}:
            raise RuntimeError('Heldout grading requires all three independent readers')
        if platform.system() == 'Darwin':
            expected = subprocess.check_output(['getconf', 'DARWIN_USER_TEMP_DIR'], text=True, timeout=5).strip()
            if not expected or os.environ.get('TMPDIR') != expected:
                raise RuntimeError('Darwin grading TMPDIR must equal DARWIN_USER_TEMP_DIR')
        import numpy as np
        probe = np.full((96, 384, 3), 255, dtype=np.uint8)
        cv2.putText(probe, 'SHIELD READY 123', (8, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        pytesseract.image_to_data(probe, lang='eng', config='--psm 11', output_type=Output.DICT, timeout=30)
        self.vision.read(probe)
        self.paddle.read(probe)

    def read(self, frame):
        digest = hashlib.sha256(frame.tobytes()+str((frame.shape,str(frame.dtype))).encode()+'|'.join(self.names).encode()+self.signature).hexdigest()
        path = self.cache / f'{digest}.json'
        if path.exists():
            return json.loads(path.read_text())
        data = pytesseract.image_to_data(frame, lang='eng', config='--psm 11', output_type=Output.DICT, timeout=30)
        result = []
        for i, word in enumerate(data['text']):
            if word.strip() and float(data['conf'][i]) >= 50:
                x, y, w, h = (int(data[k][i]) for k in ['left', 'top', 'width', 'height'])
                result.append({'text': word, 'confidence': float(data['conf'][i])/100,
                               'box': [x,y,x+w,y+h], 'judge': 'tesseract'})
        for item in self.vision.read(frame):
            if item['confidence'] >= .5:
                result.append({**item, 'judge': 'vision-accurate'})
        if self.paddle:
            for item in self.paddle.read(frame):
                if item['confidence'] >= .5:
                    result.append({**item, 'judge': 'ppocr-independent'})
        path.write_text(json.dumps(result))
        return result

    def close(self):
        try:
            self.vision.close()
        finally:
            if self.paddle:
                self.paddle.close()
