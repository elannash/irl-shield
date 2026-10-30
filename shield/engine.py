"""A transport-free frame clock. Detector, motion and render adapters sit at its seams."""
import threading
import time
import math
from collections import deque

import numpy as np

from shield.control import Control
from shield.render import Renderer
from shield.types import Coverage,Frame,PresentedFrame


class MaskingEngine:
    def __init__(self,lanes,options,motion=None,renderer=None,control=None):
        if set(lanes)!={'fast','accurate'}:
            raise ValueError('Both fast and accurate lanes are required')
        self.lanes=lanes
        self.timeline={name:[] for name in lanes}
        self.fps=float(options.get('fps',30))
        self.delay=float(options.get('delay_seconds',1))
        if not math.isfinite(self.fps) or not math.isfinite(self.delay) or self.fps<=0 or self.delay<0:
            raise ValueError('Invalid source rate or presentation delay')
        self.options=options
        self.tracking_persist_frames=options.get('tracking_persist_frames',0)
        if (type(self.tracking_persist_frames) is not int or self.tracking_persist_frames<0
                or self.tracking_persist_frames>math.floor(self.delay*self.fps)
                or self.tracking_persist_frames and options.get('motion_mode')!='box-flow'):
            raise ValueError('Tracking persistence requires box-flow within the configured delay horizon')
        self._frame_generations={}
        self._generation_fencing=False
        self.max_buffer_frames=int(options.get('max_buffer_frames',math.ceil(self.fps*(self.delay+1))+8))
        self.max_poll_frames=int(options.get('max_poll_frames',4))
        if self.max_buffer_frames<1 or self.max_poll_frames<1:
            raise ValueError('Frame buffer must have positive capacity')
        if motion is None:
            from shield.motion import MotionHistory,MotionWorker
            motion=MotionWorker(MotionHistory(max_frames=120,analysis_width=options.get('motion_width',320),mode=options.get('motion_mode','phase'),
                                              phase_min_response=options.get('motion_min_response',.5),
                                              max_projection_frames=math.floor(self.delay*self.fps)),
                                capacity=self.max_buffer_frames)
        self.motion=motion
        self.renderer=renderer or Renderer(padding=options.get('padding',.3),badge=options.get('badge',False))
        self.control=control or Control()
        self.lock=threading.RLock()
        self.frames={}
        self.origin=None
        self.first_index=self.next_index=0
        self.first_pts=0.
        self.last_index=-1
        self.terminal=None
        self.last_frame=None
        self.protect_since=None
        self.outputs=0
        self.protected_count=0
        self.late_ingest=0
        self.buffer_evictions=0
        self.stage_seconds={name:deque(maxlen=4096) for name in ['motion_submit','coverage','render','poll_lock_wait']}
        self.stage_cpu_seconds={name:deque(maxlen=4096) for name in ['motion_submit','coverage','render','emit_poll_per_frame']}
        self.emit_poll_cpu_seconds=0.

    def submit(self,frame,now=None,*,generation=None):
        """Flow callers pass the ingest generation captured with this frame.

        Indices remain globally increasing across generations. The default
        token zero is for uninterrupted inputs such as an offline file.
        """
        if generation is not None and (self.options.get('motion_mode') not in {'flow','box-flow'}
                                       or type(generation) is not int or generation < 0):
            raise ValueError('Ingest generation requires optical flow and a nonnegative integer')
        now=time.monotonic() if now is None else now
        if not math.isfinite(frame.pts) or not math.isfinite(now):
            raise ValueError('Frame and clock timestamps must be finite')
        if not isinstance(frame.index,int) or frame.index<0:
            raise ValueError('Frame index must be a nonnegative integer')
        if frame.pixels.dtype!=np.uint8 or frame.pixels.ndim!=3 or frame.pixels.shape[2]!=3:
            raise ValueError('Frames must be uint8 BGR images')
        with self.lock:
            if self.terminal is not None:
                raise RuntimeError('Input is closed')
            if self.origin is None:
                self.origin=now-frame.pts
                self.first_pts=frame.pts
                self.first_index=self.next_index=frame.index
            if frame.index<self.next_index:
                self.late_ingest+=1
                return
            if frame.index<=self.last_index:
                raise ValueError('Input frame indices must increase')
            if now>self.origin+frame.pts+self.delay:
                self.late_ingest+=1
                self.last_index=frame.index
                return
            pixels=frame.pixels.copy()
            pixels.setflags(write=False)
            token=frame.generation if generation is None else generation
            if type(token) is not int or token<0:
                raise ValueError('Ingest generation must be a nonnegative integer')
            owned=Frame(frame.index,frame.pts,pixels,token)
            self._frame_generations[frame.index]=token
            self._generation_fencing=self._generation_fencing or token!=0
            self.frames[frame.index]=owned
            while len(self.frames)>self.max_buffer_frames:
                self.frames.pop(next(iter(self.frames)))
                self.buffer_evictions+=1
            self.last_frame=owned
            self.last_index=frame.index
            began,cpu=time.monotonic(),time.thread_time()
            if self.options.get('motion_mode') in {'flow','box-flow'}:
                self.motion.add(frame.index,pixels,generation=token)
            else:
                self.motion.add(frame.index,pixels)
            self.stage_seconds['motion_submit'].append(time.monotonic()-began)
            self.stage_cpu_seconds['motion_submit'].append(time.thread_time()-cpu)
            for lane in self.lanes.values():
                lane.offer(owned)

    def end(self,last_index=None):
        with self.lock:
            self.terminal=self.last_index if last_index is None else last_index

    @property
    def drained(self):
        return self.terminal is not None and self.next_index>self.terminal

    def _coverage_and_quads(self,index,deadline):
        before=self.options.get('before',6)
        after=self.options.get('after',18)
        ages={}
        quads=[]
        reason='covered'
        failed_active_track=False
        for name in ['fast','accurate']:
            available=[r for r in self.timeline[name] if r.error is None and r.completed_at<=deadline]
            had_candidates=any(index-before<=r.frame_index<=index+after for r in available)
            if self.options.get('motion_mode')=='box-flow' or self._generation_fencing:
                target_generation=self._frame_generations.get(index)
                available=[r for r in available if target_generation is not None
                    and all(self._frame_generations.get(step)==target_generation
                            for step in range(min(r.frame_index,index),max(r.frame_index,index)+1))]
            inside=[r for r in available if index-max(before,self.tracking_persist_frames)<=r.frame_index<=index+after]
            connected=[]
            for receipt in inside:
                if self.options.get('motion_mode') in {'flow','box-flow'} and abs(receipt.frame_index-index)>math.floor(self.delay*self.fps):
                    continue
                # Empty results still describe a particular scene, never every scene.
                projected=self.motion.project_many(receipt.quads,receipt.frame_index,index,deadline)
                if projected is None:
                    if self.options.get('motion_mode')=='box-flow' and receipt.quads:
                        failed_active_track=True
                    continue
                if index-before<=receipt.frame_index:
                    connected.append(receipt)
                quads.extend(projected)
            nearest=min(connected,key=lambda r:abs(r.frame_index-index),default=None)
            ages[name]=abs(nearest.frame_index-index) if nearest else None
            maximum=self.options.get(name+'_max_age',6 if name=='fast' else 12)
            if nearest is None or ages[name]>maximum:
                reason=('unresolved-motion-' if inside or had_candidates else 'missing-')+name+'-coverage'
        if failed_active_track:
            reason='unresolved-box-track'
        return Coverage(ages['fast'],ages['accurate'],reason=='covered',reason),quads

    def poll(self,now=None):
        now=time.monotonic() if now is None else now
        results=[]
        poll_cpu=time.thread_time()
        began=time.monotonic()
        with self.lock:
            self.stage_seconds['poll_lock_wait'].append(time.monotonic()-began)
            if self.origin is None:
                self.emit_poll_cpu_seconds+=time.thread_time()-poll_cpu
                return results
            for name,lane in self.lanes.items():
                self.timeline[name].extend(lane.drain())
            while not self.drained and len(results)<self.max_poll_frames:
                index=self.next_index
                frame=self.frames.get(index)
                pts=frame.pts if frame else self.first_pts+(index-self.first_index)/self.fps
                deadline=self.origin+pts+self.delay
                if now<deadline:
                    break
                began,cpu=time.monotonic(),time.thread_time()
                coverage,quads=self._coverage_and_quads(index,deadline)
                self.stage_seconds['coverage'].append(time.monotonic()-began)
                self.stage_cpu_seconds['coverage'].append(time.thread_time()-cpu)
                if frame is None:
                    coverage=Coverage(coverage.fast_age,coverage.accurate_age,False,'ingest-gap')
                self.control.update_coverage(coverage.ok,coverage.reason,now)
                if self.control.state=='LIVE':
                    self.protect_since=None
                elif self.protect_since is None:
                    self.protect_since=deadline
                pixels=frame.pixels if frame else self.last_frame.pixels
                began,cpu=time.monotonic(),time.thread_time()
                rendered=self.renderer.render(pixels,quads,self.control.state,len(quads),0 if self.protect_since is None else now-self.protect_since)
                self.stage_seconds['render'].append(time.monotonic()-began)
                self.stage_cpu_seconds['render'].append(time.thread_time()-cpu)
                results.append(PresentedFrame(index,pts,rendered.pixels,rendered.mask,quads,coverage,
                                              self.control.state,deadline,now,rendered.protected,rendered.slate))
                self.frames.pop(index,None)
                self.next_index+=1
                self.outputs+=1
                self.protected_count+=int(rendered.protected)
            oldest=self.next_index-max(self.options.get('before',6),self.tracking_persist_frames)
            self._frame_generations={index:token for index,token in self._frame_generations.items() if index>=oldest}
            for name in self.timeline:
                self.timeline[name]=[r for r in self.timeline[name] if r.frame_index>=oldest]
            if results:
                self.stage_cpu_seconds['emit_poll_per_frame'].append((time.thread_time()-poll_cpu)/len(results))
            self.emit_poll_cpu_seconds+=time.thread_time()-poll_cpu
        return results

    def hold(self,active,source='local',reason='manual',now=None):
        with self.lock:
            return self.control.set_hold(active,source,reason,time.monotonic() if now is None else now)

    @property
    def stats(self):
        return {'outputs':self.outputs,'protected':self.protected_count,'late_ingest':self.late_ingest,
                'buffered_frames':len(self.frames),'buffer_evictions':self.buffer_evictions,
                'stage_seconds':{name:list(values) for name,values in self.stage_seconds.items()},
                'stage_thread_cpu_seconds':{name:list(values) for name,values in self.stage_cpu_seconds.items()},
                'stage_sample_capacity':4096,
                'stage_cpu_scope':'emit_poll_per_frame is a batch-normalized emitting-poll sample, not a frame-weighted p95; motion_submit measures enqueue only',
                'all_poll_thread_cpu_seconds':self.emit_poll_cpu_seconds,
                'all_poll_thread_cpu_ms_per_output':1000*self.emit_poll_cpu_seconds/self.outputs if self.outputs else None,
                'motion_worker':getattr(self.motion,'stats',{}),
                'lanes':{name:lane.stats for name,lane in self.lanes.items()},'transitions':self.control.transitions}

    def close(self):
        errors=[]
        workers=([self.motion] if hasattr(self.motion,'close') else [])+list(self.lanes.values())
        for lane in workers:
            try:
                lane.close()
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError('; '.join(errors))
