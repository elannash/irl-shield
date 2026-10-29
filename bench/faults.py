"""Exercise deadline protection with real worker stalls and synthetic in-memory video."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import cv2
import numpy as np

from shield.engine import MaskingEngine
from shield.lanes import DetectorLane
from shield.types import Frame


class ProbeDetector:
    metadata={'engine':'synthetic-fault-probe','model':'none'}
    def detect_quads(self,frame):
        return [[[70,50],[170,50],[170,80],[70,80]]]
    def close(self):
        pass


def exercise(kind):
    fps,count,delay=30,54,.15
    lanes={name:DetectorLane(name,ProbeDetector(),30 if name=='fast' else 10,
                            fault_intervals=[(.3,1.2)] if kind==name+'-stall' else
                                            ([(.6,.95)] if kind=='motion-burst' else []))
           for name in ['fast','accurate']}
    engine=MaskingEngine(lanes,{'fps':fps,'delay_seconds':delay,'before':4,'after':4,
                               'fast_max_age':3,'accurate_max_age':4})
    rng=np.random.default_rng(731)
    texture=rng.integers(0,256,(180,320,3),dtype=np.uint8)
    cv2.putText(texture,'SYNTHETIC 123',(40,70),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
    replacement=rng.integers(0,256,texture.shape,dtype=np.uint8)
    source_hashes={}
    outputs=[]
    origin=time.monotonic()
    def observe(frames):
        for frame in frames:
            if frame.state=='LIVE' and (not frame.coverage.ok or frame.protected):
                raise AssertionError('Uncovered LIVE frame escaped')
            digest=hashlib.sha256(frame.pixels.tobytes()).hexdigest()
            if frame.protected and digest==source_hashes.get(frame.index):
                raise AssertionError('Raw pixels escaped in protection')
            outputs.append({'index':frame.index,'state':frame.state,'covered':frame.coverage.ok,
                            'reason':frame.coverage.reason,'protected':frame.protected,'sha256':digest})
    try:
        for index in range(count):
            time.sleep(max(0,origin+index/fps-time.monotonic()))
            base=replacement if kind=='motion-burst' and index>=20 else texture
            pixels=cv2.warpAffine(base,np.float32([[1,0,index*.4],[0,1,index*.2]]),(320,180))
            source_hashes[index]=hashlib.sha256(pixels.tobytes()).hexdigest()
            if not(kind=='ingest-drop' and 15<=index<27):
                engine.submit(Frame(index,index/fps,pixels))
            observe(engine.poll())
        engine.end(count-1)
        while not engine.drained:
            observe(engine.poll())
            time.sleep(.002)
        if len(outputs)!=count or not any(frame['protected'] for frame in outputs):
            raise AssertionError(f'{kind}: fault did not exercise protection on the complete source clock')
        if kind=='ingest-drop' and not any(row['reason']=='ingest-gap' for row in outputs):
            raise AssertionError('Dropped ingest did not become protected clock output')
        return {'fault':kind,'frames':count,'protected':sum(row['protected'] for row in outputs),
                'pass':True,'transitions':engine.stats['transitions'],'outputs':outputs}
    finally:
        engine.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('out/faults.json'))
    args=parser.parse_args()
    cv2.setNumThreads(1)
    results=[exercise(kind) for kind in ['fast-stall','accurate-stall','ingest-drop','motion-burst']]
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'scope':'Synthetic faults; no OCR-quality or throughput claim',
                                    'results':results,'pass':all(row['pass'] for row in results)},indent=2)+'\n')
    print(json.dumps([{key:row[key] for key in ['fault','frames','protected','pass']} for row in results]))


if __name__=='__main__':
    main()
