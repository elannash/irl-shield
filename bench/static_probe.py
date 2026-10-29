"""Bounded inference-only CPU/CoreML comparison on one licensed tune video."""

import argparse
from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import time
import traceback

import cv2
import numpy as np
import onnxruntime as ort
from rapidocr.ch_ppocr_det.utils import DBPostProcess, DetPreProcess

from bench.static_model import prepare_static
from models.prepare import sha256_file, verified_path


@contextmanager
def native_stderr(path):
    saved = os.dup(2)
    try:
        with Path(path).open("wb") as stream:
            os.dup2(stream.fileno(), 2)
            yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)


def distribution(values):
    values = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values), "mean_ms": float(values.mean()),
        "median_ms": float(np.median(values)), "p10_ms": float(np.percentile(values, 10)),
        "p90_ms": float(np.percentile(values, 90)), "p95_ms": float(np.percentile(values, 95)),
        "min_ms": float(values.min()), "max_ms": float(values.max()),
        "std_ms": float(values.std()), "coefficient_of_variation": float(values.std() / values.mean()),
    }


def video_frames(path):
    capture = cv2.VideoCapture(str(path))
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 20:
            raise RuntimeError(f"Video has insufficient frames: {total}")
        indices = np.linspace(int(total * 0.1), int(total * 0.9), 20, dtype=int).tolist()
        frames = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None or float(frame.std()) < 5:
                raise RuntimeError(f"Failed real-video decode at frame {index}")
            frames.append(frame)
        return frames, {"video_path": str(path), "video_sha256": sha256_file(path), "video_total_frames": total,
                        "sample_indices": indices, "frame_shapes": [list(f.shape) for f in frames],
                        "frame_sha256": [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]}
    finally:
        capture.release()


