"""A real codec boundary check for delayed frame accounting; no detector mocks."""
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

import cv2
import numpy as np

from bench.pipeline import run


@unittest.skipUnless(platform.system()=='Darwin','VideoToolbox requires macOS')
class DelayedVideo(unittest.TestCase):
    def test_lookahead_preserves_every_frame_in_order_including_tail(self):
        root=Path(__file__).resolve().parents[1]
        (root/'.tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root/'.tmp') as folder:
            folder=Path(folder)
            source=folder/'source.mp4'
            frames=[]
            for index in range(12):
                frame=np.zeros((180,320,3),np.uint8)
                frame[:]=[20+15*index,80,180]
                frame[20:80,20:80]=[200,30+10*index,50]
                # A spatial ID survives codec color/range shifts; subtle color ramps do not.
                for bit in range(4):
                    frame[110:150,20+bit*60:60+bit*60]=255 if index & (1<<bit) else 0
                frames.append(frame)
            encoder=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo',
                '-pix_fmt','bgr24','-s','320x180','-r','30','-i','pipe:0','-an','-c:v',
                'h264_videotoolbox','-bf','0','-b:v','5M',str(source)],input=b''.join(f.tobytes() for f in frames))
            self.assertEqual(encoder.returncode,0)
            for delay in [0,6,20]:
                output=folder/f'delay-{delay}.mp4'
                result=run(source,output,'unmasked',{'padding':.3,'lookahead':delay})
                self.assertEqual(result['frames'],12)
                records=json.loads(output.with_suffix('.masks.json').read_text())
                self.assertEqual([r['frame'] for r in records],list(range(12)))
                cap=cv2.VideoCapture(str(output))
                for index in range(12):
                    ok,frame=cap.read()
                    self.assertTrue(ok)
                    decoded_id=sum((1<<bit) for bit in range(4)
                                   if float(frame[120:140,30+bit*60:50+bit*60].mean())>128)
                    self.assertEqual(decoded_id,index)
                self.assertFalse(cap.read()[0])
                cap.release()
