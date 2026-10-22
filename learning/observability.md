# Observability: what to measure, and the tools that measure it

The concepts behind add-observability.md, which records *how* this project added observability one layer at a time (4a–4e). This note explains *what* the pieces are and why they fit together the way they do. Written 2026-10-20 from questions asked while rereading the steps in two sessions: "Server performance measurement setup" and "Nginx reverse proxy concepts".

Evidence labels:
- **Observed**: printed or measured on this project's machines.
- **Inferred / general**: worked out from observed output, or general knowledge not checked here.

The questions this note answers, in the asker's words:
- *"What is a span? Why don't we need to change any of the code? … What does auto-instrumentation mean?"*
- *"If opentelemetry doesn't change any of our python code, where are these environment variables loaded?"*
- *"I don't understand how the sql parts are done bypassing django."*
- *"What is opentelemetry usually used to measure? Is there a standard on what we measure on a software system? … When do people look at traces?"*
- *"Why can't we store the trace, metric and logs together? … What are the logs here? Isn't it just the traces?"*
- *"Does opentelemetry return json?" / "What is the difference between otlp with http/json?"*
- *"In our docker compose file … don't I need to set the ports? … I don't see where the database file is … they need health check?"*
- And from planning this note: Grafana and the stores "aren't built for each other"; how they're set up in production and in AWS; what `traceparent` provides.

---

## 1. What to measure

### 1.1 Not only time: the three signals

*"I guess the only things we could measure is probably time."* Time is one of several things. Observability data comes in three kinds, called **signals**:

| Signal | Records | Example from this app (observed) |
|---|---|---|
| **Traces** | What happened in **one** request, step by step: names, durations, details, errors | The 2-minute reading of receipt #47 split into photo prep (345 + 315 ms), the model call (118.9 s) and saving (2.6 ms) |
| **Metrics** | **Numbers aggregated over time**: counts, rates, durations as histograms, sizes, gauges | The thumbnail route sent 15.56 of 15.67 MB; p95 of each route; 4,096 output tokens on a failed reading |
| **Logs** | **Events the code writes**, as text, with a timestamp | `Reading 63 of receipt 46 by vllm: failed truncated in 157.7 s` |

A fourth signal, **profiles** (which functions burn CPU), is being added to OpenTelemetry. The `lgtm` image already contains a profile store (Pyroscope), unused here.

Beyond time, the numbers people record:
- **Counts and rates:** requests per second, readings per hour.
- **Errors:** share of 5xx responses, failed readings, exceptions.
- **Sizes:** response bytes (the thumbnails), upload sizes, queue lengths.
- **Saturation:** active requests, busy threads, database connections, CPU, memory. The load test found gunicorn's CPU at 264% this way.
- **Business numbers:** tokens used, receipts read, money posted.
- **The user's view (browser):** **Web Vitals**.
  - **LCP:** when the largest thing appeared.
  - **INP:** how long from a click until the screen updates; good ≤ 200 ms, poor > 500 ms.
  - **CLS:** how much the layout jumps.
  - **FCP:** first content drawn.
  - **TTFB:** first byte from the server.

### 1.2 Is there a standard?

Two kinds:

**What to measure:** well-known checklists rather than a formal standard.
- **RED**, for anything that serves requests: **R**ate, **E**rrors, **D**uration, per route.
- **USE**, for every resource (CPU, memory, threads, connections): **U**tilization, **S**aturation (how much is waiting), **E**rrors.
- **The four golden signals** (Google SRE): latency, traffic, errors, saturation. Roughly RED plus saturation.
- **SLIs and SLOs:** pick the few numbers that mean "the user is fine" (SLIs, e.g. "p95 of the calendar"), then set a target for each (SLOs, e.g. "under 300 ms"). That's step 1 of `pm/issues/app-evaluation-observability.md`.

**How to name it:** OpenTelemetry's **semantic conventions**, standard names for metrics and attributes: `http.server.request.duration`, `http.route`, `http.response.status_code`, `db.statement`, `gen_ai.usage.output_tokens`. Because Django's and FastAPI's instrumentations both use them, one Grafana query works for both backends.

### 1.3 Measure where the user is

A measurement only sees what happens where it runs. One thumbnail request, seen by each layer (observed, `add-observability.md` 4b–4c):

| Layer | Said |
|---|---|
| Django's span (backend trace) | **3 ms**, success |
| nginx's log | `rt=1.227 urt=0.006`: 1.2 s total, 6 ms in Django |
| The browser | **6,988 ms**: 6,302 ms waiting for one of 6 connections, 619 ms downloading |

The slow part happened **after** Django was done, between the server and the browser. A backend-only setup reports a healthy service while the user waits seconds. So measure at the user's end too (browser spans, Web Vitals), not only where your code runs.

The same lesson came back in the load test: a request waited **48 s in gunicorn's queue** while Django's own metric said 24.6 ms, because Django's instrumentation only starts once a thread picks the request up (`learning/load-testing.md`).

### 1.4 Debugging, and when people look at traces

*"I don't think it's be used to debug code functionality. But maybe traces?"*

