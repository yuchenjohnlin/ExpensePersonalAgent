# Load testing: how much the app takes, and what breaks first

Step 6 of `pm/issues/app-evaluation-observability.md`. Written 2026-10-17. Everything ran on the test stack (`perf/README.md`): nginx + gunicorn (2 workers × 4 threads) + tracing, with k6 on the PC itself. Tools and scripts: `perf/load/` (`perf/load/README.md`).

Evidence labels:
- **Observed**: from k6, Prometheus, nginx or gunicorn.
- **Inferred**: worked out from observed numbers.

---

## 1. What load testing is (and isn't)

*"I think we have done enough testing, because load testing would need to have a lot of data in the dataset right?"*, then: *"I misunderstood load testing, in that case I think we can do load testing."*

**Load testing is about how many requests arrive at once, not how much data there is.** It sends many requests in parallel, more than one person ever would, and watches when responses slow down or fail. (Lots of data is a separate test: "how do queries behave with a million rows?")

The usual kinds:

| Kind | What it does | Here |
|---|---|---|
| **Smoke** | A tiny run to check the script and the setup work | 1 user, 10 s |
| **Load** | Expected traffic; are the targets met? | — |
| **Stress / ramp** | Keep increasing until something gives; find the limit and what breaks | Test 1 |
| **Spike** | A sudden burst | — |
| **Soak** | Hours at normal load; finds slow leaks | — |
| **Scenario** | A realistic mix of different requests at once | Test 2 |

**Open vs closed models.** Many tools run N virtual users who each send a request, wait for the answer, then send the next: a **closed** model. If the server slows down, the users slow down too, and the tool quietly sends less traffic. Real users don't wait for each other, so test 1 uses an **open** model (k6's `arrival-rate` executors): requests start on a schedule whether or not earlier ones finished. When the server can't keep up, k6 reports **dropped iterations**: requests it should have started but had no free virtual user for. (The smoke test shows the closed model's effect: one user looping without pauses already made 194 requests/s.)

## 2. The setup

```
PC
├─ k6 (container)  ──HTTP──▶  <lan-ip>:8081  nginx ─▶ gunicorn (2 × 4 threads) ─▶ Django ─▶ MySQL
│      │                                                                         └─▶ fake vLLM (test 2)
│      └─ its own measurements ──remote write──▶ Prometheus (lgtm) ◀── Django's metrics
```

