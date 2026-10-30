"""CPU-cost repetitions on licensed pixels; contended wall times are diagnostic only."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

import cv2
import numpy as np
import psutil

from bench.clocked_pipeline import perf_health
from bench.pipeline import detector_for
from shield.motion import MotionHistory
from shield.render import Renderer


def measure(function):
    def children_cpu():
        result={}
        for process in psutil.Process().children(recursive=True):
            try:
                cpu=process.cpu_times()
                result[(process.pid,process.create_time())]=cpu.user+cpu.system
            except psutil.NoSuchProcess:
                continue
        return result
    before=children_cpu()
    wall,cpu,thread=time.monotonic(),time.process_time(),time.thread_time()
    result=function()
    values={'wall':time.monotonic()-wall,'process_cpu':time.process_time()-cpu,
            'thread_cpu':time.thread_time()-thread}
    after=children_cpu()
    values['owned_subprocess_cpu']=sum(value-before.get(key,0) for key,value in after.items())
    values['process_tree_cpu']=values['process_cpu']+values['owned_subprocess_cpu']
    return result,values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--masks',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=Path('out/cpu-cost.json'))
    parser.add_argument('--candidate',default='ppocr-v6-tiny')
    parser.add_argument('--provider',choices=('cpu','coreml','cuda'),default='coreml')
    parser.add_argument('--static-model',action='store_true')
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--side',type=int,default=960)
    parser.add_argument('--samples',type=int,default=16)
    parser.add_argument('--repetitions',type=int,default=5)
    parser.add_argument('--padding',type=float,default=.3)
    args=parser.parse_args()
    if args.repetitions<5 or args.samples<2:
        parser.error('At least5 repetitions and2 consecutive frames are required')
    cv2.setNumThreads(1)
    records=json.loads(args.masks.read_text())[:args.samples]
    cap=cv2.VideoCapture(str(args.source),cv2.CAP_FFMPEG,[cv2.CAP_PROP_N_THREADS,2])
    frames=[]
    try:
        for _ in records:
            ok,pixels=cap.read()
            if not ok:
                raise RuntimeError('CPU profile source is truncated')
            frames.append(pixels)
    finally:
        cap.release()
    if len(frames)!=args.samples or [row['frame'] for row in records]!=list(range(args.samples)):
        raise ValueError('CPU profile needs matching consecutive source/mask records from frame0')
    h,w=frames[0].shape[:2]
    detector=detector_for(args.candidate,{'provider':args.provider,'static_model':args.static_model,
                                         'input_size':[h,w],'detect_width':args.width,'limit_side_len':args.side})
    renderer=Renderer(padding=args.padding)
    detection_frames=[cv2.resize(frame,(args.width,round(h*args.width/w))) for frame in frames]
    runs=[]
    try:
        for _ in range(2):
            detector.detect_quads(detection_frames[0])
        for repetition in range(args.repetitions):
            health_start=perf_health()
            history=MotionHistory(mode='phase',analysis_width=320)
            _,motion=measure(lambda:[history.add(i,frame) for i,frame in enumerate(frames)])
            def project():
                for index,row in enumerate(records):
                    history.project_many(row['quads'],max(0,index-1),index)
            _,projection=measure(project)
            _,render=measure(lambda:[renderer.render(frame,row['quads'],'LIVE',len(row['quads']))
                                    for frame,row in zip(frames,records)])
            _,inference=measure(lambda:[detector.detect_quads(frame) for frame in detection_frames])
            stages={name:{clock+'_ms_per_frame':seconds*1000/len(frames) for clock,seconds in values.items()}
                    for name,values in [('motion',motion),('projection',projection),('render',render),('inference',inference)]}
            runs.append({'repetition':repetition,'health_start':health_start,'health_end':perf_health(),'stages':stages})
            print(json.dumps({'repetition':repetition,'stages':stages}),flush=True)
        median={stage:{clock:statistics.median(run['stages'][stage][clock] for run in runs)
                       for clock in runs[0]['stages'][stage]} for stage in runs[0]['stages']}
        emit=median['projection']['thread_cpu_ms_per_frame']+median['render']['thread_cpu_ms_per_frame']
        card={'scope':'CPU-stage profile on retained tune quads;5+repetitions; wall cost not a real-time receipt',
              'cpu_scope':'Thread CPU for emit/motion; process-tree CPU includes native ORT threads and owned Vision bridge. Hardware GPU/ANE and system-daemon CPU are not attributed.',
              'emit_cost_scope':'Batch projection per receipt and render only; excludes timeline selection/control and transport. Full poll CPU is recorded by the engine in sustained receipts.',
              'candidate':args.candidate,'samples':args.samples,'repetitions':args.repetitions,'runs':runs,
              'median_repetition_cost':median,'emit_thread_cpu_ms_per_frame':emit,'emit_under_8ms':emit<8,
              'quad_counts':[len(row['quads']) for row in records],
              'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'mask_records_sha256':hashlib.sha256(args.masks.read_bytes()).hexdigest(),
              'detector':detector.metadata,'options':vars(args)|{'source':str(args.source),'masks':str(args.masks),'out':str(args.out)}}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(card,indent=2)+'\n')
        print(json.dumps({'receipt':str(args.out),'median_repetition_cost':median,'emit_thread_cpu_ms_per_frame':emit}))
    finally:
        detector.close()


if __name__=='__main__':
    main()
