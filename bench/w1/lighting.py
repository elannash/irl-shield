"""Dev-only tune lighting derivatives; input truth is re-observed at grading."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import cv2
import numpy as np

RECIPES={r["id"]:r for r in json.loads(Path(__file__).with_name("lighting-stress.json").read_text())["variants"]}


def transform(pixels,variant):
    if variant not in RECIPES: raise ValueError("Unknown W1 lighting variant")
    recipe=RECIPES[variant]
    if recipe["operation"]=="gamma":
        table=np.rint(255*(np.arange(256)/255.)**recipe["gamma"]).astype(np.uint8)
        return cv2.LUT(pixels,table)
    if recipe["operation"]=="gain-bias":
        return np.clip(pixels.astype(float)*recipe["gain"]+recipe["bias"],0,255).astype(np.uint8)
    return cv2.blur(pixels,(recipe["kernel"],1),borderType=cv2.BORDER_CONSTANT)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("release","queue-dir","source-freeze","gate-receipt","parity"):
        parser.add_argument("--"+name,required=True,type=Path)
    parser.add_argument("--inputs",required=True)
    parser.add_argument("--directory",required=True)
    parser.add_argument("--variant",required=True,choices=tuple(RECIPES))
    args=parser.parse_args(argv)
    from bench.q2_execution.queued import require_release,local_path,write_json
    from bench.w1.identity import verify_metric_barriers,sha256,V2_SHA,ROOT
    from bench.quality_bundle import entries
    from bench.offline_quality import _media
    release=require_release(args.release,V2_SHA,args.queue_dir)
    verify_metric_barriers(args.source_freeze,args.gate_receipt,args.parity)
    cv2.setNumThreads(1)
    inputs=local_path(args.inputs);data,snapshot=entries(ROOT,inputs)
    directory=local_path(args.directory);directory.mkdir(parents=True,exist_ok=False)
    rows=[]
    for row in data["clips"]:
        source,truth=Path(row["source"]),Path(row["truth"])
        if sha256(source)!=row["source_sha256"] or sha256(truth)!=row["truth_sha256"]:
            raise ValueError("Lighting base frozen source/truth changed")
        media=_media(source);width,height=media["resolution"]
        name=row["clip"]+("-synthetic" if row["synthetic_variant"] else "-natural")
        output=directory/(name+".mp4");annotations=directory/(name+".truth.json")
        capture=cv2.VideoCapture(str(source));process=None
        command=["ffmpeg","-hide_banner","-loglevel","error","-nostdin","-f","rawvideo","-pix_fmt","bgr24",
            "-s",f"{width}x{height}","-r",str(media["fps"]),"-i","pipe:0","-an","-c:v","libx264",
            "-preset","ultrafast","-threads","2","-bf","0","-pix_fmt","yuv420p",str(output)]
        try:
            with (directory/(name+".encoder.log")).open("w") as log:
                process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log)
                for _ in range(media["frames"]):
                    ok,pixels=capture.read()
                    if not ok: raise ValueError("Lighting base source truncated")
                    process.stdin.write(transform(pixels,args.variant).tobytes())
                if capture.read()[0]: raise ValueError("Lighting base source has extra frames")
                process.stdin.close()
                if process.wait(timeout=60): raise RuntimeError("Lighting source encoder failed")
        finally:
            capture.release()
            if process is not None and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=3)
        if _media(output)!=media: raise ValueError("Lighting transform changed source frame clock")
        shutil.copyfile(truth,annotations)
        rows.append({**row,"source":str(output),"truth":str(annotations),"source_sha256":sha256(output),"truth_sha256":sha256(annotations)})
        if inputs.read_bytes()!=snapshot: raise ValueError("Lighting input manifest changed")
    verify_metric_barriers(args.source_freeze,args.gate_receipt,args.parity)
    manifest={"fixture_manifest_sha256":data["fixture_manifest_sha256"],"clips":rows}
    write_json(directory/"inputs.json",manifest)
    write_json(directory/"derivation.json",{"scope":"Dev-only transformed tune inputs, never V2; independent input truth must be re-observed at these exact encoded pixels.",
        "release":release,"base_inputs_sha256":sha256(inputs),"variant":RECIPES[args.variant],"inputs_sha256":sha256(directory/"inputs.json"),"source_freeze_sha256":sha256(args.source_freeze)})
    return 0


if __name__=="__main__": raise SystemExit(main())
