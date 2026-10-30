"""One latest-frame handoff: ingest never waits for a destination's native writer."""
import threading
import time

from relay.stream import EgressError, enforce_hold


class EgressWriter:
    """Own Egress on one thread, retaining at most one pending engine result.

    A pending result is replaceable. A failed/slow write discards that slot;
    recovery must wait for a result presented after the writer became available.
    Nothing can retract a frame already handed to the native encoder.

    write() reports destination readiness, independently of slot replacement:
    None until readiness is known, False during recovery, True when healthy.
    """
    capacity = 1

    def __init__(self, output, hold_active):
        self.output, self.hold_active = output, hold_active
        output.hold_active = hold_active
        self.dropped = 0
        self._condition = threading.Condition()
        self._pending = None
        self._ready = None
        self._stopped = False
        self._error = None
        self._cleanup_error = None
        self._fresh_after = 0.
        self.thread = threading.Thread(target=self._run, name='relay-egress-writer')
        self.thread.start()

    def write(self, result, pcm):
        with self._condition:
            if self._error is not None:
                raise self._error
            if self._stopped:
                raise EgressError('egress-closed')
            if result.presented_at < self._fresh_after:
                self.dropped += 1
                return self._ready
            if self._pending is not None:
                self.dropped += 1
            self._pending = (result, pcm)
            self._condition.notify()
            return self._ready

    def raise_if_failed(self):
        """Collect terminal write errors even when shutdown prevents another write."""
        with self._condition:
            if self._error is not None:
                raise self._error

    def _run(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._stopped or self._pending is not None)
                    if self._stopped:
                        return
                    result, pcm = self._pending
                    self._pending = None
                result = enforce_hold(result, self.hold_active())
                began = time.monotonic()
                accepted = self.output.write(result, pcm)
                with self._condition:
                    if accepted is not None:
                        self._ready = accepted
                    if accepted is False or time.monotonic() - began > .25:
                        self._fresh_after = time.monotonic()
                        if self._pending is not None:
                            self.dropped += 1
                            self._pending = None
        except Exception:
            # Surface write errors on the relay loop, never raw upstream text.
            with self._condition:
                self._error = EgressError('egress-writer-failed')
                self._ready = False
        finally:
            try:
                self.output.close()
            except Exception:
                with self._condition:
                    self._cleanup_error = EgressError('egress-writer-cleanup')

    def close(self):
        """Join the writer and report only cleanup failures; write errors stay separate."""
        with self._condition:
            self._stopped = True
            self._pending = None
            self._condition.notify()
        # A write has bounded send/reply/reap deadlines, followed by bounded close.
        self.thread.join(timeout=25)
        if self.thread.is_alive():
            raise EgressError('egress-writer-survived')
        if self._cleanup_error is not None:
            raise self._cleanup_error