Observability doesn't replace tests or a debugger. But traces do help with **correctness**, especially in production, where you can't attach a debugger:
- **Which path the code took and where it failed.** The truncated reading showed as a red `chat` span with `finish_reasons: [length]` and `output_tokens: 4096`: the cause, not just "it failed".
- **What it called and how often.** 50 SQL spans where 3 were expected is the classic "N+1 queries" bug, visible at a glance.
- **Which service broke**, when a request crosses browser → nginx → Django → Spark.

When people open traces:
1. **During an incident:** an alert fires on a metric. People open example traces of the bad requests to see *where*, then those traces' logs to see *why*.
2. **For one user's complaint:** find that request's trace by time, user or request ID.
3. **For performance work:** which step dominates (the model: 99.4% of a reading).
4. **After a deploy:** compare the same route before and after.
5. **To learn a system:** traces drawn as a service map show what actually calls what.

The usual order is **metrics → traces → logs**: wide and cheap first, then narrow and detailed.

---

## 2. The pieces, and why they're separate

### 2.1 The map

```
                 PRODUCE (inside each program)                  ROUTE                 STORE                    LOOK
┌──────────────────────────────┐
│ Python app                   │
│  OpenTelemetry API + SDK     │──┐
│  + instrumentations          │  │
└──────────────────────────────┘  │ OTLP     ┌─────────────────────────┐      ┌──────────────┐
┌──────────────────────────────┐  │ :4317 /  │ OpenTelemetry Collector │─────▶│ Tempo        │ traces ──┐
│ Another service (any language│──┼─:4318───▶│  receivers              │      └──────────────┘          │
│  with an OpenTelemetry SDK)  │  │          │  processors (batch,     │      ┌──────────────┐          │  ┌──────────┐
└──────────────────────────────┘  │          │   filter, sample)       │─────▶│ Prometheus   │ metrics ─┼─▶│ Grafana  │
┌──────────────────────────────┐  │          │  exporters (one per     │      └──────────────┘          │  └──────────┘
│ Browser (web SDK)            │──┘          │   destination)          │      ┌──────────────┐          │
└──────────────────────────────┘             └─────────────────────────┘─────▶│ Loki         │ logs ────┘
                                                                              └──────────────┘
```

(Redrawn from the "typical OpenTelemetry setup" diagram in "Nginx reverse proxy concepts".) In CojiDaily, the Collector, Tempo, Prometheus, Loki and Grafana all run inside **one** container, `grafana/otel-lgtm` (§4.4).

### 2.2 What each piece is

| Piece | What it is | Where it runs |
|---|---|---|
| **OpenTelemetry (OTel)** | A vendor-neutral **standard plus libraries** for *producing* telemetry: an API your code calls, an SDK that makes it real, instrumentation plug-ins for libraries, exporters, and a protocol (**OTLP**) | Inside each program |
| **OpenTelemetry Collector** | A separate program that **receives, processes and forwards** telemetry. Part of the OpenTelemetry project, but it can also speak dozens of other formats | Its own service |
| **Tempo** | A **trace store** (Grafana Labs): keeps traces, finds them by ID or by TraceQL search | Its own service |
| **Prometheus** | A **metrics store**, a time-series database: keeps numbers over time, answers PromQL, evaluates alert rules | Its own service |
| **Loki** | A **log store** (Grafana Labs): keeps log lines with labels, answers LogQL | Its own service |
| **Grafana** | A **UI and query layer**: dashboards, Explore, alerts. Stores no telemetry itself | Its own service |

Two spellings to keep apart: **OTLP** (OpenTelemetry Protocol) vs **OLTP** (online transaction processing, a database term).

### 2.3 Not built for each other

*"They can actually come from different sources and opentelemetry just happens to be one of them."* That's the right picture. These tools grew separately, and OpenTelemetry later standardised the *producing* side (general history, from memory):

| Year | What appeared |
|---|---|
| 2012 | **Prometheus** (SoundCloud): metrics, with its own client libraries and a *pull* model (it fetches `/metrics` pages). **Zipkin** (Twitter): traces |
| 2014 | **Grafana**: dashboards over many databases |
| 2015–2017 | **Jaeger** (Uber): traces. Two competing app-side standards: **OpenTracing** and **OpenCensus** |
| 2018 | **Loki**: logs |
| 2019 | **OpenTelemetry** = OpenTracing + OpenCensus merged: one API, SDK and protocol for all signals |
| 2020 | **Tempo**: traces |
| since | The stores added **OTLP input**; Prometheus can now accept OTLP pushes, which is how this project's metrics get in |

Each store accepts many sources, not only OpenTelemetry:
- **Prometheus** scrapes `/metrics` endpoints from databases, `node_exporter` (machine stats), Kubernetes, nginx exporters… and accepts remote writes. k6 wrote its load-test metrics there directly (`learning/load-testing.md`).
- **Loki** takes logs from agents that tail files and container output (Promtail, Grafana Alloy, Fluent Bit), not only OTLP.
- **Tempo** accepts Jaeger and Zipkin formats as well as OTLP.
- **The Collector** has receivers for many formats (Prometheus scraping, Jaeger, Kafka, host metrics, Docker stats), processors (filter, sample, redact, add attributes) and exporters to almost any vendor. It's a general telemetry router, not just an OTLP relay.

