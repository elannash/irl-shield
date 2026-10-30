# Q2 giant-quad confirmation log

2026-10-30 04:47:20 UTC start. Dedicated clean worktree at exact base
0648e0f64d599b223d101f6643ed7d75a36331e3, prepared branch t3/q2-giants
renamed in place to elannash/q2-giants. Six-hour deadline 10:47:20 UTC.
Only Q2-owned paths may change; no git staging or commits.

Retained evidence opened: Mazatlan natural frame45 pavement. Tiny .95272732
and Small .99783095 area at .3 threshold both hallucinate a giant. Existing
second-lane agreement rejected. Sealed Linux output frame45 is completely
masked while LIVE and covered. See docs/Q2-GIANTS.md for exact paths.

TDD 01 RED: pass-through returns false giant; expected behavioral assertion
fails. TDD 02 GREEN: confirmation removes false giant, retains equal-area text
and ordinary quad; actual Renderer pixels asserted. Logs out/q2/test-01-red.log
and test-02-green.log. 2/24 test invocations spent.

E1 planned: PP crop recognizer confirmation, .5 confidence and .5 giant trigger.
No GPU or Mac OCR started; waiting for common root harness/launch.
No install, model download, external write, or source beyond ownership.

TDD03/04: unavailable confirmation RED, conservative retention+error telemetry
GREEN. TDD05/06: blank crop incorrectly rescued RED; real rectification and
confidence check GREEN. 6/24 invocations, three test methods green.

E1 executed CPU only under canonical SH lock/app slice/nice10/threads2/cv1.
Nine-case artifact out/q2/recognizer-e1-cpu/probe.json read: pass=false.
Pavement hallucinates 11 at .53872 and remains masked. Eight close-up positives
retained. Reject .5 crop-recognizer policy; no corpus quality claim.
No install/download. GPU/Mac remains held for common harness.

E2 CPU direct PP-v5 support: pavement has4.85776% candidate coverage; oblique
plate and number have zero support. E2 rectified fixed640x352 input: pavement
5.00181%; street-oblique and number-front/oblique have zero support. Both
rejected; no support threshold can retain a zero-support readable candidate.
Exact scripts copied to out/q2/, raw JSON and logs read.

Root explicitly steered finish/reject tested arms with null corpus metrics,
no ensembles/higher thresholds and no unsafe all7 run. Common root q-run was
read; E1 CUDA lightweight challenge replicated pavement hallucination11 at
.53872, all8 synthetic positives retained; probe.json pass=false. Receipt
out/q2/recognizer-e1-cuda/probe.json. CUDAExecutionProvider active; no performance
acceptance. Shared lock released on exit. No Mac mirror needed/created.

Full Linux functional gate once:108 main tests(one skip)+3relay+compileall,
exit0, out/q2/test-07-full-functional-gate.log. Test budget8/24 Python suite
invocations spent. Swift/Mac build not run. Generic optional adapter and rejected
E1 implementation remain uncommitted review prototypes, no common integration.
Final source/artifact hashes, metrics=null and cleanup in out/q2/handback.json.
