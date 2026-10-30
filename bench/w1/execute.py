"""Root-queued complete tune render; never starts a queue or judges locally."""
import argparse
import json
from pathlib import Path
from bench.q2_execution.queued import require_release,local_path,write_json
from bench.w1.identity import verify_metric_barriers,sha256,V2_SHA,ROOT
from bench.w1.cards import validate_policy


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",required=True,type=Path)
    parser.add_argument("--queue-dir",required=True,type=Path)
    parser.add_argument("--source-freeze",required=True,type=Path)
    parser.add_argument("--gate-receipt",required=True,type=Path)
    parser.add_argument("--parity",required=True,type=Path)
    parser.add_argument("--inputs",required=True)
    parser.add_argument("--config",required=True)
    parser.add_argument("--directory",required=True)
    args=parser.parse_args(argv)
    release=require_release(args.release,V2_SHA,args.queue_dir)
    verify_metric_barriers(args.source_freeze,args.gate_receipt,args.parity)
    config_path=local_path(args.config)
    config_bytes=config_path.read_bytes();config=json.loads(config_bytes)
    validate_policy(config)
    from bench.quality_bundle import render,entries
    inputs=local_path(args.inputs);data,input_bytes=entries(ROOT,inputs)
    directory=local_path(args.directory);directory.mkdir(parents=True,exist_ok=False)
    plans=[]
    complete=False
    try:
        for row in data["clips"]:
            clip=row["clip"];synthetic=row["synthetic_variant"]
            destination=directory/(clip+("-synthetic" if synthetic else "-natural"))
            plan=render(ROOT,inputs,config_path,destination,clip,synthetic)
            plans.append({"clip":clip,"synthetic_variant":synthetic,"bundle":str(destination.relative_to(directory)),
                          "bundle_sha256":sha256(destination/"bundle.json"),"frames":plan["frames"]})
            verify_metric_barriers(args.source_freeze,args.gate_receipt,args.parity)
            if inputs.read_bytes()!=input_bytes or config_path.read_bytes()!=config_bytes:
                raise ValueError("W1 frozen policy/input changed")
        complete=True
    finally:
        write_json(directory/"render-run.json",{"status":"awaiting-judging" if complete else "incomplete",
            "release":release,"source_freeze_sha256":sha256(args.source_freeze),"config_sha256":sha256(config_path),
            "input_manifest_sha256":sha256(inputs),"bundles":plans,"arm_scores":None})
        (directory/"render-run.sha256").write_text(sha256(directory/"render-run.json")+"\n")
    return 0


if __name__=="__main__": raise SystemExit(main())
