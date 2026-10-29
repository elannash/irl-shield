"""Bounded Linux CPU/CUDA portability check, without OCR or privacy-score claims."""

import argparse
from collections import Counter
import gc
import hashlib
from importlib.metadata import distributions, version
import json
import os
from pathlib import Path
import platform
import subprocess
import time

import cv2
import numpy as np
import onnxruntime as ort
import psutil
from rapidocr.ch_ppocr_det.utils import DBPostProcess, DetPreProcess

from models.prepare import sha256_file, verified_path
from shield.masking import masked_frame


CANDIDATES = ("ppocr-v5-mobile", "ppocr-v6-tiny", "ppocr-v6-small", "ppocr-v6-medium")
CUDA_OPTIONS = {
    "device_id": "0",
    "gpu_mem_limit": str(2 * 1024**3),
    "arena_extend_strategy": "kSameAsRequested",
    "cudnn_conv_algo_search": "HEURISTIC",
    "cudnn_conv_use_max_workspace": "0",
    "do_copy_in_default_stream": "1",
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def distribution(values):
    return {
        "count": len(values), "mean_ms": float(np.mean(values)),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "min_ms": min(values), "max_ms": max(values),
    }


def resources():
    return {
        "available_ram_bytes": psutil.virtual_memory().available,
        "swap_used_bytes": psutil.swap_memory().used,
        "load_average": list(os.getloadavg()),
        "gpu": subprocess.check_output([
            "nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used",
            "--format=csv,noheader",
        ], text=True).strip(),
    }


def sample_frames(project_root):
    manifest_path = project_root / "fixtures/manifest.json"
    clip = next(c for c in json.loads(manifest_path.read_text())["clips"] if c["id"] == "sf-market")
    if clip["split"] != "tune" or clip["license"] != "CC BY 3.0":
        raise RuntimeError("Probe only accepts the licensed sf-market tune fixture")
    path = project_root / clip["path"]
    if sha256_file(path) != clip["sha256"]:
        raise RuntimeError("Tune fixture SHA-256 mismatch")
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    try:
        if not capture.isOpened():
            raise RuntimeError(f"Cannot decode {path}")
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 20:
            raise RuntimeError(f"Insufficient real-video frames: {total}")
        indices = np.linspace(int(total * .1), int(total * .9), 20, dtype=int).tolist()
        frames = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None or frame.std() < 5:
                raise RuntimeError(f"Real-video decode failed at {index}")
            frames.append(frame)
    finally:
        capture.release()
    return frames, {"clip": clip, "path": str(path), "total_frames": total,
                    "indices": indices, "frame_shape": list(frames[0].shape),
                    "frame_sha256": [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]}


def create_session(path, provider, output_dir, profiling=True):
    requested = "CUDAExecutionProvider" if provider == "cuda" else "CPUExecutionProvider"
    if requested not in ort.get_available_providers():
        raise RuntimeError(f"Requested {requested}, available {ort.get_available_providers()}")
    config = ort.SessionOptions()
    config.intra_op_num_threads = 2
    config.inter_op_num_threads = 1
    config.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    config.enable_cpu_mem_arena = False
    config.enable_profiling = profiling
    config.profile_file_prefix = str(output_dir / f"{provider}-profile")
    providers = [(requested, CUDA_OPTIONS), "CPUExecutionProvider"] if provider == "cuda" else [requested]
    session = ort.InferenceSession(str(path), sess_options=config, providers=providers)
    session.disable_fallback()
    if requested not in session.get_providers():
        raise RuntimeError(f"ONNX Runtime failed to activate {requested}; no CPU substitution accepted")
    return session


def boxes_for(probability, frame, postprocess):
    polygons, _ = postprocess(probability, frame.shape[:2])
    height, width = frame.shape[:2]
    boxes = []
    for polygon in polygons:
        if not np.isfinite(polygon).all():
            raise RuntimeError("Nonfinite detection polygon")
        box = [max(0, int(np.floor(polygon[:, 0].min()))),
               max(0, int(np.floor(polygon[:, 1].min()))),
               min(width, int(np.ceil(polygon[:, 0].max())) + 1),
               min(height, int(np.ceil(polygon[:, 1].max())) + 1)]
        if not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height:
            raise RuntimeError(f"Invalid bounded box: {box}")
        boxes.append(box)
    return boxes


def mask_check(frame, boxes):
    output, mask = masked_frame(frame, boxes, .3)
    outside = mask == 0
    inside = ~outside
    if not np.array_equal(output[outside], frame[outside]):
        raise RuntimeError("Opaque mask changed pixels outside its bounds")
    if inside.any() and np.any(output[inside] != 0):
        raise RuntimeError("Mask contains nonopaque pixels")
    if outside.mean() < .5 or output.std() < 5:
        raise RuntimeError("Masked output lost real video")
    return output, mask, {"mask_fraction": float(inside.mean()), "outside_exact": True,
                          "opaque_inside": True, "output_std": float(output.std())}


def profile_summary(session, provider):
    path = Path(session.end_profiling())
    events = json.loads(path.read_text())
    kernels = [e for e in events if e.get("cat") == "Node" and e.get("args", {}).get("provider")]
    counts = Counter(e["args"]["provider"] for e in kernels)
    durations = Counter()
    for event in kernels:
        durations[event["args"]["provider"]] += event.get("dur", 0)
    if provider == "cuda" and counts["CUDAExecutionProvider"] == 0:
        raise RuntimeError("Requested CUDA session executed no profiled CUDA kernels")
    return {"path": str(path), "kernel_event_count_by_provider": dict(counts),
            "kernel_duration_us_by_provider": dict(durations)}


def run_variant(path, provider, tensors, frames, postprocess, output_dir, reference=None):
    before = time.perf_counter()
    session = create_session(path, provider, output_dir)
    record = {"provider": provider, "session_creation_seconds": time.perf_counter() - before,
              "active_providers": session.get_providers(), "provider_options": session.get_provider_options(),
              "declared_input_shape": session.get_inputs()[0].shape,
              "warmup_count": 2, "measured_count": 18, "frames": []}
    outputs, inference_ms, post_ms, mask_ms, service_ms = [], [], [], [], []
    cpu_times = psutil.Process().cpu_times()
    wall_start = time.perf_counter()
    try:
        for index, (tensor, frame) in enumerate(zip(tensors, frames, strict=True)):
            start = time.perf_counter()
            probability = session.run(None, {session.get_inputs()[0].name: tensor})[0]
            inference_ms.append((time.perf_counter() - start) * 1000)
            if probability.shape != (1, 1, *tensor.shape[2:]) or not np.isfinite(probability).all():
                raise RuntimeError(f"Invalid probability output at sample {index}: {probability.shape}")
            if probability.std() <= 1e-5 or probability.min() < -1e-5 or probability.max() > 1.00001:
                raise RuntimeError(f"Constant or unbounded probability output at sample {index}")
            post_start = time.perf_counter()
            boxes = boxes_for(probability, frame, postprocess)
            post_ms.append((time.perf_counter() - post_start) * 1000)
            mask_start = time.perf_counter()
            output, mask, masking = mask_check(frame, boxes)
            mask_ms.append((time.perf_counter() - mask_start) * 1000)
            service_ms.append((time.perf_counter() - start) * 1000)
            validation = {"index": index, "boxes": boxes, "masking": masking,
                          "probability_min": float(probability.min()), "probability_max": float(probability.max()),
                          "probability_std": float(probability.std()),
                          "probability_sha256": hashlib.sha256(probability.tobytes()).hexdigest()}
            if reference is None:
                outputs.append(probability)
            else:
                diff = np.abs(reference[index] - probability)
                validation["max_abs_error_vs_cpu"] = float(diff.max())
                validation["mean_abs_error_vs_cpu"] = float(diff.mean())
                if diff.max() > .01:
                    raise RuntimeError(f"CUDA probability map differs from CPU by > .01 at sample {index}")
            record["frames"].append(validation)
            if index == 10:
                for suffix, image in (("source", frame), ("masked", output), ("mask", mask)):
                    if not cv2.imwrite(str(output_dir / f"{provider}-{suffix}.png"), image):
                        raise RuntimeError(f"Cannot write {suffix} sample")
        if not any(f["boxes"] for f in record["frames"]) or not any(f["masking"]["mask_fraction"] > 0 for f in record["frames"]):
            raise RuntimeError("No detections or meaningful masks on real video")
        record["profile"] = profile_summary(session, provider)
        for label, values in (("inference", inference_ms), ("postprocess", post_ms),
                              ("mask_validation", mask_ms), ("service", service_ms)):
            record[label] = distribution(values[2:])
            record[label + "_ms"] = values
        elapsed = time.perf_counter() - wall_start
        after_cpu = psutil.Process().cpu_times()
        record.update({"status": "ok", "wall_seconds_including_validation": elapsed,
                       "cpu_percent_one_core_100": 100 * (after_cpu.user + after_cpu.system - cpu_times.user - cpu_times.system) / elapsed,
                       "rss_mb_after_run": psutil.Process().memory_info().rss / 1024**2,
                       "total_boxes": sum(len(f["boxes"]) for f in record["frames"]),
                       "max_abs_error_vs_cpu": max((f.get("max_abs_error_vs_cpu", 0) for f in record["frames"]), default=0) if reference else None})
    finally:
        del session
        gc.collect()
    write_json(output_dir / f"{provider}.json", record)
    print(json.dumps({k: v for k, v in record.items() if k not in {"frames", "provider_options"}}), flush=True)
    return record, outputs


def encode_clip(path, model, preprocess, postprocess, output_dir):
    """Exercise serial decode/infer/mask/NVENC; exclude loading and warmup."""
    session = create_session(model, "cuda", output_dir, profiling=False)
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    if not capture.isOpened():
        raise RuntimeError(f"Cannot decode {path}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    ok, first = capture.read()
    if not ok:
        raise RuntimeError("No pipeline warmup frame")
    session.run(None, {session.get_inputs()[0].name: preprocess(first)})
    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
    output_path = output_dir / "cuda-pipeline.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0",
               "-an", "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-bf", "0",
               "-pix_fmt", "yuv420p", "-threads", "2", str(output_path)]
    counts, service_ms = [], []
    encoder = None
    start = time.perf_counter()
    with (output_dir / "cuda-pipeline.ffmpeg.log").open("w") as log:
        try:
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
            for _ in range(150):
                before = time.perf_counter()
                ok, frame = capture.read()
                if not ok:
                    break
                tensor = preprocess(frame)
                probability = session.run(None, {session.get_inputs()[0].name: tensor})[0]
                boxes = boxes_for(probability, frame, postprocess)
                masked, _ = masked_frame(frame, boxes, .3)
                encoder.stdin.write(masked.tobytes())
                counts.append(len(boxes))
                service_ms.append((time.perf_counter() - before) * 1000)
            encoder.stdin.close()
            code = encoder.wait(timeout=30)
            if code:
                raise RuntimeError(f"NVENC pipeline failed exit {code}; see cuda-pipeline.ffmpeg.log")
        finally:
            capture.release()
            if encoder is not None and encoder.poll() is None:
                encoder.terminate()
                try:
                    encoder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    encoder.kill()
                    encoder.wait(timeout=5)
            del session
            gc.collect()
    elapsed = time.perf_counter() - start
    if len(counts) != 150 or sum(counts) == 0:
        raise RuntimeError(f"Pipeline frame/detection accounting failed: {len(counts)}, {sum(counts)}")
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=codec_name,width,height,nb_read_frames,r_frame_rate,duration", "-of", "json", str(output_path),
    ], text=True))
    if int(metadata["streams"][0]["nb_read_frames"]) != len(counts):
        raise RuntimeError("Encoded output frame count differs from input")
    return {"path": str(output_path), "sha256": sha256_file(output_path), "command": command,
            "frames": len(counts), "wall_seconds": elapsed, "fps": len(counts) / elapsed,
            "service": distribution(service_ms), "boxes_per_frame": counts,
            "metadata": metadata, "scope": "five-second unpaced serial pipeline; no OCR or privacy gate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=CANDIDATES, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit-side-len", type=int, default=960)
    parser.add_argument("--encode", action="store_true")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ort.disable_telemetry_events()
    cv2.setNumThreads(2)
    model, artifact = verified_path(args.candidate, args.project_root / "models/cache")
    frames, sampling = sample_frames(args.project_root)
    preprocess = DetPreProcess(args.limit_side_len, "max", artifact["preprocess"]["mean"], artifact["preprocess"]["std"])
    before = time.perf_counter()
    tensors = [preprocess(frame) for frame in frames]
    preprocess_seconds = time.perf_counter() - before
    postprocess = DBPostProcess(thresh=.3, box_thresh=.5, max_candidates=1000, unclip_ratio=1.6,
                                use_dilation=True, score_mode="fast")
    sources = [Path(__file__), Path(masked_frame.__code__.co_filename),
               Path(verified_path.__code__.co_filename), args.project_root / "models/manifest.json"]
    source_hashes = {str(p): sha256_file(p) for p in sources}
    summary = {"candidate": args.candidate, "model": artifact, "sampling": sampling,
               "machine": platform.platform(), "python_version": platform.python_version(),
               "onnxruntime_version": ort.__version__, "rapidocr_version": version("rapidocr"),
               "available_providers": ort.get_available_providers(), "resources_before": resources(),
               "source_sha256": source_hashes, "limit_side_len": args.limit_side_len,
               "tensor_shape": list(tensors[0].shape), "preprocess_seconds_for_20_frames": preprocess_seconds,
               "scope": "sf-market tune only; CPU then CUDA on identical 20 real frames, first two warmup; no OCR/privacy gate",
               "packages": sorted([{"name": d.metadata["Name"], "version": d.version} for d in distributions()], key=lambda p: p["name"].lower()),
               "variants": []}
    write_json(output_dir / "summary.json", summary)
    for provider in ("cpu", "cuda"):
        record, outputs = run_variant(model, provider, tensors, frames, postprocess, output_dir,
                                      reference if provider == "cuda" else None)
        summary["variants"].append(record)
        if provider == "cpu":
            reference = outputs
        write_json(output_dir / "summary.json", summary)
    if args.encode:
        summary["pipeline"] = encode_clip(sampling["path"], model, preprocess, postprocess, output_dir)
    if any(sha256_file(Path(p)) != digest for p, digest in source_hashes.items()):
        raise RuntimeError("Probe source changed during measurement")
    summary["resources_after"] = resources()
    summary["status"] = "ok"
    write_json(output_dir / "summary.json", summary)
    print(json.dumps({"event": "complete", "summary": str(output_dir / "summary.json"), "status": "ok"}), flush=True)


if __name__ == "__main__":
    main()
