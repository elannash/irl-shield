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


def camera_box(index):
    if type(index) is not int or not 0 <= index < FPS * SECONDS:
        raise ValueError('Camera index outside the single shot')
    progress = index / (FPS * SECONDS - 1)
    # Strictly increasing approach and pan; no modulo, wrap or repeated segment.
    width = 1500 - 240 * progress
    left = 36 + 180 * progress
    top = 40 + 18 * math.sin(progress * math.pi * 3)
    return left, top, left + width, top + width * 9 / 16


def compose():
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


def build(output):
    inherited_exclusive()
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
        scene = compose()
        with av.open(str(video), 'w', format='mp4', options={'movflags': '+faststart'}) as container:
            stream = container.add_stream('h264_nvenc', rate=FPS)
            stream.width, stream.height, stream.pix_fmt = 1280, 720, 'yuv420p'
            stream.codec_context.thread_count = 2
            stream.codec_context.max_b_frames = 0
            stream.codec_context.gop_size = FPS
            stream.time_base = stream.codec_context.time_base = Fraction(1, FPS)
            stream.options = {'preset': 'p4', 'tune': 'ull', 'cq': '18'}
            for index in range(FPS * SECONDS):
                view = scene.resize((1280, 720), Image.Resampling.BICUBIC, box=camera_box(index))
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
                frames.append({'source_index': index, 'pts': str(pts),
                               'pixels_sha256': hashlib.sha256(frame.to_ndarray(format='rgb24').tobytes()).hexdigest()})
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
        (work / 'source.json').write_text(json.dumps(manifest, indent=2) + '\n')
        work.rename(output)
    return output / 'source.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output))


if __name__ == '__main__':
    main()
