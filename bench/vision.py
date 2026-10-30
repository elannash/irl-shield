"""Bounded, persistent Apple Vision process; exceptions never become empty boxes."""
import json
import struct
import select
import subprocess
from pathlib import Path

import cv2
from bench.independence import candidate_metadata

ROOT = Path(__file__).resolve().parents[1]


class Vision:
    def __init__(self, mode="vision-accurate"):
        self.process = subprocess.Popen([str(ROOT / '.build/vision-bridge'), mode],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.metadata = {**candidate_metadata(mode), "engine": mode, "framework": "macOS Vision", "offline": True,"recognition_languages":["en-US"],"minimum_text_height":.005,"uses_language_correction":False}

    def read(self, frame):
        pixels = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
        h, w = pixels.shape[:2]
        self.process.stdin.write(struct.pack('<III', w, h, pixels.nbytes))
        self.process.stdin.write(pixels.tobytes())
        self.process.stdin.flush()
        if not select.select([self.process.stdout],[],[],30)[0]:
            self.process.kill()
            self.process.wait(timeout=5)
            raise TimeoutError('Vision did not produce a response within30 seconds')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f'Vision bridge exited: {self.process.poll()}')
        return json.loads(line)

    def detect(self, frame):
        return [item['box'] for item in self.read(frame)]

    def detect_quads(self, frame):
        return [item['quad'] for item in self.read(frame)]

    def close(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        self.process.stdout.close()
        self.process.wait(timeout=10)
        if self.process.returncode:
            raise RuntimeError(f'Vision bridge failed: {self.process.returncode}')
