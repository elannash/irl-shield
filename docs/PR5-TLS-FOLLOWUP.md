# PR5 RTMPS peer-verification follow-up

The **current runtime route is verified** by a standard-library TLS forwarder.
PyAV writes plain RTMP to `127.0.0.1`; the forwarder verifies the ingest
certificate and hostname using system CAs before forwarding RTMP bytes.
There is no direct unverified RTMPS runtime route or fallback. See
[LIVE-EGRESS.md](LIVE-EGRESS.md) and [RUN.md](RUN.md) for the current interface
and the loopback publication/negative/mutation proofs. Real Twitch ingest
acceptance remains an attended bandwidth-test qualification, not a result of
these local fixtures.

The rest of this document records the **historical direct-PyAV defect** found
at `4f3adbe`, and its diagnostic reproducer. That old route could encrypt
traffic without authenticating the peer, exposing the stream key to an active
MITM. Memory-only storage and bandwidth-test mode did not remove that risk.
The original conductor-approved documentation fallback was superseded by the
verified forwarder. The direct legacy probe below is deliberately a loopback
counterexample and is never used by the runtime.

## Source and installed-library receipts

Observed 2026-10-30 on Linux at project base
`4f3adbec1e628891bb3cfc855c3a617a851425cf`:

- `relay/stream.py:326` opens the network FLV with `av.open(url, 'w', ...)`.
- The installed PyAV 16.0.1 `av/container/output.py:361-379` calls
  `avio_open()` before forwarding container options to `avformat_write_header()`.
  Its primary output open receives no protocol-options dictionary. The compiled
  output extension imports `avio_open@LIBAVFORMAT_62`; `readelf --dyn-syms`
  finds no `avio_open2` import there. The
  [versioned PyAV source](https://github.com/PyAV-Org/PyAV/blob/v16.0.1/av/container/output.py#L361-L379)
  agrees with the installed generated Python source.
- Installed `av/container/core.pyx:282-285` assigns the optional `io_open`
  callback to the format context. It does not replace that direct primary
  `avio_open()` call. The runtime callback control below records zero calls.
- The actual wheel's `av.libs/libavformat-5bf2a196.so.62.3.100` reports FFmpeg
  **8.0**, libavformat **62.3.100**, and `--enable-gnutls`. Its bundled TLS
  backend is `libgnutls-cd598300.so.30.40.3`. Enumeration through exported
  `avio_protocol_get_class()` / `av_opt_next()` gives `tls_verify` default
  **0**, and `ca_file` / `verifyhost` defaults **NULL**. These are observations
  of the loaded wheel, not the system ffmpeg executable. PyAV 16.0.1 does not
  expose `av.protocols_available`.
- [FFmpeg 8.0 `tls.h`](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavformat/tls.h#L75-L96)
  defines those options. Its
  [GnuTLS client](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavformat/tls_gnutls.c#L196-L227)
  checks chain validity and the hostname when verification is enabled. That
  backend capability is confirmed by the native controls below.
- [FFmpeg 8.0 `rtmpproto.c`](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavformat/rtmpproto.c#L2514-L2539)
  constructs the nested TLS URL from hostname and port, omitting the RTMP
  path/query. Although
  [raw TLS URLs accept `verify` and `cafile`](https://github.com/FFmpeg/FFmpeg/blob/n8.0/libavformat/tls.c#L32-L62),
  appending `verify=1` to the RTMPS URL does not configure the nested TLS
  connection. It is not a workaround.

Primary web sources above were accessed 2026-10-30. Installed-source root:
`/home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/lib/python3.11/site-packages/`.
SHA-256 receipts:

| File under that root | SHA-256 |
| --- | --- |
| `av/container/output.py` | `671b13f6e859df9e078228c147b8dd6ac9d88ff1558f7772fcf20754d3941b26` |
| `av/container/output.cpython-311-x86_64-linux-gnu.so` | `00bdbf2b5fd5003f20c40c2ca51f017d0fbfb6425a0c2d811dba0a879aa0e0dc` |
| `av/container/core.pyx` | `fca960c941ae2eb2e4e13d83cfbde28c637fe7cca207cf702f2fd922e02e95fb` |
| `av.libs/libavformat-5bf2a196.so.62.3.100` | `809f38b763f72de884f27b493363ac419d147ddd063d841f67b1351cffeb2cc2` |
| `av.libs/libgnutls-cd598300.so.30.40.3` | `31e889e0ba9ead833b4bc4c0f0b66e172e2ecc479f2fad2240779fade582e810` |

## Loopback evidence

[The standalone probe](../tests/m2/tls_probe.py) generates two independent
self-signed certificates at run time. The peer has a `localhost` DNS SAN.
It runs MediaMTX 1.21.3 with strict RTMPS bound only to `127.0.0.1` and disables
all other servers, including MoQ. Certificates/private keys are synthetic,
temporary, and deleted on completion. Only logs and a JSON receipt remain.

The native controls call the wheel's exported `avio_open2()` with protocol
options and complete the RTMPS open against that same server. Each negative
case changes just the CA file or expected hostname. The PyAV cases use the
same output-open interface as the relay, then encode 61 silent, text-free
64x32 H.264 frames. MediaMTX's publication log independently witnesses actual
RTMP publication; a socket connection or generic open error alone does not
count. The probe is not a privacy/real-video benchmark. It now reruns trusted native
and PyAV controls after their negatives, requires the server to remain alive,
and attributes rejected rows to the wheel’s exact GnuTLS certificate/hostname
verification diagnostics. A timeout or connection error is fixture failure
(exit 2), never a secure pass. Capturing those diagnostics temporarily enables
FFmpeg ERROR logging, then restores the previous setting.

Observed in `final-red/receipt.json`:

| Connection | Peer accepted | Independent publication witness |
| --- | --- | --- |
| Bundled `avio_open2`, trusted CA and matching hostname | yes, return 0 | RTMPS open control only |
| Same call, unrelated CA only | no, return -5 | not applicable |
| Same call, mismatched hostname only | no, return -5 | not applicable |
| PyAV, current relay output options | yes | yes |
| PyAV, `tls_verify=1`, trusted CA, matching hostname | yes | yes |
| PyAV, `tls_verify=1`, unrelated CA | **yes** | **yes** |
| PyAV, `tls_verify=1`, mismatched hostname | **yes** | **yes** |
| PyAV, RTMPS query `verify=1` | **yes** | **yes** |
| PyAV, rejecting custom `io_open` plus unrelated CA | **yes**, callback calls 0 | **yes** |

PyAV also reports the TLS options as unused. Thus backend protocol support
is present and verification works when configured, but the pinned PyAV output
API used by this relay does not deliver that configuration. Merely adding
TLS options to `relay/stream.py` would create a false security claim. A custom
native-I/O wrapper, TLS proxy or toolchain migration is outside this follow-up;
none was introduced.

## Reproduction and result meanings

Run only after coordinating with the root queue; do not interrupt timed jobs.
Use a fresh evidence directory for each invocation. This command uses the
authorized read-only SDK and MediaMTX binary; no install, site-package overlay,
account or secret is required:

```sh
scripts/host-lock shared env \
  XDG_RUNTIME_DIR=/run/user/1000 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus \
  systemd-run --user --scope --quiet --slice=app-t3code-agents.slice \
  nice -n 10 env PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  NUMEXPR_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 OPENCV_FOR_THREADS_NUM=1 \
  timeout --kill-after=5s 30s \
  /home/elan/.t3/worktrees/irl-shield/t3-7cba93a7/.tmp/integration/venv/bin/python \
  tests/m2/tls_probe.py \
  --mediamtx /home/elan/.t3/worktrees/irl-shield/t3-ae860af9/.tmp/tools/mediamtx-v1.21.3/mediamtx \
  --out /tmp/agents/irl-shield/tls-reproduce-red
```

The expected full-probe result on this pin is **exit 1** with
`unverified_publication: true`. This is the security **red**, not a failing
fixture hidden as success. Exit 2 means fixture/control failure and provides
no security conclusion. A timeout likewise provides no conclusion. The script
is deliberately a standalone diagnostic, not a discovered unittest or a new
passing security gate. It does not exercise the relay worker's lifecycle.

For the independent backend **green**, repeat with a fresh `--out` directory
and `--controls-only`. That run exits 0 only after trusted acceptance and both
negative verification controls agree. Its receipt explicitly limits the result
to the backend; it does not establish verified relay egress. Both final runs
recorded `owned_mediamtx_exit: 0` after stopping their own server.

Raw investigation evidence is retained at
`/tmp/agents/irl-shield/pr5-tls-051d7f7d/`: `invocations.jsonl`,
`probe-7.log`, `final-red/{receipt.json,mediamtx.log}`,
`probe-8.log`, `final-controls/{receipt.json,mediamtx.log}`, and
`probe-9.log` (corrected AVOption type decoding and installed hashes).
Earlier attempts and logs remain, including fixture failures: missing user
bus; outdated readiness wording/MoQ default; insufficient media for track
identification; and a query containing slashes that changed the RTMP path
witness. They do not count as security results. The accidental synthetic
MoQ files were moved out of the checkout into `failed-attempt3/`, and that
server exited. No production-source mutation was made, so no restoration
claim is needed. No full host gate, native/performance rerun, detector work,
held-out evaluation, Mac sync or Twitch connection was performed.

The probe adds no runtime dependency or model/data download. It reuses PyAV
16.0.1 (BSD-3-Clause), its existing FFmpeg/GnuTLS/x264 wheel components (see
`relay/requirements.txt` and `bench/PORTABILITY.md` for component licenses),
MediaMTX 1.21.3 (MIT, bundled `LICENSE`), Python's standard library, and installed
OpenSSL 3.5.5 (Apache-2.0; certificate generation only). Generated certificates
and silent black frames are synthetic CC0 test fixtures, with no third-party
logos, readable labels or music; they are not demonstration assets.
