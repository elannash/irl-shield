"""Run the actual serial decode/detect/mask/VideoToolbox encode path, without OCR judges."""
import json
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import psutil

from bench.metrics import quantiles
from bench.reference_engine import MaskingEngine
from bench.vision import Vision
from bench.provenance import pipeline_fingerprint


class ControlDetector:
    def __init__(self,name):
        self.name=name
        self.metadata={'engine':name,'benchmark_control':True}
    def detect(self,frame):
        h,w=frame.shape[:2]
        return [[0,0,w,h]] if self.name=='slate' else []
    def close(self):
        pass


def detector_for(name, options):
    if name=='vision-scheduled':
        from bench.scheduled import ScheduledVision
        return ScheduledVision(options)
    if name.startswith('vision'):
        return Vision(name)
    if name in ('unmasked','slate'):
        return ControlDetector(name)
    from bench.onnx_detectors import create_detector
    model_options={k:v for k,v in options.items() if k in {"provider","threads","limit_side_len","thresh","box_thresh","unclip_ratio"}}
    if options.get('static_model'):
        from rapidocr.ch_ppocr_det.utils import DetPreProcess
        h,w=options['input_size']
        scale=options.get('detect_width',w)/w
        small=np.zeros((int(h*scale),int(w*scale),3),np.uint8)
        tensor=DetPreProcess(options.get('limit_side_len',960),'max')(small)
        if tensor is None:
            raise RuntimeError('Static preprocessing shape failed')
        model_options['static_shape']=list(tensor.shape[2:])
    return create_detector(name,model_options)


def run(input_path, output_path, name, options, max_frames=None):
    persistence=options.get('persistence',1)
    lookahead=options.get('lookahead',0)
    stride=options.get('stride',1)
    if persistence<1 or lookahead<0 or stride<1:
        raise ValueError('Invalid temporal configuration')
    fingerprint=pipeline_fingerprint()
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise RuntimeError(f'Cannot decode {input_path}')
    width, height = (int(capture.get(p)) for p in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    load_start=time.monotonic()
    detector = detector_for(name, {**options,'input_size':[height,width]})
    if detector:
        ok,warm=capture.read()
        if not ok:
            raise RuntimeError('No frame available to warm detector')
        scale=options.get('detect_width',width)/width
        warm=cv2.resize(warm,(int(width*scale),int(height*scale))) if scale!=1 else warm
        if name=='vision-scheduled':
            detector.warmup(warm)
        else:
            detector.detect(warm)
        capture.set(cv2.CAP_PROP_POS_FRAMES,0)
    load_seconds=time.monotonic()-load_start
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoder_log = output_path.with_suffix('.ffmpeg.log')
    starts, completes, masks, processing = [], [], [], []
    process = psutil.Process()
    cpu_start = time.monotonic()
    cpu_times = {}
    memory = []
    running = True
    def monitor():
        while running:
            procs = [process] + process.children(recursive=True)
            rss = 0
            for p in procs:
                try:
                    t = p.cpu_times()
                    key = (p.pid, p.create_time())
                    if key not in cpu_times:
                        cpu_times[key] = [t.user+t.system, t.user+t.system]
                    else:
                        cpu_times[key][1] = t.user+t.system
                    rss += p.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            memory.append(rss)
            time.sleep(.05)
    with encoder_log.open('w') as log:
        codec=options.get('encoder','h264_videotoolbox')
        if codec not in {'h264_videotoolbox','h264_nvenc','libx264'}:
            raise ValueError('Unsupported benchmark encoder')
        codec_options=['-realtime','1'] if codec=='h264_videotoolbox' else ['-preset','p4'] if codec=='h264_nvenc' else ['-preset','veryfast','-threads','2']
        encoder = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y',
            '-f','rawvideo','-pix_fmt','bgr24','-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0',
            '-an','-c:v',codec,*codec_options,'-bf','0','-b:v','10M',
            '-pix_fmt','yuv420p','-stats_period','0.01','-progress','pipe:1',str(output_path)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
        def progress():
            for line in iter(encoder.stdout.readline, b''):
                key, _, value = line.decode().strip().partition('=')
                if key == 'frame':
                    count = int(value)
                    now = time.monotonic()
                    while len(completes) < count:
                        completes.append(now)
        progress_thread = threading.Thread(target=progress)
        sampler = threading.Thread(target=monitor)
        progress_thread.start()
        sampler.start()
        engine=MaskingEngine(detector,options)
        def emit(result):
            masks.append({'frame':result.index,'boxes':result.boxes,
                          'mask_fraction':float((result.mask>0).mean())})
            encoder.stdin.write(result.pixels.tobytes())
        start = time.monotonic()
        try:
            index = 0
            while max_frames is None or index < max_frames:
                if options.get('pace', False):
                    time.sleep(max(0, start+index/fps-time.monotonic()))
                beginning = time.monotonic()
                ok, frame = capture.read()
                if not ok:
                    break
                starts.append(beginning)
                result=engine.push(frame)
                if result is not None:
                    emit(result)
                processing.append(time.monotonic()-beginning)
                index += 1
            for result in engine.flush():
                emit(result)
        finally:
            capture.release()
            try:
                try:
                    encoder.stdin.close()
                except BrokenPipeError:
                    pass
                try:
                    code=encoder.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    encoder.terminate()
                    try:
                        encoder.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        encoder.kill()
                        encoder.wait(timeout=5)
                    raise RuntimeError('Encoder did not drain within60 seconds')
            finally:
                end=time.monotonic()
                running=False
                sampler.join(timeout=5)
                progress_thread.join(timeout=5)
                encoder.stdout.close()
                if detector:
                    detector.close()
        if code:
            raise RuntimeError(f'ffmpeg failed ({code}): {encoder_log.read_text()}')
    if len(starts) == 0 or len(completes) != len(starts):
        raise RuntimeError(f'Frame accounting failed: input={len(starts)}, encoded={len(completes)}')
    latency = [c-s for c,s in zip(completes, starts)]
    # Latency for a 30 fps source additionally includes accumulating service backlog.
    realtime_latency = [c-(start+i/fps) for i,c in enumerate(completes)]
    if pipeline_fingerprint()!=fingerprint:
        raise RuntimeError('Pipeline source changed during measurement')
    stats = {'pipeline_sha256':fingerprint,'pace':options.get('pace',False),'frames': len(starts), 'seconds': end-start, 'fps': len(starts)/(end-start),
             'encoder':codec,'model_load_and_warmup_seconds':load_seconds,'source_fps': fps, 'resolution':[width,height], 'latency_seconds': quantiles(latency),
             'realtime_added_latency_seconds': quantiles([max(0,x) for x in realtime_latency]),
             'service_seconds': quantiles(processing),
             'cpu_percent_one_core_100': 100*sum(b-a for a,b in cpu_times.values())/(end-cpu_start),
             'peak_tree_rss_mb': max(memory,default=0)/1024**2,
             'detector': detector.metadata if detector else {'engine':name}}
    output_path.with_suffix('.masks.json').write_text(json.dumps(masks))
    output_path.with_suffix('.performance.json').write_text(json.dumps(stats,indent=2))
    return stats
