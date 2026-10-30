"""Staged selection on real natural footage; no model, media, or queue execution."""
import math


def natural_summary(clips):
    if any(type(row.get("synthetic_variant")) is not bool for row in clips):
        raise ValueError("Selection variant flag must be boolean")
    natural=[r for r in clips if r["synthetic_variant"] is False]
    synthetic=[r for r in clips if r["synthetic_variant"] is True]
    if len(natural)!=7 or len({r["clip"] for r in natural})!=7:
        raise ValueError("Selection requires seven unique natural tune clips")
    hidden=total=0
    for row in natural:
        h,n=row["natural"]["hidden"],row["natural"]["total"]
        if type(h) is not int or type(n) is not int or not 0<=h<=n:
            raise ValueError("Selection interval counts must be valid integers")
        hidden+=h;total+=n
    return {"natural":{"hidden":hidden,"total":total,"hidden_fraction":hidden/total if total else None,
                       "hidden_percent":100*hidden/total if total else None},
            "natural_flicker_frames":sum(r["flicker"]["natural"]["flicker_leak_count"] for r in natural),
            "synthetic_regression":{"hidden":sum(r["synthetic"]["hidden"] for r in synthetic),
                                    "total":sum(r["synthetic"]["total"] for r in synthetic),"selection_numerator":False}}


def finite(value):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value)


def assess(row,baseline,*,cpu_budget_one_core_percent=None):
    """Return evidence state, never an adoption decision; missing cost is ineligible."""
    for key in ("source_freeze_sha256","selection_identity_sha256"):
        if row.get(key)!=baseline.get(key) or not row.get(key):
            raise ValueError("Selection requires matching frozen source and real-input identities")
    pending=[];rejected=[]
    required=("natural_hidden_percent","gpu_ms_per_source_frame","cpu_percent_one_core_100",
              "gpu_utilization_p95_percent","max_sustainable_fps","e2e_latency_p95_seconds_including_D")
    for key in required:
        if not finite(row.get(key)): pending.append("missing-"+key)
    score=row.get("natural_hidden_percent");base=baseline.get("natural_hidden_percent")
    if finite(score) and score<90.: rejected.append("natural-below90percent")
    if finite(score) and finite(base) and score<base: rejected.append("natural-OCR-regression")
    for key in ("sustained_30fps_pass","real_video_guard_pass","synthetic_regression_pass","per_clip_protection_pass","area_guard_pass","queue_clean"):
        if row.get(key) is False: rejected.append(key)
        elif row.get(key) is not True: pending.append("missing-"+key)
    if finite(row.get("gpu_utilization_p95_percent")) and row["gpu_utilization_p95_percent"]>70.:
        rejected.append("GPU-headroom-over70percent")
    if finite(row.get("max_sustainable_fps")) and row["max_sustainable_fps"]<30.:
        rejected.append("max-sustainable-FPS-below30")
    if finite(row.get("e2e_latency_p95_seconds_including_D")) and row["e2e_latency_p95_seconds_including_D"]>3.:
        rejected.append("total-added-latency-over3s")
    if cpu_budget_one_core_percent is None:
        pending.append("CPU-walk-budget-threshold-not-provided")
    elif not finite(cpu_budget_one_core_percent) or cpu_budget_one_core_percent<0:
        raise ValueError("CPU walk budget must be a finite nonnegative measured threshold")
    elif finite(row.get("cpu_percent_one_core_100")) and row["cpu_percent_one_core_100"]>cpu_budget_one_core_percent:
        rejected.append("CPU-walk-budget-exceeded")
    if not finite(base): pending.append("missing-fresh-baseline-natural-score")
    gain=score-base if finite(score) and finite(base) else None
    added_cost=row.get("gpu_ms_per_source_frame")-baseline.get("gpu_ms_per_source_frame") if finite(row.get("gpu_ms_per_source_frame")) and finite(baseline.get("gpu_ms_per_source_frame")) else None
    if not finite(baseline.get("gpu_ms_per_source_frame")): pending.append("missing-baseline-cost")
    gain_stop=gain is not None and gain<.5
    speed_stop=any(r in rejected for r in ("sustained_30fps_pass","GPU-headroom-over70percent","max-sustainable-FPS-below30","CPU-walk-budget-exceeded"))
    return {"status":"rejected" if rejected else "pending" if pending else "measured-guard-passing",
            "eligible_for_owner_shortlist":not rejected and not pending,
            "natural_gain_percentage_points":gain,"added_gpu_ms_per_source_frame":added_cost,
            "gain_percentage_points_per_added_gpu_ms":gain/added_cost if gain is not None and added_cost is not None and added_cost>0 else None,
            "cost_effectiveness_class":"dominates-parent-cost" if gain is not None and gain>0 and added_cost is not None and added_cost<=0 else "positive-increment-cost" if added_cost is not None and added_cost>0 else "unresolved-or-no-gain",
            "stop_adding_factor":gain_stop or speed_stop,"pending":pending,"rejected":rejected,
            "adoption":"Owner decision required; D>1 is never adopted by this function"}


def natural_area(records_by_clip):
    from bench.metrics import quantiles
    if len(records_by_clip)!=7:
        raise ValueError("Natural area requires exactly seven clip records")
    values=[]
    for rows in records_by_clip.values():
        if not rows: raise ValueError("Natural area cannot omit a source frame set")
        for row in rows:
            fraction=row["mask_fraction"]
            if not finite(fraction) or not 0<=fraction<=1:
                raise ValueError("Natural area requires actual finite raster fractions")
            values.append(fraction)
    return quantiles(values)
