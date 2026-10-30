"""Static split view with an evidence timeline. No cosmetic mask reconstruction."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / 'fixtures/fonts/DejaVuSans-Bold.ttf'
MONO = ROOT / 'fixtures/fonts/DejaVuSansMono-Bold.ttf'
BACKGROUND = '#151719'
TEXT = '#f3f2ee'
MUTED = '#bdc3c8'
MASK = '#8bd5b4'
BACKWARD = '#f2bd69'


class Layout:
    def __init__(self, evidence):
        self.evidence = evidence
        self.font = {n: ImageFont.truetype(str(FONT), n) for n in (16, 20, 26, 32)}
        self.mono = ImageFont.truetype(str(MONO), 16)
        self.receipts = {r['id']: r for r in evidence.sidecar['detections']}
        self.start = evidence.sidecar['capture_origin_monotonic']
        self.times = [t['capture_seconds'] for t in evidence.timeline]
        from fractions import Fraction
        self.frame_duration = 1 / float(Fraction(evidence.provenance['fps']))
        self.end = max(self.times[-1] + self.frame_duration,
                       max((r['completed_at_monotonic']-self.start for r in self.receipts.values()), default=0))
        applied = [t for t in evidence.timeline if t['applied_receipt_ids']]
        self.mask_start = min((t['capture_seconds'] for t in applied), default=None)
        self.confirm = min((self.receipts[r]['completed_at_monotonic']-self.start
                            for t in applied for r in t['applied_receipt_ids']), default=None)

    def compose(self, before, after, current):
        canvas = Image.new('RGB', (1280, 720), BACKGROUND)
        draw = ImageDraw.Draw(canvas)
        test = self.evidence.sidecar['evidence_kind'] == 'synthetic-test'
        mode = self.evidence.sidecar['execution_mode']
        draw.text((28, 16), 'IRL Shield', font=self.font[32], fill=TEXT)
        label = 'SYNTHETIC TEST / OFFLINE' if test else f'RECORDED {mode.upper()} RUN'
        draw.text((430, 29), label, font=self.font[20], fill=BACKWARD if test else TEXT)
        draw.text((28, 70), 'Raw / fictional signs', font=self.font[20], fill=TEXT)
        draw.text((654, 70), 'Shielded / archived output', font=self.font[20], fill=TEXT)
        for pixels, left in ((before, 28), (after, 654)):
            image = Image.fromarray(pixels)
            image.thumbnail((598, 338), Image.Resampling.LANCZOS)
            canvas.paste(image, (left + (598-image.width)//2, 106 + (338-image.height)//2))
        item = self.evidence.timeline[current]
        note = ('Backward-painted frame' if item['backward_receipt_ids'] else
                'Archived protection frame' if item['state'] != 'LIVE' else
                'Archived mask frame' if item['masked'] else 'No archived mask')
        draw.text((28, 458), note, font=self.font[26], fill=BACKWARD if item['backward_receipt_ids'] else TEXT)
        draw.text((28, 495), f"Source frame {item['index']}  |  source PTS {item['source_pts']} s  |  {item['state']}",
                  font=self.mono, fill=MUTED)
        timing = (f'First detector mask: {self.mask_start:.2f}s   |   First applied confirmation: {self.confirm:.2f}s'
                  if self.mask_start is not None else 'No detector mask in this archive')
        draw.text((28, 519), timing, font=self.mono, fill=MUTED)
        left, right = 180, 1252
        def x(seconds):
            return left + (right-left) * seconds / self.end
        draw.text((28, 548), 'Mask frames', font=self.font[16], fill=TEXT)
        draw.text((28, 585), 'Confirmed', font=self.font[16], fill=TEXT)
        for i, frame in enumerate(self.evidence.timeline):
            a = x(frame['capture_seconds'])
            b = x(self.times[i+1] if i+1 < len(self.times) else self.times[i] + self.frame_duration)
            fill = BACKWARD if frame['backward_receipt_ids'] else MASK if frame['masked'] else '#3e444a'
            draw.rectangle((a, 545, max(a, b-2), 572), fill=fill)
        for receipt in self.receipts.values():
            px = x(receipt['completed_at_monotonic']-self.start)
            draw.line((px, 581, px, 609), fill=TEXT, width=2)
        px = x(item['capture_seconds'])
        draw.line((px, 534, px, 616), fill=TEXT, width=2)
        for t in (0, self.end/2, self.end):
            label = f'{t:.2f}s'
            draw.text((min(x(t), 1180), 620), label, font=self.mono, fill=MUTED)
        draw.text((28, 660), 'Amber: earlier than detector source frame. Green: other masks. Ticks: detector completion.',
                  font=self.font[16], fill=MUTED)
        draw.text((28, 690), 'Illustrative receipts. No native performance measured.' if test else
                  'Recorded evidence only. This export does not measure throughput or guarantee privacy.',
                  font=self.font[16], fill=MUTED)
        return canvas