The practical consequence: **decide what you want to answer first** (one request in detail → traces; trends and alerts → metrics; what the code said → logs), then pick the stores and wire Grafana to them.

### 2.4 Why three stores instead of one database

*"Why can't we store the trace, metric and logs together?"* Because the three kinds of data have different shapes and are asked different questions:

| | Shape | Typical question | Built for it |
|---|---|---|---|
| **Traces** | Trees of spans, one per request; huge volume, lots of detail | "Show me request X", "requests where `chat` took > 60 s" | Tempo: cheap bulk storage, fast lookup by trace ID |
| **Metrics** | Just numbers per time step, e.g. "requests so far = 412" every 10 s per route | "p95 per route over the last hour", "requests/s" | Prometheus: math over time series |
| **Logs** | Text lines with labels | "lines containing `truncated` from the backend" | Loki: search by labels and text |

Single databases that hold all three do exist (Elasticsearch, some ClickHouse-based tools); it's a design choice. Grafana's stack splits by type.

A correction to *"Prometheus does the metrics calculation"*: **the app produces the metrics.** OpenTelemetry counts requests and fills in histograms inside the process. Prometheus **stores** the numbers and **does the math when you query** (rates, percentiles). It doesn't derive metrics from traces. (Tempo can generate some metrics from spans, but that's an extra feature, not used here.)

*"What are the logs here? Isn't it just the traces?"* No: **logs are messages the code chose to write**, as text, usually to say *why*. Traces are structured timings recorded automatically. They connect when a log line carries the trace ID of the request that wrote it (§3.5).

### 2.5 Grafana: one UI, many data sources

*"Because there could be multiple services, Grafana also supports multiple providers?"* Yes, and that's what makes it fit a stack that isn't unified. Grafana doesn't store telemetry. It **queries data sources** when you open a page:

```
write:  app ──OTLP──▶ collector ──▶ tempo / prometheus / loki         (push)
read:   browser ──▶ grafana ──query──▶ tempo / prometheus / loki      (pull)
```

Data sources are added in the UI or in a provisioning file read at startup:

```yaml
# grafana/provisioning/datasources/stores.yaml (sketch)
apiVersion: 1
datasources:
  - { name: Tempo,      type: tempo,      url: http://tempo:3200 }
  - { name: Prometheus, type: prometheus, url: http://prometheus:9090 }
  - { name: Loki,       type: loki,       url: http://loki:3100 }
```

Beyond these three, Grafana reads Elasticsearch, MySQL and PostgreSQL, AWS CloudWatch, Azure Monitor, Google Cloud Monitoring, and vendor plug-ins. Kubernetes shows up as something to *monitor*: ready-made setups collect cluster metrics and logs into the same stores. The **"Logs for this span"** and **"Trace: <id>"** links are extra settings on the Tempo and Loki data sources; `otel-lgtm` ships them configured (observed: `tracesToLogsV2` on Tempo, a `trace_id` derived field on Loki).

**Reading a trace in Grafana:** Explore → data source **Tempo** → query type **TraceQL** → a query or a trace ID → click a trace ID.
- **The waterfall:** each span is a bar on a shared time axis, indented under its parent. Length = duration; position = when it ran. **Colours are per service:** the browser's spans in one colour, the backend's in another. Gaps are time nobody recorded (usually network or queueing).
- **Click a row** for its attributes, resource and events.
- **Drag across the overview** to zoom.
- **Critical path / Errors** buttons for the chain that decided the total, or the red spans.

Queries that came up:

| TraceQL | Finds |
|---|---|
| `{resource.service.name="cojidaily-browser"}` | everything the browser recorded |
| `{name="receipt reading"} && {resource.service.name="cojidaily-browser"}` | readings started by a click (browser + backend in one trace) |
| `{status=error}` | failed spans |
| `{name=~"GET img .*/preview/" \|\| span.http.route=~".*preview.*"}` | browser image spans *and* Django's preview spans side by side (raise **Limit** in Search Options; narrow the time range) |

---

## 3. OpenTelemetry inside a program

### 3.1 Span and trace

A **span** is **one timed operation**: one step. It isn't the lifetime of the request.

| | What it is | In the reading of receipt #47 (observed) |
|---|---|---|
| **Span** | One operation with a start and an end | `prepare photo` 345 ms; one `SELECT` 0.2 ms; `chat Qwen/…` 118.9 s |
| **Root span** | The top span, with no parent; it covers the whole request | the browser's `POST`, 119.8 s |
| **Trace** | **All spans sharing one trace ID**: the request's whole journey as a tree | 18 spans, trace `59a78c5e…` |

