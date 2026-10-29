"""Bind gate receipts to the executed pipeline and the actual measured workload."""
import hashlib
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def pipeline_fingerprint():
    paths=['shield/engine.py','shield/masking.py','bench/provenance.py','bench/pipeline.py','bench/scheduled.py','bench/vision.py',
           'bench/onnx_detectors.py','bench/static_model.py','bench/metrics.py',
           'Sources/VisionBridge/main.swift','models/manifest.json','requirements.txt','requirements-models.txt']
    digest=hashlib.sha256()
    for name in paths:
        path=ROOT/name
        digest.update(name.encode()+b'\0'+path.read_bytes())
    bridge=ROOT/'.build/vision-bridge'
    digest.update(b'vision-executable\0'+(bridge.read_bytes() if bridge.exists() else b'missing'))
    return digest.hexdigest()


def validate_sustained(card,candidate,options,source_sha256,fingerprint):
    expected=(candidate,options,source_sha256,fingerprint)
    actual=(card.get('candidate'),card.get('options'),card.get('source_sha256'),card.get('pipeline_sha256'))
    if actual!=expected:
        raise ValueError('Sustained receipt differs in candidate, options, slowest source, or pipeline fingerprint')
    if card.get('seconds',0)<30:
        raise ValueError('Sustained receipt requests less than30 seconds')
    for name,height,pace in [('720-saturated',720,False),('720-paced',720,True),('1080-saturated',1080,False)]:
        result=card.get('results',{}).get(name,{})
        if (result.get('frames',0)<900 or result.get('resolution')!=[height*16//9,height]
                or result.get('source_fps')!=30 or result.get('pace') is not pace
                or result.get('pipeline_sha256')!=fingerprint):
            raise ValueError(f'Sustained {name} did not exercise900+ frames at expected resolution, rate, and pacing')
        if not math.isfinite(result.get('seconds',float('nan'))) or result['seconds']<=0:
            raise ValueError(f'Sustained {name} has invalid elapsed time')
        if pace and result['seconds']<29.9:
            raise ValueError('Paced measurement finished before30fps arrivals could occur')
        if not math.isclose(result.get('fps',0),result['frames']/result['seconds'],rel_tol=1e-6):
            raise ValueError(f'Sustained {name} has inconsistent frame accounting')
        for quantile in ['p50','p95']:
            latency=result.get('realtime_added_latency_seconds',{}).get(quantile,float('nan'))
            if not math.isfinite(latency) or latency<0:
                raise ValueError(f'Sustained {name} has invalid latency')
