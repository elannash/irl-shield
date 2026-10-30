"""Rescore unrotated legacy/offline evidence; clocked windows use clocked_bench."""
import argparse
import hashlib
import json
from pathlib import Path

from bench.scoring import score_records
from bench.metrics import masked_area_pass
from bench.independence import retained_policy_metadata, annotate_card

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('run_id')
    p.add_argument('--output-id')
    a=p.parse_args()
    source=ROOT/'out'/a.run_id
    output_id=a.output_id or 'regraded-'+a.run_id
    dest=ROOT/'out'/output_id
    card=json.loads((source/'scorecard.json').read_text())
    if card.get('schema_version',0)>=2:
        raise ValueError('Clocked quality must be scored through bench.clocked_bench; regrade accepts unrotated legacy/offline evidence only')
    families=retained_policy_metadata(card)['detector_families']
    area_valid=masked_area_pass(card)
    retained=[]
    for record in card['clips']:
        label=record['clip']+('-synthetic' if record['synthetic_variant'] else '-natural')
        evidence=json.loads((source/f'{label}-masked.evidence.json').read_text())
        if ('quality_window' in evidence or any('source_frame' in row or 'original_frame' in row
                                              for row in evidence.get('presentation',[]))):
            raise ValueError('Clocked/windowed truth mapping is unsupported by the legacy/offline regrader')
        truth=json.loads((source/f'{label}-input.truth.json').read_text())
        retained.append((record,label,evidence,truth))
    dest.mkdir(parents=True,exist_ok=False)
    card['rescore_of']=card['run_id']
    card['scope']=('Latin-script text and Arabic digits; natural input confidence>=.9 on at least2 frames; '
                   'synthetic truth splits at every known visibility gap; output confidence>=.5. '
                   'Judges: Tesseract eng, Apple Vision accurate en-US, PP-OCRv5 English-mobile. '
                   'Non-Latin coverage is unproven. '+card.get('scope',''))
    card['run_id']=output_id
    card['evidence_base']=str(source)
    for record,label,evidence,truth in retained:
        if 'raw_input_readings' not in evidence:
            raise ValueError('Independent rescore requires original raw judge-tagged readings')
        quality,details=score_records(evidence['raw_input_readings'],evidence['output_readings'],truth,evidence['guards'],detector_families=families)
        record.update(quality)
        (dest/f'{label}-masked.evidence.json').write_text(json.dumps(details))
    for kind in ['natural','synthetic']:
        hidden=sum(r[kind]['hidden'] for r in card['clips'])
        total=sum(r[kind]['total'] for r in card['clips'])
        card[kind]={'hidden':hidden,'total':total,'hidden_fraction':hidden/total if total else None}
    controls=[r['synthetic_input_control'] for r in card['clips'] if r['synthetic_variant']]
    total=sum(r['total'] for r in controls)
    unreadable=sum(r['unreadable'] for r in controls)
    card['synthetic_input_control']={'total':total,'unreadable':unreadable,
                                     'unverified_intervals':max(0,card['synthetic']['total']-total)}
    card['gate_1'].update({'natural':card['natural']['hidden_fraction'] is not None and card['natural']['hidden_fraction']>=.9,
                          'synthetic':card['synthetic']['total']>0 and card['synthetic']['hidden_fraction']==1,
                          'judge_discrimination':total>0 and total==card['synthetic']['total'] and unreadable==0,'eligible':False,'pass':False})
    if 'quality_checks' in card:
        for key in ['natural','synthetic','judge_discrimination']:
            card['quality_checks'][key]=card['gate_1'][key]
    independence=annotate_card(card)
    card['gate_1']['independent_judges']=independence['sufficient_independent_engines']
    if 'quality_checks' in card:
        card['quality_checks']['independent_judges']=independence['sufficient_independent_engines']
        checks=card['quality_checks']
        checks['masked_area']=checks.get('masked_area') is True and area_valid
        card['comparison_valid']=bool(checks['independent_judges'] and checks['judge_discrimination'] and checks['protected'] and card['real_video_pass'] and checks.get('masked_area') is True)
    card['measurement_code_sha256']=hashlib.sha256((ROOT/'bench/scoring.py').read_bytes()+(ROOT/'bench/metrics.py').read_bytes()).hexdigest()
    baseline=json.loads((ROOT/'bench/baseline.json').read_text())
    card.pop('baseline_deltas',None)
    card['baseline_deltas_pp']={kind:(100*(card[kind]['hidden_fraction']-baseline[kind]['hidden_fraction'])
                                     if card[kind]['hidden_fraction'] is not None and baseline[kind]['hidden_fraction'] is not None else None)
                                for kind in ('natural','synthetic')}
    card['baseline_reference']={'path':'bench/baseline.json','run_id':baseline.get('run_id'),
                                'sha256':hashlib.sha256((ROOT/'bench/baseline.json').read_bytes()).hexdigest(),
                                'natural':baseline['natural'],'synthetic':baseline['synthetic']}
    card['rescore_scope']='Unrotated legacy/offline evidence only; no accepted real-time performance claim'
    card['regrade_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (dest/'scorecard.json').write_text(json.dumps(card,indent=2))
    print(json.dumps({k:card[k] for k in ['run_id','natural','synthetic','synthetic_input_control','gate_1']},indent=2))


if __name__=='__main__':
    main()
