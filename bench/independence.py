"""Declared detector and judge provenance; names are registry keys, not heuristics."""
CANDIDATE_METADATA = {
    'unmasked': {'detector_families': []},
    'slate': {'detector_families': []},
    'vision-fast': {'detector_families': ['apple-vision']},
    'vision-accurate': {'detector_families': ['apple-vision']},
    'vision-rectangles': {'detector_families': ['apple-vision']},
    'vision-union': {'detector_families': ['apple-vision']},
    'vision-scheduled': {'detector_families': ['apple-vision']},
    'ppocr-v5-mobile': {'detector_families': ['paddleocr']},
    'ppocr-v5-server': {'detector_families': ['paddleocr']},
    'ppocr-v6-tiny': {'detector_families': ['paddleocr']},
    'ppocr-v6-small': {'detector_families': ['paddleocr']},
    'ppocr-v6-medium': {'detector_families': ['paddleocr']},
    'ppocr-v5-english-rec': {'detector_families': ['paddleocr']},
}
for _candidate in ('w1-small-server-union', 'w1-small-light-pair', 'w1-small-tiled'):
    CANDIDATE_METADATA[_candidate] = {'detector_families': ['paddleocr']}

DEFAULT_FAST_CANDIDATES = {
    'unmasked': None, 'slate': None,
    'vision-fast': 'vision-rectangles', 'vision-accurate': 'vision-rectangles',
    'vision-rectangles': 'vision-rectangles', 'vision-union': 'vision-rectangles',
    'vision-scheduled': 'vision-rectangles',
    'ppocr-v5-mobile': 'ppocr-v6-tiny', 'ppocr-v5-server': 'ppocr-v6-tiny',
    'ppocr-v6-tiny': 'ppocr-v6-tiny', 'ppocr-v6-small': 'ppocr-v6-tiny',
    'ppocr-v6-medium': 'ppocr-v6-tiny', 'ppocr-v5-english-rec': 'ppocr-v6-tiny',
}
for _candidate in ('w1-small-server-union', 'w1-small-light-pair', 'w1-small-tiled'):
    DEFAULT_FAST_CANDIDATES[_candidate] = 'ppocr-v6-tiny'

JUDGE_METADATA = {
    'tesseract': {'family': 'tesseract'},
    'vision-accurate': {'family': 'apple-vision'},
    'ppocr-independent': {'family': 'paddleocr'},
}


def candidate_metadata(name):
    try:
        families = list(CANDIDATE_METADATA[name]['detector_families'])
    except KeyError as error:
        raise ValueError(f'Candidate has no declared detector families: {name}') from error
    if not families and name not in ('unmasked', 'slate'):
        raise ValueError(f'Only no-detector controls may declare empty detector families: {name}')
    return {'detector_families': families}


def resolve_fast_candidate(candidate, options):
    """Resolve the declared fast lane for both runtime construction and provenance."""
    if 'detector_families' in options:
        raise ValueError('detector_families overrides are not supported; families come from the candidate/lane registry')
    candidate_metadata(candidate)
    if candidate in ('unmasked', 'slate'):
        return None
    fast = options.get('fast_candidate', DEFAULT_FAST_CANDIDATES[candidate])
    candidate_metadata(fast)
    return fast


def policy_metadata(candidate, options):
    lanes = {'accurate': candidate_metadata(candidate)}
    fast = resolve_fast_candidate(candidate, options)
    if fast is not None:
        lanes['fast'] = candidate_metadata(fast)
    return {'lanes': lanes, 'detector_families': sorted({family for lane in lanes.values()
                                                       for family in lane['detector_families']})}


def retained_policy_metadata(card):
    """Validate retained provenance without inventing an unrecorded fast lane."""
    candidate, options = card['candidate'], card.get('options', {})
    if ('detector_metadata' not in card and candidate not in ('unmasked', 'slate')
            and 'fast_candidate' not in options):
        raise ValueError('Retained scorecard needs recorded detector_metadata or an explicit options.fast_candidate')
    declared = policy_metadata(candidate, options)
    if 'detector_metadata' in card:
        recorded = card['detector_metadata']
        if recorded != declared:
            raise ValueError('Retained scorecard recorded detector_metadata differs from the declared registry policy')
        return recorded
    return declared


def _validated_families(detector_families):
    families = set(detector_families)
    declared = {meta['family'] for meta in JUDGE_METADATA.values()}
    declared.update(family for meta in CANDIDATE_METADATA.values() for family in meta['detector_families'])
    unknown = families - declared
    if unknown:
        raise ValueError(f'Unregistered detector families: {sorted(unknown)}')
    return families


def independent_readings(frames, detector_families):
    families = _validated_families(detector_families)
    if not families:
        return frames
    selected = []
    for frame in frames:
        kept = []
        for reading in frame:
            judge = reading.get('judge')
            if judge not in JUDGE_METADATA:
                raise ValueError(f'Reading has no declared judge family: {judge}')
            if JUDGE_METADATA[judge]['family'] not in families:
                kept.append(reading)
        selected.append(kept)
    return selected


def judging_scope(detector_families):
    families = sorted(_validated_families(detector_families))
    included = [name for name, meta in JUDGE_METADATA.items() if meta['family'] not in families]
    return {'detector_families': families, 'included_judges': included,
            'truth_judges': included, 'output_leak_judges': list(JUDGE_METADATA),
            'scope': 'Family independence applies to natural truth and synthetic input controls only; every credible output judge counts as a leak.',
            'excluded_judges': [name for name in JUDGE_METADATA if name not in included],
            'sufficient_independent_engines': len(included) >= 2,
            'warning': 'Mixed detector families leave only one independent judge: Tesseract.' if len(included) == 1 else None}


def annotate_card(card):
    """Keep aggregate primary/secondary provenance visible on every scorecard."""
    metadata=policy_metadata(card['candidate'],card.get('options',{}))
    scope=judging_scope(metadata['detector_families'])
    card['detector_metadata']=metadata
    card['judge_independence']=scope
    card['scope']='Primary truth/input controls exclude detector families '+str(scope['detector_families'])+'; truth judges '+str(scope['truth_judges'])+'; output leaks use ALL judges '+str(scope['output_leak_judges'])+'. '+card.get('scope','')
    clips=card.get('clips',[])
    if clips and all('pooled_not_independent' in row for row in clips):
        pooled={'scope':'Secondary all-judge pooled diagnostic; NOT independent and ineligible for privacy gates.'}
        for kind in ('natural','synthetic'):
            total=sum(row['pooled_not_independent'][kind]['total'] for row in clips)
            hidden=sum(row['pooled_not_independent'][kind]['hidden'] for row in clips)
            pooled[kind]={'hidden':hidden,'total':total,'hidden_fraction':hidden/total if total else None}
        card['pooled_not_independent']=pooled
    return scope
