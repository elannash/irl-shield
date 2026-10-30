"""Interval scoring and anti-cheating metrics, independent of detector code."""
import math
import re
from difflib import SequenceMatcher
from numbers import Real

import cv2
import numpy as np


def validate_area_ceiling(ceiling, basis=None, *, required=False):
    """Return a backed fractional ceiling, or no configured diagnostic guard.

    Basis is a nonempty receipt reference, retained for human review; it may
    name a repository artifact, a retained run, or a source URL.
    """
    if ceiling is None:
        if required:
            raise ValueError('An explicit masked-area ceiling and basis receipt are required')
        return None
    if isinstance(ceiling, bool) or not isinstance(ceiling, Real) or not math.isfinite(ceiling) or not 0 <= ceiling <= 1:
        raise ValueError('Area ceiling must be finite and between zero and one')
    if not isinstance(basis, str) or not basis.strip():
        if required:
            raise ValueError('Area ceiling requires a nonempty basis receipt reference')
        return None
    return float(ceiling)


def masked_area_pass(card):
    """A comparison needs a backed ceiling and a finite measured median."""
    options = card.get('options', {})
    ceiling = validate_area_ceiling(card.get('area_ceiling', options.get('area_ceiling')),
                                    card.get('area_ceiling_basis', options.get('area_ceiling_basis')))
    median = card.get('masked_area_fraction', {}).get('p50')
    return bool(ceiling is not None and not isinstance(median, bool) and isinstance(median, Real)
                and math.isfinite(median) and 0 <= median <= ceiling)


def normalize(text):
    return ''.join(c for c in text.casefold() if c.isalnum())


def matches(a, b):
    a, b = normalize(a), normalize(b)
    if min(len(a), len(b)) < 3:
        return a == b and len(a) >= 1
    if a in b or b in a:
        return min(len(a), len(b)) >= 3 or a == b
    matcher = SequenceMatcher(None, a, b)
    return matcher.ratio() >= .8 or matcher.find_longest_match().size >= max(3, .3 * min(len(a),len(b)))


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection / union if union > 0 else 0


def overlap(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    minimum=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
    return intersection/minimum if minimum>0 else 0


def readable(target, readings):
    # A judge recognizing a short fragment is already a privacy leak.
    short=normalize(target['text'])
    def found(text):
        if 0<len(short)<3:
            for token in re.findall(r'[^\W_]+',text):
                word=normalize(token)
                for hit in re.finditer(re.escape(short),word):
                    start,end=hit.span()
                    left=start==0 or word[start-1].isdigit()!=short[0].isdigit()
                    right=end==len(word) or word[end].isdigit()!=short[-1].isdigit()
                    if left and right:
                        return True
        return matches(target['text'],text)
    return any(found(item['text']) and overlap(target['box'], item['box']) > .05 for item in readings)


def truth_from_readings(readings):
    found = []
    for item in sorted(readings,key=lambda r:len(normalize(r['text'])),reverse=True):
        if len(normalize(item['text'])) < 1:
            continue
        if not any((normalize(item['text']) in normalize(old['text'])) and iou(item['box'], old['box']) > .2 for old in found):
            found.append(item)
    return found


def fidelity(source, output, mask):
    outside = mask == 0
    fraction = float(outside.mean())
    # Masks may not remove every informative pixel and call the remaining void real video.
    if fraction < .5:
        return {'outside_fraction': fraction, 'outside_mae': None, 'source_std': 0, 'pass': False}
    a, b = source[outside].astype(float), output[outside].astype(float)
    mae = float(np.abs(a-b).mean())
    std = float(b.std())
    return {'outside_fraction': fraction, 'outside_mae': mae, 'source_std': std,
            'pass': mae < 12 and std > 8}


def quantiles(values):
    return {'p50': float(np.percentile(values, 50)), 'p95': float(np.percentile(values, 95))} if values else {'p50': None, 'p95': None}
