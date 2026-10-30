"""Privacy boundary checks use wholly invented transcript data."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.session_replay import replay


class SessionReplay(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'private-input.jsonl'
        # Includes shapes that pattern redaction commonly misses. None may propagate.
        self.canaries = ['https://private.invalid/callback?code=CANARY_DEVICE',
                         'sk-CANARY_TOKEN', 'live_CANARY_KEY', 'ownerdata CANARY_CHILD',
                         '123 Willow Canary Lane', '+1 202 555 0199',
                         'canary@example.invalid', '\x1b]52;c;CANARY_CLIPBOARD\x07',
                         '$(touch CANARY_EXECUTED)', 'device code CANARY_CODE',
                         '/home/canary/private', '192.0.2.5', 'phone password CANARY_PHONE']
        text = ' '.join(self.canaries)
        rows = [
            {'timestamp': '2026-10-30T10:00:00-07:00', 'type': 'session_meta',
             'payload': {'id': text, 'cwd': text, 'instructions': text}},
            {'timestamp': '2026-10-30T17:00:01Z', 'type': 'response_item',
             'payload': {'type': 'message', 'role': 'user', 'content': [{'text': text}]}},
            {'timestamp': '2026-10-30T17:00:02Z', 'type': 'response_item',
             'payload': {'type': 'function_call', 'name': text, 'arguments': text}},
            {'timestamp': '2026-10-30T17:00:03Z', 'type': 'response_item',
             'payload': {'type': 'function_call_output', 'output': text}},
            {'timestamp': '2026-10-30T17:00:04Z', 'type': 'response_item',
             'payload': {'type': 'message', 'role': 'assistant', 'content': [{'text': text}]}},
            {'timestamp': '2026-10-30T17:00:04Z', 'type': 'event_msg',
             'payload': {'type': 'agent_message', 'message': text}},
            {'timestamp': '2026-10-30T17:00:05Z', 'type': text, 'payload': text},
        ]
        self.raw = ''.join(json.dumps(row) + '\n' for row in rows).encode()
        self.source.write_bytes(self.raw)

    def extract(self, **kwargs):
        return replay.extract(self.source, self.root / 'bundle', **kwargs)

    def test_raw_bytes_never_reach_any_export_or_terminal_or_prompt(self):
        bundle = self.extract()
        exported = b''.join(p.read_bytes() for p in (self.root / 'bundle').iterdir())
        terminal = io.StringIO()
        replay.play(bundle, terminal, no_wait=True)
        for canary in self.canaries:
            self.assertNotIn(canary.encode(), exported)
            self.assertNotIn(canary, terminal.getvalue())
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(bundle['source_sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual([event['kind'] for event in bundle['events']],
                         ['session', 'user', 'tool-request', 'tool-result', 'assistant'])
        self.assertEqual(bundle['counts'], {'lines': 7, 'selected': 5, 'excluded': 2})
        self.assertIn('REPLAY', terminal.getvalue())
        self.assertIn('2026-10-30T17:00:01.000000Z', terminal.getvalue())

    def test_filters_are_explicit_and_do_not_count_excluded_events(self):
        bundle = self.extract(since='2026-10-30T17:00:02Z', until='2026-10-30T17:00:03Z')
        self.assertEqual([event['line'] for event in bundle['events']], [3, 4])
        self.assertEqual(bundle['counts'], {'lines': 7, 'selected': 2, 'excluded': 5})
        self.assertEqual(bundle['window']['since'], '2026-10-30T17:00:02.000000Z')

    def test_invalid_records_fail_without_echoing_values_or_writing_partial_bundle(self):
        for raw in [b'{CANARY_MALFORMED', json.dumps({'timestamp': 'CANARY_TIMESTAMP',
                     'type': 'response_item', 'payload': {'type': 'message', 'role': 'user'}}).encode(),
                    json.dumps({'timestamp': '0001-01-01T00:00:00+14:00',
                                'type': 'session_meta', 'payload': {}}).encode(),
                    b'[]', b'{"type":"CANARY_UNKNOWN"}\n']:
            with self.subTest(raw_hash=hashlib.sha256(raw).hexdigest()):
                self.source.write_bytes(raw)
                with self.assertRaises(replay.ReplayError) as caught:
                    self.extract()
                self.assertNotIn('CANARY', str(caught.exception))
                self.assertFalse((self.root / 'bundle').exists())

    def test_input_and_output_symlinks_and_overwrites_are_rejected(self):
        link = self.root / 'input-link'
        link.symlink_to(self.source)
        with self.assertRaises(replay.ReplayError):
            replay.extract(link, self.root / 'bundle')
        self.extract()
        before = {p.name: p.read_bytes() for p in (self.root / 'bundle').iterdir()}
        with self.assertRaises(replay.ReplayError):
            self.extract()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'bundle').iterdir()})
        self.assertEqual(os.stat(self.root / 'bundle').st_mode & 0o777, 0o700)
        for path in (self.root / 'bundle').iterdir():
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_tampered_bundle_and_terminal_escape_injection_fail_closed(self):
        self.extract()
        path = self.root / 'bundle/events.json'
        data = json.loads(path.read_text())
        data['events'][0]['kind'] = '\x1b]52;c;CANARY\x07'
        path.write_text(json.dumps(data))
        with self.assertRaises(replay.ReplayError):
            replay.load(self.root / 'bundle')
        stream = io.StringIO()
        with self.assertRaises(replay.ReplayError):
            replay.play(data, stream, no_wait=True)
        self.assertEqual(stream.getvalue(), '')

    def test_annotations_only_accept_fixed_milestones_and_full_commit_ids(self):
        annotations = self.root / 'annotations.json'
        annotations.write_text(json.dumps([{'line': 4, 'milestone': 'tests-passed',
                                           'commit': 'a' * 40}]))
        bundle = self.extract(annotations=annotations)
        event = bundle['events'][3]
        self.assertEqual(event['milestone'], 'tests-passed')
        self.assertEqual(event['commit'], 'a' * 40)
        self.assertEqual(event['annotation_origin'], 'editor-supplied-unverified')
        for invalid in [[{'line': 999, 'milestone': 'tests-passed', 'commit': 'a'*40}],
                        [{'line': 4, 'milestone': 'CANARY_PRIVATE', 'commit': 'a'*40}],
                        [{'line': 4, 'milestone': 'tests-passed', 'commit': 'CANARY_PRIVATE'}]]:
            annotations.write_text(json.dumps(invalid))
            with self.assertRaises(replay.ReplayError) as caught:
                replay.extract(self.source, self.root / 'another', annotations=annotations)
            self.assertNotIn('CANARY', str(caught.exception))
            self.assertFalse((self.root / 'another').exists())

    def test_bad_order_bounds_and_unbounded_records_fail(self):
        with self.assertRaises(replay.ReplayError):
            self.extract(since='2026-10-31T00:00:00Z', until='2026-10-30T00:00:00Z')
        self.source.write_bytes(self.raw + json.dumps({'timestamp': '2020-01-01T00:00:00Z',
                               'type': 'session_meta', 'payload': {}}).encode())
        with self.assertRaises(replay.ReplayError):
            self.extract()
        self.source.write_bytes(b'x' * (replay.MAX_LINE + 1))
        with self.assertRaises(replay.ReplayError):
            self.extract()

    def test_timelapse_uses_real_intervals_and_reports_capped_gaps(self):
        bundle = self.extract()
        stream = io.StringIO()
        waits = []
        replay.play(bundle, stream, speed=2, max_gap=.1, sleep=waits.append)
        self.assertEqual(waits, [.1, .1, .1, .1])
        self.assertIn('Gaps capped', stream.getvalue())
        self.assertIn('speed=2', stream.getvalue())
        with self.assertRaises(replay.ReplayError):
            replay.play(bundle, io.StringIO(), speed=float('nan'))

    def test_cli_failure_never_echoes_private_path_or_content(self):
        path = self.root / 'CANARY_SECRET_FILENAME'
        path.write_text('CANARY_INVALID_JSON')
        run = subprocess.run([sys.executable, '-m', 'tools.session_replay', 'extract',
                              '--input', str(path), '--output', str(self.root / 'bundle')],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertNotIn('CANARY', run.stdout + run.stderr)
        self.assertNotIn('Traceback', run.stderr)
        self.assertFalse((self.root / 'bundle').exists())

    def test_bundle_can_be_loaded_and_replayed_without_source_access(self):
        self.extract()
        self.source.unlink()
        bundle = replay.load(self.root / 'bundle')
        stream = io.StringIO()
        replay.play(bundle, stream, no_wait=True)
        self.assertIn('L000004', stream.getvalue())
        prompt = (self.root / 'bundle/replay-prompt.txt').read_text()
        self.assertIn('Do not write code', prompt)
        self.assertIn('not the original build', prompt)

    def test_rehashed_prompt_cannot_inject_new_content(self):
        self.extract()
        directory = self.root / 'bundle'
        prompt = directory / 'replay-prompt.txt'
        prompt.write_text('CANARY_OWNERDATA')
        path = directory / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['sha256']['replay-prompt.txt'] = hashlib.sha256(prompt.read_bytes()).hexdigest()
        path.write_text(json.dumps(manifest))
        with self.assertRaises(replay.ReplayError):
            replay.load(directory)

    def test_cli_end_to_end_does_not_need_the_original_log_to_play(self):
        output = self.root / 'cli-bundle'
        command = [sys.executable, '-m', 'tools.session_replay']
        run = subprocess.run(command + ['extract', '--input', str(self.source),
                                       '--output', str(output)], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['counts']['selected'], 5)
        self.source.unlink()
        run = subprocess.run(command + ['play', '--bundle', str(output), '--no-wait'],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(run.stdout.splitlines()), 7)
        self.assertIn('STATIC METADATA EXPORT', run.stdout)
        for canary in self.canaries:
            self.assertNotIn(canary, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
