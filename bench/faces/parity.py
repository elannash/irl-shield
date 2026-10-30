"""Root EX job: exact-model CPU/OpenCV/ORT CUDA parity; no judge dependency."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from shield.faces import FaceBatch, FacePolicy, FaceTracker
from shield.faces.detector import YuNetDetector, model_path
from shield.faces.yunet_ort import YuNetORTDetector, prepare, source_faces
from bench.faces.synthetic import load_assets, overlay


def compare(a, b, shape):
    """Greedy geometric correspondence; tolerances are fixed before queue run."""
    from shield.faces.policy import iou
    pairs = sorted(((iou(x.box, y.box), i, j) for i, x in enumerate(a.faces)
                    for j, y in enumerate(b.faces)), reverse=True)
    used_a, used_b, deltas = set(), set(), []
    for overlap, i, j in pairs:
        if i not in used_a and j not in used_b:
            used_a.add(i);used_b.add(j)
            deltas.append({'iou':overlap,'box_max_px':float(np.max(np.abs(np.array(a.faces[i].box)-b.faces[j].box))),
                           'score_abs':abs(a.faces[i].confidence-b.faces[j].confidence)})
    masks = {}
    for mode in ('all', 'bystanders', 'off'):
        policy = FacePolicy(mode)
        pa = policy.plan(shape, a.source_index, a.generation, a, now=a.completed_at)
        pb = policy.plan(shape, b.source_index, b.generation, b, now=b.completed_at)
        masks[mode] = {'xor_pixels':int(np.count_nonzero(pa.mask != pb.mask)),
                       'xor_fraction':float(np.count_nonzero(pa.mask != pb.mask))/pa.mask.size,
                       'masked_count_equal':len(pa.masked_track_ids)==len(pb.masked_track_ids),
                       'exemption_count_equal':(pa.exempt_track_id is None)==(pb.exempt_track_id is None),
                       'coverage_equal':pa.coverage.ok==pb.coverage.ok}
    return {'count_a':len(a.faces),'count_b':len(b.faces),'count_equal':len(a.faces)==len(b.faces),
            'pairs':deltas,'policy_masks':masks,
            'within_tolerance':a.error is None and b.error is None and len(a.faces)==len(b.faces) and all(d['box_max_px'] <= 1. and d['score_abs'] <= 0.001 for d in deltas)
                and all(m['xor_fraction'] <= 0.001 and m['masked_count_equal'] and m['exemption_count_equal'] and m['coverage_equal'] for m in masks.values())}


def frames(root, background_root=None):
    assets = load_assets(root)
    for scenario in ('selfie-bystander', 'bystanders-only', 'equal-large', 'edge-entry', 'no-people'):
        image, truth = overlay(np.full((720,1280,3),128,np.uint8), 0, assets, scenario)
        yield scenario, image, truth, False
    # Full-face control exercises the large, frame-filling case separately.
    face = assets[0][0]
    yield 'full-face', cv2.cvtColor(face[:900, 200:1100], cv2.COLOR_BGRA2BGR), (), False
    if background_root is not None:
        manifest = json.loads((root/'fixtures/manifest.json').read_text())
        tune = [c for c in manifest['clips'] if c['split']=='tune']
        if len(tune)!=7:
            raise ValueError('expected exactly seven tune clips')
        for clip in tune:
            path = Path(background_root)/clip['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=clip['sha256']:
                raise ValueError('tune source hash mismatch: '+clip['id'])
            cap=cv2.VideoCapture(str(path))
            try:
                for index in (0,30,60):
                    cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,background=cap.read()
                    if not ok:raise ValueError('tune frame decode failed')
                    image,truth=overlay(background,index,assets,'selfie-bystander' if index!=30 else 'bystanders-only')
                    yield f"tune:{clip['id']}:{index}",image,truth,True
            finally:cap.release()



def raw_row_parity(reference, candidate):
    reference = np.asarray(reference, dtype=np.float32).reshape(-1, 15)
    candidate = np.asarray(candidate, dtype=np.float32).reshape(-1, 15)
    # Both implementations use score-ordered NMS, but pair geometrically so ties
    # do not manufacture a numeric difference from row order alone.
    used = set()
    differences = []
    for row in reference:
        choices = [(float(np.max(np.abs(row[:4] - other[:4]))), j) for j, other in enumerate(candidate) if j not in used]
        if not choices:
            break
        _, j = min(choices)
        used.add(j)
        differences.append({'xywh_max_px_at_graph_scale':float(np.max(np.abs(row[:4]-candidate[j,:4]))),
                            'landmark_max_px_at_graph_scale':float(np.max(np.abs(row[4:14]-candidate[j,4:14]))),
                            'score_abs':float(abs(row[14]-candidate[j,14]))})
    return {'reference_rows':len(reference),'candidate_rows':len(candidate),'deltas':differences,
            'within_tolerance':len(reference)==len(candidate) and all(d['xywh_max_px_at_graph_scale']<=1. and d['landmark_max_px_at_graph_scale']<=1. and d['score_abs']<=0.001 for d in differences)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--background-root',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[2]
    cv2.setNumThreads(1)
    cpu=YuNetDetector()
    opencv_square=cv2.FaceDetectorYN.create(str(model_path('yunet-2023mar')),'',(640,640),0.6,0.3,5000)
    square_tracker=FaceTracker();ort_tracker=FaceTracker();cuda_tracker=FaceTracker()
    ort_cpu=YuNetORTDetector(provider='CPUExecutionProvider',profile_prefix=a.out/'cpu')
    cuda=None;errors=[];rows=[];placement={}
    try:
        try:cuda=YuNetORTDetector(profile_prefix=a.out/'cuda')
        except Exception as e:
            errors.append({'stage':'strict-cuda-init','type':type(e).__name__,'detail':str(e)})
            # Explicit diagnostic arm, never labeled strict GPU or eligible by default.
            try:cuda=YuNetORTDetector(profile_prefix=a.out/'cuda-diagnostic',allow_cpu_fallback=True)
            except Exception as e:errors.append({'stage':'diagnostic-cuda-init','type':type(e).__name__,'detail':str(e)})
        for index,(label,image,truth,natural) in enumerate(frames(root,a.background_root)):
            dynamic=cpu.detect(image,index,0)
            padded,scales=prepare(image);_,raw=opencv_square.detect(padded)
            square=square_tracker.assign(FaceBatch(index,0,image.shape[:2],time.monotonic(),source_faces(raw if raw is not None else [],image.shape[:2],scales)))
            cpu_rows,cpu_scales=ort_cpu.infer_rows(image)
            oc=ort_tracker.assign(FaceBatch(index,0,image.shape[:2],time.monotonic(),source_faces(cpu_rows,image.shape[:2],cpu_scales)))
            gpu=None;gpu_rows=None
            if cuda:
                gpu_rows,gpu_scales=cuda.infer_rows(image)
                gpu=cuda_tracker.assign(FaceBatch(index,0,image.shape[:2],time.monotonic(),source_faces(gpu_rows,image.shape[:2],gpu_scales)))
            rows.append({'label':label,'shape':list(image.shape[:2]),'truth':[asdict(t) for t in truth], 'natural_background':natural,
                         'batches':{name:asdict(batch) if batch else None for name,batch in [('opencv-dynamic',dynamic),('opencv-square',square),('ort-cpu',oc),('ort-cuda',gpu)]},
                         'square_opencv_vs_ort_cpu':compare(square,oc,image.shape[:2]),
                         'raw_square_opencv_vs_ort_cpu':raw_row_parity(raw if raw is not None else [],cpu_rows),
                         'raw_ort_cpu_vs_cuda':raw_row_parity(cpu_rows,gpu_rows) if gpu_rows is not None else None,
                         'dynamic_opencv_vs_square':compare(dynamic,square,image.shape[:2]),
                         'ort_cpu_vs_cuda':compare(oc,gpu,image.shape[:2]) if gpu else None})
    finally:
        placement['cpu']=ort_cpu.finish_profile()
        if cuda:placement['cuda']=cuda.finish_profile()
    positive_controls = all(all(batch is not None and batch['error'] is None and len(batch['faces']) >= (len(row['truth']) or 1) for batch in row['batches'].values()) for row in rows if row['label'] != 'no-people')
    negative_controls = all(all(batch is not None and batch['error'] is None and not batch['faces'] for batch in row['batches'].values()) for row in rows if row['label'] == 'no-people')
    report={'schema_version':1, 'positive_controls':positive_controls, 'negative_controls':negative_controls,'precision':'FP32','tolerances':{'box_max_px':1.,'score_abs':0.001,'policy_mask_xor_fraction':0.001,'count_exemption_coverage':'exact'},
            'rows':rows,'placement':placement,'errors':errors,'graph':ort_cpu.graph_schema,
            'source_note':'OpenCV dynamic arm has tight divisor32 padding. Exact pinned ORT graph requires640x640. Square OpenCV arm isolates decoder/provider parity.',
            'eligible': bool(rows) and positive_controls and negative_controls and not errors and placement.get('cuda',{}).get('placement_verified',False)
                and all(r['square_opencv_vs_ort_cpu']['within_tolerance'] and r['ort_cpu_vs_cuda']['within_tolerance'] and r['raw_square_opencv_vs_ort_cpu']['within_tolerance'] and r['raw_ort_cpu_vs_cuda']['within_tolerance'] for r in rows)}
    (a.out/'parity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'eligible':report['eligible'],'errors':errors,'frames':len(rows),'report':str(a.out/'parity.json')},indent=2))
    return 0 if report['eligible'] else 1


if __name__=='__main__':raise SystemExit(main())
