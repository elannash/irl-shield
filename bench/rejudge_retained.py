"""Fresh OCR on a sealed tune movie; original processing/evidence stay immutable."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from bench.clocked_bench import score_video, aggregate_card
from bench.cross_host import bundle_file, validate_card
from bench.clocked_pipeline import file_sha256

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run',required=True)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if any(Path(x).name!=x or x in ('.','..') for x in (args.source_run,args.run_id)):
        parser.error('Run IDs must be basenames')
    source=ROOT/'out'/args.source_run;destination=ROOT/'out'/args.run_id
    original=source/'scorecard.json';card=deepcopy(json.loads(original.read_text()))
    expected={c['id'] for c in json.loads((ROOT/'fixtures/manifest.json').read_text())['clips'] if c['split']=='tune'}
    if card['split']!='tune' or len(card['clips'])!=14 or {r['clip'] for r in card['clips']}!=expected:
        raise ValueError('Fresh judging requires all seven tune clips, natural and synthetic')
    plan_path=source/'measurement-plan.json';plan=json.loads(plan_path.read_text())
    if file_sha256(plan_path)!=plan_path.with_suffix('.sha256').read_text().strip():
        raise ValueError('Original sealed plan changed')
    for name,identity in plan['artifacts'].items():
        p=bundle_file(source,name)
        if p.stat().st_size!=identity['bytes'] or file_sha256(p)!=identity['sha256']:
            raise ValueError('Original sealed artifact changed: '+name)
    for row in card['clips']:
        label=row['clip']+('-synthetic' if row['synthetic_variant'] else '-natural')
        row['source']=str(source/(label+'-input.mp4'));row['output']=str(source/(label+'-masked.mp4'))
    validate_card(card,source)
    destination.mkdir(parents=True,exist_ok=False)
    from bench.judges import Judges
    judge=Judges(card['candidate'],ROOT/'out/judge-cache')
    try:
        for row in card['clips']:
            label=row['clip']+('-synthetic' if row['synthetic_variant'] else '-natural')
            for suffix in ('-input.mp4','-input.truth.json','-masked.mp4','-masked.masks.json','-masked.performance.json','-masked.mask-pixels.zip','-masked.egress.json'):
                (destination/(label+suffix)).symlink_to(source/(label+suffix))
            row['source']=str(destination/(label+'-input.mp4'));row['output']=str(destination/(label+'-masked.mp4'))
            truth=json.loads((destination/(label+'-input.truth.json')).read_text())
            row.update(score_video(row['source'],row['output'],judge,truth))
            print(label+': fresh independent judging complete',flush=True)
        card['judging']=judge.metadata;card['judges']=list(judge.names)
    finally:judge.close()
    validate_card(card,source)
    card['run_id']=args.run_id
    card['rejudge']={'source_scorecard':str(original),'source_sha256':file_sha256(original),
                    'measurement_plan_sha256':file_sha256(plan_path),'processing_pipeline_sha256':card['pipeline_sha256'],
                    'scope':'Fresh cache-v2 OCR of exact sealed CUDA output; no new detector/performance measurement. Original evidence untouched.'}
    card['queue_measurement_trust']={'clean':False,'scope':'Historical diagnostic processing; this untimed OCR run cannot qualify performance.'}
    aggregate_card(card,destination)

if __name__=='__main__':main()
