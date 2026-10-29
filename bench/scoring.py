"""OCR-observed interval scoring, separate from detectors and video I/O."""
import numpy as np
from bench.metrics import matches,iou,readable,truth_from_readings


def same_occurrence(track,index,box):
    last_index,last_box=track['observations'][-1]
    if iou(last_box,box)>0:
        return True
    if len(track['observations'])<2:
        return False
    previous_index,previous_box=track['observations'][-2]
    velocity=(np.array(last_box)-previous_box)/max(1,last_index-previous_index)
    predicted=np.array(last_box)+velocity*(index-last_index)
    return iou(predicted,box)>0


def intervals(truth, output, synthetic):
    tracks = []
    for index, targets in enumerate(truth):
        used = set()
        for item in targets:
            if synthetic and not item['visible']:
                continue
            candidates=[t for t in tracks if id(t) not in used and
                        ((synthetic and t['id']==item['id'] and t['last']==index-1) or
                         (not synthetic and matches(t['text'],item['text']) and same_occurrence(t,index,item['box'])))]
            match=max(candidates,key=lambda t:iou(t['observations'][-1][1],item['box']),default=None)
            if match is None:
                match = {'id': item.get('id',str(len(tracks))), 'text':item['text'],
                         'first':index, 'last':index, 'observations':[], 'texts':[]}
                tracks.append(match)
            if len(item['text'])>len(match['text']):
                match['text']=item['text']
            if item['text'] not in match['texts']:
                match['texts'].append(item['text'])
            match['last'] = index
            match['observations'].append((index,item['box']))
            used.add(id(match))
    for track in tracks:
        track['leak_frames'] = []
        observations = dict(track['observations'])
        observed_frames=np.array([f for f,_ in track['observations']])
        observed_boxes=np.array([box for _,box in track['observations']])
        for f in range(track['first'],track['last']+1):
            box=[float(np.interp(f,observed_frames,observed_boxes[:,k])) for k in range(4)]
            if any(readable({'text':text,'box':box},output[f]) for text in track['texts']):
                track['leak_frames'].append(f)
        track['leaked'] = bool(track['leak_frames'])
    return tracks


def score_records(input_readings,outputs,synthetic_truth,guards):
    inputs=[truth_from_readings([r for r in frame if r['confidence']>=.9]) for frame in input_readings]
    natural_truth=[[t for t in frame if not any(matches(t['text'],l['text']) and iou(t['box'],l['box'])>.05 for l in synthetic_truth[i])]
                   for i,frame in enumerate(inputs)]
    natural_all=intervals(natural_truth,outputs,False)
    natural=[t for t in natural_all if len(t['observations'])>=2]
    synthetic=intervals(synthetic_truth,outputs,True)
    control=intervals(synthetic_truth,input_readings,True)
    real=bool(guards) and all(g['pass'] for g in guards)
    def result(tracks):
        total=len(tracks)
        hidden=sum(not t['leaked'] for t in tracks) if real else 0
        return {'total':total,'hidden':hidden,'hidden_fraction':hidden/total if total else None}
    details={'natural':natural,'excluded_unstable_natural':[t for t in natural_all if len(t['observations'])<2],
             'synthetic':synthetic,'guards':guards,'input_readings':inputs,'raw_input_readings':input_readings,'output_readings':outputs}
    quality={'excluded_unstable_natural_intervals':len(natural_all)-len(natural),
             'natural':result(natural),'synthetic':result(synthetic),
             'synthetic_input_control':{'total':len(control),'unreadable':sum(not t['leaked'] for t in control)},
             'real_video_pass':real}
    return quality,details
