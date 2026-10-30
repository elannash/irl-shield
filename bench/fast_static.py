"""Hash-pinned FAST shape derivation; graph operations and weights stay intact."""
import hashlib
import os
from pathlib import Path
import tempfile

from models.prepare import sha256_file


def prepare_static(source, source_sha256, side, cache_dir):
    import onnx
    from onnx import helper

    if sha256_file(source) != source_sha256:
        raise ValueError('FAST source SHA-256 mismatch')
    if isinstance(side, bool) or not isinstance(side, int) or side < 32 or side % 32:
        raise ValueError('FAST static side must be a positive multiple of 32')
    model = onnx.load(source, load_external_data=False)
    if len(model.graph.input) != 1 or len(model.graph.output) != 1:
        raise ValueError('FAST requires one tensor input and one tensor output')
    if any(t.data_location == onnx.TensorProto.EXTERNAL for t in model.graph.initializer):
        raise ValueError('FAST requires embedded weights')
    shape = [1, 3, side, side]
    info = model.graph.input[0]
    if info.type.tensor_type.elem_type != onnx.TensorProto.FLOAT:
        raise ValueError('FAST requires float32 input')
    info.type.CopyFrom(helper.make_tensor_value_info(info.name, onnx.TensorProto.FLOAT, shape).type)
    # Outputs/intermediates must be inferred from the new input, not the export's dimensions.
    del model.graph.value_info[:]
    model.graph.output[0].type.tensor_type.ClearField('shape')
    model = onnx.shape_inference.infer_shapes(model, check_type=True, strict_mode=True, data_prop=True)
    onnx.checker.check_model(model, full_check=True)
    data = model.SerializeToString(deterministic=True)
    digest = hashlib.sha256(data).hexdigest()
    destination = Path(cache_dir) / f'fast-static-{side}-{digest}.onnx'
    if destination.exists():
        if sha256_file(destination) != digest:
            raise ValueError('FAST derived artifact SHA-256 mismatch')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix='fast-static-', dir=destination.parent)
        try:
            with os.fdopen(handle, 'wb') as stream:
                stream.write(data)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    output = model.graph.output[0]
    return destination, {'recipe': 'fast-static-input-shape-inference-v1',
                         'source_sha256': source_sha256, 'derived_sha256': digest,
                         'derived_path': str(destination), 'input_shape': shape,
                         'output_shape': [d.dim_value if d.HasField('dim_value') else d.dim_param
                                          for d in output.type.tensor_type.shape.dim],
                         'onnx_version': onnx.__version__,
                         'validation': 'onnx.checker.check_model(full_check=True)'}
