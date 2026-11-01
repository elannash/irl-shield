# Future work

## Selective text masking, closed for this hackathon

The conductor stopped Lane S after 2 of its 24 allowed units. Selective text
masking is not implemented in the product and is not qualified. The proposed
path is local PP-OCR text recognition followed by a small local classifier,
with a normalized-string decision cache. Digits must always stay hidden before
any LLM call or cache lookup. Uncertain, late or errored decisions must keep
the text hidden.

The standalone synthetic probe used Qwen2.5-0.5B-Instruct GGUF Q8_0 on CPU
with privately pinned `llama-cpp-python` 0.3.16. All 60/60 model responses
were HIDE, including 40/40 generic-text calls: OPEN, CLOSED, WELCOME and
THANK YOU each returned HIDE ten times. Twenty digit-rule decisions bypassed
the model, with zero digit model calls. This showed no useful discrimination.

Call-only timing, excluding OCR, normalization, queueing and relay work:

| Probe condition | Calls | p50 ms | p95 ms | Late at 750 ms |
| --- | ---: | ---: | ---: | ---: |
| Cold KV reset in one resident model | 30 | 972.438903 | 1126.704357 | 30/30 |
| Warm identical-prompt repeat | 30 | 392.707437 | 455.568806 | 0/30 |

Warm repeats were not production cache hits. The cold condition was not a
cold process start. Construction took 675.219806 ms. Process high-water memory
was 801,153,024 bytes, or 764.039 MiB. These are descriptive CPU observations
from a standalone forced/recovered/contended queue execution. They establish
neither GPU latency nor useful area reduction, privacy or native contention
performance. Four new-socket/connect EPERM controls do not establish the
absence of inherited network descriptors or product network isolation.

A future attempt would need few-shot prompting or a larger model, GPU latency
measurements, and native contention evidence. Independent judges on the Mac
must establish recall with every location hidden on real video before any
privacy claim. An optional hosted classifier could later serve streamers who
accept its cost and off-box privacy tradeoff; no hosted classifier is
implemented today. The model cache and venv remain private and gitignored.
The model payload and private runtime are not published or packaged as a
model download.

The private closure, root inspection and independent receipt audit have
SHA-256 seals, respectively:

- `69728ba76a273bc7a2fe152b743afe8ef416ba32780a66daabb11dd91b6dba6c`
- `36daa9ab7411d538077b0e45ccece442fa5de74e182b39ea17a843964bee90af`
- `34d51c533ed8d7676acded4045907addcaabb8fd9b2acd82a12ab26923d2490f`
