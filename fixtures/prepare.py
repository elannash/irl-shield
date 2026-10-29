#!/usr/bin/env python3
"""Fetch licensed originals, verify their hashes, and prepare frozen excerpts.

Requires Python 3.11+, ffmpeg and ffprobe. Uses VideoToolbox on macOS and
NVENC elsewhere. Canonical derived hashes describe the provisioned NVENC cache;
new encodes retain verified source provenance in a generated receipt.
Verification never changes the manifest or the tune/heldout allocation.
"""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).with_name("manifest.json")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")


def probe(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                             "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def verify_video(path: Path, clip: dict) -> None:
    metadata = probe(path)
    streams = metadata["streams"]
    videos = [stream for stream in streams if stream["codec_type"] == "video"]
    if len(videos) != 1 or any(stream["codec_type"] == "audio" for stream in streams):
        raise ValueError(f"{path} must contain exactly one video stream and no audio")
    video = videos[0]
    actual = (video["width"], video["height"], float(Fraction(video["avg_frame_rate"])),
              int(video["nb_read_frames"]))
    expected = (clip["width"], clip["height"], clip["fps"], round(clip["duration"] * clip["fps"]))
    if actual != expected:
        raise ValueError(f"Video properties differ for {path}: {actual} != {expected}")
    if abs(float(metadata["format"]["duration"]) - clip["duration"]) > 1 / clip["fps"]:
        raise ValueError(f"Duration differs for {path}")


def download(url: str, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={
        "User-Agent": "IRLShieldBench/1.0 (licensed research fixtures; local preparation)"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(destination)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        retry_after = error.headers.get("Retry-After")
        detail = f"; server requests retry after {retry_after} seconds" if retry_after else ""
        raise RuntimeError(f"Download failed: HTTP {error.code} for {url}{detail}. Rerun later.") from error
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def recipe_sha256(clip: dict) -> str:
    recipe = {key: clip[key] for key in
              ("source_sha256", "excerpt_start", "duration", "width", "height", "fps")}
    return hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_cached(output: Path, clip: dict) -> None:
    actual = sha256(output)
    if actual != clip["sha256"]:
        receipt_path = output.with_suffix(".receipt.json")
        if not receipt_path.exists():
            raise ValueError(f"Noncanonical cache has no provenance receipt: {output}")
        receipt = json.loads(receipt_path.read_text())
        expected = (clip["source_sha256"], actual, recipe_sha256(clip))
        found = (receipt.get("source_sha256"), receipt.get("sha256"), receipt.get("recipe_sha256"))
        if found != expected:
            raise ValueError(f"Cache provenance receipt differs for {output}")
    verify_video(output, clip)


def prepare(clip: dict, verify_only: bool, encoder: str) -> None:
    source = ROOT / clip["source_path"]
    output = ROOT / clip["path"]
    if output.exists():
        verify_cached(output, clip)
        print(f"Verified cached {clip['id']}: {sha256(output)}", flush=True)
        return
    if verify_only:
        raise FileNotFoundError(output)
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {clip['id']} ({clip['source_url']})", flush=True)
        download(clip["download_url"], source)
        time.sleep(3)
    verify_hash(source, clip["source_sha256"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem + ".part.mp4")
    encoder_options = ["-preset", "p4"] if encoder == "h264_nvenc" else []
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(clip["excerpt_start"]),
               "-i", str(source), "-map", "0:v:0", "-an", "-t", str(clip["duration"]),
               "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30,setsar=1",
               "-c:v", encoder, *encoder_options, "-b:v", "10M", "-pix_fmt", "yuv420p",
               "-map_metadata", "-1", "-movflags", "+faststart", str(temporary)]
    try:
        subprocess.run(command, check=True)
        verify_video(temporary, clip)
        actual = sha256(temporary)
        temporary.replace(output)
        receipt = {"fixture_id": clip["id"], "source_sha256": clip["source_sha256"],
                   "sha256": actual, "recipe_sha256": recipe_sha256(clip), "encoder": encoder}
        output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    verify_cached(output, clip)
    print(f"Prepared {clip['id']}: {clip['split']}, {clip['width']}x{clip['height']}, "
          f"{clip['fps']:g} fps, {clip['duration']:g}s, no audio, {actual}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="check local files without network or encoding")
    parser.add_argument("--ids", nargs="+", help="prepare only these IDs (split allocation stays fixed)")
    parser.add_argument("--encoder", choices=("h264_nvenc", "h264_videotoolbox"),
                        default="h264_videotoolbox" if platform.system() == "Darwin" else "h264_nvenc")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    clips = manifest["clips"]
    ids = [clip["id"] for clip in clips]
    if manifest.get("status") == "frozen":
        allocation = manifest["source_allocation"]
        if {clip["id"]: clip["split"] for clip in clips} != allocation:
            raise ValueError("Clips differ from the frozen source allocation")
        if sum(split == "tune" for split in allocation.values()) != 7 or sum(split == "heldout" for split in allocation.values()) != 3:
            raise ValueError("Frozen allocation must contain seven tune and three heldout clips")
    if (len(ids) != len(set(ids))
            or len({clip["source_url"] for clip in clips}) != len(clips)
            or len({clip["source_sha256"] for clip in clips}) != len(clips)):
        raise ValueError("Manifest repeats a clip ID or original source")
    if any(clip["license"] not in ("CC0", "CC BY 3.0", "CC BY 4.0", "Public domain") for clip in clips):
        raise ValueError("Manifest contains a license outside the fixture policy")
    if args.ids:
        unknown = set(args.ids) - set(ids)
        if unknown:
            raise ValueError(f"Unknown fixture IDs: {sorted(unknown)}")
        clips = [clip for clip in clips if clip["id"] in args.ids]
    for clip in clips:
        prepare(clip, args.verify_only, args.encoder)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Fixture preparation failed: {error}", file=sys.stderr)
        sys.exit(1)
