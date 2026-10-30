"""Root EX job: BlazeFace controls and privacy scoring of retained parity batches."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import cv2
from bench.faces.parity import frames
from bench.faces.judge import BlazeFaceJudge
from bench.faces.scoring import score_frame
from shield.faces import Face, FaceBatch, FacePolicy, opaque


def main():
    p=argparse.ArgumentParser();p.add_argument('--parity',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--background-root',type=Path)
    a=p.parse_args();root=Path(__file__).resolve().parents[2];retained=json.loads(a.parity.read_text())
    judge=BlazeFaceJudge();rows=[]
    try:
        rendered=list(frames(root,a.background_root))
        if len(rendered)!=len(retained['rows']):raise ValueError('parity source selection mismatch')
        for (label,before,truth,natural),data in zip(rendered,retained['rows']):
            if label!=data['label']:raise ValueError('source label mismatch')
            for arm,values in data['batches'].items():
                if values is None:continue
                batch=FaceBatch(values['source_index'],values['generation'],tuple(values['shape']),time.monotonic(),
                                tuple(Face(tuple(f['box']),f['confidence'],f['track_id']) for f in values['faces']),values['error'])
                for mode in ('all','bystanders','off'):
                    plan=FacePolicy(mode).plan(before.shape[:2],batch.source_index,batch.generation,batch,now=batch.completed_at)
                    score=score_frame(before,opaque(before,plan.mask),truth,plan,judge,mode=mode,natural_background=natural)
                    rows.append({'label':label,'arm':arm,**score})
    finally:judge.close()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    privacy_rows = [r for r in rows if r['truth_faces'] and r['mode'] != 'off']
    acceptance = bool(privacy_rows) and all(r['privacy_pass'] for r in privacy_rows)
    a.out.write_text(json.dumps({'schema_version':1,'parity_sha256':hashlib.sha256(a.parity.read_bytes()).hexdigest(),
                    'acceptance_pass':acceptance,'judge_family':judge.family,'judge_backend':judge.backend,'rows':rows,
                    'limits':'Two fictional adults; natural backgrounds have unlabeled real faces. Full-face control has no placement truth, cannot earn privacy pass. No identity/anonymity inference. No text/real-video guard evaluation.'},indent=2)+'\n')
    print('Face scorecard:',a.out,'rows',len(rows),'acceptance',acceptance)
    return 0 if acceptance else 1


if __name__=='__main__':raise SystemExit(main())
