"""What a job reports to observability (platform/jobs.py): a span per run, how long it waited once
ready, and how long it ran. The SDK here keeps everything in memory instead of sending it."""
import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy import text

from cojidaily.platform.db import make_engine, make_sessions
from cojidaily.platform.jobs import Worker, enqueue

SPANS = InMemorySpanExporter()
METRICS = InMemoryMetricReader()


@pytest.fixture(scope="module", autouse=True)
def sdk():
    # A process gets one global provider; the module-level tracer and meter in jobs.py are proxies
    # that start using these once they are set.
    tracing = TracerProvider()
    tracing.add_span_processor(SimpleSpanProcessor(SPANS))
    trace.set_tracer_provider(tracing)
    metrics.set_meter_provider(MeterProvider(metric_readers=[METRICS]))


@pytest.fixture
def sessions(database_url):
    engine = make_engine(database_url, 5)
    yield make_sessions(engine)
    engine.dispose()


def histogram(name: str, **attributes) -> tuple[int, float]:
    """(count, sum) of the points whose attributes include these, as recorded so far."""
    count, total = 0, 0.0
    data = METRICS.get_metrics_data()  # None until something was recorded
    for resource in data.resource_metrics if data else ():
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    if all(point.attributes.get(key) == value for key, value in attributes.items()):
                        count, total = count + point.count, total + point.sum
    return count, total


def test_a_job_is_a_span_and_reports_how_long_it_waited_once_ready(sessions):
    SPANS.clear()
    with sessions() as db:
        enqueue(db, "noted", {})
        db.commit()
        # Ready for 5 s before any worker looked: what a busy queue looks like.
        db.execute(text("UPDATE platform_job SET run_after = now() - interval '5 seconds'"))
        db.commit()
    waits_before = histogram("coji.job.wait", **{"coji.job.kind": "noted"})

    Worker(sessions, {"noted": lambda *_: None}).run_until_idle()

    [span] = SPANS.get_finished_spans()
    assert span.name == "job noted"
    assert span.attributes["coji.job.attempt"] == 1
    assert span.attributes["coji.job.outcome"] == "done"
    assert 5 <= span.attributes["coji.job.waited_s"] < 30
    count, total = histogram("coji.job.wait", **{"coji.job.kind": "noted"})
    assert count == waits_before[0] + 1
    assert 5 <= total - waits_before[1] < 30
    assert histogram("coji.job.duration", **{"coji.job.kind": "noted", "coji.job.outcome": "done"})[0] >= 1


def test_a_failed_attempt_is_an_error_span_and_counts_as_a_retry(sessions):
    SPANS.clear()
    with sessions() as db:
        enqueue(db, "broken", {})
        db.commit()
    retries_before = histogram("coji.job.duration", **{"coji.job.kind": "broken", "coji.job.outcome": "retry"})[0]

    def fail(*_):
        raise ValueError("the model answered nothing")

    Worker(sessions, {"broken": fail}).run_once()

    [span] = SPANS.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["coji.job.outcome"] == "retry"
    assert [event.name for event in span.events] == ["exception"]
    assert histogram("coji.job.duration", **{"coji.job.kind": "broken", "coji.job.outcome": "retry"})[0] == retries_before + 1
