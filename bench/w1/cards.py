"""Strict W1 evidence composition. Missing runtime evidence never becomes a win."""
import math
from bench.independence import policy_metadata
from bench.metrics import validate_area_ceiling


def validate_policy(config):
    metadata=policy_metadata(config["candidate"],config["options"])
    options=config["options"]
    ceiling=validate_area_ceiling(options.get("area_ceiling"),options.get("area_ceiling_basis"),required=True)
    if ceiling>.15:
        raise ValueError("W1 area ceiling cannot exceed .15")
    return metadata


def compare(baseline,arm):
    if any(baseline[key]!=arm[key] for key in ("source_freeze_sha256","input_identity")):
        raise ValueError("W1 comparisons require identical common source/input identities")
    reasons=[]
    if not baseline["complete"] or not baseline["guards_pass"]: reasons.append("baseline-invalid")
    if not arm["complete"] or not arm["guards_pass"]: reasons.append("arm-invalid")
    total=arm["actual_total_added_latency_seconds"]
    if not isinstance(total,(int,float)) or not math.isfinite(total) or total>3.:
        reasons.append("total-latency-over3s")
    improvement=arm["natural_fraction"]-baseline["natural_fraction"] if arm["natural_fraction"] is not None and baseline["natural_fraction"] is not None else None
    if improvement is None or improvement<=0: reasons.append("no-natural-improvement")
    added=total-baseline["actual_total_added_latency_seconds"] if isinstance(total,(int,float)) else None
    return {"stack_eligible":not reasons,"winner":"arm" if not reasons else None,
            "natural_gain_pp":improvement*100 if improvement is not None else None,
            "natural_gain_pp_per_added_second":improvement*100/added if improvement is not None and added is not None and added>0 else None,
            "flicker_leak_delta":arm["flicker_leaks"]-baseline["flicker_leaks"],
            "gpu_ms_per_source_frame_delta":arm["gpu_ms_per_source_frame"]-baseline["gpu_ms_per_source_frame"] if arm["gpu_ms_per_source_frame"] is not None and baseline["gpu_ms_per_source_frame"] is not None else None,
            "rejection_reasons":reasons,
            "scope":"Descriptive deltas remain visible for rejected arms. No invalid baseline or arm can qualify stacking. Adoption above1s remains reserved Opus."}


def complete_card(quality,normal_performance,cost,*,source_freeze_sha256,input_identity,live_feasibility):
    """Compose retained evidence; caller verifies sealed files and source identities."""
    from bench.w1.stack_selection import natural_summary
    selection=natural_summary(quality["clips"])
    checks=quality["quality_checks"]
    if len(quality.get("clips",[]))!=14:
        raise ValueError("W1 card requires all14 tune clip variants")
    if quality.get("split")!="tune":
        raise ValueError("W1 development card must use tune, never reserved v2")
    if not all("flicker" in clip for clip in quality["clips"]):
        raise ValueError("Every clip needs observed flicker evidence")
    trials=cost.get("trials",[])
    if len(trials)<5:
        raise ValueError("W1 card requires at least five GPU cost repetitions")
    source_frames=sum(t["source_frames"] for t in trials)
    valid_cost=all(t["valid"] for t in trials)
    parity_verified=cost.get("provider_output_parity_verified") is True
    lanes=[v for t in trials for v in t["lanes"].values()]
    total=sum(l["cost"]["device_interval_sum_ms"] for l in lanes) if valid_cost else None
    fps=normal_performance["fps"]
    p95=normal_performance["realtime_added_latency_seconds"]["p95"]
    # Transport latency must come from the native relay receipt, not bench emission delay.
    actual_total=live_feasibility.get("total_added_latency_p95_seconds")
    runtime_ok=(live_feasibility.get("pass") is True and live_feasibility.get("source_fps")==30
                and live_feasibility.get("encoder")=="h264_nvenc" and fps>=29.9
                and normal_performance["protected_fraction"]<.02
                and isinstance(actual_total,(int,float)) and math.isfinite(actual_total) and actual_total<=3.)
    protected_max=max(row["protected_fraction"] for row in quality["per_clip_protected"])
    if not all("render_budget" in clip and clip["render_budget"]["source_frames"]==clip["frames"] for clip in quality["clips"]):
        raise ValueError("Every clip needs an explicit source-frame budget diagnostic tally")
    budget_failures=sum(clip["render_budget"]["impossible_frames"] for clip in quality["clips"])
    return {"complete":True,"guards_pass":all(checks.values()) and selection["natural"]["hidden_fraction"] is not None and selection["natural"]["hidden_fraction"]>=.9 and runtime_ok and valid_cost and parity_verified and budget_failures==0,
            "natural_fraction":selection["natural"]["hidden_fraction"],"natural_selection":selection,"quality_checks":checks,
            "area":quality["masked_area_fraction"],"per_clip_protected":quality["per_clip_protected"],
            "maximum_clip_protected_fraction":protected_max,"union_budget_failures":budget_failures,
            "flicker_per_clip":[{"clip":c["clip"],"synthetic_variant":c["synthetic_variant"],"flicker":c["flicker"]} for c in quality["clips"]],
            "flicker_leaks":selection["natural_flicker_frames"],
            "gpu_ms_per_source_frame":total/source_frames if valid_cost and source_frames else None,
            "gpu_cost_repetitions":len(trials),"provider_output_parity_verified":parity_verified,"steady_fps":fps,"bench_p95_latency_seconds":p95,
            "actual_total_added_latency_seconds":actual_total,"live_feasibility":live_feasibility,
            "source_freeze_sha256":source_freeze_sha256,"input_identity":input_identity,
            "adoption_above1s":"reserved Opus; total added latency cap3s"}
