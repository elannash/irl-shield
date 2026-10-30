"""Reproducible offline quality/performance bench. See bench/README.md for contracts."""
import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from bench.judges import Judges
from bench.metrics import fidelity, quantiles
from shield.masking import masked_frame
from bench.scoring import score_records
from bench.independence import policy_metadata, annotate_card
from bench.pipeline import run
from bench.provenance import pipeline_fingerprint,validate_sustained

ROOT = Path(__file__).resolve().parents[1]


def variant(clip, out, synthetic, seconds):
    from bench.synthetic import overlay
    path = ROOT / clip['path']
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open fixture: {path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    width,height = (int(cap.get(p)) for p in (cv2.CAP_PROP_FRAME_WIDTH,cv2.CAP_PROP_FRAME_HEIGHT))
    if min(width,height) < 720:
        raise ValueError('Fixture below 720p')
    n = min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), round(seconds*fps))
    seed = int(clip['synthetic_seed'])
    truth = []
    previous_gray=None
    camera=np.zeros(2,dtype=float)
    out.parent.mkdir(parents=True,exist_ok=True)
    logpath = out.with_suffix('.prepare.log')
    with logpath.open('w') as log:
        writer = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo',
            '-pix_fmt','bgr24','-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0','-an',
            '-c:v','h264_videotoolbox','-b:v','15M','-bf','0',str(out)],stdin=subprocess.PIPE,stderr=log)
        try:
            for f in range(n):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Fixture truncated during decode')
                labels = []
                if synthetic:
                    gray=cv2.cvtColor(cv2.resize(frame,(320,180)),cv2.COLOR_BGR2GRAY)
                    if previous_gray is not None:
                        points=cv2.goodFeaturesToTrack(previous_gray,100,.02,8)
                        if points is not None:
                            moved,status,_=cv2.calcOpticalFlowPyrLK(previous_gray,gray,points,None)
                            valid=status.ravel()==1
                            if valid.sum()>=8:
                                motion=np.median((moved-points).reshape(-1,2)[valid],axis=0)
                                camera+=motion*np.array([width/320,height/180])
                    previous_gray=gray
                    frame, labels = overlay(frame,f,fps,seed,camera_offset=tuple(camera))
                    for label in labels:
                        quad = np.array(label['quad'])
                        label['box'] = [float(quad[:,0].min()),float(quad[:,1].min()),float(quad[:,0].max()),float(quad[:,1].max())]
                truth.append(labels)
                writer.stdin.write(frame.tobytes())
        finally:
            cap.release()
            writer.stdin.close()
            writer.wait(timeout=60)
        if writer.returncode:
            raise RuntimeError(logpath.read_text())
    out.with_suffix('.truth.json').write_text(json.dumps(truth))
    return truth


def score(input_path, output_path, judge, synthetic_truth, options, candidate):
    metadata = policy_metadata(candidate, options)
    cap = cv2.VideoCapture(str(input_path))
    masked = cv2.VideoCapture(str(output_path))
    masks = json.loads(output_path.with_suffix('.masks.json').read_text())
    outputs, guards = [], []
    input_readings=[]
    for index, record in enumerate(masks):
        ok, before = cap.read()
        good, after = masked.read()
        if not ok or not good:
            raise RuntimeError(f'Quality decode missing frame {index}')
        original_readings=judge.read(before)
        input_readings.append(original_readings)
        outputs.append(judge.read(after))
        _, mask = masked_frame(before,record['boxes'],options['padding'])
        if candidate == 'slate':
            mask[:] = 255
        guards.append(fidelity(before,after,mask))
        if index % 30 == 0:
            print(f'  judge frame {index}/{len(masks)}',flush=True)
    if cap.read()[0] or masked.read()[0]:
        raise RuntimeError('Unexpected extra frames')
    cap.release()
    masked.release()
    quality,details=score_records(input_readings,outputs,synthetic_truth,guards,detector_families=metadata['detector_families'])
    quality['judging']=details['judging']=getattr(judge,'metadata',None)
    output_path.with_suffix('.evidence.json').write_text(json.dumps(details))
    return {**quality,'masked_area_fraction':quantiles([m['mask_fraction'] for m in masks]),
            'outside_mae_p95':quantiles([g['outside_mae'] for g in guards if g['outside_mae'] is not None])['p95']}


def summary(card):
    print('\n'+card['run_id']+'  '+card['split']+'  '+card['candidate'])
    for kind in ['natural','synthetic']:
        s = card[kind]
        print(f"  {kind}: {s['hidden']}/{s['total']} intervals hidden ({s['hidden_fraction']})")
    print('  masked area',card['masked_area_fraction'],'real video',card['real_video_pass'])
    print('  minimum clip fps',card['minimum_clip_fps'],'latency',card['latency_seconds'])
    print('  gate',card['gate_1'],'baseline deltas',card['baseline_deltas'])