def run_variant(name, source, artifact, tensors, frames, output_dir, reference):
    warning_path = output_dir / f"{name}.warnings.log"
    started = time.perf_counter()
    record = {"name": name, "source_sha256": artifact["sha256"], "warnings_path": str(warning_path),
              "warmup_frame_count": 2, "measured_frame_count": 18, "total_inference_count": 20}
    session = None
    outputs = []
    try:
        with native_stderr(warning_path):
            model_path = source
            if name.endswith("static"):
                before = time.perf_counter()
                model_path, record["static_artifact"] = prepare_static(source, artifact["sha256"], *tensors[0].shape[2:], output_dir / "static-models")
                record["derivation_ms"] = (time.perf_counter() - before) * 1000
            config = ort.SessionOptions()
            config.intra_op_num_threads = 2
            config.inter_op_num_threads = 1
            config.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            config.enable_cpu_mem_arena = False
            config.log_severity_level = 2
            providers = ["CPUExecutionProvider"]
            if "coreml" in name:
                if "CoreMLExecutionProvider" not in ort.get_available_providers():
                    raise RuntimeError("CoreML EP unavailable")
                coreml_options = {"ModelFormat": "MLProgram", "MLComputeUnits": "ALL",
                                  "RequireStaticInputShapes": "1" if name.endswith("static") else "0",
                                  "ModelCacheDirectory": str(output_dir / "coreml-cache" / name)}
                providers = [("CoreMLExecutionProvider", coreml_options), "CPUExecutionProvider"]
                record["coreml_options"] = coreml_options
            before = time.perf_counter()
            session = ort.InferenceSession(str(model_path), sess_options=config, providers=providers)
            session.disable_fallback()
            record["session_creation_ms"] = (time.perf_counter() - before) * 1000
            record["active_providers"] = session.get_providers()
            if "coreml" in name and "CoreMLExecutionProvider" not in record["active_providers"]:
                raise RuntimeError("Requested CoreML provider was not activated")
            actual_shape = session.get_inputs()[0].shape
            record["declared_input_shape"] = actual_shape
            if name.endswith("static") and actual_shape != list(tensors[0].shape):
                raise RuntimeError(f"Static declaration differs from actual tensor: {actual_shape}")
            postprocess = DBPostProcess(thresh=.3, box_thresh=.5, max_candidates=1000, unclip_ratio=1.6, use_dilation=True, score_mode="fast")
            latency = []
            post_latency = []
            validations = []
            boxes_per_frame = []
            errors = []
            for index, tensor in enumerate(tensors):
                before = time.perf_counter()
                probability = session.run(None, {session.get_inputs()[0].name: tensor})[0]
                latency.append((time.perf_counter() - before) * 1000)
                if probability.shape != (1, 1, *tensor.shape[2:]) or not np.isfinite(probability).all():
                    raise RuntimeError(f"Invalid probability map at frame {index}: {probability.shape}")
                validations.append({"min": float(probability.min()), "max": float(probability.max()), "std": float(probability.std()),
                                    "sha256": hashlib.sha256(probability.tobytes()).hexdigest()})
                before = time.perf_counter()
                boxes, scores = postprocess(probability, frames[index].shape[:2])
                post_latency.append((time.perf_counter() - before) * 1000)
                if len(boxes):
                    height, width = frames[index].shape[:2]
                    if not np.isfinite(boxes).all() or boxes[..., 0].min() < 0 or boxes[..., 1].min() < 0 or boxes[..., 0].max() > width or boxes[..., 1].max() > height:
                        raise RuntimeError("Detection boxes escaped the real-video frame")
                boxes_per_frame.append(len(boxes))
                if reference is None:
                    outputs.append(probability)
                else:
                    errors.append(float(np.max(np.abs(reference[index] - probability))))
            if not any(v["std"] > 1e-5 for v in validations) or sum(boxes_per_frame) == 0:
                raise RuntimeError("No nonconstant maps or text boxes on the sampled real video")
            record.update({"status": "ok", "warmup_ms": latency[:2], "inference": distribution(latency[2:]),
                           "inference_ms": latency[2:], "postprocess": distribution(post_latency[2:]),
                           "boxes_per_frame": boxes_per_frame, "map_validation": validations,
                           "max_abs_error_vs_cpu": max(errors) if errors else None})
    except Exception as exc:
        record.update({"status": "error", "error": str(exc), "traceback": traceback.format_exc()})
    finally:
        session = None
        gc.collect()
    warnings = warning_path.read_text(errors="replace") if warning_path.exists() else ""
    record["capability_warnings"] = [line for line in warnings.splitlines() if "CoreMLExecutionProvider" in line or "GetCapability" in line]
    for key, pattern in (("coreml_partitions", r"number of partitions supported by CoreML:\s*(\d+)"),
                         ("optimized_graph_nodes", r"number of nodes in the graph:\s*(\d+)"),
                         ("coreml_supported_nodes", r"number of nodes supported by CoreML:\s*(\d+)")):
        matches = re.findall(pattern, warnings, flags=re.IGNORECASE)
        record[key] = [int(v) for v in matches]
    record["variant_total_seconds"] = time.perf_counter() - started
    (output_dir / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: v for k, v in record.items() if k not in {"map_validation", "traceback", "capability_warnings"}}), flush=True)
    return record, outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ort.disable_telemetry_events()
    cv2.setNumThreads(2)
    source, artifact = verified_path("ppocr-v5-mobile", args.project_root / "models/cache")
    frames, sampling = video_frames(args.project_root / "fixtures/cache/sf-market.mp4")
    summary = {"model": artifact, "sampling": sampling, "machine": platform.platform(), "processor": platform.processor(),
               "onnxruntime_version": ort.__version__, "available_providers": ort.get_available_providers(),
               "thread_limit": 2, "scope": "inference-only probe; concurrent parent bakeoff; no quality or end-to-end FPS claim", "variants": []}
    print(json.dumps({"event": "start", "machine": summary["machine"], "providers": summary["available_providers"], "sample_indices": sampling["sample_indices"]}), flush=True)
    for side in (960, 640, 480):
        preprocess = DetPreProcess(side, "max", artifact["preprocess"]["mean"], artifact["preprocess"]["std"])
        before = time.perf_counter()
        tensors = [preprocess(frame) for frame in frames]
        preprocess_ms = (time.perf_counter() - before) * 1000
        if len({tensor.shape for tensor in tensors}) != 1:
            raise RuntimeError("Sampled video changed detector tensor dimensions")
        order = ("cpu", "coreml-dynamic", "coreml-static") if side != 640 else ("cpu", "coreml-static", "coreml-dynamic")
        reference = None
        for variant in order:
            record, outputs = run_variant(f"{side}-{variant}", source, artifact, tensors, frames, output_dir, reference)
            record["preprocessed_shape"] = list(tensors[0].shape)
            record["preprocess_total_ms_for_20_frames"] = preprocess_ms
            summary["variants"].append(record)
            if variant == "cpu":
                reference = outputs
        del tensors, reference
        gc.collect()
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"event": "complete", "summary": str(output_dir / "summary.json"), "successful_variants": sum(v["status"] == "ok" for v in summary["variants"])}), flush=True)
    return 0 if all(v["status"] == "ok" for v in summary["variants"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
