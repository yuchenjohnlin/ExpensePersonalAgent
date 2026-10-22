"""Background jobs: a table in PostgreSQL and a worker process (pm/decisions/jobs-hand-written-table.md).

    enqueue(db, kind, payload)   inside the caller's transaction: the job exists exactly when the
                                 rows that need it were committed with it
    Worker(...).run_forever()    `python -m cojidaily.worker`: claim, run, finish, repeat

Claiming takes the oldest ready job with FOR UPDATE SKIP LOCKED, so several workers never take the
same job, and commits at once: a handler never holds that transaction while it works (a reading
waits minutes for the model). A handler gets the sessionmaker and opens its own transactions.

Delivery is at least once. A worker that dies mid-job leaves it running; after LEASE another
worker takes it again. A job whose handler raises is retried with a growing delay until
max_attempts, then marked failed. So handlers must be safe to run twice.

Each run is a span (`job <kind>`), and two histograms say how long jobs waited once ready and how
long they ran. They go through the OpenTelemetry API, so they do nothing unless the process runs
with an SDK (deploy/README.md).
"""
import contextlib
import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

try:  # the image's `otel` extra; without it nothing is instrumented, so there is nothing to hold back
    from opentelemetry.instrumentation.utils import suppress_instrumentation
except ImportError:
    suppress_instrumentation = contextlib.nullcontext
from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Integer, Text, func, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from . import clock
from .db import Base

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_meter = metrics.get_meter(__name__)
# Ready but not yet taken: what a growing queue or too few worker threads look like.
job_wait = _meter.create_histogram("coji.job.wait", unit="s", description="Time a ready job waited for a worker")
job_duration = _meter.create_histogram("coji.job.duration", unit="s", description="Time a worker spent on a job")

LEASE = timedelta(minutes=15)  # longer than the slowest job (a reading allows the model 300 s)
RETRY_DELAY = timedelta(seconds=10)  # doubled after each failed attempt

Handler = Callable[[sessionmaker[Session], dict], None]


class Job(Base):
    __tablename__ = "platform_job"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        # The worker's question, "the most urgent, then oldest, job ready to run", stays an index scan.
        Index("ix_platform_job_ready", "priority", "id", postgresql_where=text("status = 'queued'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    # Higher runs first. A short follow-up step must not wait behind minutes-long readings queued
    # before it (FOLLOW_UP); among equals, the oldest first.
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


FOLLOW_UP = 10  # the priority of a quick step that continues work a slow job just finished


def enqueue(db: Session, kind: str, payload: dict, *, max_attempts: int = 3, priority: int = 0) -> None:
    # Ready at the database's now(), the clock the claim compares with (the app's may drift from it).
    db.add(Job(kind=kind, payload=payload, priority=priority, status="queued", attempts=0, max_attempts=max_attempts,
               run_after=func.now(), locked_by="", last_error="", created_at=clock.now()))


CLAIM = text("""
    UPDATE platform_job
       SET status = 'running', locked_at = now(), locked_by = :worker, attempts = attempts + 1
     WHERE id = (SELECT id FROM platform_job
                  WHERE (status = 'queued' AND run_after <= now())
                     OR (status = 'running' AND locked_at < now() - :lease)
                  ORDER BY priority DESC, id
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED)
 RETURNING id, kind, payload, attempts, max_attempts,
           EXTRACT(EPOCH FROM now() - run_after)::float AS waited
""")


class Worker:
    def __init__(self, sessions: sessionmaker[Session], handlers: dict[str, Handler], *,
                 poll_seconds: float = 1.0, lease: timedelta = LEASE, name: str = ""):
        self.sessions, self.handlers = sessions, handlers
        self.poll_seconds, self.lease = poll_seconds, lease
        # Shown in locked_by: which process (and which of its workers) holds a job.
        self.name = f"{socket.gethostname()}:{os.getpid()}:{name or id(self)}"

    def run_once(self) -> bool:
        """Run one ready job; False when there was none."""
        # Each thread asks every second; traced, every empty ask would be a trace of its own
        # (about 150,000 a day). What a job does is traced under its own span below.
        with suppress_instrumentation(), self.sessions() as db:
            job = db.execute(CLAIM, {"worker": self.name, "lease": self.lease}).mappings().first()
            db.commit()
        if job is None:
            return False
        kind = job["kind"]
        job_wait.record(max(job["waited"], 0.0), {"coji.job.kind": kind})
        if job["attempts"] > job["max_attempts"]:
            # Only a job taken back from a dead worker again and again gets here.
            self._end(job["id"], "failed", "工作逾時的次數超過上限。")
            return True
        handler = self.handlers.get(kind)
        started = time.monotonic()
        with tracer.start_as_current_span(f"job {kind}", attributes={
                "coji.job.id": job["id"], "coji.job.kind": kind, "coji.job.attempt": job["attempts"],
                "coji.job.waited_s": round(max(job["waited"], 0.0), 3)}) as span:
            try:
                if handler is None:
                    raise LookupError(f"no handler for job kind {kind!r}")
                handler(self.sessions, job["payload"])
            except Exception as error:
                logger.exception("job %s (%s) failed on attempt %s", job["id"], kind, job["attempts"])
                span.record_exception(error)
                span.set_status(Status(StatusCode.ERROR, type(error).__name__))
                message = f"{type(error).__name__}: {error}"[:2000]
                if job["attempts"] < job["max_attempts"]:
                    outcome = "retry"
                    delay = RETRY_DELAY * 2 ** (job["attempts"] - 1)
                    # The database's clock, as the claim compares with: the app's may drift from it.
                    self._end(job["id"], "queued", message, run_after=func.now() + delay)
                else:
                    outcome = "failed"
                    self._end(job["id"], "failed", message)
            else:
                outcome = "done"
                self._end(job["id"], "done", "")
            span.set_attribute("coji.job.outcome", outcome)
        job_duration.record(time.monotonic() - started, {"coji.job.kind": kind, "coji.job.outcome": outcome})
        return True

    def _end(self, job_id: int, status: str, error: str, run_after=None) -> None:
        values = {"status": status, "last_error": error, "locked_at": None, "locked_by": ""}
        if status in ("done", "failed"):
            values["finished_at"] = func.now()
        if run_after is not None:
            values["run_after"] = run_after
        with self.sessions() as db:
            db.execute(update(Job).where(Job.id == job_id).values(**values))
            db.commit()

    def run_until_idle(self) -> int:
        """Run jobs until none is ready, including the ones the jobs enqueue; how many ran (tests)."""
        count = 0
        while self.run_once():
            count += 1
        return count

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        logger.info("worker %s started with %s", self.name, sorted(self.handlers))
        while not stop.is_set():
            try:
                ran = self.run_once()
            except Exception:  # the database went away: wait and try again
                logger.exception("worker could not claim a job")
                ran = False
            if not ran:
                stop.wait(self.poll_seconds)
