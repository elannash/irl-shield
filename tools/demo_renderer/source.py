"""Build one 210-second fictional street shot; root schedules execution."""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .lease import ROOT, inherited_exclusive

PLATE_SHA256 = 'ddfaf72b9a30f6ffe78a1c52df357b5f9bd2e809cea95080cebbb244ee3dbcb6'
FONT_SHA256 = 'e1d733afbbfce842a1b43dced0c9885a76a4e67290dc7e690c4e9b76ebfc7d23'
FPS, SECONDS = 30, 210


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def camera_box(index, *, scene_plan=None):
    if type(index) is not int or not 0 <= index < FPS * SECONDS:
        raise ValueError('Camera index outside the single shot')
    progress = index / (FPS * SECONDS - 1)
    if scene_plan is not None:
        camera = scene_plan['camera']
        left, top, width = (camera[key][0] + (camera[key][1] - camera[key][0]) * progress
                            for key in ('left', 'top', 'width'))
        if camera.get('opening_scan_frames'):
            scan = min(index / camera['opening_scan_frames'], 1)
            top = camera['top'][1] + (camera['top'][0] - camera['top'][1]) * (1-scan)**2
        return left, top, left + width, top + width * 9 / 16
    # Strictly increasing approach and pan; no modulo, wrap or repeated segment.
    width = 1500 - 240 * progress
    left = 36 + 180 * progress
    top = 40 + 18 * math.sin(progress * math.pi * 3)
    return left, top, left + width, top + width * 9 / 16


