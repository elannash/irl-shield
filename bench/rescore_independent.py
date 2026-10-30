"""Rescore independent truth/all-judge leaks, retaining both earlier scoring columns."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from bench.independence import retained_policy_metadata, annotate_card
from bench.scoring import score_records

ROOT=Path(__file__).resolve().parents[1]


def score_evidence(evidence,truth,families):
    if 'raw_input_readings' not in evidence:
        raise ValueError('Independent rescore requires raw judge-tagged input readings')
    if 'quality_window' in evidence:
        presentation=evidence['presentation']
        if len(presentation)!=len(evidence['raw_input_readings']):
            raise ValueError('Clocked source-frame mapping is incomplete')
        indices=[row['source_frame'] for row in presentation]
        if any(not isinstance(i,int) or not 0<=i<len(truth) for i in indices):
            raise ValueError('Clocked source-frame index is invalid')
        truth=[truth[i] for i in indices]
    return score_records(evidence['raw_input_readings'],evidence['output_readings'],truth,
                         evidence['guards'],detector_families=families)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--independent-both',type=Path,required=True)
    args=parser.parse_args()
    comparison=json.loads((ROOT/'bench/results/m1-tune-comparison.json').read_text());rows=[]
    prior_bytes=args.independent_both.read_bytes()
    prior={r['run_id']:r for r in json.loads(prior_bytes)['rows']}
    retained=[]
    for original in comparison['rows']:
        source=ROOT/original['source'];raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=original['source_sha256']:
            raise ValueError('Original comparison card changed')
        old=json.loads(raw)
        metadata=retained_policy_metadata(old)
        retained.append((original,source,old,metadata))
    args.out.mkdir(parents=True,exist_ok=False)
    for original,source,old,metadata in retained:
        card=deepcopy(old);families=metadata['detector_families']
        dest=args.out/card['run_id'];dest.mkdir()
        artifacts=[]
        for record in card['clips']:
            label=record['clip']+('-synthetic' if record['synthetic_variant'] else '-natural')
            relative=Path(original['source']).parent
            evidence_path=args.retained_root/relative/(label+'-masked.evidence.json')
            truth_path=args.retained_root/relative/(label+'-input.truth.json')
            if not evidence_path.is_file():
                evidence_path=ROOT/relative/evidence_path.name;truth_path=ROOT/relative/truth_path.name
            if not truth_path.is_file():
                parts=Path(record['source']).parts
                last_out=max(i for i,value in enumerate(parts) if value=='out')
                relative_truth=Path(*parts[last_out:]).with_suffix('.truth.json')
                truth_path=args.retained_root/relative_truth
                if not truth_path.is_file():truth_path=ROOT/relative_truth
            evidence=json.loads(evidence_path.read_text());truth=json.loads(truth_path.read_text())
            quality,details=score_evidence(evidence,truth,families)
            record.update(quality)
            # Keep clocked frame mapping and protection/window accounting exactly.
            for key in ('quality_window','presentation','frame_guards'):
                if key in evidence:details[key]=evidence[key]
            (dest/(label+'-masked.evidence.json')).write_text(json.dumps(details))
            artifacts.append({'evidence':str(evidence_path),'sha256':hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                              'truth':str(truth_path),'truth_sha256':hashlib.sha256(truth_path.read_bytes()).hexdigest()})
        for kind in ('natural','synthetic'):
            hidden=sum(r[kind]['hidden'] for r in card['clips']);total=sum(r[kind]['total'] for r in card['clips'])
            card[kind]={'hidden':hidden,'total':total,'hidden_fraction':hidden/total if total else None}
        controls=[r['synthetic_input_control'] for r in card['clips'] if r['synthetic_variant']]
        card['synthetic_input_control']={k:sum(r[k] for r in controls) for k in ('total','unreadable')}
        previous=prior[card['run_id']]
        if previous['old_pooled']!={k:old[k] for k in ('natural','synthetic')}:
            raise ValueError('Previous pooled comparison differs from original card')
        for kind in ('natural','synthetic'):
            new,former=card[kind],previous['independent'][kind]
            if new['total']!=former['total'] or new['hidden']>former['hidden']:
                raise ValueError('All-judge leaks cannot shrink independent truth or add hidden credit')
        card['independent_both_superseded']={'scope':'Superseded independent truth AND independent-only output leaks; diagnostic history, not primary.',**previous['independent']}
        scope=annotate_card(card)
        for kind in ('natural','synthetic'):
            if card['pooled_not_independent'][kind]!=old[kind]:
                raise ValueError('Original all-judge pooled count did not reproduce')
        checks={'natural':card['natural']['hidden_fraction'] is not None and card['natural']['hidden_fraction']>=.9,
                'synthetic':card['synthetic']['total']>0 and card['synthetic']['hidden_fraction']==1.,
                'judge_discrimination':card['synthetic_input_control']['total']>0 and card['synthetic_input_control']['unreadable']==0,
                'independent_judges':scope['sufficient_independent_engines']}
        card['gate_1'].update(checks);card['gate_1'].update({'eligible':False,'pass':False})
        if 'quality_checks' in card:
            card['quality_checks'].update(checks)
            c=card['quality_checks'];card['comparison_valid']=all(c.get(k) is True for k in ('judge_discrimination','independent_judges','protected','real_video')) and c.get('masked_area') is True
        baseline=json.loads((ROOT/'bench/baseline.json').read_text())
        card['baseline_deltas_pp']={k:100*(card[k]['hidden_fraction']-baseline[k]['hidden_fraction']) if card[k]['hidden_fraction'] is not None and baseline[k]['hidden_fraction'] is not None else None for k in ('natural','synthetic')}
        card['rescore_provenance']={'source_card':str(source),'source_sha256':original['source_sha256'],
            'readings_run_head':'2dd52a610eb569ac51eedc84b7840fa852da96c9',
            'reviewed_source_commit':'ec1d1f96a1c29ab82109c66f27064f3fd6cb326d',
            'cache_origin_limit':'Cached readings may predate the checkpoint; exact cache-miss commit is not recorded. Judge implementation files are byte-identical at2dd52a6 andec1d1f9.',
            'processing_fingerprint':old.get('pipeline_sha256'),'raw_evidence':artifacts,
            'previous_independent_both_comparison_sha256':hashlib.sha256(prior_bytes).hexdigest(),
            'rescore_source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('bench/scoring.py','bench/metrics.py','bench/independence.py','bench/rescore_independent.py')}}
        (dest/'scorecard.json').write_text(json.dumps(card,indent=2)+'\n')
        row={'run_id':card['run_id'],'old_pooled':{k:old[k] for k in ('natural','synthetic')},
             'independent_both':previous['independent'],
             'primary':{k:card[k] for k in ('natural','synthetic')},'judges':scope,
             'input_control':card['synthetic_input_control'],'scorecard':str(dest/'scorecard.json')};rows.append(row)
        (args.out/'comparison.json').write_text(json.dumps({'scope':'PRIMARY = independent truth and synthetic input controls, ALL-judge output leaks. Original pooled and superseded independent-both columns retained; no OCR or performance measurement.','rows':rows},indent=2)+'\n')
        print(json.dumps(row),flush=True)

if __name__=='__main__':main()
