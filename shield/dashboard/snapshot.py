"""Explicit scalar allowlists at the dashboard and viewer boundaries."""
from collections.abc import Mapping
import math

STATES = ('LIVE', 'PROTECT', 'HOLD')
FACE_MODES = ('bystanders', 'all', 'off')
SKINS = ('frosted', 'opaque', 'black', 'pixel', 'mosaic', 'solid', 'blocks')
REASONS = {
    'startup': 'Waiting for protected video.',
    'manual': 'Your manual hold is active.',
    'chat': 'Chat requested a hold.',
    'shield_mode': 'Twitch Shield Mode is active.',
    'transport': 'Waiting for the stream connection.',
    'egress': 'Waiting for safe output.',
    'coverage': 'Checking privacy coverage.',
    'clear': 'Privacy coverage is current.',
    'ok': 'Privacy coverage is current.',
    'stale': 'Waiting for fresh privacy coverage.',
    'unknown': 'Protection state supplied by the stream controller.',
}


def _count(value):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError('Invalid dashboard count')
    return value


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValueError('Invalid dashboard mode')
    return value


def public_snapshot(raw):
    """Copy only safe, bounded fields; caller counts are unique session tracks.

    Unknown reason strings never become user-facing text. No metadata, URL,
    arbitrary skin/voter name, coordinates or engine object is serialized.
    """
    if not isinstance(raw, Mapping):
        raise ValueError('Invalid dashboard snapshot')
    reason = raw.get('reason_code')
    votes = raw['votes']
    if not isinstance(votes, Mapping) or len(votes) > len(SKINS):
        raise ValueError('Invalid dashboard votes')
    if type(raw['skin_locked']) is not bool:
        raise ValueError('Invalid dashboard lock')
    result = {
        'state': _enum(raw['state'], STATES),
        'reason_code': reason if type(reason) is str and reason in REASONS else 'unknown',
        'clues_hidden': _count(raw['clues_hidden']),
        'faces_hidden': _count(raw['faces_hidden']),
        'face_mode': _enum(raw['face_mode'], FACE_MODES),
        'skin': _enum(raw['skin'], SKINS),
        'votes': {_enum(key, SKINS): _count(value) for key, value in votes.items()},
        'skin_locked': raw['skin_locked'],
    }
    if 'geo_risk' in raw or 'geo_risk_age_s' in raw:
        risk, age = raw['geo_risk'], raw['geo_risk_age_s']
        if (type(risk) not in (int, float) or type(age) not in (int, float)
                or not math.isfinite(risk) or not math.isfinite(age)
                or not 0 <= risk <= 1 or not 0 <= age <= 2**53 - 1):
            raise ValueError('Invalid dashboard risk')
        result.update(geo_risk=float(risk), geo_risk_age_s=float(age))
    return result


def presentation_fields(raw):
    """W7-only projection. Private pairing/QR and even geo risk are excluded."""
    safe = public_snapshot(raw)
    return {'state': safe['state'], 'reason_code': safe['reason_code'],
            'clue_count': safe['clues_hidden'], 'face_count': safe['faces_hidden'],
            'skin_name': safe['skin']}
