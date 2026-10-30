"""Root EX only: CPU/CUDA face path plus real NVENC30, local tune input.

CUDA events measure the stream interval around synchronous ORT session.run,
including transfers/dispatch gaps. This is not isolated sum-of-kernel compute.
No text pipeline integration or live relay throughput is claimed by this job.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import cv2
import numpy as np
from shield.faces import FaceBatch, FacePolicy, FaceTracker, opaque
from shield.faces.detector import YuNetDetector
from shield.faces.yunet_ort import YuNetORTDetector, prepare, decode, source_faces
from bench.faces.synthetic import load_assets, overlay


class CUDAClock:
    def __init__(self):
        library = ctypes.util.find_library('cudart')
        if library is None:
            options=list(Path(sys.prefix).glob('lib/python*/site-packages/nvidia/cuda_runtime/lib/libcudart.so*'))
            if not options:raise RuntimeError('CUDA runtime unavailable for device-event measurements')
            library=str(sorted(options)[0])
        self.lib=ctypes.CDLL(library)
        pointer=ctypes.c_void_p
        signatures={'cudaStreamCreate':[ctypes.POINTER(pointer)],'cudaStreamDestroy':[pointer],
                    'cudaEventCreate':[ctypes.POINTER(pointer)],'cudaEventDestroy':[pointer],
                    'cudaEventRecord':[pointer,pointer],'cudaEventSynchronize':[pointer],
                    'cudaEventElapsedTime':[ctypes.POINTER(ctypes.c_float),pointer,pointer]}
        for name,args in signatures.items():
            getattr(self.lib,name).argtypes=args;getattr(self.lib,name).restype=ctypes.c_int
        self.stream=pointer();self.start=pointer();self.end=pointer()
        try:
            self.call('cudaStreamCreate',ctypes.byref(self.stream))
            self.call('cudaEventCreate',ctypes.byref(self.start));self.call('cudaEventCreate',ctypes.byref(self.end))
        except Exception:
            self.close();raise

    def call(self,name,*args):
        result=getattr(self.lib,name)(*args)
        if result:raise RuntimeError(f'{name} failed with CUDA status {result}')

    def measure(self,action):
        self.call('cudaEventRecord',self.start,self.stream)
        result=action()
        self.call('cudaEventRecord',self.end,self.stream);self.call('cudaEventSynchronize',self.end)
        elapsed=ctypes.c_float();self.call('cudaEventElapsedTime',ctypes.byref(elapsed),self.start,self.end)
        return result,elapsed.value

    def close(self):
        # Only the events and stream created by this instance are destroyed.
        for name,obj in [('cudaEventDestroy',self.start),('cudaEventDestroy',self.end),('cudaStreamDestroy',self.stream)]:
            if obj.value:self.call(name,obj);obj.value=None


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--source-sha256',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=150)
    a=p.parse_args()
    if a.frames<30 or a.frames>900:raise ValueError('frames must be between30 and900')
    root=Path(__file__).resolve().parents[2]
    manifest=json.loads((root/'fixtures/manifest.json').read_text())
    if not any(c['split']=='tune' and c['sha256']==a.source_sha256 for c in manifest['clips']):raise ValueError('only pinned tune sources allowed')
    if hashlib.sha256(a.source.read_bytes()).hexdigest()!=a.source_sha256:raise ValueError('cost source hash mismatch')
    a.out.mkdir(parents=True,exist_ok=True);cv2.setNumThreads(1)
    gpu_info=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip()
    if '1080 Ti' not in gpu_info:raise RuntimeError('packet requires GTX1080Ti')
    assets=load_assets();report={'gpu':gpu_info,'frames_per_arm':a.frames,'fps':30,'results':[],'limits':'Face-only adapter workload;1080p upscaled from720p tune. Not native relay or text+face pipeline cost. Device events include dispatch/transfer interval. Profiling overhead included.'}
    clock=None
    try:
        clock=CUDAClock()
        for height in (720,1080):
            for arm in ('opencv-cpu','ort-cuda-fp32'):
                cap=cv2.VideoCapture(str(a.source));stderr_path=a.out/f'{height}-{arm}-ffmpeg.log'
                stderr=stderr_path.open('w');encoder=None;detector=None
                rows=[];tracker=FaceTracker();policy=FacePolicy('all');started=time.perf_counter()
                try:
                    detector=YuNetDetector() if arm=='opencv-cpu' else YuNetORTDetector(profile_prefix=a.out/f'{height}-cuda',user_compute_stream=clock.stream.value)
                    argv=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{height*16//9}x{height}','-r','30','-i','pipe:0','-an','-c:v','h264_nvenc','-preset','p4','-bf','0',str(a.out/f'{height}-{arm}.mp4')]
                    encoder=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=stderr)
                    paced_start=time.perf_counter()
                    for index in range(a.frames):
                        ok,background=cap.read()
                        if not ok:
                            cap.set(cv2.CAP_PROP_POS_FRAMES,0);ok,background=cap.read()
                        if not ok:raise RuntimeError('cost source cannot decode')
                        background=cv2.resize(background,(height*16//9,height))
                        image,_=overlay(background,index,assets,'selfie-bystander')
                        remaining=paced_start+index/30-time.perf_counter()
                        if remaining>0:time.sleep(remaining)
                        begin=time.perf_counter();cpu_begin=time.process_time();device_ms=None
                        if arm=='opencv-cpu':batch=detector.detect(image,index,0)
                        else:
                            padded,scales=prepare(image);tensor=np.ascontiguousarray(padded.transpose(2,0,1)[None],dtype=np.float32)
                            outputs,device_ms=clock.measure(lambda:detector.infer_tensor(tensor))
                            batch=tracker.assign(FaceBatch(index,0,image.shape[:2],time.monotonic(),source_faces(decode(outputs),image.shape[:2],scales)))
                        if batch.error:raise RuntimeError('cost detector error: '+batch.error)
                        plan=policy.plan(image.shape[:2],index,0,batch,now=time.monotonic())
                        if plan.requires_hold:raise RuntimeError('cost face coverage failed')
                        painted=opaque(image,plan.mask)
                        detect_paint_ms=(time.perf_counter()-begin)*1000;cpu_ms=(time.process_time()-cpu_begin)*1000
                        encoder.stdin.write(painted.tobytes())
                        rows.append({'index':index,'detect_paint_wall_ms':detect_paint_ms,'cpu_process_ms':cpu_ms,'cuda_stream_interval_ms':device_ms,
                                     'writer_handoff_ms':(time.perf_counter()-begin)*1000,'face_area_fraction':plan.area_fraction})
                    encoder.stdin.close();code=encoder.wait(timeout=30)
                    if code:raise RuntimeError('NVENC encoder failed; see '+str(stderr_path))
                    placement=detector.finish_profile() if arm!='opencv-cpu' else None
                    report['results'].append({'height':height,'arm':arm,'ffmpeg_argv':argv,'source_frames':rows,
                                              'wall_seconds':time.perf_counter()-started,'placement':placement})
                finally:
                    cap.release()
                    if encoder is not None and encoder.poll() is None:
                        encoder.terminate()
                        try:encoder.wait(timeout=5)
                        except subprocess.TimeoutExpired:encoder.kill();encoder.wait()
                    if isinstance(detector,YuNetORTDetector):detector.finish_profile()
                    stderr.close()
    finally:
        if clock:clock.close()
        (a.out/'cost.json').write_text(json.dumps(report,indent=2)+'\n')
    qualified = len(report['results']) == 4 and all(row['arm']=='opencv-cpu' or row['placement']['placement_verified'] for row in report['results'])
    report['cost_qualified'] = qualified
    (a.out/'cost.json').write_text(json.dumps(report,indent=2)+'\n')
    print('NVENC face cost receipt:',a.out/'cost.json','qualified',qualified)
    return 0 if qualified else 1


if __name__=='__main__':raise SystemExit(main())
