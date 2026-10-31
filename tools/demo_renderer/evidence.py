"""Structural contract for a future native observer; never certifies native execution."""
from fractions import Fraction
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Missing artifact hash')


def integer(value):
    require(type(value) is int and value >= 0, 'Invalid frame identity')
    return value


def unique(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        require(key not in result, 'Duplicate evidence identity')
        result[key] = row
    return result


def validate_structure(document):
    require(document['schema'] == 'irl-shield-w8-native-v3', 'Expected W8 native v3')
    require(document['producer_kind'] in ('actual-native-relay', 'synthetic-test'), 'Unknown evidence kind')
    digest(document['source_manifest_sha256'])
    sources = unique(document['sources'], 'id')
    for source in sources.values():
        require(isinstance(source['id'], str) and source['id'], 'Missing source identity')
        integer(source['source_index'])
        integer(source['ingest_generation'])
        require(Fraction(source['ingest_pts']) >= 0, 'Invalid ingest PTS')
        digest(source['input_vcl_sha256'])
    selections = unique(document['selections'], 'engine_index')
    for row in selections.values():
        integer(row['engine_index'])
        if row['kind'] == 'source':
            require(row['source_id'] in sources and row['reason'] is None, 'Unbound input selection')
        else:
            require(row['kind'] == 'source-less' and row['source_id'] is None,
                    'Protective selection must keep its source null')
            require(row['reason'] in ('startup', 'missing-capture', 'transport-disconnected'),
                    'Missing source-less reason')
    detections = unique(document['detections'], 'id')
    for row in detections.values():
        selected = selections[row['engine_index']]
        require(row['lane'] in ('fast', 'accurate') and selected['kind'] == 'source'
                and row['source_id'] == selected['source_id'], 'Detector bound to fabricated input')
        digest(row['model_sha256'])
    outputs = document['outputs']
    require(outputs, 'No output evidence')
    previous_pts = None
    seen_outputs = set()
    emitted_indices = set()
    for output in outputs:
        key = (integer(output['egress_generation']), integer(output['output_index']))
        require(key not in seen_outputs, 'Duplicate encoded output')
        seen_outputs.add(key)
        index = integer(output['engine_index'])
        emitted_indices.add(index)
        selected = selections[index]
        pts = Fraction(output['session_pts'])
        require(pts >= 0 and (previous_pts is None or pts > previous_pts), 'Output clock regression')
        previous_pts = pts
        require(output['state'] in ('LIVE', 'PROTECT', 'HOLD') and type(output['slate']) is bool,
                'Invalid output state')
        require(output['source_id'] == selected['source_id'], 'Output source disagrees with selection')
        if selected['kind'] == 'source-less':
            require(output['state'] in ('PROTECT', 'HOLD') and output['slate']
                    and not output['applied_detection_ids'], 'Source-less output cannot claim LIVE or masks')
        elif output['state'] == 'LIVE':
            require(not output['slate'], 'LIVE output cannot be slate')
        for receipt_id in output['applied_detection_ids']:
            require(receipt_id in detections, 'Missing detector receipt')
        digest(output['pixels_sha256'])
        digest(output['mask_sha256'])
        digest(output['output_vcl_sha256'])
    missing = set()
    for gap in document['gaps']:
        first, stop = integer(gap['first_engine_index']), integer(gap['stop_engine_index'])
        require(first < stop and gap['reason'] in ('not-emitted', 'archive-drop')
                and gap['source_id'] is None, 'Invalid explicit output gap')
        indices = set(range(first, stop))
        require(not indices & (emitted_indices | missing), 'Gap overlaps output or another gap')
        missing.update(indices)
    first, stop = document['window']['first_engine_index'], document['window']['stop_engine_index']
    integer(first)
    integer(stop)
    require(first < stop and emitted_indices | missing == set(range(first, stop)), 'Unreported output gap')
    return {'status': 'STRUCTURE ONLY / NOT CLEARED', 'native_verified': False,
            'producer_claim': document['producer_kind'], 'outputs': len(outputs),
            'source_less_outputs': sum(selections[row['engine_index']]['kind'] == 'source-less' for row in outputs),
            'unemitted_slots': len(missing),
            'limitations': ['No model execution, projection, pixel, timing or brand proof is established by this check']}