def load_scene_plan(path, *, asset_base):
    """Validate the opt-in, relative-path recipe before any native imports."""
    path = Path(path).resolve()
    asset_base = Path(asset_base).resolve()
    if not asset_base.is_dir():
        raise ValueError('W8b cached asset directory missing')
    plan = json.loads(path.read_text())
    if (plan.get('schema') != 'irl-shield-w8b-mosaic-v1'
            or plan.get('fps') != FPS or plan.get('seconds') != SECONDS
            or plan.get('output') != [1280, 720] or plan.get('canvas') != [5760, 1024]):
        raise ValueError('W8b scene plan format mismatch')
    assets = plan.get('assets', [])
    if not isinstance(assets, list) or len(assets) != 4:
        raise ValueError('W8b requires four ordered assets')
    for index, (asset, identity) in enumerate(zip(assets, ('shops', 'homes', 'car', 'corner'))):
        filename = asset.get('file')
        if (not isinstance(filename, str) or Path(filename).name != filename
                or not filename.endswith('.png') or '\\' in filename):
            raise ValueError('W8b asset path must be a sibling PNG')
        target = asset_base / filename
        if target.is_symlink() or target.resolve().parent != asset_base:
            raise ValueError('W8b asset path escapes cache')
        if (asset.get('id') != identity or asset.get('origin') != [index * 1408, 0]
                or asset.get('size') != [1536, 1024]):
            raise ValueError('W8b asset geometry mismatch')
        if sha256(target) != asset.get('sha256'):
            raise ValueError('W8b asset seal mismatch')
        with target.open('rb') as source:
            header = source.read(24)
        if (header[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
                or int.from_bytes(header[16:20], 'big') != 1536
                or int.from_bytes(header[20:24], 'big') != 1024):
            raise ValueError('W8b PNG dimensions mismatch')
    camera = plan.get('camera', {})
    for key in ('left', 'top', 'width'):
        values = camera.get(key)
        if (not isinstance(values, list) or len(values) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
            raise ValueError('W8b camera endpoints invalid')
    if (not camera['left'][0] < camera['left'][1]
            or not 1280 <= camera['width'][1] < camera['width'][0]):
        raise ValueError('W8b camera must pan and approach without upsampling')
    scan_frames = camera.get('opening_scan_frames')
    if (type(scan_frames) is not int or not 0 < scan_frames < FPS * SECONDS
            or camera['top'][0] < camera['top'][1]):
        raise ValueError('W8b opening scan must move upward and settle within the shot')
    # Top and height both decrease; their endpoint bounds also contain the opening scan.
    for index in (0, FPS * SECONDS - 1):
        left, top, right, bottom = camera_box(index, scene_plan=plan)
        if not (0 <= left < right <= 5760 and 0 <= top < bottom <= 1024):
            raise ValueError('W8b camera outside canvas')
    joins = plan.get('joins', [])
    if not isinstance(joins, list) or len(joins) != 3:
        raise ValueError('W8b requires three static joins')
    for index, join in enumerate(joins):
        band = join.get('feather')
        overlap_left = (index + 1) * 1408
        if (join.get('pair') != [assets[index]['id'], assets[index + 1]['id']]
                or not isinstance(band, list) or len(band) != 2
                or any(type(value) is not int for value in band)
                or not overlap_left <= band[0] < band[1] <= overlap_left + 128
                or band[1] - band[0] > 4):
            raise ValueError('W8b static feather outside overlap or too wide')
    poles = plan.get('foreground_poles', [])
    if not isinstance(poles, list) or len(poles) != 3:
        raise ValueError('W8b requires three declared foreground pole cutouts')
    for number, pole in enumerate(poles):
        if (pole.get('join') != number or pole.get('source_asset') != 'corner'
                or pole.get('source_box') != [504, 240, 560, 1024]
                or pole.get('opaque_rows') != [[240,512,550], [420,514,551], [600,519,550],
                                                [820,523,552], [1024,527,553]]):
            raise ValueError('W8b pole must use the inspected shaft crop and manual matte')
        translation = pole.get('translation')
        if (not isinstance(translation, list) or len(translation) != 2
                or any(type(value) is not int for value in translation)):
            raise ValueError('W8b pole translation invalid')
        dx, dy = translation
        start, stop = joins[number]['feather']
        for _, body_left, body_right in pole['opaque_rows']:
            if not body_left + dx + 6 <= start < stop <= body_right + dx - 6:
                raise ValueError('W8b pole does not cover join with sampling margin')
        for index in range(FPS * SECONDS):
            left, top, right, bottom = camera_box(index, scene_plan=plan)
            if right > dx+512 and left < dx+553 and not 240+dy <= top < bottom <= 1024+dy:
                raise ValueError('W8b pole ends inside a visible viewport')
    samples = plan.get('raw_samples', [])
    if (not isinstance(samples, list) or not 12 <= len(samples) <= 48
            or any(type(index) is not int or not 0 <= index < FPS * SECONDS for index in samples)
            or samples != sorted(set(samples)) or samples[0] != 0 or samples[-1] != FPS * SECONDS - 1):
        raise ValueError('W8b raw sample roster invalid')
    per_plate = plan.get('per_plate_samples', {})
    if not isinstance(per_plate, dict) or set(per_plate) != {asset['id'] for asset in assets}:
        raise ValueError('W8b per-plate sample roster invalid')
    for roster in per_plate.values():
        if (not isinstance(roster, list) or len(roster) != 12
                or any(type(index) is not int or index not in samples for index in roster)
                or roster != sorted(set(roster))):
            raise ValueError('W8b per-plate sample roster invalid')
    if sorted({index for roster in per_plate.values() for index in roster}) != samples:
        raise ValueError('W8b raw and per-plate sample rosters disagree')
    for key in ('readability_regions', 'raw_detail_regions'):
        regions = plan.get(key)
        if not isinstance(regions, list) or not regions:
            raise ValueError('W8b reference regions missing')
        for region in regions:
            bounds = region.get('bounds')
            if (region.get('asset') not in per_plate or not isinstance(bounds, list) or len(bounds) != 4
                    or any(type(value) is not int for value in bounds)
                    or not (0 <= bounds[0] < bounds[2] <= 1536 and 0 <= bounds[1] < bounds[3] <= 1024)):
                raise ValueError('W8b reference region outside plate')
    for filename, key in (('ATTRIBUTION.json', 'attribution_sha256'), ('prompts.json', 'prompts_sha256')):
        target = path.parent / filename
        if target.is_symlink() or sha256(target) != plan.get(key):
            raise ValueError('W8b provenance seal mismatch')
    return {**plan, '_directory': path.parent, '_asset_base': asset_base, '_sha256': sha256(path)}


def frame_geometry(index, plan):
    """Declared source geometry only; no detector, mask or native identity attestation."""
    left, top, right, bottom = camera_box(index, scene_plan=plan)
    scale = 1280 / (right - left)
    assets = []
    references = []
    for number, asset in enumerate(plan['assets']):
        x, y = asset['origin']
        assets.append({'id': asset['id'], 'origin': asset['origin'], 'size': asset['size'],
                       'plate_to_output': [[scale, 0, (x-left)*scale], [0, scale, (y-top)*scale]],
                       'output_to_plate': [[1/scale, 0, left-x], [0, 1/scale, top-y]],
                       'entry_feather': None if number == 0 else plan['joins'][number-1]['feather'],
                       'exit_feather': None if number == 3 else plan['joins'][number]['feather']})
        for kind, regions in (('planned-label', plan['readability_regions']),
                              ('unplanned-detail', plan['raw_detail_regions'])):
            for region in regions:
                if region['asset'] != asset['id']:
                    continue
                a, b, c, d = region['bounds']
                quad = [[a, b], [c, b], [c, d], [a, d]]
                references.append({'asset': asset['id'], 'kind': kind,
                    'name': region.get('label', region.get('reason')),
                    'reference_quad': quad,
                    'output_quad': [[(x+u-left)*scale, (y+v-top)*scale] for u, v in quad],
                    'declared_rectangle_inside_crop': left <= x+a < x+c <= right and top <= y+b < y+d <= bottom,
                    'actual_mask_coverage': None})
    return {'evidence_scope': 'declared geometry lookup; manual approximate ROIs, not native/source-model attestation',
            'coordinate_convention': 'pixel edges; pixel centers at (x+0.5,y+0.5); bicubic sampling',
            'crop': [left, top, right, bottom], 'output': [1280, 720],
            'assets': assets, 'references': references,
            'foreground_layers': [{**pole,
                'source_asset_sha256': plan['assets'][3]['sha256'],
                'source_to_output': [[scale, 0, (pole['translation'][0]-left)*scale],
                                     [0, scale, (pole['translation'][1]-top)*scale]],
                'evidence_scope': 'manual matte and source-pixel translation; visual acceptance pending'}
                for pole in plan['foreground_poles']]}


def compose_mosaic(plan):
    """One static spatial blend; every output frame samples the same atlas."""
    from PIL import Image
    scene = Image.new('RGB', tuple(plan['canvas']))
    for index, asset in enumerate(plan['assets']):
        path = plan['_asset_base'] / asset['file']
        if sha256(path) != asset['sha256']:
            raise ValueError('W8b asset seal mismatch')
        with Image.open(path) as image:
            if image.format != 'PNG' or image.size != (1536, 1024) or image.n_frames != 1:
                raise ValueError('W8b decoded plate format mismatch')
            plate = image.convert('RGB')
        x, y = asset['origin']
        if index == 0:
            scene.paste(plate, (x, y))
            continue
        start, stop = plan['joins'][index - 1]['feather']
        # The mask has no time coordinate. It cannot switch scenes mid-shot.
        row = bytes(0 if x + local <= start else 255 if x + local >= stop
                    else round(255 * (x + local - start) / (stop - start))
                    for local in range(1536))
        mask = Image.frombytes('L', (1536, 1024), row * 1024)
        scene.paste(plate, (x, y), mask)
    with Image.open(plan['_asset_base'] / plan['assets'][3]['file']) as image:
        pole_source = image.convert('RGB')
    for pole in plan['foreground_poles']:
        a, b, c, d = pole['source_box']
        rows = pole['opaque_rows']
        alpha = bytearray()
        segment = 0
        for y in range(b, d):
            while y >= rows[segment+1][0] and segment < len(rows)-2:
                segment += 1
            y0, left0, right0 = rows[segment]
            y1, left1, right1 = rows[segment+1]
            fraction = (y-y0)/(y1-y0)
            left_edge = left0 + (left1-left0)*fraction
            right_edge = right0 + (right1-right0)*fraction
            alpha.extend(255 if left_edge <= x < right_edge else 0 for x in range(a, c))
        mask = Image.frombytes('L', (c-a, d-b), bytes(alpha))
        dx, dy = pole['translation']
        scene.paste(pole_source.crop((a,b,c,d)), (a+dx,b+dy), mask)
    return scene


def compose(*, scene_plan=None):
    if scene_plan is not None:
        return compose_mosaic(scene_plan)
    from PIL import Image, ImageDraw, ImageFont
    plate = ROOT / 'fixtures/demo-renderer/fictional-street.png'
    font = ROOT / 'fixtures/fonts/DejaVuSans-Bold.ttf'
    if sha256(plate) != PLATE_SHA256 or sha256(font) != FONT_SHA256:
        raise ValueError('W8 asset seal mismatch')
    with Image.open(plate) as image:
        scene = image.convert('RGB').resize((1920, 1080), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(scene)
    face = ImageFont.truetype(str(font), 52)
    for box, words in (((220, 445, 670, 605), ('Cedar Vale', '142')),
                       ((1060, 330, 1510, 490), ('Elder Lane', '731'))):
        draw.rectangle(box, fill='#183c34', outline='#f3f2ee', width=4)
        for line, word in enumerate(words):
            draw.text((box[0] + 18, box[1] + 12 + line * 66), word, font=face, fill='#f3f2ee')
    return scene


def build(output, *, scene_plan=None, asset_base=None):
    inherited_exclusive()
    if (scene_plan is None) != (asset_base is None):
        raise ValueError('W8b requires paired --scene-plan and --asset-base')
    plan = load_scene_plan(scene_plan, asset_base=asset_base) if scene_plan is not None else None
    if plan is not None and sha256(ROOT / 'fixtures/fonts/DejaVuSans-Bold.ttf') != FONT_SHA256:
        raise ValueError('W8 control font seal mismatch')
    import av
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Use a fresh W8 output directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='w8-source-', dir=output.parent) as temporary:
        work = Path(temporary)
        video = work / 'source.mp4'
        scene = compose(scene_plan=plan)
        with av.open(str(video), 'w', format='mp4', options={'movflags': '+faststart'}) as container:
            stream = container.add_stream('h264_nvenc', rate=FPS)
            stream.width, stream.height, stream.pix_fmt = 1280, 720, 'yuv420p'
            stream.codec_context.thread_count = 2
            stream.codec_context.max_b_frames = 0
            stream.codec_context.gop_size = FPS
            stream.time_base = stream.codec_context.time_base = Fraction(1, FPS)
            stream.options = {'preset': 'p4', 'tune': 'ull', 'cq': '18'}
            for index in range(FPS * SECONDS):
                view = scene.resize((1280, 720), Image.Resampling.BICUBIC,
                                    box=camera_box(index, scene_plan=plan))
                frame = av.VideoFrame.from_ndarray(np.asarray(view), format='rgb24')
                frame.pts, frame.time_base = index, Fraction(1, FPS)
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        frames = []
        with av.open(str(video)) as container:
            if len(container.streams.video) != 1 or container.streams.audio:
                raise ValueError('W8 source must be video only')
            container.streams.video[0].codec_context.thread_count = 2
            for index, frame in enumerate(container.decode(video=0)):
                pts = frame.pts * frame.time_base
                if pts != Fraction(index, FPS):
                    raise ValueError('W8 source decoded clock mismatch')
                row = {'source_index': index, 'pts': str(pts),
                       'pixels_sha256': hashlib.sha256(frame.to_ndarray(format='rgb24').tobytes()).hexdigest()}
                if plan is not None:
                    row['declared_geometry'] = frame_geometry(index, plan)
                frames.append(row)
        if len(frames) != FPS * SECONDS or len({row['pixels_sha256'] for row in frames}) != len(frames):
            raise ValueError('W8 source missing or repeated decoded frame')
        (work / 'controls').mkdir()
        controls = {}
        for name, text in (('positive', 'Cedar 142'), ('blank', ''), ('unknown', 'Unlisted 946')):
            control = Image.new('RGB', (1280, 720), '#f3f2ee')
            ImageDraw.Draw(control).text((100, 250), text,
                font=ImageFont.truetype(str(ROOT / 'fixtures/fonts/DejaVuSans-Bold.ttf'), 72), fill='#183c34')
            path = work / 'controls' / (name + '.png')
            control.save(path)
            controls[name] = {'file': str(path.relative_to(work)), 'sha256': sha256(path), 'expected_text': text}
        manifest = {'schema': 'irl-shield-w8-source-v1', 'status': 'NOT CLEARED',
                    'kind': 'generated-still-with-camera-motion', 'fps': FPS,
                    'seconds': SECONDS, 'video': 'source.mp4', 'video_sha256': sha256(video),
                    'frames': frames, 'controls': controls,
                    'plate_sha256': PLATE_SHA256, 'font_sha256': FONT_SHA256,
                    'builder_sha256': sha256(Path(__file__)),
                    'attribution_sha256': sha256(ROOT / 'fixtures/demo-renderer/ATTRIBUTION.json'),
                    'brand_clearance': None, 'human_logo_eye': None,
                    'native_evidence': None, 'audio': 'none'}
        if plan is not None:
            manifest.pop('plate_sha256')
            manifest['kind'] = 'generated-stills-with-continuous-mosaic-camera'
            manifest['attribution_sha256'] = sha256(plan['_directory'] / 'ATTRIBUTION.json')
            manifest['composition'] = {
                'scene_plan_sha256': plan['_sha256'],
                'recipe': {key: value for key, value in plan.items() if not key.startswith('_')},
                'atlas_rgb_sha256': hashlib.sha256(scene.tobytes()).hexdigest(),
                'visual_join_acceptance': None,
                'note': 'Static pole-shaft cutouts cover join bands geometrically; photographic and native acceptance pending'}
        (work / 'source.json').write_text(json.dumps(manifest, indent=2) + '\n')
        work.rename(output)
    return output / 'source.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scene-plan', type=Path, help='Explicit W8b recipe; omitted keeps the legacy source')
    parser.add_argument('--asset-base', type=Path, help='Explicit directory of sealed cached W8b PNGs')
    args = parser.parse_args()
    print(build(args.output, scene_plan=args.scene_plan, asset_base=args.asset_base))


if __name__ == '__main__':
    main()
