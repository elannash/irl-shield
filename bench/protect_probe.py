"""Known synthetic large text challenges full-frame protection; no demo asset claim.

Existing DejaVu font license: fixtures/fonts/LICENSE-DejaVu.txt; OCR/model notices and hashes
remain in models/manifest.json and models/licenses/dependencies.json.
"""
import json
import argparse
import hashlib
import inspect
from pathlib import Path

import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont

from bench.judges import Judges
from bench.metrics import matches
from shield.render import Renderer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('out/protect-probe'))
    directory=parser.parse_args().out
    directory.mkdir(parents=True,exist_ok=False)
    judge=Judges('protection-probe',directory/'judge-cache')
    rows=[]
    try:
        for text,size in [('8',650),('59',600),('1842',400),('CEDAR AVE',190)]:
            image=Image.new('RGB',(1280,720),'white')
            draw=ImageDraw.Draw(image)
            font=ImageFont.truetype('fixtures/fonts/DejaVuSans-Bold.ttf',size)
            x0,y0,x1,y1=draw.textbbox((0,0),text,font=font)
            draw.text(((1280-(x1-x0))/2-x0,(720-(y1-y0))/2-y0),text,font=font,fill='black')
            source=np.array(image)[:,:,::-1].copy()
            output=Renderer().render(source,[],'PROTECT',0).pixels
            before,after=judge.read(source),judge.read(output)
            readable=lambda readings:any(matches(text,row['text']) for row in readings)
            row={'target':text,'input_readable':readable(before),'output_readable':readable(after),
                 'input':before,'output':after}
            rows.append(row)
            cv2.imwrite(str(directory/(text.replace(' ','-')+'.png')),output)
            print(json.dumps(row),flush=True)
        source_path=Path(inspect.getfile(Renderer))
        (directory/'receipt.json').write_text(json.dumps({'benchmark_only':True,'demo_ready':False,
                'renderer_source':str(source_path),'renderer_source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
                'judges':judge.names,'vision':judge.vision.metadata,'paddle':judge.paddle.metadata,
                'cases':rows},indent=2)+'\n')
    finally:
        judge.close()


if __name__=='__main__':
    main()
