"""One common source/model/config identity before any W1 arm evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
V2_SHA="bb284c1cc701eadf3e7b4dc463e8bf6f46cc6cd606436e033d8cbee3fbf43093"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_files(root=ROOT):
    paths=set()
    for directory in ("shield","bench","tests","relay"):
        paths.update(p for p in (Path(root)/directory).rglob("*.py") if "__pycache__" not in p.parts)
    for name in ("scripts/check","models/manifest.json","fixtures/manifest.json","requirements.txt","requirements-models.txt","requirements-linux-gpu.txt","bench/gate-1-policy.json"):
        paths.add(Path(root)/name)
    paths.update((Path(root)/"bench/w1").rglob("*.json"))
    paths.update((Path(root)/"models").glob("w1-*.json"))
    return {str(path.relative_to(root)):sha256(path) for path in sorted(paths)}


def freeze(destination):
    from bench.offline_quality import _fingerprint
    from bench.clocked_pipeline import fingerprint
    destination=Path(destination)
    if destination.exists(): raise FileExistsError(destination)
    value={"schema_version":1,"base":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
           "files":source_files(),"offline_pipeline_sha256":_fingerprint(),"clocked_pipeline_sha256":fingerprint(),
           "scope":"W1 common source/model/config freeze. Changing any file or source inventory requires a new freeze and paired baseline. No V2 media included.",
           "v2_reserved_manifest_sha256":V2_SHA}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(value,indent=2)+"\n")
    return value


def verify_freeze(path):
    value=json.loads(Path(path).read_bytes())
    if value["files"]!=source_files():
        raise ValueError("W1 common source/model/config freeze differs")
    if value["v2_reserved_manifest_sha256"]!=V2_SHA:
        raise ValueError("W1 reserved V2 manifest differs")
    return value


def verify_gate(path,freeze_path):
    receipt=json.loads(Path(path).read_bytes())
    if (receipt.get("exit_code")!=0 or receipt.get("full_gate") is not True
            or receipt.get("lock_mode")!="SH" or not any(str(arg)=="scripts/check" or str(arg).endswith("/scripts/check") for arg in receipt.get("argv",[]))
            or receipt.get("source_freeze_sha256")!=sha256(freeze_path)):
        raise ValueError("W1 metrics require a full SH composition gate0 on this source freeze")
    if sha256(receipt["raw_log"])!=receipt["raw_log_sha256"]:
        raise ValueError("W1 full-gate raw log changed")
    return receipt


def verify_metric_barriers(freeze_path,gate_path,parity_path):
    frozen=verify_freeze(freeze_path)
    verify_gate(gate_path,freeze_path)
    parity=json.loads(Path(parity_path).read_bytes())
    if (parity.get("pass") is not True or parity.get("pipeline_sha256")!=frozen["clocked_pipeline_sha256"]
            or parity.get("source_freeze_sha256")!=sha256(freeze_path)
            or {r.get("lane") for r in parity.get("rows",[])}!={"fast","accurate","small1280","medium960","server960","tile960"}
            or not all(r.get("pass") is True for r in parity["rows"])):
        raise ValueError("W1 metrics require functional CUDA parity0 on this source freeze")
    return frozen
