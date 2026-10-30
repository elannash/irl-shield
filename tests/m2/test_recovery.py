"""Real CPU RTMP recovery at Egress and RelaySession's public interfaces.

Existing test_stream covers fatal handshake shutdown, not a steady-state mux
stall or the presenter batch/hold contract during a replacement connection.
These regressions use no production reset hooks and no detector-quality claims.
"""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

from relay.bridge import NoOpDetector
from relay.live import RelaySession
from relay.stream import Egress, EgressError, _OPERATIONS
from shield.engine import MaskingEngine
from shield.lanes import DetectorLane
from shield.types import Frame
from recovery_fixture import FaultProxy, LocalSink, NoOpMotion, PAUSE_SECONDS, child_pids, engine, record, safe_failure


def rows(directory, name):
    path = directory / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@unittest.skipUnless(sys.platform == 'linux', 'Native MediaMTX fixture requires Linux')
class EgressRecovery(unittest.TestCase):
    def assert_recovery(self, directory, output, proxy):
        events = rows(directory, 'egress-recovery.jsonl')
        self.assertGreaterEqual(len(events), 1, 'the injected fault must cause a recovery')
        event = events[0]
        self.assertEqual(event['code'], 'egress-write-timeout')
        self.assertEqual(event['operation'], 'network-mux')
        self.assertTrue(event['old_worker_reaped'])
        self.assertEqual((event['generation'], event['next_generation']), (1, 2))
        for previous, startup in zip(events, events[1:]):
            self.assertEqual(startup['generation'], previous['next_generation'])
            self.assertEqual(startup['next_generation'], startup['generation'] + 1)
            self.assertEqual(startup['code'], 'egress-startup-timeout')
            self.assertIn(startup['operation'], ('unknown', 'encoder-startup'))
            self.assertTrue(startup['old_worker_reaped'])
        self.assertGreaterEqual(proxy.connections, 2, 'a replacement network writer must really connect')
        manifest = rows(directory, 'frames.jsonl')
        self.assertEqual(len(manifest), output.count, 'count must reflect real writer ACKs')
        indices = [row['index'] for row in manifest]
        self.assertEqual(indices, sorted(set(indices)), 'failed/precomputed frames must not replay')
        self.assertTrue(all(fault['failed_index'] not in indices for fault in events))
        old = [row for row in manifest if row['egress_generation'] == 1]
        final_generation = events[-1]['next_generation']
        new = [row for row in manifest if row['egress_generation'] == final_generation]
        self.assertTrue(all(row['egress_generation'] in (1, final_generation) for row in manifest),
                        'a failed startup generation must not acknowledge any media')
        self.assertGreaterEqual(len(old), 90)
        self.assertGreaterEqual(len(new), 20)
        self.assertGreater(new[0]['index'], old[-1]['index'] + 1, 'recovery must leave honest index gaps')
        for row in manifest:
            self.assertAlmostEqual(row['pts'], row['index'] / 30)
            self.assertEqual(row['audio_pts_samples'], row['index'] * 1600)
        self.assertTrue((directory / 'encoded.flv').stat().st_size > 0)
        self.assertTrue((directory / f'encoded-g{final_generation:04d}.flv').stat().st_size > 0)
        self.assertEqual(output.recovery_count, len(events))
        return old, new, event

    def control_condition(self, directory, mode):
        before = child_pids()
        source = engine()
        origin = time.monotonic()
        source.hold(True, source='local', reason='synthetic hold')
        source.submit(Frame(0, 0., np.zeros((32, 64, 3), np.uint8)), now=origin)
        sink = output = None
        failure = None
        owned = set()
        receipt = {'mode': mode, 'failure': None}
        try:
            sink = LocalSink(mode)
            output = Egress(sink.proxy.url, directory, width=64, height=32, encoder='libx264')
            owned.update(child_pids() - before)
            # The source/presentation clock advances independently of ACK count.
            # Completion is ACK-driven; this is only a cleanup fuse. Recovery
            # may correctly retry a slow worker startup on a busy host.
            deadline = time.monotonic() + 90
            armed = False
            while time.monotonic() < deadline:
                for frame in source.poll(now=time.monotonic()):
                    sound = np.random.default_rng(frame.index).integers(-1000, 1000, 1600, dtype=np.int16)
                    if output.write(frame, sound) is False:
                        if 'old_archive_sha256' not in receipt:
                            receipt['old_archive_sha256'] = hashlib.sha256((directory / 'encoded.flv').read_bytes()).hexdigest()
                        break  # No remainder of the old poll batch may reach the new writer.
                owned.update(child_pids() - before)
                if not armed and output.count >= 90:
                    receipt['warmup_acks'] = output.count
                    sink.proxy.requested.set()
                    self.assertTrue(sink.proxy.injected.wait(30), 'fixture-control-injection-not-reached')
                    armed = True
                if mode == 'full' and output.count >= 300:
                    break
                if (mode == 'fragmented' and output.recovery_events
                        and output.generation == output.recovery_events[-1]['next_generation']):
                    manifest = rows(directory, 'frames.jsonl')
                    if sum(row['egress_generation'] == output.generation for row in manifest) >= 20:
                        break
                time.sleep(.002)
        except EgressError as error:
            failure = safe_failure(error, output)
        finally:
            if sink is not None and sink.proxy.injected.is_set():
                sink.proxy.completed.wait(PAUSE_SECONDS + 30)
            if output is not None:
                try:
                    output.close()
                except EgressError as error:
                    receipt['close_failure'] = safe_failure(error, output)
            source.close()
            if sink is not None:
                receipt.update(injected=sink.proxy.injected.is_set(),
                               pause_completed=sink.proxy.completed.is_set(),
                               injected_at=sink.proxy.injected_at, finished_at=sink.proxy.finished_at,
                               connections=sink.proxy.connections, forwarded_bytes=sink.proxy.forwarded_bytes,
                               proxy_error=sink.proxy.error_code, ports=sink.ports + [sink.proxy.port])
                sink.close()
                receipt.update(server_pid=sink.pid, server_exit=sink.server.process.returncode,
                               proxy_stopped=not sink.proxy.thread.is_alive())
            receipt.update(failure=failure, acknowledged=output.count if output else 0,
                           owned_worker_pids=sorted(owned), surviving_workers=sorted(child_pids() - before),
                           worker_pids_gone=all(not Path(f'/proc/{pid}').exists() for pid in owned),
                           egress_recoveries=list(output.recovery_events) if output else [],
                           worker_reaped=output._worker_reaped if output else None)
        diagnostic = record(self, {'control_condition': receipt}, sink.secrets if sink else ())
        self.assertEqual(receipt['surviving_workers'], [], diagnostic)
        self.assertTrue(receipt['worker_pids_gone'], diagnostic)
        return receipt, sink, output

    def test_fragmented_proxy_retirement_keeps_fault_duration_and_reaps_controls(self):
        stopped = threading.Event()
        server_error = []
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(.1)

        def serve():
            try:
                while not stopped.is_set():
                    try:
                        peer, _ = listener.accept()
                        break
                    except socket.timeout:
                        continue
                else:
                    return
                with peer:
                    peer.settimeout(.1)
                    # MessageGate passes the RTMP server handshake through.
                    # No real encoder or authenticated application is needed
                    # to exercise retirement of the proxy's own two threads.
                    peer.sendall(bytes(3073))
                    while not stopped.is_set():
                        try:
                            if not peer.recv(64):
                                break
                        except socket.timeout:
                            continue
            except OSError as error:
                server_error.append(type(error).__name__)

        server = threading.Thread(target=serve, name='recovery-fixture-retirement-peer')
        server.start()
        proxy = None
        try:
            proxy = FaultProxy(f'rtmp://127.0.0.1:{listener.getsockname()[1]}/shielded', 'fragmented')
            with socket.create_connection(('127.0.0.1', proxy.port), timeout=2) as client:
                remaining = 3073
                while remaining:
                    data = client.recv(remaining)
                    self.assertTrue(data, 'fixture-handshake-closed')
                    remaining -= len(data)
                proxy.requested.set()
                self.assertTrue(proxy.injected.wait(30), 'fixture-injection-not-reached')
                self.assertEqual(client.recv(1), b'\x02')
                client.shutdown(socket.SHUT_RDWR)
            # Retire the peer well before the six-second fragment timer ends.
            self.assertTrue(proxy.completed.wait(PAUSE_SECONDS + 3), 'fixture-pause-not-completed')
            for worker in proxy.threads:
                worker.join(timeout=PAUSE_SECONDS + 3)
        finally:
            if proxy is not None:
                proxy.close()
            stopped.set()
            server.join(timeout=3)
            listener.close()
        receipt = {'proxy_error': proxy.error_code, 'pause_seconds': proxy.finished_at - proxy.injected_at,
                   'connections': proxy.connections, 'server_error': server_error,
                   'server_stopped': not server.is_alive(),
                   'controls_stopped': not any(worker.is_alive() for worker in proxy.threads)}
        diagnostic = record(self, receipt)
        self.assertFalse(server.is_alive(), diagnostic)
        self.assertEqual(server_error, [], diagnostic)
        self.assertTrue(receipt['controls_stopped'], diagnostic)
        self.assertGreaterEqual(receipt['pause_seconds'], PAUSE_SECONDS, diagnostic)
        self.assertIsNone(receipt['proxy_error'], diagnostic)

    def test_full_ping_is_valid_then_fragmented_ping_recovers_without_replay(self):
        with tempfile.TemporaryDirectory(prefix='m2-recovery-control-') as temporary:
            directory = Path(temporary)
            full, full_sink, _ = self.control_condition(directory / 'full', 'full')
            fragmented, fragment_sink, output = self.control_condition(directory / 'fragmented', 'fragmented')
            secrets = full_sink.secrets + fragment_sink.secrets
            report = {'baseline': full, 'fragmented': fragmented}
            diagnostic = record(self, report, secrets)
            self.assertIsNone(full['failure'], diagnostic)
            self.assertGreaterEqual(full['acknowledged'], 300, diagnostic)
            self.assertTrue(full['injected'] and full['pause_completed'], diagnostic)
            self.assertIsNone(full['proxy_error'], diagnostic)
            self.assertTrue(fragmented['injected'] and fragmented['pause_completed'], diagnostic)
            self.assertIsNone(fragmented['proxy_error'], diagnostic)
            self.assertGreaterEqual(fragmented['finished_at'] - fragmented['injected_at'], 6)
            # On legacy code this is the intended red: network-mux times out
            # with active_frame_index > completed_frame_index after real warmup.
            self.assertIsNone(fragmented['failure'], diagnostic)
            self.assertNotIn('close_failure', fragmented, diagnostic)
            self.assert_recovery(directory / 'fragmented', output, fragment_sink.proxy)
            self.assertEqual(hashlib.sha256((directory / 'fragmented/encoded.flv').read_bytes()).hexdigest(),
                             fragmented['old_archive_sha256'], 'the old archive must never be overwritten')

    def test_saturated_media_pause_preserves_moderator_hold_across_reconnect(self):
        before = child_pids()
        owned = set()
        stopped = threading.Event()
        observation = {'inflight': None, 'last_ack': time.monotonic(),
                       'controller_error': None, 'producer_error': None}
        observation_lock = threading.Lock()
        receipt = {'failure': None}
        coverage_reasons = {}
        worker_waits = {}
        self.assertIn('network-mux', _OPERATIONS)
        network_mux_phase = _OPERATIONS.index('network-mux')
        # This fixture must retain real input while a slow consumer catches up;
        # otherwise buffer eviction turns the intended LIVE mux load into slates.
        source = MaskingEngine({name: DetectorLane(name, NoOpDetector(), 120)
                                for name in ('fast', 'accurate')},
                               {'fps': 30, 'delay_seconds': 1., 'max_buffer_frames': 480},
                               motion=NoOpMotion())
        sink = output = controller = producer = session = None
        with tempfile.TemporaryDirectory(prefix='m2-recovery-backpressure-') as temporary:
            directory = Path(temporary)
            try:
                sink = LocalSink('backpressure')
                output = Egress(sink.proxy.url, directory, width=640, height=360, encoder='libx264')
                owned.update(child_pids() - before)

                def write(frame, pcm):
                    coverage_reasons[frame.coverage.reason] = coverage_reasons.get(frame.coverage.reason, 0) + 1
                    with observation_lock:
                        observation['inflight'] = (time.monotonic(), frame.index, frame.state,
                                                   frame.presented_at, frame.coverage.reason)
                    accepted = output.write(frame, pcm)
                    if accepted is False and 'old_archive_sha256' not in receipt:
                        receipt['old_archive_sha256'] = hashlib.sha256((directory / 'encoded.flv').read_bytes()).hexdigest()
                    with observation_lock:
                        observation['last_ack'] = time.monotonic()
                        observation['inflight'] = None
                    return accepted

                start = time.monotonic()
                receipt['source_started_at'] = start
                session = RelaySession(source, write, width=640, height=360, start=start)

                def moderate_when_blocked():
                    warmup_deadline = time.monotonic() + 60
                    while not sink.proxy.requested.is_set():
                        if stopped.wait(.02):
                            return
                        if time.monotonic() > warmup_deadline:
                            observation['controller_error'] = 'fixture-warmup-not-reached'
                            return
                    deadline = time.monotonic() + 60
                    while not stopped.is_set() and time.monotonic() < deadline:
                        now = time.monotonic()
                        with observation_lock:
                            inflight = observation['inflight']
                            last_ack = observation['last_ack']
                            stale = now - last_ack
                        worker = output._process
                        progress = tuple(output._progress)
                        phase, operation_start, active_index, completed_index = progress
                        network_blocked = (int(phase) == network_mux_phase and inflight is not None
                                           and int(active_index) == inflight[1]
                                           and completed_index < active_index
                                           and now - operation_start > .25)
                        if network_blocked:
                            # Phase age alone can describe a descheduled runnable
                            # encoder. Require an actual native wait before arming
                            # the pause; an idle IPC reader is not a blocked mux.
                            try:
                                proc = Path(f'/proc/{worker.pid}')
                                state = (proc / 'stat').read_text().rsplit(') ', 1)[1].split()[0]
                                wait = (proc / 'wchan').read_text().strip()
                                worker_waits[state + ':' + wait] = worker_waits.get(state + ':' + wait, 0) + 1
                                network_blocked = (state == 'S' and wait not in
                                                   ('0', 'unix_stream_data_wait', 'futex_do_wait',
                                                    'hrtimer_nanosleep'))
                            except (OSError, ValueError, IndexError):
                                network_blocked = False

                        if network_blocked:
                            # The sampled write can finish while /proc is read.
                            # Never arm a later writer using that old frame.
                            with observation_lock:
                                network_blocked = (output._process is worker
                                                   and observation['inflight'] == inflight
                                                   and observation['last_ack'] == last_ack
                                                   and tuple(output._progress) == progress)
                            now = time.monotonic()
                            stale = now - last_ack

                        if network_blocked and now - inflight[0] > .25 and stale > .2:
                            receipt.update(blocked_seconds_before_pause=now - inflight[0],
                                           blocked_index=inflight[1], blocked_state=inflight[2],
                                           blocked_batch_presented_at=inflight[3],
                                           blocked_coverage_reason=inflight[4],
                                           worker_phase=int(phase),
                                           worker_operation_started_at=float(operation_start),
                                           worker_active_index=int(active_index),
                                           worker_completed_index=int(completed_index),
                                           worker_wait=wait)
                            sink.proxy.pause.set()
                            if not sink.proxy.pause_started.wait(30):
                                observation['controller_error'] = 'fixture-pause-not-reached'
                                return
                            # Public M3 control changes while the OLD write is
                            # still blocked, before its five-second timeout.
                            session.control.hold(True, source='twitch-chat', reason='moderator')
                            receipt['hold_at'] = time.monotonic()
                            return
                        stopped.wait(.005)
                    observation['controller_error'] = 'fixture-kernel-buffers-not-saturated'

                controller = threading.Thread(target=moderate_when_blocked, name='recovery-fixture-moderator')
                controller.start()
                def produce_video():
                    random = np.random.default_rng(68)
                    last_source_index = -1
                    try:
                        while not stopped.is_set():
                            now = time.monotonic()
                            due_index = int((now - start) * 30)
                            for source_index in range(last_source_index + 1, due_index + 1):
                                pixels = random.integers(0, 256, (360, 640, 3), dtype=np.uint8)
                                session.video(source_index / 30, pixels, generation=1, now=now)
                                last_source_index = source_index
                            stopped.wait(.002)
                    except Exception as error:
                        observation['producer_error'] = type(error).__name__

                # Ingest must keep running during a blocked write; otherwise the
                # fixture itself creates ingest-gap slates and drains the mux.
                # RelaySession supplies real silence for this video-only source.
                producer = threading.Thread(target=produce_video, name='recovery-fixture-video')
                producer.start()
                # Completion is driven by final-generation ACKs; this is a cancellation fuse.
                deadline = start + 150
                while time.monotonic() < deadline:
                    session.tick(time.monotonic())
                    owned.update(child_pids() - before)
                    if output.count >= 90 and not sink.proxy.requested.is_set():
                        receipt['warmup_acks'] = output.count
                        receipt['prelude_started_at'] = time.monotonic()
                        sink.proxy.requested.set()
                    if observation['controller_error'] or observation['producer_error']:
                        break
                    if (output.recovery_events
                            and output.generation == output.recovery_events[-1]['next_generation']):
                        manifest = rows(directory, 'frames.jsonl')
                        if sum(row['egress_generation'] == output.generation for row in manifest) >= 20:
                            break
                    time.sleep(.002)
            except EgressError as error:
                receipt['failure'] = safe_failure(error, output)
            finally:
                stopped.set()
                if producer is not None:
                    producer.join(timeout=30)
                if controller is not None:
                    controller.join(timeout=30)
                if sink is not None and sink.proxy.pause_started.is_set():
                    sink.proxy.completed.wait(PAUSE_SECONDS + 30)
                if output is not None:
                    try:
                        output.close()
                    except EgressError as error:
                        receipt['close_failure'] = safe_failure(error, output)
                source.close()
                if sink is not None:
                    receipt.update(pause_reached=sink.proxy.pause_started.is_set(),
                                   pause_at=sink.proxy.pause_at, finished_at=sink.proxy.finished_at,
                                   pause_completed=sink.proxy.completed.is_set(),
                                   connections=sink.proxy.connections, receive_buffer=sink.proxy.receive_buffer,
                                   forwarded_bytes=sink.proxy.forwarded_bytes, proxy_error=sink.proxy.error_code,
                                   ports=sink.ports + [sink.proxy.port])
                    sink.close()
                    receipt.update(server_pid=sink.pid, server_exit=sink.server.process.returncode)
                receipt.update(coverage_reasons=coverage_reasons, worker_waits=worker_waits,
                               buffer_evictions=source.buffer_evictions, late_ingest=source.late_ingest,
                               source_last_index=source.last_index, presenter_next_index=source.next_index,
                               controller_error=observation['controller_error'],
                               producer_error=observation['producer_error'],
                               producer_stopped=producer is not None and not producer.is_alive(),
                               controller_stopped=controller is not None and not controller.is_alive(),
                               acknowledged=output.count if output else 0,
                               owned_worker_pids=sorted(owned), surviving_workers=sorted(child_pids() - before),
                               worker_pids_gone=all(not Path(f'/proc/{pid}').exists() for pid in owned),
                               egress_recoveries=list(output.recovery_events) if output else [],
                               egress_error_code=output.error_code if output else None,
                               egress_error_details=output.error_details if output else None,
                               worker_reaped=output._worker_reaped if output else None)
            manifest = rows(directory, 'frames.jsonl')
            receipt['live_baseline_rows'] = sum(row['state'] == 'LIVE' and not row['slate'] for row in manifest)
            diagnostic = record(self, receipt, sink.secrets if sink else ())
            self.assertEqual(receipt['surviving_workers'], [], diagnostic)
            self.assertTrue(receipt['worker_pids_gone'] and receipt['controller_stopped']
                            and receipt['producer_stopped'], diagnostic)
            self.assertIsNone(receipt['producer_error'], diagnostic)
            self.assertIsNone(receipt['controller_error'], diagnostic)
            self.assertTrue(receipt['pause_reached'] and receipt['pause_completed'], diagnostic)
            self.assertGreater(receipt['blocked_seconds_before_pause'], .2)
            self.assertLess(receipt['pause_at'] - receipt['prelude_started_at'], 60,
                            'buffer saturation must finish within the fixture cancellation fuse')
            self.assertLess(receipt['pause_at'] - receipt['source_started_at'], 120,
                            'warmup and saturation must finish within their combined cancellation fuses')
            self.assertGreaterEqual(receipt['finished_at'] - receipt['pause_at'], 6)
            self.assertGreaterEqual(receipt['hold_at'], receipt['pause_at'])
            self.assertGreater(receipt['live_baseline_rows'], 0, diagnostic)
            self.assertEqual(receipt['blocked_state'], 'LIVE', diagnostic)
            self.assertIsNone(receipt['proxy_error'], diagnostic)
            self.assertIsNone(receipt['failure'], diagnostic)
            self.assertNotIn('close_failure', receipt, diagnostic)
            _, new, event = self.assert_recovery(directory, output, sink.proxy)
            self.assertEqual(hashlib.sha256((directory / 'encoded.flv').read_bytes()).hexdigest(),
                             receipt['old_archive_sha256'], 'the old archive must never be overwritten')
            self.assertEqual(event['failed_index'], receipt['blocked_index'])
            self.assertEqual(receipt['worker_phase'], network_mux_phase, diagnostic)
            self.assertLess(receipt['hold_at'], event['at_monotonic'],
                            'the moderator hold must be applied before the old write times out')
            self.assertTrue(all(row['state'] == 'HOLD' and row['protected'] and row['slate'] for row in new))
            black = hashlib.sha256(np.zeros((360, 640, 3), np.uint8).tobytes()).hexdigest()
            self.assertTrue(all(row['pixels_sha256'] == black for row in new))
            self.assertTrue(all(row['presented_at'] > receipt['hold_at'] for row in new),
                            'a result computed before the hold must never cross the new connection')
            self.assertFalse(any(row['presented_at'] == receipt['blocked_batch_presented_at'] for row in new))
            self.assertEqual(session.stats['sessions'], 1, 'egress recovery must not restart ingest')
            self.assertEqual(session.stats['disconnections'], 0)
            self.assertGreater(session.stats['egress_interruptions'], 0)
            self.assertEqual(source.control.state, 'HOLD', 'recovery must retain the moderator hold')
            session.control.hold(False, source='twitch-chat', reason='moderator')
            self.assertNotEqual(source.control.state, 'HOLD', 'the temporary egress hold must release after ready ACK')

    def test_destination_blip_recovers_but_persistent_refusal_gets_at_least_sixty_seconds(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from relay.mediamtx import MediaMTX
        from relay.security import Credentials, RelayAddress
        from test_stream import presented

        for recover in (False, True):
            with self.subTest(recover=recover), tempfile.TemporaryDirectory() as temporary:
                before = child_pids()
                # Reserve all listener ports, with the RTMP port genuinely refusing.
                sockets = [socket.socket(socket.AF_INET, kind) for kind in
                           (socket.SOCK_STREAM, socket.SOCK_DGRAM, socket.SOCK_STREAM)]
                for reserved in sockets:
                    reserved.bind(('127.0.0.1', 0))
                address = RelayAddress('127.0.0.1', *(r.getsockname()[1] for r in sockets))
                phone, internal = Credentials.generate(), Credentials.generate()
                clock = SimpleNamespace(now=1000.)
                output = server = None
                terminal = None
                recovered_at = None
                try:
                    # Only the parent's scheduling clock is controlled. Spawned
                    # encoders, refused TCP and MediaMTX are actual transports.
                    with patch('relay.stream.time', SimpleNamespace(monotonic=lambda: clock.now)):
                        output = Egress(address.rtmp('shielded', internal), Path(temporary),
                                        width=64, height=32, encoder='libx264')
                        for index in range(1000):
                            clock.now = 1000. + index / 10
                            if recover and clock.now >= 1010. and server is None:
                                for reserved in sockets:
                                    reserved.close()
                                server = MediaMTX(address, phone, internal).__enter__()
                            frame = presented(index)
                            frame.presented_at = clock.now
                            try:
                                accepted = output.write(frame, np.zeros(1600, np.int16))
                            except EgressError as error:
                                terminal = (error.code, clock.now - 1000.)
                                break
                            if recover and server is not None and accepted is True:
                                recovered_at = clock.now - 1000.
                                break
                        if recover:
                            self.assertIsNone(terminal, 'a ten-second outage must not terminate the relay')
                            self.assertIsNotNone(recovered_at, 'fresh output must resume after the destination returns')
                            self.assertGreaterEqual(recovered_at, 10.)
                            self.assertLess(recovered_at, 30.)
                        else:
                            self.assertIsNotNone(terminal)
                            self.assertEqual(terminal[0], 'egress-recovery-limit')
                            self.assertGreaterEqual(terminal[1], 60., 'a persistent outage gets a full time budget')
                            self.assertLess(terminal[1], 75.)
                            self.assertGreaterEqual(output.recovery_count, 5)
                        events = list(output.recovery_events)
                        gaps = [b['at_monotonic'] - a['at_monotonic'] for a, b in zip(events, events[1:])]
                        if not recover:
                            self.assertGreater(max(gaps), 4., 'retry delay must grow instead of spinning')
                        record(self, {'recover': recover, 'terminal': terminal, 'recovered_at': recovered_at,
                                      'events': events}, (phone.password, internal.password))
                finally:
                    if output is not None:
                        output.close()
                    if server is not None:
                        server.__exit__(None, None, None)
                    for reserved in sockets:
                        reserved.close()
                self.assertEqual(child_pids(), before)


if __name__ == '__main__':
    unittest.main()
