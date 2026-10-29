"""Independent OCR union with explicit, cached input/output evidence."""
import hashlib
import json
from pathlib import Path

import cv2
import pytesseract
from pytesseract import Output

from bench.vision import Vision


class Judges:
    def __init__(self, detector, cache):
        self.vision = Vision('vision-accurate')
        from bench.onnx_detectors import create_recognizer
        self.paddle = create_recognizer({})
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.signature=hashlib.sha256(Path(__file__).read_bytes()+(Path(__file__).parent/'vision.py').read_bytes()+(Path(__file__).parents[1]/'Sources/VisionBridge/main.swift').read_bytes()+(Path(__file__).parents[1]/'models/manifest.json').read_bytes()).digest()
        self.names = ['tesseract-5-psm11', 'vision-accurate'] + (['ppocr-independent'] if self.paddle else [])

    def read(self, frame):
        digest = hashlib.sha256(frame.tobytes() + '|'.join(self.names).encode()+self.signature).hexdigest()
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
