#!/usr/bin/env python3
"""Root-only CPU preparation of the metadata-selected, ungraded v3 holdout.

No download, decode, native import, or queue access occurs on import. Every CLI
action needs a hash-pinned root release and an inherited canonical EX lease.
Failures retain partial files and consume the action; there are no retries.
"""

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import itertools
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATASET = 'fresh-heldout-v3'
METADATA = ROOT / 'fixtures/fresh-heldout-v3'
CACHE = 'fixtures/cache/fresh-heldout-v3'
SELECTION_SHA256 = '0dbb14bb2da57364c6b1ca131c29619e9270297298abb4222aa277d633c5f1df'
CONTRACT_SHA256 = '21db67a6797db123f040cd4405d8632245df4247f4c44f382e194a8e17eb9d7b'
NOT_BEFORE = '2026-11-02T12:00:00Z'
PERF_LOCK = Path('/tmp/agents/irl-shield/perf.lock')
THREAD_ENV = ('OMP_NUM_THREADS', 'OMP_THREAD_LIMIT', 'OPENBLAS_NUM_THREADS',
              'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')
CLIP_IDS = ('ryde-somerset-walk', 'madison-state-street-walk', 'katowice-footbridge-walk')
VARIANTS = ('natural', 'synthetic')
RECIPE = {
    'encoder': 'libx264', 'preset': 'medium', 'bitrate': '10M', 'pixel_format': 'yuv420p',
    'threads': 2, 'filter_threads': 1, 'opencv_threads': 1, 'opencl': False,
    'excerpt_start': 2.0, 'excerpt_end_exclusive': 7.0, 'frames': 150,
    'width': 1280, 'height': 720, 'fps': 30, 'duration': 5.0,
    'filter': 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=30:start_time=0,setsar=1',
    'audio': False, 'subtitles': False, 'data': False, 'source_metadata': False, 'chapters': False,
    'overlay': 'bench.synthetic.overlay; v2 camera tracking; deterministic v3 seed',
}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def is_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def checked_path(base, relative):
    """Reject traversal and symlinks, including dangling output symlinks."""
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or str(PurePosixPath(relative)) != relative
            or PurePosixPath(relative).is_absolute()
            or any(part in ('.', '..') for part in relative.split('/'))):
        raise ValueError('Unsafe relative path')
    base = Path(base).resolve(strict=True)
    current = base
    for part in relative.split('/'):
        current /= part
        if current.is_symlink():
            raise ValueError('Symlink in sealed path')
    if not current.resolve().is_relative_to(base):
        raise ValueError('Path escapes sealed directory')
    return current