- **k6 runs on the PC**, so Wi-Fi isn't in the numbers (`learning/baseline-dev-measurements.md` §1.5). It calls the PC's own address, not Docker's `http://web`: Django rejects `web` as a host name (400, `ALLOWED_HOSTS`), which the smoke test caught.
- **A test session made inside the test database** (`perf/load/make_session.py`), so no password is involved. It's sent explicitly with every request: putting it in k6's cookie jar worked for virtual users but not in `setup()`, which runs on its own (test 2's first attempt crashed on that).
- **A fake vLLM for test 2** (`perf/load/fake_vllm.py`, `compose.load.yaml`): answers like vLLM after a fixed 60 s, with a real saved reply. The app runs its whole reading path while the GPU stays untouched, so runs repeat exactly. The reply is receipt content, so it lives outside git (`~/CojiDaily-testdata/fake-vllm-reply.json`), and only one-photo receipts are read, because the reply names photo positions and the app rejects positions a receipt doesn't have.
- **Each browsing request is tagged with its 30 s stage,** so the summary reports every load level separately. (k6's own percentiles in Prometheus are cumulative from the start of a test, so a tag per stage is the clean way to split them.)

Two mistakes on the way, kept here because they're typical:
- The first run of test 1 was cut off by my output filter (`head`) after 29 s. **The k6 container kept running in the background**, so the second run overlapped it and the first numbers were mixed. Check that nothing else is generating load before trusting a result.
- k6's own p95 in Prometheus looked like it was slowly "recovering". It's cumulative, not per window.

## 3. Test 1: browsing, rate climbing to 400 requests/s (observed)

Read-only pages in a fixed mix (calendar month/day, review month/pending, reading results, receipts page, session), rate rising every 30 s. Run with `perf/load/run.sh browse`.

| Stage | Rate (requests/s) | Requests | p95 |
|---|---|---|---|
| 1 | 10 → 25 | 524 | 11 ms |
| 2 | 25 → 50 | 1,125 | 10 ms |
| 3 | 50 → 100 | 2,250 | 12 ms |
| 4 | 100 → 200 | 4,500 | 13 ms |
| 5 | 200 → 300 | 7,500 | **32 ms** |
| 6 | 300 → 400 | 10,278 of 10,500 (222 dropped) | **670 ms** |

Zero errors in 26,177 requests. **The knee is between 300 and 400 requests/s:** flat up to ~300, then latency climbs steeply and k6 can't start requests on time.

### What ran out (observed)

Holding a fixed rate for 40 s and sampling each container's CPU (100% = one core; the PC has 12):

| | 150 req/s | 350 req/s |
|---|---|---|
| backend (gunicorn) | 74% | **264%** |
| MySQL | 11% | 34% |
| nginx | 1.5% | 3.9% |
| lgtm (observability) | 2.9% | 5.9% |
| Latency | median 4.8 ms, p95 14 ms | median 95 ms, p95 226 ms, 33 dropped |

**The two gunicorn workers' CPU is the bottleneck**: each worker is one Python process held to about one core by the GIL. (Slightly over 200% because threads also run while MySQL's C library and the exporter work.) MySQL, nginx and the observability stack have plenty to spare. This is the USE method from the first discussion: Utilization of each resource, find the one that's full.

### One change: 4 workers (observed)

`GUNICORN_CMD_ARGS="--workers 4"`, nothing else:

| Held for 40 s | 2 workers | 4 workers |
|---|---|---|
| 350 req/s | p95 226 ms, 33 dropped | p95 **20 ms**, 0 dropped |
| 500 req/s | (past the limit) | p95 **46 ms**, 0 dropped, backend CPU 467% |

Roughly double the capacity, as predicted from "CPU-bound, one core per worker". **`gunicorn.conf.py` stays at 2 workers:** one person makes a few requests per second, ~100× below the limit, and every worker is another full copy of Django in memory. It's a known lever now, with numbers behind it.

## 4. Test 2: readings and browsing at the same time (observed)

Browsing at a steady 20 requests/s for 6 minutes. Meanwhile 4, then 8, then 12 virtual users each start a reading, wait for it (60 s, the fake vLLM), and start the next, for 2 minutes per level. gunicorn has **8 threads**. Run with `perf/load/run.sh fake-on 60`, then `perf/load/run.sh readings`.

| Stages | Readings running | Browsing p95 | Browsing median |
|---|---|---|---|
| 1–4 | 4 | **10–13 ms** | 5 ms |
| 5 | 4 → 8 | **47.8 s** | 9 ms (the stage started before the 8th reading) |
| 6 | 8 | **34.9 s** | 33 s |
| 7 | 8 | **51.1 s** | 7.5 s |
| 9 | 12 | **58.5 s** | 45.8 s |
| 11 | 12 | **59.6 s** | 51.2 s |
| 8, 10, 12 | 8 / 12 | — | no browsing request could even start |

- **Readings:** 39 succeeded; median 60 s (the fake's delay), max **1 min 57 s**: the slowest reading waited almost a minute for a thread before its own 60 s began.
- **Browsing:** 3,191 requests were **dropped** (k6 hit its 200-user cap: all 200 were stuck waiting), and 9 hit k6's 60 s timeout. k6 warned: `Insufficient VUs, reached 200 active VUs`.
- **gunicorn:** no worker timeouts, no restarts. Nothing crashed; everything just waited.

**What happened (inferred from the numbers):** with 4 readings, 4 threads were free and browsing didn't notice. With 8 readings, **all 8 threads sat waiting on the model**, and every calendar or review request queued until a reading finished. **The whole app froze for up to a minute at a time, while the server was doing almost nothing.** That's what the very first discussion predicted ("sync Django runs out of threads while waiting"), now measured.

### The queue the app can't see (observed)

| Where | Says, for the same calendar request |
|---|---|
| nginx | `rt=48.252 urt=48.251`: waited 48 s for gunicorn |
| Django's own metric (`http.server.request.duration`) | p95 for that route during the test: **24.6 ms** |
| Requests inside Django at once (`http.server.active_requests`) | max **10** |

The 48 s were spent in **gunicorn's queue**: the connection was accepted at the socket but no thread was free to run Django. Django's middleware, its metrics and its traces only start when a thread picks the request up. **An app-level dashboard would have shown a healthy, fast service throughout.** Only the layers in front of it (nginx's log, k6, the browser) saw the wait. Production systems measure this "request queue time" explicitly, typically with a timestamp header set by the proxy (e.g. `X-Request-Start`) that the app compares with when it starts. That's a candidate addition to the observability stack.

## 5. What the two tests say

1. **For normal pages, capacity is ~300 requests/s with 2 workers, ~500+ with 4.** That's two orders of magnitude above one person's use. Not a problem to solve now.
2. **Readings are the real limit: 8 at once freeze the app.** More threads only move the cliff (16 threads → 16 readings), at the cost of memory, and don't fix the design. The fix is **not holding a request open while the model works**: start the reading as a background job, answer immediately ("reading started"), and let the browser ask "done yet?" or be notified. That's the design planned for the FastAPI port, and it's now motivated by a measurement, not just a guess.
3. **Measure from the outside too.** The worst problem in test 2 was invisible to the app's own observability.

## 6. Rerun it

On the PC, with the test stack up (`OTEL=1 PROD=1 perf/test-stack.sh reset`):

```sh
perf/load/run.sh browse              # test 1
perf/load/run.sh fake-on 60          # readings use the fake vLLM (60 s each)
perf/load/run.sh readings            # test 2 (~7 min)
perf/load/run.sh fake-off            # back to the real Spark
```

k6's numbers also land in Prometheus (`k6_*` metrics, label `testid`), next to the server's.

Things to keep in mind:
- **Readings write to the test database** (39 new readings in test 2). That's harmless in the copy, and `perf/test-stack.sh reset` restores it.
- **Tracing is on at 100% during these tests.** Every request makes spans. Production systems usually sample (keep e.g. 10%). The capacity numbers include that overhead.
- **One run each.** A second run would show how much they vary.
