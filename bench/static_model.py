"""Derive a checked, fixed-resolution PP-OCR detector without changing weights."""

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import onnx
from onnx import helper

from models.prepare import sha256_file


def prepare_static(source_path, source_sha256, height, width, cache_dir):
    """Return ``(Path, metadata)`` for a 1×3×H×W detector with 1×1×H×W output.

    H/W must be the actual preprocessed detector tensor dimensions, both
    multiples of 32. This changes shape declarations and infers intermediate
    shapes; graph operations, weights, opsets and model metadata are retained.
    """
    source_path = Path(source_path).expanduser().resolve()
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 hex digest")
    actual_source_sha256 = sha256_file(source_path)
    if actual_source_sha256 != source_sha256:
        raise ValueError(f"SHA-256 mismatch for static-model source {source_path}: {actual_source_sha256}")
    for name, value in (("height", height), ("width", width)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 32 or value % 32:
            raise ValueError(f"{name} must be a positive multiple of 32")

    derivation = {
        "recipe": "ppocr-static-io-and-shape-inference-v1",
        "source_sha256": source_sha256,
        "height": height,
        "width": width,
        "onnx_version": onnx.__version__,
    }
    cache_key = hashlib.sha256(json.dumps(derivation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    model = onnx.load(source_path, load_external_data=False)
    if len(model.graph.input) != 1 or len(model.graph.output) != 1:
        raise ValueError("Static PP-OCR derivation requires exactly one graph input and output")
    if any(t.data_location == onnx.TensorProto.EXTERNAL for t in model.graph.initializer):
        raise ValueError("Static PP-OCR derivation requires a single-file model with embedded weights")
    input_info = model.graph.input[0]
    output_info = model.graph.output[0]
    for info, shape in ((input_info, [1, 3, height, width]), (output_info, [1, 1, height, width])):
        if not info.type.HasField("tensor_type") or info.type.tensor_type.elem_type != onnx.TensorProto.FLOAT:
            raise ValueError("Static PP-OCR derivation requires float32 input and output tensors")
        fixed = helper.make_tensor_value_info(info.name, onnx.TensorProto.FLOAT, shape)
        info.type.tensor_type.shape.CopyFrom(fixed.type.tensor_type.shape)

    # Static intermediate shapes can make more nodes eligible for CoreML EP.
    model = onnx.shape_inference.infer_shapes(model, check_type=True, strict_mode=True, data_prop=True)
    onnx.checker.check_model(model, full_check=True)
    serialized = model.SerializeToString(deterministic=True)
    derived_sha256 = hashlib.sha256(serialized).hexdigest()
    destination = Path(cache_dir).expanduser().resolve() / f"det-static-{cache_key}.onnx"
    if destination.exists():
        actual = sha256_file(destination)
        if actual != derived_sha256:
            raise ValueError(f"SHA-256 mismatch for cached static model {destination}: {actual}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=destination.name + ".", dir=destination.parent)
        try:
            with os.fdopen(handle, "wb") as output:
                output.write(serialized)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    metadata = {
        **derivation,
        "cache_key": cache_key,
        "source_path": str(source_path),
        "derived_path": str(destination),
        "derived_sha256": derived_sha256,
        "input_name": input_info.name,
        "input_shape": [1, 3, height, width],
        "output_name": output_info.name,
        "output_shape": [1, 1, height, width],
        "validation": "onnx.checker.check_model(full_check=True)",
    }
    return destination, metadata
