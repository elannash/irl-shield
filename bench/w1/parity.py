"""Queue-only CUDA provider/output parity on synthetic pixels, never an arm score."""
import argparse
import json
from pathlib import Path
from bench.q2_execution.queued import require_release,local_path,write_json
from bench.q2_execution.adapters import sha256


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",required=True,type=Path)
    parser.add_argument("--v2-manifest-sha256",required=True)
    parser.add_argument("--queue-dir",required=True,type=Path)
    parser.add_argument("--cudart",required=True,type=Path)
    parser.add_argument("--source-freeze",required=True,type=Path)
    parser.add_argument("--gate-receipt",required=True,type=Path)
    parser.add_argument("--directory",required=True)
    args=parser.parse_args(argv)
    release=require_release(args.release,args.v2_manifest_sha256,args.queue_dir)
    from bench.w1.identity import verify_freeze,verify_gate
    verify_freeze(args.source_freeze)
    verify_gate(args.gate_receipt,args.source_freeze)
    directory=local_path(args.directory)
    directory.mkdir(parents=True,exist_ok=False)
    import cv2
    import numpy as np
    from bench.pipeline import detector_for
    from bench.q2_execution.measured import MeasuredBackends
    from bench.clocked_pipeline import fingerprint
    cv2.setNumThreads(1)
    code=fingerprint()
    rows=[]
    specifications=(("fast","ppocr-v6-tiny",640,640,[720,1280]),
        ("accurate","ppocr-v6-small",1280,960,[720,1280]),
        ("small1280","ppocr-v6-small",1280,1280,[720,1280]),
        ("medium960","ppocr-v6-medium",1280,960,[720,1280]),
        ("server960","ppocr-v5-server",1280,960,[720,1280]),
        ("tile960","ppocr-v6-small",768,960,[432,768]))
    for lane,model,width,side,input_size in specifications:
        options={"input_size":input_size,"detect_width":width,"provider":"cuda","threads":2,
                 "static_model":True,"limit_side_len":side,"thresh":.3,"box_thresh":.5,"unclip_ratio":1.6}
        normal=None
        measured=MeasuredBackends(args.cudart)
        row={"lane":lane,"model":model,"pass":False,"samples":[]}
        rows.append(row)
        try:
            normal=detector_for(model,options)
            explicit=measured(lane,model,options)
            for gain in (1.,.55,1.3):
                image=np.full((720,1280,3),30,np.uint8)
                cv2.rectangle(image,(100,220),(1180,470),(230,230,230),-1)
                cv2.putText(image,"ELM ROAD 42",(145,380),cv2.FONT_HERSHEY_SIMPLEX,2.8,(10,10,10),7)
                image=np.clip(image.astype(float)*gain,0,255).astype(np.uint8)
                pixels=cv2.resize(image,(width,round(720*width/1280))) if width!=1280 else image
                baseline=normal.detect_quads(pixels)
                observed=explicit.detect_quads(pixels)
                equal=json.dumps(baseline,sort_keys=True)==json.dumps(observed,sort_keys=True)
                row["samples"].append({"input_sha256":sha256_bytes(pixels.tobytes()),"gain":gain,
                    "normal_quads":baseline,"explicit_stream_quads":observed,"exact_equal":equal})
            row["normal_metadata"]=normal.metadata
            row["explicit_stream_metadata"]=explicit.metadata
            row["pass"]=(all(r["exact_equal"] for r in row["samples"])
                and any(r["normal_quads"] for r in row["samples"])
                and normal.metadata["execution_provider"]=="CUDAExecutionProvider"
                and explicit.metadata["execution_provider"]=="CUDAExecutionProvider")
        except BaseException as error:
            row["error"]=f"{type(error).__name__}: {error}"
            raise
        finally:
            try:
                if normal is not None: normal.close()
                measured.close()
            except BaseException as error:
                row["pass"]=False
                row["cleanup_error"]=f"{type(error).__name__}: {error}"
                raise
            finally:
                write_json(directory/"parity.json",{"scope":"Functional synthetic provider/output parity only. Event costs deliberately omitted; not an arm score, live perf result or NVENC qualification.",
                    "pipeline_sha256":code,"source_freeze_sha256":sha256(args.source_freeze),"release":release,"rows":rows,"pass":len(rows)==len(specifications) and all(r["pass"] for r in rows)})
                (directory/"parity.sha256").write_text(sha256(directory/"parity.json")+"\n")
    if fingerprint()!=code:
        raise ValueError("Parity source changed")
    return 0 if all(r["pass"] for r in rows) else 2


def sha256_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


if __name__=="__main__": raise SystemExit(main())