def exclusive_write(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Symlink output forbidden')
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def metadata_contract():
    path = METADATA / 'metadata-contract.json'
    if sha256(path) != CONTRACT_SHA256:
        raise ValueError('Metadata contract changed')
    contract = json.loads(path.read_text())
    for name, expected in contract['files'].items():
        if sha256(checked_path(METADATA, name)) != expected:
            raise ValueError('Sealed metadata changed: ' + name)
    return contract


def canonical_url(value):
    url = urllib.parse.urlsplit(value)
    return (url.hostname, urllib.parse.unquote(url.path).replace(' ', '_').casefold())


def validate_selection(data):
    if (data.get('dataset_id') != DATASET or data.get('status') != 'source-selection-sealed'
            or data.get('benchmark_only') is not True or data.get('demo_ready') is not False
            or data.get('root_source_choice_accepted') is not True):
        raise ValueError('V3 requires sealed benchmark-only source choices')
    clips = data.get('clips', [])
    if tuple(c['id'] for c in clips) != CLIP_IDS:
        raise ValueError('Exactly the three ordered v3 sources are required')
    for clip in clips:
        id = clip['id']
        seed = int.from_bytes(hashlib.sha256((DATASET + ':' + id).encode()).digest()[:4], 'big')
        extension = '.ogv' if id == CLIP_IDS[0] else '.webm'
        if (re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', id) is None
                or clip['source_path'] != f'{CACHE}/{id}{extension}'
                or clip['seed'] != seed or clip['split'] != 'heldout'
                or tuple(clip[k] for k in ('excerpt_start', 'excerpt_end_exclusive', 'duration',
                                          'width', 'height', 'fps', 'frames'))
                != (2.0, 7.0, 5.0, 1280, 720, 30, 150)
                or clip['source_duration_seconds'] < 7 or clip['source_width'] < 1280
                or clip['source_height'] < 720 or clip['source_sha256'] is not None
                or clip['preparation_argv'] is not None or clip['payload_verified'] is not False):
            raise ValueError('V3 source path, seed or fixed excerpt recipe differs')
        version = '4.0' if id == CLIP_IDS[2] else '3.0'
        license_url = 'https://creativecommons.org/licenses/by/' + version
        identity, evidence = clip['license_identity'], clip['license_evidence']
        if (clip['license'] != 'CC BY ' + version or clip['license_url'] != license_url
                or evidence['metadata_license_key'] != 'cc-by-' + version
                or identity != {'work': clip['origin_work_identities'],
                                'licensor_urls': clip['author_identity_urls'],
                                'licensor_name': clip['author'], 'license_url': license_url}):
            raise ValueError('V3 license/author/origin binding differs; only fixed BY3/BY4 allowed')
        if (urllib.parse.urlsplit(clip['download_url']).hostname != 'upload.wikimedia.org'
                or urllib.parse.urlsplit(clip['download_url']).scheme != 'https'
                or not urllib.parse.urlsplit(clip['download_url']).path.endswith(extension)):
            raise ValueError('V3 requires the original sealed Commons URL and extension')
    for left, right in itertools.combinations(clips, 2):
        for key in ('title', 'commons_pageid', 'source_path', 'source_sha1'):
            if left[key] == right[key]:
                raise ValueError('V3 source identities must be distinct')
        for key in ('source_url', 'download_url'):
            if canonical_url(left[key]) == canonical_url(right[key]):
                raise ValueError('V3 URLs must be distinct')
        for key in ('origin_work_identities', 'author_identity_urls'):
            if set(left[key]) & set(right[key]):
                raise ValueError('V3 origin and author identities must be disjoint')
    sealed = METADATA / 'selection.json'
    if sha256(sealed) != SELECTION_SHA256 or data != json.loads(sealed.read_text()):
        raise ValueError('Source selection changed after root seal')
    return clips


def selection():
    metadata_contract()
    data = json.loads((METADATA / 'selection.json').read_text())
    validate_selection(data)
    # All provenance is mirrored locally; no old dataset, marker or receipt is opened.
    nonreuse = json.loads((METADATA / data['nonreuse_path']).read_text())
    if nonreuse['collision_count'] != 0:
        raise ValueError('Root nonreuse evidence reports a collision')
    for clip in data['clips']:
        extract = json.loads(checked_path(METADATA, clip['license_evidence']['page_extract']).read_text())
        page = extract['page']
        info = page['imageinfo'][0]
        meta = info['extmetadata']
        if (page['pageid'] != clip['commons_pageid'] or page['title'] != clip['title']
                or page['revisions'][0]['revid'] != clip['revision_id']
                or (info['size'], info['sha1'], info['width'], info['height'], info['url'])
                != tuple(clip[k] for k in ('source_size_bytes', 'source_sha1', 'source_width',
                                          'source_height', 'download_url_advertised'))
                or meta['Artist']['value'] != clip['author_html']
                or meta['License']['value'] != clip['license_evidence']['metadata_license_key']
                or meta['LicenseUrl']['value'].rstrip('/') != clip['license_url']):
            raise ValueError('Commons source/author/license metadata differs from accepted selection')
    return data


def code_identity():
    contract = metadata_contract()
    for name, expected in contract['source_pins'].items():
        if sha256(checked_path(ROOT, name)) != expected:
            raise ValueError('Recipe or queue source pin changed: ' + name)
    # Harness files are pinned at root release, after the disjoint harness patch
    # is applied. The older v2 recipe and overlay source pins stay fixed here.
    names = [*contract['source_pins'], *contract['font_paths'], 'fixtures/prepare_heldout_v3.py',
             'bench/heldout_bench.py', 'bench/quality_bundle.py']
    return {name: sha256(checked_path(ROOT, name)) for name in names}


def cache_file(cache_root, name):
    prefix = CACHE + '/'
    if not isinstance(name, str) or not name.startswith(prefix):
        raise ValueError('V3 payload must stay in its own cache namespace')
    return checked_path(cache_root, name[len(prefix):])


def original(clip, cache_root, *, expected_sha256=None):
    path = cache_file(cache_root, clip['source_path'])
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size != clip['source_size_bytes']:
        raise ValueError('Original size differs from advertised source')
    with path.open('rb') as stream:
        digest1 = hashlib.file_digest(stream, 'sha1').hexdigest()
    if digest1 != clip['source_sha1']:
        raise ValueError('Original SHA1 differs from advertised source')
    digest = sha256(path)
    if expected_sha256 is not None and (not is_hash(expected_sha256) or digest != expected_sha256):
        raise ValueError('Original SHA256 differs from payload plan')
    return digest


def queue_lease():
    fd = int(os.environ['IRL_SHIELD_PERF_QUEUE_LEASE_FD'])
    actual, expected = os.fstat(fd), PERF_LOCK.stat()
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError('Preparation needs the canonical inherited EX lease')
    identity = f'{os.major(actual.st_dev):02x}:{os.minor(actual.st_dev):02x}:{actual.st_ino}'
    locks = Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines()
    if not any('FLOCK' in row and 'WRITE' in row and identity in row for row in locks):
        raise RuntimeError('Canonical descriptor does not hold an exclusive flock')
    receipt = Path(os.environ['IRL_SHIELD_PERF_QUEUE_RECEIPT'])
    attempt = json.loads(receipt.read_text())
    if (attempt.get('execution_started') is not True or attempt.get('execution_attempt') != 1
            or str(attempt['attempt']) != os.environ['IRL_SHIELD_PERF_QUEUE_ATTEMPT']
            or attempt.get('forced') or os.environ['IRL_SHIELD_PERF_QUEUE_FORCED'] != '0'):
        raise RuntimeError('V3 requires a non-forced first root queue execution')
    return {'receipt': str(receipt), 'receipt_sha256_at_launch': sha256(receipt),
            'attempt': attempt['attempt'], 'execution_attempt': 1,
            'device': actual.st_dev, 'inode': actual.st_ino, 'exclusive': True}


def root_context(args):
    """A null draft release fails before queue, tools, native imports or payloads."""
    release_bytes = args.release.read_bytes()
    if not is_hash(args.release_sha256) or hashlib.sha256(release_bytes).hexdigest() != args.release_sha256:
        raise ValueError('Root release hash missing or mismatched')
    release = json.loads(release_bytes)
    if (release.get('status') != 'root-authorized-v3-preparation'
            or release.get('selection_sha256') != SELECTION_SHA256
            or release.get('metadata_contract_sha256') != CONTRACT_SHA256
            or release.get('recipe') != RECIPE or release.get('root_owned') is not True
            or release.get('max_preparation_jobs') != 2 or release.get('max_execution_attempts') != 1
            or release.get('new_tuning_output_started') is not False
            or not release.get('resource_check_receipt') or not release.get('resource_check_sha256')):
        raise ValueError('Root release is null, incomplete or changes the sealed contract')
    argv = [sys.executable, *sys.argv]
    allowed = [[arg.replace('{release_sha256}', args.release_sha256) for arg in command]
               for command in release.get('argv_templates', [])]
    if (argv not in allowed
            or release.get('runtime_root') != str(ROOT)
            or release.get('cache_root') != str(args.cache_root.resolve(strict=True))
            or args.cache_root.resolve().name != DATASET
            or release.get('code_identity') != code_identity()):
        raise ValueError('Root release argv, cache, runtime or source identity differs')
    if (os.getpriority(os.PRIO_PROCESS, 0) != 10
            or 'app-t3code-agents.slice' not in Path('/proc/self/cgroup').read_text()
            or any(os.environ.get(name) != '2' for name in THREAD_ENV)):
        raise RuntimeError('Root launch must use nice10, agent slice and native2')
    resource_path = Path(release['resource_check_receipt'])
    if sha256(resource_path) != release['resource_check_sha256']:
        raise ValueError('Root resource check receipt changed')
    lease = queue_lease()
    if (not 1 <= len(release.get('queue_receipts', [])) <= 2
            or lease['receipt'] not in release['queue_receipts']):
        raise ValueError('Canonical EX attempt was not bound by root')
    resources = json.loads(resource_path.read_text())
    checked_at = datetime.fromisoformat(resources['checked_at_utc'].replace('Z', '+00:00'))
    age = (datetime.now(timezone.utc) - checked_at).total_seconds()
    if (not 0 <= age <= 120 or resources.get('queue_receipt') != lease['receipt']
            or resources.get('canonical_exclusive') is not True
            or resources.get('other_physical_jobs') != 0
            or resources.get('model_cache_readonly_verified') is not True
            or resources.get('mediamtx_readonly_verified') is not True
            or resources.get('native_threads') != 2 or resources.get('opencv_threads') != 1):
        raise RuntimeError('Fresh root EX/model/cache/MediaMTX/resource checks required before launch')
    queue_sources = release.get('queue_sources')
    if not queue_sources:
        raise ValueError('Actual root EX wrapper/queue source hashes must be bound')
    for path, expected in queue_sources.items():
        if not Path(path).is_absolute() or not is_hash(expected) or sha256(path) != expected:
            raise ValueError('Actual root EX wrapper/queue source changed')
    tools = release['tools']
    for name in ('python', 'ffmpeg', 'ffprobe'):
        tool = tools[name]
        path = Path(tool['path'])
        if not path.is_absolute() or sha256(path) != tool['sha256']:
            raise ValueError('Root tool binding differs: ' + name)
    if Path(tools['python']['path']).resolve() != Path(sys.executable).resolve():
        raise ValueError('Runtime interpreter differs from root binding')
    action = args.action + ('-' + args.clip if args.action == 'prepare' else '')
    # This is an attempt ledger, never an evaluation-start marker. Failed work
    # leaves its claim in place so a repeated command cannot silently retry.
    exclusive_write(checked_path(args.cache_root, action + '.attempt.json'), {
        'action': action, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'root_release_sha256': args.release_sha256, 'argv': argv,
        'queue': lease, 'resource_check_sha256': release['resource_check_sha256'],
    })
    provenance = checked_path(args.cache_root, 'provenance')
    provenance.mkdir(exist_ok=True)
    archives = {}
    for label, source, expected in (('root-release', args.release, args.release_sha256),
                                    ('resource-check', resource_path, release['resource_check_sha256'])):
        name = f'provenance/{label}.{expected}.json'
        destination = checked_path(args.cache_root, name)
        if not destination.exists():
            with destination.open('xb') as output:
                output.write(source.read_bytes())
        if sha256(destination) != expected:
            raise ValueError('Root provenance archive changed during launch')
        archives[CACHE + '/' + name] = expected
    return {'release': release, 'release_sha256': args.release_sha256, 'queue': lease,
            'cache_root': args.cache_root, 'tools': tools, 'provenance': archives}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError('Redirect forbidden for sealed source download')


def download_originals(context):
    opener = urllib.request.build_opener(NoRedirect)
    for clip in selection()['clips']:
        destination = cache_file(context['cache_root'], clip['source_path'])
        row = {'clip': clip['id'], 'url': clip['download_url'], 'path': clip['source_path'],
               'root_release_sha256': context['release_sha256'], 'queue': context['queue'],
               'rate_limit_bytes_per_second': 3 * 1024 * 1024,
               'started_at_utc': datetime.now(timezone.utc).isoformat()}
        try:
            if destination.exists():
                row.update(status='verified-existing', sha256=original(clip, context['cache_root']))
                continue
            partial = destination.with_suffix(destination.suffix + '.part')
            if partial.exists() or partial.is_symlink():
                raise FileExistsError('Partial retained; no automatic retry or resumption')
            request = urllib.request.Request(clip['download_url'], headers={
                'User-Agent': 'IRLShieldBench/1.0 (licensed Commons benchmark preparation)'})
            began, fetched = time.monotonic(), 0
            with partial.open('xb') as output, opener.open(request, timeout=120) as response:
                row.update(http_status=response.status, final_url=response.url)
                if response.status != 200 or response.url != clip['download_url']:
                    raise ValueError('Original response status/URL differs; no redirect substitution')
                length = response.headers.get('Content-Length')
                if length is not None and int(length) != clip['source_size_bytes']:
                    raise ValueError('Original HTTP length differs from advertised source')
                while chunk := response.read(1024 * 1024):
                    if fetched + len(chunk) > clip['source_size_bytes']:
                        raise ValueError('Original download exceeds advertised size')
                    output.write(chunk)
                    fetched += len(chunk)
                    time.sleep(max(0., fetched / row['rate_limit_bytes_per_second'] - (time.monotonic() - began)))
            with partial.open('rb') as stream:
                digest1 = hashlib.file_digest(stream, 'sha1').hexdigest()
            if partial.stat().st_size != clip['source_size_bytes'] or digest1 != clip['source_sha1']:
                raise ValueError('Original download size/SHA1 differs; partial retained')
            digest = sha256(partial)
            # link is exclusive; rename would overwrite an unexpected destination.
            os.link(partial, destination)
            partial.unlink()
            row.update(status='downloaded-verified', size_bytes=fetched, sha1=digest1, sha256=digest)
        except BaseException as error:
            row.update(status='failed', error=str(error))
            raise
        finally:
            row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
            with checked_path(context['cache_root'], 'downloads.jsonl').open('a') as output:
                output.write(json.dumps(row, allow_nan=False) + '\n')


def make_plan(path, context):
    selected = selection()
    clips = [dict(c, source_sha256=original(c, context['cache_root'])) for c in selected['clips']]
    exclusive_write(path, {'schema_version': 1, 'dataset_id': DATASET, 'status': 'planned-ungraded',
                          'selection_sha256': SELECTION_SHA256, 'metadata_contract_sha256': CONTRACT_SHA256,
                          'recipe': RECIPE, 'code_identity': code_identity(), 'clips': clips,
                          'root_release_sha256': context['release_sha256']})


def load_plan(path):
    plan = json.loads(Path(path).read_text())
    if (plan.get('schema_version') != 1 or plan.get('dataset_id') != DATASET
            or plan.get('status') != 'planned-ungraded' or plan.get('recipe') != RECIPE
            or plan.get('selection_sha256') != SELECTION_SHA256
            or plan.get('metadata_contract_sha256') != CONTRACT_SHA256
            or plan.get('code_identity') != code_identity()):
        raise ValueError('Plan differs from sealed v3 source/recipe/code')
    clips = plan['clips']
    stripped = [dict(c, source_sha256=None) for c in clips]
    if stripped != selection()['clips'] or any(not is_hash(c['source_sha256']) for c in clips):
        raise ValueError('Plan differs from the three sources or lacks original SHA256')
    if len({c['source_sha256'] for c in clips}) != 3:
        raise ValueError('V3 original payload SHA256 identities must be distinct')
    return plan


def probe(path, context, *, frames=False):
    command = [context['tools']['ffprobe']['path'], '-v', 'error', '-threads', '2',
               '-show_streams', '-show_format', '-show_chapters']
    if frames:
        command += ['-count_frames', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time']
    command += ['-of', 'json', str(path)]
    return json.loads(subprocess.check_output(command, text=True, timeout=120))


def validate_video(data):
    streams = data['streams']
    if len(streams) != 1 or streams[0]['codec_type'] != 'video' or data.get('chapters'):
        raise ValueError('Derived v3 requires one video stream, no audio/subtitles/data/chapters')
    video = streams[0]
    if (video['width'], video['height'], Fraction(video['avg_frame_rate']),
            Fraction(video['r_frame_rate']), int(video['nb_read_frames']), video['pix_fmt'],
            video['codec_name']) != (1280, 720, Fraction(30), Fraction(30), 150, 'yuv420p', 'h264'):
        raise ValueError('Derived v3 must be exactly 150 actual frames at 1280x720 CFR30 yuv420p')
    times = [float(f['best_effort_timestamp_time']) for f in data['frames']]
    start, duration = float(video['start_time']), float(data['format']['duration'])
    if (len(times) != 150 or any(not math.isfinite(t) or abs(t - i/30) > 2e-6 for i, t in enumerate(times))
            or not math.isfinite(start) or abs(start) > 1e-6
            or not math.isfinite(duration) or abs(duration - 5.) > 1/30):
        raise ValueError('Derived v3 PTS must start at zero and advance at 30fps for five seconds')
    for tags in (video.get('tags', {}), data['format'].get('tags', {})):
        if set(tags) - {'language', 'handler_name', 'vendor_id', 'encoder', 'major_brand',
                        'minor_version', 'compatible_brands'}:
            raise ValueError('Derived v3 retains unexpected source metadata')
    return data


def check_video(path, context):
    return validate_video(probe(path, context, frames=True))


def commands(source, natural, synthetic, context):
    ffmpeg = context['tools']['ffmpeg']['path']
    common = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
              '-threads', '2', '-filter_threads', '1', '-filter_complex_threads', '1']
    encode = ['-an', '-sn', '-dn', '-frames:v', '150', '-c:v', 'libx264', '-preset', 'medium',
              '-b:v', '10M', '-pix_fmt', 'yuv420p', '-threads:v', '2',
              '-map_metadata', '-1', '-map_chapters', '-1', '-metadata', 'encoder=',
              '-metadata:s:v', 'encoder=', '-movflags', '+faststart']
    return [common + ['-ss', '2.0', '-i', str(source), '-map', '0:v:0', '-t', '5.0',
                       '-vf', RECIPE['filter']] + encode + [str(natural)],
            common + ['-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '1280x720', '-r', '30',
                       '-i', 'pipe:0', '-map', '0:v:0'] + encode + [str(synthetic)]]


def validate_truth(truth, clip, synthetic):
    if not isinstance(truth, list) or len(truth) != 150:
        raise ValueError('Truth must describe all 150 frames')
    kinds = ('street', 'plate', 'house', 'storefront')
    for frame_index, labels in enumerate(truth):
        if not isinstance(labels, list) or len(labels) != (4 if synthetic else 0):
            raise ValueError('Natural truth must be empty; synthetic truth needs four labels per frame')
        for kind_index, label in enumerate(labels):
            interval = int((frame_index/30 + kind_index*.67)//4.8)
            if (label['id'] != f"{clip['seed']}:{kinds[kind_index]}:{interval}"
                    or not isinstance(label['text'], str) or not label['text']
                    or type(label['visible']) is not bool
                    or not math.isfinite(label['visibility_fraction'])
                    or not 0 <= label['visibility_fraction'] <= 1
                    or len(label['quad']) != 4 or any(len(p) != 2 for p in label['quad'])
                    or any(not math.isfinite(v) for point in label['quad'] for v in point)):
                raise ValueError('Synthetic truth lacks exact quads, text or deterministic stable IDs')
            xs, ys = zip(*label['quad'])
            if label['box'] != [min(xs), min(ys), max(xs), max(ys)]:
                raise ValueError('Synthetic truth box differs from its text quad')


def prepare(plan_path, clip_id, context):
    plan, identity, plan_hash = load_plan(plan_path), code_identity(), sha256(plan_path)
    clip = next(c for c in plan['clips'] if c['id'] == clip_id)
    base = context['cache_root']
    source = cache_file(base, clip['source_path'])
    # Verify all original bytes before any native import or decode.
    original(clip, base, expected_sha256=clip['source_sha256'])
    natural, synthetic = [checked_path(base, clip_id + '-' + v + '.mp4') for v in VARIANTS]
    receipt = checked_path(base, clip_id + '.prepared.json')
    log_path = checked_path(base, clip_id + '.encode.log')
    targets = [natural, synthetic, receipt, log_path, natural.with_suffix('.truth.json'),
               synthetic.with_suffix('.truth.json')]
    if any(p.exists() or p.is_symlink() for p in targets):
        raise FileExistsError('V3 refuses to overwrite derived assets, logs or receipts')
    source_probe = probe(source, context)
    videos = [v for v in source_probe['streams'] if v['codec_type'] == 'video']
    duration = float(source_probe['format']['duration'])
    if (len(videos) != 1 or (videos[0]['width'], videos[0]['height'])
            != (clip['source_width'], clip['source_height']) or not math.isfinite(duration) or duration < 7):
        raise ValueError('Original dimensions/duration differ; stop without substitution')
    import cv2
    import numpy as np
    import PIL
    sys.path.insert(0, str(ROOT))
    from bench.synthetic import overlay
    versions = {'opencv': cv2.__version__, 'numpy': np.__version__, 'pillow': PIL.__version__}
    if versions != context['release']['packages']:
        raise ValueError('Native package versions differ from root pins')
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    argv = commands(source, natural, synthetic, context)
    subprocess.run(argv[0], check=True, timeout=300)
    natural_probe = check_video(natural, context)
    cap = cv2.VideoCapture(str(natural), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2,
                           cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE])
    process = None
    truth, previous, camera = [], None, np.zeros(2, dtype=float)
    try:
        if not cap.isOpened():
            raise RuntimeError('Could not open natural v3 video with two-thread CPU decode')
        with log_path.open('x') as log:
            process = subprocess.Popen(argv[1], stdin=subprocess.PIPE, stderr=log)
            for index in range(150):
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Fixed 2–7s excerpt truncated; stop without substitution')
                gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
                if previous is not None:
                    points = cv2.goodFeaturesToTrack(previous, 100, .02, 8)
                    if points is not None:
                        moved, status, _ = cv2.calcOpticalFlowPyrLK(previous, gray, points, None)
                        valid = status.ravel() == 1
                        if valid.sum() >= 8:
                            motion = np.median((moved - points).reshape(-1, 2)[valid], axis=0)
                            camera += motion * np.array([4., 4.])
                previous = gray
                frame, labels = overlay(frame, index, 30., clip['seed'], camera_offset=tuple(camera))
                for label in labels:
                    quad = np.array(label['quad'])
                    label['box'] = [float(quad[:, 0].min()), float(quad[:, 1].min()),
                                    float(quad[:, 0].max()), float(quad[:, 1].max())]
                truth.append(labels)
                process.stdin.write(frame.tobytes())
            if cap.read()[0]:
                raise RuntimeError('Natural v3 has more than 150 frames')
            process.stdin.close()
            if process.wait(timeout=60):
                raise RuntimeError('Synthetic CPU encoder failed; retained encode log')
    finally:
        cap.release()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    synthetic_probe = check_video(synthetic, context)
    rows = []
    for index, (path, labels) in enumerate(((natural, [[] for _ in range(150)]), (synthetic, truth))):
        validate_truth(labels, clip, bool(index))
        truth_path = path.with_suffix('.truth.json')
        exclusive_write(truth_path, labels)
        rows.append({'clip': clip_id, 'synthetic_variant': bool(index),
                     'source': CACHE + '/' + path.name, 'truth': CACHE + '/' + truth_path.name,
                     'source_sha256': sha256(path), 'truth_sha256': sha256(truth_path)})
    original(clip, base, expected_sha256=clip['source_sha256'])
    if code_identity() != identity or sha256(plan_path) != plan_hash:
        raise ValueError('Preparation source or plan changed during execution')
    exclusive_write(receipt, {'clip': clip, 'inputs': rows, 'source_probe': source_probe,
        'natural_probe': natural_probe, 'synthetic_probe': synthetic_probe, 'commands': argv,
        'code_identity': identity, 'recipe': RECIPE, 'plan_sha256': plan_hash,
        'root_release_sha256': context['release_sha256'], 'queue': context['queue'],
        'tools': context['tools'], 'packages': versions, 'ungraded': True,
        'provenance': context['provenance']})


def verify_inputs(plan, plan_hash, context, *, decode=False):
    rows, receipts = [], {}
    for clip in plan['clips']:
        original(clip, context['cache_root'], expected_sha256=clip['source_sha256'])
        receipt_name = clip['id'] + '.prepared.json'
        path = checked_path(context['cache_root'], receipt_name)
        receipt = json.loads(path.read_text())
        if (receipt['clip'] != clip or receipt['plan_sha256'] != plan_hash
                or receipt['code_identity'] != code_identity() or receipt['recipe'] != RECIPE
                or not is_hash(receipt['root_release_sha256']) or receipt['ungraded'] is not True
                or receipt['queue']['exclusive'] is not True or receipt['queue']['execution_attempt'] != 1
                or receipt['tools'] != context['tools'] or receipt['packages'] != context['release']['packages']):
            raise ValueError('Preparation receipt differs from sealed plan/code/root provenance')
        validate_video(receipt['natural_probe'])
        validate_video(receipt['synthetic_probe'])
        release_name = f"{CACHE}/provenance/root-release.{receipt['root_release_sha256']}.json"
        if (receipt['provenance'].get(release_name) != receipt['root_release_sha256']
                or len(receipt['provenance']) != 2):
            raise ValueError('Preparation lacks archived root release and resource evidence')
        for name, expected in receipt['provenance'].items():
            if not is_hash(expected) or sha256(cache_file(context['cache_root'], name)) != expected:
                raise ValueError('Archived root preparation provenance changed')
            receipts[name] = expected
        released = json.loads(cache_file(context['cache_root'], release_name).read_text())
        resource_name = f"{CACHE}/provenance/resource-check.{released['resource_check_sha256']}.json"
        if (receipt['provenance'].get(resource_name) != released['resource_check_sha256']
                or released['status'] != 'root-authorized-v3-preparation' or released['root_owned'] is not True
                or released['code_identity'] != plan['code_identity'] or released['recipe'] != RECIPE
                or released['queue_sources'] != context['release']['queue_sources']
                or released['tools'] != context['tools']):
            raise ValueError('Archived root code, recipe, queue or tool pins differ')
        if len(receipt['inputs']) != 2:
            raise ValueError('Preparation receipt must contain both variants')
        for index, row in enumerate(receipt['inputs']):
            expected_source = f"{CACHE}/{clip['id']}-{VARIANTS[index]}.mp4"
            if (row['clip'] != clip['id'] or type(row['synthetic_variant']) is not bool
                    or row['synthetic_variant'] != bool(index) or row['source'] != expected_source
                    or row['truth'] != str(PurePosixPath(expected_source).with_suffix('.truth.json'))):
                raise ValueError('Preparation pair identity differs')
            for key, digest in (('source', 'source_sha256'), ('truth', 'truth_sha256')):
                if not is_hash(row[digest]) or sha256(cache_file(context['cache_root'], row[key])) != row[digest]:
                    raise ValueError('Prepared asset changed before freeze')
            validate_truth(json.loads(cache_file(context['cache_root'], row['truth']).read_text()), clip, bool(index))
            if decode:
                check_video(cache_file(context['cache_root'], row['source']), context)
            rows.append(row)
        receipts[CACHE + '/' + receipt_name] = sha256(path)
    return rows, receipts


def manifest_value(plan, plan_hash, rows, receipts):
    selected = selection()
    return {'schema_version': 1, 'dataset_id': DATASET, 'split': 'heldout',
        'status': 'frozen-ungraded', 'benchmark_only': True, 'demo_ready': False,
        'evaluation_marker': CACHE + '/EVALUATION.started.json',
        'evaluation_reservation': {'maximum_evaluations': 1, 'not_before_utc': NOT_BEFORE,
            'evaluation_started': False, 'policy': 'Conductor owns final Monday one-shot; no tuning on v3'},
        'selection_sha256': SELECTION_SHA256, 'metadata_contract_sha256': CONTRACT_SHA256,
        'plan_sha256': plan_hash, 'selection': selected['selection'], 'seed_recipe': selected['seed_recipe'],
        'recipe': selected['recipe'], 'preparation_recipe': RECIPE,
        'natural_truth': '150 empty synthetic-truth arrays; no natural OCR, detection or human preview',
        'clips': plan['clips'], 'inputs': rows, 'receipts': receipts, 'code_identity': plan['code_identity'],
        'commons_metadata': {c['id']: json.loads(checked_path(METADATA, c['license_evidence']['page_extract']).read_text())
                             for c in selected['clips']}, 'nonreuse_sha256': selected['nonreuse_sha256']}


def freeze(plan_path, output, context):
    plan = load_plan(plan_path)
    plan_hash = sha256(plan_path)
    rows, receipts = verify_inputs(plan, plan_hash, context)
    if sha256(plan_path) != plan_hash:
        raise ValueError('Plan changed during freeze')
    exclusive_write(output, manifest_value(plan, plan_hash, rows, receipts))
    print('V3_FROZEN_UNGRADED', sha256(output), flush=True)


def verify(plan_path, manifest_path, context):
    plan = load_plan(plan_path)
    plan_hash, manifest_hash = sha256(plan_path), sha256(manifest_path)
    rows, receipts = verify_inputs(plan, plan_hash, context, decode=True)
    if json.loads(Path(manifest_path).read_text()) != manifest_value(plan, plan_hash, rows, receipts):
        raise ValueError('V3 final manifest differs from sealed six pairs or one-shot reservation')
    if sha256(manifest_path) != manifest_hash or sha256(plan_path) != plan_hash:
        raise ValueError('Manifest or plan changed during verification')
    print('V3_VERIFIED_UNGRADED', manifest_hash, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('download', 'plan', 'prepare', 'freeze', 'verify'))
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--release-sha256', required=True)
    parser.add_argument('--cache-root', type=Path, required=True,
                        help='Explicit root-bound fresh v3 cache, never a v1/v2 cache')
    parser.add_argument('--plan', type=Path, default=METADATA / 'plan.json')
    parser.add_argument('--output', type=Path, default=METADATA / 'manifest.json')
    parser.add_argument('--clip', choices=CLIP_IDS)
    args = parser.parse_args()
    if args.action == 'prepare' and args.clip is None:
        parser.error('prepare requires --clip')
    for path in (args.plan, args.output):
        if path.parent.resolve() != METADATA.resolve() or path.is_symlink():
            parser.error('Plan and final manifest must stay in the v3 metadata directory')
    context = root_context(args)
    if args.action == 'download':
        download_originals(context)
    elif args.action == 'plan':
        make_plan(args.plan, context)
    elif args.action == 'prepare':
        prepare(args.plan, args.clip, context)
    elif args.action == 'freeze':
        freeze(args.plan, args.output, context)
    else:
        verify(args.plan, args.output, context)


if __name__ == '__main__':
    main()
