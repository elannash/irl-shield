"""30-second sustained tests, plus paced arrival-to-encode latency at 720p30."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from bench.pipeline import run
from bench.provenance import pipeline_fingerprint

ROOT=Path(__file__).resolve().parents[1]


def measure(candidate,options,source,directory,seconds=30):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    fingerprint=pipeline_fingerprint()
    results={}
    for height in [720,1080]:
        path=directory/f'source-{height}.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-stream_loop','-1',
                        '-i',str(source),'-t',str(seconds),'-an','-vf',f'scale={height*16//9}:{height},fps=30',
                        '-c:v','h264_videotoolbox','-b:v','15M','-bf','0',str(path)],check=True)
        for pace in ([False,True] if height==720 else [False]):
            label=f'{height}-'+('paced' if pace else 'saturated')
            print('sustained',label,flush=True)
            results[label]=run(path,directory/f'{label}.mp4',candidate,{**options,'pace':pace})
    if fingerprint!=pipeline_fingerprint():
        raise RuntimeError('Pipeline source changed during sustained measurement')
    card={'pipeline_sha256':fingerprint,'candidate':candidate,'options':options,'source':str(source),'source_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'seconds':seconds,
          'description':'1080p is upscaled 720p fixture: workload measurement, not native-1080p detection quality.',
          'results':results}
    (directory/'sustained.json').write_text(json.dumps(card,indent=2))
    print(json.dumps(card,indent=2))
    return card


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--candidate',required=True)
    p.add_argument('--options',default='{}',help='Exact JSON options from winning scorecard')
    p.add_argument('--source',default='fixtures/cache/sf-market.mp4')
    p.add_argument('--out',default='out/sustained')
    p.add_argument('--seconds',type=int,default=30)
    a=p.parse_args()
    if a.seconds<30:
        raise ValueError('Sustained test must exercise at least30 seconds of content')
    measure(a.candidate,json.loads(a.options),ROOT/a.source,ROOT/a.out,a.seconds)


if __name__=='__main__':
    main()
