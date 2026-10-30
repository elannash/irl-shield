"""A binary upgrade must miss a persistent OCR cache for identical pixels."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from bench.judges import Judges


class Reader:
    def __init__(self,*args,**kwargs):pass
    def read(self,frame):return []
    def close(self):pass


class JudgeCache(unittest.TestCase):
    def test_tesseract_upgrade_misses_cache_but_identical_environment_hits(self):
        data={'text':['ELM'],'conf':['99'],'left':[1],'top':[2],'width':[20],'height':[10]}
        with tempfile.TemporaryDirectory() as temporary, \
             patch('bench.judges.Vision',Reader), \
             patch('bench.onnx_detectors.create_recognizer',return_value=Reader()), \
             patch('bench.judges.pytesseract.image_to_data',return_value=data) as read, \
             patch('bench.judges.pytesseract.get_tesseract_version',return_value='5.5.4') as binary:
            pixels=np.zeros((32,32,3),np.uint8)
            first=Judges('ppocr-v6-small',Path(temporary));first.read(pixels);first.close()
            same=Judges('ppocr-v6-small',Path(temporary));same.read(pixels);same.close()
            self.assertEqual(read.call_count,1)
            binary.return_value='5.5.5'
            upgraded=Judges('ppocr-v6-small',Path(temporary));upgraded.read(pixels);upgraded.close()
            self.assertEqual(read.call_count,2)

    def test_each_runtime_version_and_macos_product_change_misses_cache(self):
        data={'text':[],'conf':[],'left':[],'top':[],'width':[],'height':[]}
        versions={'pytesseract':'0.3.13','onnxruntime':'1.31.1','rapidocr':'3.10.0'}
        with tempfile.TemporaryDirectory() as temporary, \
             patch('bench.judges.Vision',Reader), \
             patch('bench.onnx_detectors.create_recognizer',return_value=Reader()), \
             patch('bench.judges.pytesseract.image_to_data',return_value=data) as read, \
             patch('bench.judges.pytesseract.get_tesseract_version',return_value='5.5.4'), \
             patch('bench.judges.version',side_effect=lambda name:versions[name]), \
             patch('bench.judges.platform.system',return_value='Darwin'), \
             patch('bench.judges.subprocess.check_output',return_value='27.0\n') as macos:
            pixels=np.zeros((32,32,3),np.uint8)
            def read_once():
                reader=Judges('ppocr-v6-small',Path(temporary));reader.read(pixels);reader.close()
            read_once();read_once();self.assertEqual(read.call_count,1)
            for count,name in enumerate(versions,2):
                versions[name]+='-upgrade';read_once();self.assertEqual(read.call_count,count)
            macos.return_value='27.1\n';read_once();self.assertEqual(read.call_count,5)

    def test_detector_implementation_and_pixel_shape_are_part_of_cache_identity(self):
        from bench import judges
        data={'text':[],'conf':[],'left':[],'top':[],'width':[],'height':[]}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in judges.CACHE_SOURCES:
                source=root/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_text('original '+name)
            with patch('bench.judges.__file__',str(root/'bench/judges.py')), \
                 patch('bench.judges.Vision',Reader), \
                 patch('bench.onnx_detectors.create_recognizer',return_value=Reader()), \
                 patch('bench.judges.pytesseract.image_to_data',return_value=data) as read, \
                 patch('bench.judges.pytesseract.get_tesseract_version',return_value='5.5.4'):
                def read_once(shape):
                    reader=Judges('ppocr-v6-small',root/'cache');reader.read(np.zeros(shape,np.uint8));reader.close()
                read_once((32,32,3));read_once((32,32,3));self.assertEqual(read.call_count,1)
                (root/'bench/onnx_detectors.py').write_text('changed judge preprocessing')
                read_once((32,32,3));self.assertEqual(read.call_count,2)
                read_once((16,64,3));self.assertEqual(read.call_count,3)