The fields of a span (from 4a's console output, observed):

| Field | Meaning | Example |
|---|---|---|
| `trace_id` | Same for every span of one request (16 random bytes) | `0x27f583d1…cf50d94f` |
| `span_id` | This span's own ID (8 bytes) | `0xf7126d41f4a2f04b` |
| `parent_id` | The span it sits under; empty = root | SQL spans → the GET span |
| `kind` | SERVER = handling a request that came in; CLIENT = calling out (MySQL, Spark) | `SpanKind.SERVER` |
| start / end time | Duration = end − start | 8.25 ms |
| `attributes` | Details, under standard names | `http.route`, `db.statement` (values replaced by `%s`) |
| `status` | OK / ERROR + message | ERROR `truncated` |
| `events` | Timestamped moments inside the span | the browser's `requestStart`, `responseStart` |
| `resource` | Who produced it | `service.name = cojidaily-backend` |

### 3.2 The parts of OpenTelemetry in a program

```
instrumentation (Django plug-in, your own spans)
   → API       tracer.start_span(...)              "record this"; does nothing on its own
   → SDK       builds span objects, IDs, sampling, keeps finished spans in a batch
   → exporter  turns those objects into a format and sends them somewhere
   → (outside the program) Collector → stores → Grafana
```

| Part | Job | In this project |
|---|---|---|
| **API** | What code calls | `from opentelemetry import trace` in the reading code (4d) |
| **SDK** | Makes the API real | `opentelemetry-sdk`, set up by the launcher |
| **Instrumentations** | Wrappers around libraries | Django, mysqlclient, urllib, requests, botocore |
| **Exporter** | Where finished data goes, in what format | `console` (4a), then `otlp` (4b) |
| **Backend** | Stores and shows the data; not OpenTelemetry | the `lgtm` container |

The SDK's output is **in-memory objects**, the same whatever the exporter (observed: `opentelemetry.sdk.trace.ReadableSpan`, whose trace ID is a plain integer, `337166857320033226630988621752862052440`). The exporter decides how that becomes text or bytes.

### 3.3 How auto-instrumentation gets in without code changes

**Where the settings come from** (*"where are these environment variables loaded?"*), checked in the installed package source:
1. `compose.otel.yaml`'s `environment:` block puts `OTEL_SERVICE_NAME`, `OTEL_TRACES_EXPORTER`… into the backend container's environment.
2. The container runs `sh -c "… exec opentelemetry-instrument gunicorn …"`; child processes inherit the environment.
3. `opentelemetry-instrument` puts its own `auto_instrumentation/` folder at the front of `PYTHONPATH`, then **replaces itself** with `gunicorn` (`exec`).
4. When Python starts, its `site` module imports any module named `sitecustomize` it finds on the path. That folder has one, which calls `initialize()`: read `OTEL_*` from the environment, set up the SDK, patch every installed library that has an instrumentation package.
5. Only then does gunicorn import `config.wsgi` and Django, which are **already patched**.

```
compose.otel.yaml ─env─▶ sh ─▶ opentelemetry-instrument ─PYTHONPATH + exec─▶ gunicorn (Python)
                                                                                │ site → sitecustomize.py
                                                                                │   initialize(): read OTEL_*, patch libraries
                                                                                └─ import config.wsgi → Django (already patched)
```

**How it reaches SQL "bypassing Django":** it doesn't bypass Django. Django calls the MySQL driver; the instrumentation replaced the driver's functions on the module object (**monkey-patching**). A sketch of the idea, not the real code:

```python
import MySQLdb
real_connect = MySQLdb.connect

def traced_connect(*args, **kwargs):
    return TracedConnection(real_connect(*args, **kwargs))   # its cursors are wrapped too

MySQLdb.connect = traced_connect      # Django's `Database.connect(...)` now finds this

# and a wrapped cursor's execute:
def execute(self, sql, params=None):
    with tracer.start_as_current_span("SELECT", kind=CLIENT) as span:   # start the timer
        span.set_attribute("db.statement", sql)                         # the %s text, not the values
        return self._real_cursor.execute(sql, params)                   # the real call
```

`execute()` blocks until MySQL replies, so the timer covers the round trip, measured from Python's side. The same pattern wraps urllib (and **writes a `traceparent` header** into the outgoing request), `requests` and botocore. Patching must happen *before* any code takes its own reference to the original function, which is why `sitecustomize` runs first.

**The backend, before and after** (redrawn from the two "backend with/without OpenTelemetry" diagrams in "Nginx reverse proxy concepts"):

```
WITHOUT                                             WITH (opentelemetry-instrument)
nginx :80                                           nginx :80
  │                                                   │
gunicorn worker (Python)                            gunicorn worker (Python)
  └─ Django: middleware, views, ORM                   ├─ OTel middleware   inserted first in MIDDLEWARE → SERVER span
       ├─ MySQLdb   connect, execute ─▶ MySQL         ├─ Django: views, ORM (unchanged)
       ├─ urllib    urlopen          ─▶ Spark vLLM    │    ├─ wrapper ─▶ MySQLdb  ─▶ MySQL        (CLIENT span per query)
       └─ requests, botocore         ─▶ Google, AWS   │    ├─ wrapper ─▶ urllib   ─▶ Spark vLLM   (+ traceparent)
                                                      │    └─ wrapper ─▶ requests, botocore ─▶ Google, AWS
                                                      └─ SDK: batch spans ──▶ lgtm :4318
```

**OpenTelemetry doesn't run your code.** Your code runs on the ordinary interpreter; the launcher adds one setup step before it. After that, OpenTelemetry is passive: it acts only when your code calls a patched function. *"So it detects Django itself?"* Not on its own: it works because **the Django instrumentation package is installed**. Each package registers itself (an `opentelemetry_instrumentor` entry point) and `initialize()` patches every installed one whose library is present. A library with no package records nothing.

Two ways to start it:

| | Launcher: `opentelemetry-instrument gunicorn …` | In code |
|---|---|---|
| App code | none | a few lines: set up the SDK, then e.g. `DjangoInstrumentor().instrument()` |
| Configuration | env vars | env vars still work; code can override |
| FastAPI | `opentelemetry-instrument uvicorn …` | `FastAPIInstrumentor.instrument_app(app)` |

Useful settings (standard across languages): `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER`, `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=urllib,botocore` (turn plug-ins off), `OTEL_SDK_DISABLED=true` (turn everything off).

**What isn't automatic:** steps specific to your app ("resize the photo", "call the model"). Those need **manual instrumentation**, a few lines creating your own spans (4d). They use only the API, which does nothing without the SDK, so tests and the bench are unaffected.

### 3.4 Exporters and formats

*"Does opentelemetry return json?"* It doesn't return anything: it **records** and **exports**. The format comes from the exporter:

| Exporter | Goes to | Format |
|---|---|---|
| `console` (4a, `perf/show-raw-spans.sh`) | stdout | The Python SDK's own debug JSON; not a standard |
| `otlp` + `http/protobuf` (the running stack) | `lgtm:4318/v1/traces` | **Protobuf**: compact binary |
| `otlp` + `http/json` | the same endpoint | OTLP's JSON encoding: the same message, as text |
| `otlp` + `grpc` | `:4317` | Protobuf over HTTP/2, common between servers |

Spans in each format (observed, 2026-10-20; the console sample is a calendar-day request from `perf/show-raw-spans.sh`, the two OTLP samples are one `GET api/session/` span encoded both ways):

**console:**
```json
{ "name": "GET api/calendar/day/",
  "context": { "trace_id": "0x41a003401b4e364753bc83520223052f", "span_id": "0x03e1720b7a001cb7" },
  "kind": "SpanKind.SERVER", "parent_id": null,
  "attributes": { "http.route": "api/calendar/day/", "http.response.status_code": 200 } }
```

**OTLP protobuf:** 653 bytes. The start:
```
0a 8a 05 0a f6 01 0a 22 0a 16 74 65 6c 65 6d 65 74 72 79 2e 73 64 6b ...
                              t  e  l  e  m  e  t  r  y  .  s  d  k
```

**OTLP JSON:**
```json
{ "resourceSpans": [ {
    "resource": { "attributes": [ { "key": "service.name", "value": { "stringValue": "cojidaily-backend" } } ] },
    "scopeSpans": [ {
      "scope": { "name": "opentelemetry.instrumentation.django", "version": "0.66b1" },
      "spans": [ { "traceId": "…", "spanId": "…", "name": "GET api/session/", "kind": "SPAN_KIND_SERVER",
                   "startTimeUnixNano": "1792481992105027442", "attributes": [ … ] } ] } ] } ] }
```

**http/protobuf vs http/json:** same messages, same endpoint, different encoding. Protobuf is several times smaller and faster; JSON is readable and needs no protobuf library, so browsers often use it. 4c's experiment 5 posted OTLP JSON by hand. OTLP JSON writes IDs as **hex**; a generic protobuf-to-JSON converter writes them as base64, which a strict collector may reject.

**What OTLP is:** a set of **protobuf `.proto` files** published by OpenTelemetry (`ResourceSpans`, `ScopeSpans`, `Span`, `ExportTraceServiceRequest`…). Protobuf is Google's language-neutral format, not Go-specific: you define messages once and generate classes for each language. The Python classes are the `opentelemetry-proto` package in `backend/requirements.txt`. The exporter fills them and calls `SerializeToString()`. The Collector, written in Go, decodes with classes generated from the **same** files, which is why any SDK can talk to any collector.

### 3.5 Metrics and logs: separate pipelines

**They aren't built on traces.** The SDK has three independent pipelines (`TracerProvider`, `MeterProvider`, `LoggerProvider`), each with its own exporter setting (`OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`). They share the **resource** (service name) and the **context**: a log written while a span is active gets that span's trace ID. Metrics never need traces.

**A metric on the console** (observed): a histogram per route, not individual requests:
```json
{ "name": "http.server.request.duration", "unit": "s",
  "data": { "data_points": [ {
      "attributes": { "http.request.method": "GET", "http.route": "api/session/", "http.response.status_code": 200 },
      "count": 1, "sum": 0.00226,
      "bucket_counts": [1, 0, 0, 0, …], "explicit_bounds": [0.005, 0.01, 0.025, 0.05, …] } ] } }
```
"1 request so far, 2.26 ms total, in the ≤ 5 ms bucket." A million requests would be the same size, with bigger counts. That's why metrics are cheap, and why Prometheus computes percentiles from the buckets.

**A log on the console** (observed): Django's 404 warning:
```json
{ "body": "Not Found: /api/extractions/999999/", "severity_text": "WARN",
  "attributes": { "status_code": 404, "code.function.name": "log_response" },
  "trace_id": "0x00000000000000000000000000000000", "span_id": "0x0000000000000000" }
```
The all-zero trace ID: Django writes this warning after the request's span has ended, so there's nothing to link to. A log written *during* the request (like the reading log) carries the real ID.

**Which logs are collected:** records written through Python's **`logging` module**: your `logger.info/warning/exception(...)`, Django's own loggers (404s, 500s with tracebacks), library loggers, including OpenTelemetry's own complaints. **Not** `print()` or other raw console output; those stay in `docker logs`.

### 3.6 Ways to use OpenTelemetry

Auto-instrumentation is the usual starting point; real setups combine several:

| Way | What it is | Used here? |
|---|---|---|
| **Zero-code agent** | A launcher or agent patches libraries at startup: Python `opentelemetry-instrument`, the Java agent, .NET, Node's `--require`. In Kubernetes, the OpenTelemetry Operator can inject it | Yes (4a) |
| **Library instrumentation in code** | Your code calls a specific instrumentor | No |
| **Manual instrumentation** | Your code creates spans and metrics with the API | Yes (4d, 4e) |
| **Browser / mobile SDKs** | Fetch and page-load instrumentation plus your own spans | Yes (4c, `telemetry.ts`) |
| **Native OpenTelemetry** | The software emits OTel itself: proxies like Envoy, some databases, vLLM's own tracing | Not yet |
| **eBPF agents** | Watch network calls from the Linux kernel for any process; no code, no launcher; see less inside the app | No |
| **Collector receivers** | The Collector pulls from things that don't speak OTLP: Prometheus endpoints, host stats, log files | No |

---

## 4. Setting it up

### 4.1 They're separate services

*"I think they are not just database storages right? Like grafana needs to spin up service as well as collector."* Right. Each is a running program with its own config, API and (for the stores) its own storage engine:

| Service | Does | Listens on (default) | Stores |
|---|---|---|---|
| Collector | receive, process, forward | 4317 (OTLP gRPC), 4318 (OTLP HTTP), 13133 (health) | nothing; data only passes through memory |
| Tempo | ingest and index traces, answer TraceQL | 3200 (query), plus OTLP receivers | trace blocks on disk or object storage (path set in its config) |
| Prometheus | store time series, answer PromQL, alert rules | 9090 | its time-series database, `/prometheus` |
| Loki | ingest and index logs, answer LogQL | 3100 | chunks and index (path set in its config) |
| Grafana | web UI, dashboards, users, alerts | 3000 | its own small database, `grafana.db` (SQLite), `/var/lib/grafana` |

(Prometheus and Grafana paths are their images' defaults; Tempo's and Loki's depend on their config, not verified here.) **Without volumes, all of it disappears when the container is removed**, which is the `lgtm` limitation noted in 4b.

### 4.2 Ports and names: how they find each other

*"Don't I need to set the ports? Otherwise how do they know who is who?"*

| | What it does | Needed for |
|---|---|---|
| **Service name** (`tempo`, `loki`) | Docker's internal DNS turns it into the container's IP | container → container |
| **The port the program listens on** | the image's default (table above) | part of the address: `http://loki:3100` |
| **`ports:` in compose** | *publishes* a container port on the host | only for things **outside** Docker, e.g. your browser → Grafana |

So `http://tempo:3200` works between containers with no `ports:` line, just like `backend:8000` in the nginx config and `lgtm:4318` in `compose.otel.yaml`. The Collector and Tempo can both listen on 4317, because each container has its own IP; ports only clash when published on the same host.

### 4.3 Docker compose: separate services vs this project's all-in-one

**Separate services** (the usual production shape; a sketch, not run here: each store also needs its own config file, and the image versions must be pinned):

```yaml
services:
  app:
    environment:
      OTEL_SERVICE_NAME: orders-api
      OTEL_TRACES_EXPORTER: otlp
      OTEL_EXPORTER_OTLP_ENDPOINT: http://collector:4318
  collector:
    image: otel/opentelemetry-collector-contrib:<version>
    volumes: ["./otel.yaml:/etc/otelcol-contrib/config.yaml"]
  tempo:      { image: "grafana/tempo:<version>",    volumes: ["tempo-data:/var/tempo"] }
  prometheus: { image: "prom/prometheus:<version>",  volumes: ["prom-data:/prometheus"] }
  loki:       { image: "grafana/loki:<version>",     volumes: ["loki-data:/loki"] }
  grafana:
    image: grafana/grafana:<version>
    ports: ["3000:3000"]                          # the only thing the browser needs
    volumes: ["grafana-data:/var/lib/grafana", "./grafana/provisioning:/etc/grafana/provisioning"]
volumes: { tempo-data: {}, prom-data: {}, loki-data: {}, grafana-data: {} }
```

The Collector's whole job, as receivers → processors → exporters (`otel.yaml`):

```yaml
receivers:
  otlp: { protocols: { http: {}, grpc: {} } }
processors:
  batch: {}
exporters:
  otlp/tempo:            { endpoint: tempo:4317, tls: { insecure: true } }
  prometheusremotewrite: { endpoint: http://prometheus:9090/api/v1/write }
  otlphttp/loki:         { endpoint: http://loki:3100/otlp }
service:
  pipelines:
    traces:  { receivers: [otlp], processors: [batch], exporters: [otlp/tempo] }
    metrics: { receivers: [otlp], processors: [batch], exporters: [prometheusremotewrite] }
    logs:    { receivers: [otlp], processors: [batch], exporters: [otlphttp/loki] }
```

**What this project runs instead** (`compose.otel.yaml`, observed): one container, `grafana/otel-lgtm:0.34.0`, with the Collector, Tempo, Prometheus, Loki and Grafana, already configured and wired to each other (data sources and trace↔log links included). It used ~724 MB of RAM. The app side is only environment variables:

```yaml
backend:
  environment:
    OTEL_TRACES_EXPORTER: otlp
    OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
    OTEL_EXPORTER_OTLP_ENDPOINT: http://lgtm:4318
lgtm:
  image: grafana/otel-lgtm:0.34.0
  ports: ["3000:3000"]          # Grafana, no login: anyone on the Wi-Fi can read the traces
```

The trade-off: everything works in one line, but it's a **development image**. No persistence, no login, everything shares one container's resources. Fine for learning and the test stack; not for production.

### 4.4 Health checks

*"In this case they need health check?"* They help, with two caveats:
- **`depends_on` waits for *started*, not *ready*.** A health check plus `condition: service_healthy` makes Grafana wait until Loki answers. Readiness endpoints: Prometheus `/-/ready`, Loki and Tempo `/ready`, Grafana `/api/health`, the Collector's `health_check` extension on 13133.
- **The check runs inside the container**, so the image needs `wget` or `curl`. The official Collector image has no shell, so a `curl`-based check can't run there.
- **Don't make the app depend on the telemetry stack being healthy.** If the Collector is down, the SDK retries, then drops data; the app must keep serving. That's why the backend has only a plain `depends_on: lgtm`.

### 4.5 The order to set it up

The order this project followed, which generalises (`add-observability.md` 4a–4e):
1. **One app, zero code, console exporter.** See real spans before building any storage. (`opentelemetry-bootstrap -a install` lists and installs the instrumentations for the libraries you have.)
2. **A Collector and stores.** Switch the exporter to `otlp`; nothing else changes in the app.
3. **Spans and metrics for your own steps.** Auto-instrumentation knows libraries, not your business logic.
4. **Connect services and the browser.** Service to service is automatic (`traceparent`, §6); the browser posts to the Collector through the reverse proxy to stay same-origin.
5. **Before real traffic:** sampling, retention, a login (§5).

| You change… | You touch… |
|---|---|
| what's measured | the app (instrumentations, your spans) |
| where data goes, sampling, filtering, redaction | the Collector config |
| how long it's kept, dashboards, alerts | the stores and Grafana |

---

## 5. Production: what to be careful about, and how it's usually run

### 5.1 Things to be careful about

General practice; the items this project has hit are marked.
- **Sampling.** Recording every request is fine at home, expensive with real traffic.
  - **Head sampling** decides at the start, e.g. keep 10% (`OTEL_TRACES_SAMPLER=parentbased_traceidratio`, `OTEL_TRACES_SAMPLER_ARG=0.1`). "Parent-based" makes every service follow the first one's decision, so traces stay complete (§6.2).
  - **Tail sampling** decides in the Collector after seeing the whole trace, e.g. keep all errors and slow ones.
  - This project records 100%, including during load tests.
- **Retention and storage.** Decide how long each signal is kept. Large setups put Tempo's and Loki's data on object storage (S3, GCS) and use a long-term store for Prometheus (Mimir, Thanos). `lgtm` keeps nothing (observed).
- **Metric cardinality.** Every distinct combination of label values is a separate time series. A label like `user_id` or `receipt_id` creates one series per user or receipt and can overwhelm Prometheus. That's why the metrics here use the route pattern (`api/receipts/<int:pk>/…`), not the URL. IDs belong on spans, not metric labels.
- **Sensitive data.** Check what auto-instrumentation records:
  - here, full URLs and user agents (observed), with SQL values replaced by `%s`;
  - put no content in your own spans (this project records counts and sizes, never receipt contents);
  - the Collector can remove or hash attributes before storage.
- **Access.** Grafana needs a login; development Grafana here has none (observed). A public OTLP endpoint needs authentication or rate limits. The browser route `/otlp/` here accepts posts from anyone on the Wi-Fi. Use TLS between machines.
- **Telemetry must not take the app down.** Exporters retry and drop; the app shouldn't wait on the telemetry stack (§4.4).
- **Cost.** Every span, series and log line costs CPU, network and storage. Managed services usually bill by volume.
- **Clocks.** Spans from different machines line up only as well as their clocks do; run NTP everywhere.
- **Availability.** Run the Collector in two layers: an **agent** next to each app, plus a **gateway** tier with several replicas. One Collector going down then doesn't lose everything.
- **Alerts.** Dashboards nobody watches find nothing. Alert on SLOs (Grafana alerting or Prometheus Alertmanager); this project has none yet (plan step 7).
- **Pin versions and keep config in git** (dashboards and data sources as provisioning files too).

### 5.2 How it's usually run

| Approach | What it looks like | Own view (UI)? |
|---|---|---|
| **Self-hosted** | Usually on Kubernetes with Helm charts: Collector agents and a gateway, Tempo/Loki/Mimir on object storage, Grafana; the OpenTelemetry Operator injects auto-instrumentation | Grafana |
| **Managed Grafana stack** | Grafana Cloud runs the stores and Grafana; you run Collectors that send OTLP to it | Grafana |
| **AWS** | CloudWatch for metrics and logs, **X-Ray** for traces, CloudWatch Application Signals for service-level views. AWS ships its own OpenTelemetry distribution (**ADOT**) and Collector. Also Amazon Managed Service for Prometheus and Amazon Managed Grafana | CloudWatch / X-Ray consoles, or Managed Grafana |
| **Google Cloud / Azure** | Cloud Monitoring, Logging and Trace / Azure Monitor and Application Insights, all accepting OpenTelemetry data | their consoles |
| **Vendors** | Datadog, New Relic, Honeycomb, Dynatrace… all accept OTLP | their own UIs |

**Because the app only speaks OTLP to a Collector, moving between these is mostly a Collector exporter change**, not an app change. That was the reason for choosing OpenTelemetry (`add-observability.md` 4a): the same instrumentation works for Django, FastAPI, and whichever store you pick.

For CojiDaily, what's still open before real use: sampling, retention, a Grafana login, alerts (plan step 7, `pm/issues/app-evaluation-observability.md`).

---

## 6. `traceparent`: what it does and what it provides

### 6.1 What it is

An **HTTP header**, one line of text, standardised by the W3C ("Trace Context"):

```
traceparent: 00-5b6ecf11bb506c7c4491ebfe499b69d1-b2ba3af78fee4657-01
             │  │                                │                └─ flags: 01 = sampled (record it), 00 = don't
             │  │                                └─ parent span ID: the caller's span (8 bytes)
             │  └─ trace ID: the same for everything in this request (16 bytes)
             └─ version
```

Who writes and reads it here:
- The **browser SDK** writes it on every same-origin `fetch`.
- **Django's instrumentation** reads it.
- **urllib's instrumentation** writes it on the call to Spark, which ignores it (vLLM isn't traced).

### 6.2 What it provides

**It joins separate programs into one trace.** The browser creates a trace ID and its own span ID and sends them in the header. Django creates its span with **the same trace ID** and **the browser's span as its parent**. Both send their spans to the Collector separately, and Tempo reassembles them by trace ID. In Grafana that's the browser's bar on top with the backend's under it, in a different colour.

It also **carries the sampling decision**, so every service keeps or drops the same traces.

The experiments in 4c part 1 (observed; rerun with `perf/traceparent-experiments.sh`):

| Sent | Result |
|---|---|
| No header | Django starts its own new trace (no parent) |
| Our trace and span IDs, flags `01` | Django **adopts our trace ID** and makes our span its parent. Tempo shows `<root span not yet received>`, because we never sent that span |
| Flags `00` | **Nothing recorded**: parent-based sampling follows the caller |
| An all-zero trace ID (invalid) | Ignored; a fresh trace starts |
| Browser JS: make IDs, send the header, post its own span to `/otlp/` | **One trace, two services:** browser 160.9 ms, Django 5.71 ms under it, so ~155 ms was network |

### 6.3 What it doesn't do

- **It doesn't report anything.** It only carries IDs. Each side must still export its own spans; that's the "root span not yet received" case.
- **Some requests can't carry it.** The browser loads `<img>` by itself and JavaScript can't add headers to that, so each thumbnail is a blue browser span in its own trace and a separate pink Django trace (10.9 ms) with no link. You can only match them by time (`add-observability.md`, 4c part 2).
- **It's added only where allowed.** The SDK adds it to same-origin requests; other origins must allow the header (CORS) and be listed.
- **It doesn't align clocks.** A child can appear to start before its parent if the machines' clocks differ.

### 6.4 Related

- **`tracestate`**: vendor-specific extras alongside `traceparent`.
- **`baggage`**: your own key-values carried to every service (e.g. `user.plan=free`); propagated, not recorded unless code copies them onto spans.
- **Older formats** still seen in existing systems: Zipkin's B3 headers (`X-B3-TraceId`), AWS's `X-Amzn-Trace-Id`, Datadog's `x-datadog-trace-id`. Collectors and SDKs can translate between them.
- **Beyond HTTP:** the same context travels in message-queue headers (Kafka, SQS) so a trace can continue through a background job. That would matter for the background-job reading design planned for FastAPI.