def build_gate(card):
    """Build the reference-only verdict and its independent-truth report."""
    results, sustained = card['clips'], card['sustained']
    controls=[r['synthetic_input_control'] for r in results if r.get('synthetic_variant') and 'synthetic_input_control' in r]
    control_total=sum(c['total'] for c in controls)
    control_unreadable=sum(c['unreadable'] for c in controls)
    card['synthetic_input_control']={'total':control_total,'unreadable':control_unreadable}
    independence=annotate_card(card)
    card['gate_1']={'independent_judges':independence['sufficient_independent_engines'],'judge_discrimination':control_total>0 and control_unreadable==0,'natural':card['natural']['hidden_fraction'] is not None and card['natural']['hidden_fraction']>=.9,
                    'synthetic':card['synthetic']['total']>0 and card['synthetic']['hidden_fraction']==1,
                    'masked_area':card['masked_area_fraction']['p50']<=.2,
                    'throughput':bool(sustained) and sustained['results']['720-saturated']['fps']>=30,
                    'latency':bool(sustained) and sustained['results']['720-paced']['realtime_added_latency_seconds']['p95']<=1,
                    'real_video':card['real_video_pass']}
    card['gate_version']='superseded-synchronous-reference-only'
    card['gate_1']['eligible']=False
    card['gate_1']['pass']=False
    return card


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--with-sustained',action='store_true',help='Measure30s throughput and paced latency on the slowest quality fixture')
    p.add_argument('--sustained',type=Path,help='Matching bench.perf sustained.json')
    p.add_argument('--candidate',default='vision-fast')
    p.add_argument('--split',choices=['tune','heldout'],default='tune')
    p.add_argument('--clip')
    p.add_argument('--seconds',type=float,default=5)
    p.add_argument('--padding',type=float,default=.3)
    p.add_argument('--accurate-stride',type=int,default=6)
    p.add_argument('--rectangle-width',type=int,default=640)
    p.add_argument('--accurate-width',type=int,default=960)
    p.add_argument('--lookahead',type=int,default=0)
    p.add_argument('--persistence',type=int,default=1)
    p.add_argument('--stride',type=int,default=1)
    p.add_argument('--detect-width',type=int,default=1280)
    p.add_argument('--encoder',choices=['h264_videotoolbox','h264_nvenc','libx264'],default='h264_videotoolbox')
    p.add_argument('--static-model',action='store_true')
    p.add_argument('--provider',choices=['cpu','coreml','cuda'],default='cpu')
    p.add_argument('--limit-side-len',type=int,default=960)
    p.add_argument('--run-id',default=time.strftime('%Y%m%d-%H%M%S'))
    p.add_argument('--natural-only',action='store_true')
    p.add_argument('--performance-only',action='store_true')
    args=p.parse_args()
    fingerprint=pipeline_fingerprint()
    options={'encoder':args.encoder,'static_model':args.static_model,'accurate_stride':args.accurate_stride,'rectangle_width':args.rectangle_width,'accurate_width':args.accurate_width,'lookahead':args.lookahead,'padding':args.padding,'persistence':args.persistence,'stride':args.stride,'detect_width':args.detect_width,'provider':args.provider,'limit_side_len':args.limit_side_len}
    policy_metadata(args.candidate, options)
    manifest=json.loads((ROOT/'fixtures/manifest.json').read_text())
    clips=[c for c in manifest['clips'] if c['split']==args.split and (not args.clip or c['id']==args.clip)]
    if not clips:
        raise ValueError('Empty fixture selection')
    directory=ROOT/'out'/args.run_id
    directory.mkdir(parents=True,exist_ok=False)
    judge=None if args.performance_only else Judges(args.candidate,ROOT/'out/judge-cache')
    results=[]
    try:
        for clip in clips:
            raw=ROOT/clip['path']
            from fixtures.prepare import verify_cached
            verify_cached(raw,clip)
            for synthetic in ([False] if args.natural_only else [False,True]):
                label=clip['id']+('-synthetic' if synthetic else '-natural')
                print(f'{label}: {args.candidate}',flush=True)
                source=directory/f'{label}-input.mp4'
                truth=variant(clip,source,synthetic,args.seconds)
                output=directory/f'{label}-masked.mp4'
                perf=run(source,output,args.candidate,options)
                quality={} if args.performance_only else score(source,output,judge,truth,options,args.candidate)
                results.append({'clip':clip['id'],'synthetic_variant':synthetic,'performance':perf,**quality})
    finally:
        if judge:
            judge.close()
    if fingerprint!=pipeline_fingerprint():
        raise RuntimeError('Pipeline source changed during quality measurement')
    card={'pipeline_sha256':fingerprint,'scope':'Latin-script text and Arabic digits. Natural truth requires input confidence>=0.9 on at least2 frames per interval; synthetic truth includes every annotated visible label. Judges: Tesseract eng, Apple Vision accurate en-US, PP-OCRv5 English-mobile. Non-Latin coverage is unproven.','schema_version':1,'run_id':args.run_id,'candidate':args.candidate,'split':args.split,
          'options':options,'seconds_per_clip':args.seconds,'pilot':bool(args.clip) or args.seconds<5,
          'manifest_sha256':hashlib.sha256((ROOT/'fixtures/manifest.json').read_bytes()).hexdigest(),
          'environment':{'system':platform.platform(),'machine':platform.machine(),
                         'python':platform.python_version(),'opencv':cv2.__version__,
                         'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
                         'hardware':subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string','hw.ncpu','hw.memsize'],text=True).splitlines()},'judges':judge.names if judge else [],'judge_models':judge.paddle.metadata if judge else None,'clips':results}
    for kind in ['natural','synthetic']:
        hidden=sum(r.get(kind,{}).get('hidden',0) for r in results)
        total=sum(r.get(kind,{}).get('total',0) for r in results)
        card[kind]={'hidden':hidden,'total':total,'hidden_fraction':hidden/total if total else None}
    all_masks=[]
    for file in directory.glob('*.masks.json'):
        all_masks.extend(m['mask_fraction'] for m in json.loads(file.read_text()))
    card['masked_area_fraction']=quantiles(all_masks)
    card['minimum_clip_fps']=min(r['performance']['fps'] for r in results)
    card['latency_seconds']={q:max(r['performance']['latency_seconds'][q] for r in results) for q in ['p50','p95']}
    card['latency_aggregation']='Maximum per-clip quantile, not pooled; gate uses the separate paced sustained run.'
    card['real_video_pass']=all(r.get('real_video_pass',False) for r in results)
    if args.sustained and args.with_sustained:
        raise ValueError('Choose --sustained or --with-sustained')
    sustained=json.loads(args.sustained.read_text()) if args.sustained else None
    if args.with_sustained:
        from bench.perf import measure
        slowest=min(results,key=lambda r:r['performance']['fps'])
        label=slowest['clip']+('-synthetic' if slowest['synthetic_variant'] else '-natural')
        sustained=measure(args.candidate,options,directory/f'{label}-input.mp4',directory/'sustained')
    if sustained:
        slowest=min(results,key=lambda r:r['performance']['fps'])
        label=slowest['clip']+('-synthetic' if slowest['synthetic_variant'] else '-natural')
        source_sha=hashlib.sha256((directory/f'{label}-input.mp4').read_bytes()).hexdigest()
        validate_sustained(sustained,args.candidate,options,source_sha,fingerprint)
    card['sustained']=sustained
    card['cpu_percent_one_core_100']=quantiles([r['performance']['cpu_percent_one_core_100'] for r in results])
    card['peak_tree_rss_mb']=max(r['performance']['peak_tree_rss_mb'] for r in results)
    build_gate(card)
    baseline_path=ROOT/'bench/baseline.json'
    baseline=json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    card['baseline_comparison']='Same scoring thresholds; reference corpus differs' if baseline.get('manifest_sha256')!=card['manifest_sha256'] or baseline.get('pilot')!=card['pilot'] or baseline.get('split')!=card['split'] else 'Same manifest and scoring thresholds'
    card['baseline_deltas']={k:card[k]['hidden_fraction']-baseline[k]['hidden_fraction']
                             for k in ['natural','synthetic'] if baseline.get(k,{}).get('hidden_fraction') is not None and card[k]['hidden_fraction'] is not None}
    source_paths=sorted(set(ROOT.glob('bench/*.py'))|set(ROOT.glob('Sources/**/*.swift'))|set(ROOT.glob('scripts/*'))|{ROOT/'models/manifest.json',ROOT/'fixtures/manifest.json'})
    digest=hashlib.sha256()
    for path in source_paths:
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes())
    card['code_sha256']=digest.hexdigest()
    (directory/'scorecard.json').write_text(json.dumps(card,indent=2))
    (ROOT/'out/scorecard.json').write_text(json.dumps(card,indent=2))
    summary(card)


if __name__=='__main__':
    main()
