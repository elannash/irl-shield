"""Independent OCR union with explicit, cached input/output evidence."""
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import cv2
import pytesseract
from pytesseract import Output

from bench.vision import Vision


CACHE_SOURCES=('bench/judges.py','bench/vision.py','bench/onnx_detectors.py',
               'Sources/VisionBridge/main.swift','models/manifest.json')


def runtime_identity():
    try:
        ort_version=version('onnxruntime')
    except PackageNotFoundError:
        ort_version=version('onnxruntime-gpu')
    return {'tesseract_binary':str(pytesseract.get_tesseract_version()),
            'pytesseract':version('pytesseract'),'onnxruntime':ort_version,
            'rapidocr':version('rapidocr'),
            'macos_product_version':subprocess.check_output(['sw_vers','-productVersion'],text=True).strip()
                if platform.system()=='Darwin' else None}


def cache_identity():
    root=Path(__file__).resolve().parents[1]
    identity={'schema_version':2,'runtime':runtime_identity(),
              'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in CACHE_SOURCES}}
    signature=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).digest()
    return signature,identity


class Judges:
    def __init__(self, detector, cache):
        self.signature,identity=cache_identity()
        self.metadata={'cache_signature':self.signature.hex(),'cache_identity':identity}
        self.vision = Vision('vision-accurate')
        from bench.onnx_detectors import create_recognizer
        self.paddle = create_recognizer({})
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.names = ['tesseract-5-psm11', 'vision-accurate'] + (['ppocr-independent'] if self.paddle else [])

    def read(self, frame):
        digest = hashlib.sha256(frame.tobytes()+str((frame.shape,str(frame.dtype))).encode()+'|'.join(self.names).encode()+self.signature).hexdigest()
        path = self.cache / f'{digest}.json'
        if path.exists():
            return json.loads(path.read_text())
        data = pytesseract.image_to_data(frame, config='--psm 11', output_type=Output.DICT, timeout=30)
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
        self.vision.close()
        if self.paddle:
            self.paddle.close()
