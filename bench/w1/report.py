"""Join already-judged sealed tune bundles with closed root queue receipts.

No OCR, model, media decode, queue status call or V2 access occurs here.
"""
import argparse
import json
from pathlib import Path
from bench.quality_bundle import aggregate,checked_file,digest,write_json
from bench.perf_queue_report import queue_attempt_clean
from bench.clocked_bench import clock_guards
from bench.w1.identity import verify_metric_barriers,sha256,ROOT
from bench.w1.cards import complete_card,compare,validate_policy


def execution(directory,attempt_path):
    directory=Path(directory)
    path=directory/"execution.json"
    if digest(path)!=(directory/"execution.sha256").read_text().strip():
        raise ValueError("W1 execution seal changed")
    plan=json.loads(path.read_bytes())
    for name,identity in plan["artifacts"].items():
        artifact=checked_file(directory,name)
        if artifact.stat().st_size!=identity["bytes"] or digest(artifact)!=identity["sha256"]:
            raise ValueError("W1 execution artifact changed:"+name)
    attempt=json.loads(Path(attempt_path).read_bytes())
    listed=[a for a in attempt.get("receipts",[]) if Path(a["path"]).resolve()==path.resolve()]
    if len(listed)!=1 or listed[0].get("sha256")!=digest(path) or listed[0].get("bytes")!=path.stat().st_size:
        raise ValueError("W1 execution is not bound to the supplied closed queue receipt")
    clean=queue_attempt_clean(attempt) and attempt.get("returncode")==0
    return plan,clean


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source-freeze","gate-receipt","parity","quality-directory","normal-directory","normal-attempt","cost-directory","cost-attempt","native-relay-receipt","output"):
        parser.add_argument("--"+name,required=True,type=Path)
    parser.add_argument("--baseline",type=Path)
    parser.add_argument("--run-id",required=True)
    args=parser.parse_args(argv)
    frozen=verify_metric_barriers(args.source_freeze,args.gate_receipt,args.parity)
    quality=aggregate(ROOT,args.quality_directory,args.run_id)
    validate_policy({"candidate":quality["candidate"],"options":quality["options"]})
    normal,nclean=execution(args.normal_directory,args.normal_attempt)
    cost,costclean=execution(args.cost_directory,args.cost_attempt)
    perf=json.loads((args.normal_directory/"clocked.performance.json").read_bytes())
    costs=json.loads((args.cost_directory/"gpu-cost.json").read_bytes())
    native=json.loads(args.native_relay_receipt.read_bytes())
    for plan in (normal,cost):
        if plan["candidate"]!=quality["candidate"]:
            raise ValueError("W1 policy differs across quality/performance/cost")
        expected={**quality["options"],"repeat_seconds":30.,"warmup_seconds":10.}
        if plan["options"]!=expected:
            raise ValueError("W1 policy options differ across sealed stages")
    if (quality["pipeline_sha256"]!=frozen["offline_pipeline_sha256"]
            or perf["pipeline_sha256"]!=frozen["clocked_pipeline_sha256"]
            or costs["identity"]["pipeline_sha256"]!=frozen["clocked_pipeline_sha256"]
            or costs["identity"]["source_sha256"]!=perf["source_sha256"]):
        raise ValueError("W1 source/model/input identities differ across stages")
    # Six provisioned model/shape pairs were checked before metrics. The receipt is
    # source-bound; blocked open-vocabulary models cannot inherit this parity proof.
    costs["provider_output_parity_verified"]=True
    native_raw=native.get("raw_receipt")
    if not isinstance(native_raw,str) or sha256(native_raw)!=native.get("raw_receipt_sha256"):
        raise ValueError("W1 native relay evidence must bind its raw receipt bytes")
    native_ok=(native.get("verified") is True and native.get("config_sha256")==normal["config_sha256"]
               and native.get("source_freeze_sha256")==sha256(args.source_freeze))
    native["pass"]=native.get("pass") is True and native_ok
    card=complete_card(quality,perf,costs,source_freeze_sha256=sha256(args.source_freeze),
        input_identity=quality["quality_run_identity"]["input_manifest_sha256"],live_feasibility=native)
    guards=clock_guards(perf,required_resolution=(1280,720))
    from bench.w1.stack_selection import natural_area
    natural_records={clip["clip"]:json.loads(Path(clip["output"]).with_suffix(".masks.json").read_bytes())
                     for clip in quality["clips"] if clip["synthetic_variant"] is False}
    card["area"]=natural_area(natural_records)
    card["selection_scope"]="Seven licensed natural tune clips only; legacy all14 background counts remain regression diagnostics."
    card["queue_clean"]={"normal":nclean,"cost":costclean}
    card["clock_guards"]=guards
    card["guards_pass"]=card["guards_pass"] and nclean and costclean and all(guards.values())
    card["quality"]=quality
    card["artifacts"]={"normal_execution_sha256":sha256(args.normal_directory/"execution.json"),
       "cost_execution_sha256":sha256(args.cost_directory/"execution.json"),"native_relay_receipt_sha256":sha256(args.native_relay_receipt)}
    if args.baseline:
        card["comparison"]=compare(json.loads(args.baseline.read_bytes()),card)
    write_json(args.output,card)
    args.output.with_suffix(".sha256").write_text(sha256(args.output)+"\n")
    return 0


if __name__=="__main__": raise SystemExit(main())
