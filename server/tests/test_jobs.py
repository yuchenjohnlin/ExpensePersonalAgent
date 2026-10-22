"""The job table and the worker (platform/jobs.py)."""
import threading
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from cojidaily.platform import clock
from cojidaily.platform.db import make_engine, make_sessions
from cojidaily.platform.jobs import FOLLOW_UP, Job, Worker, enqueue


@pytest.fixture
def sessions(database_url):
    engine = make_engine(database_url, 5)
    yield make_sessions(engine)
    engine.dispose()


def jobs(sessions):
    with sessions() as db:
        return db.scalars(select(Job).order_by(Job.id)).all()


def test_a_job_exists_only_if_its_transaction_commits(sessions):
    with sessions() as db:
        enqueue(db, "noted", {"n": 1})
        db.rollback()
        enqueue(db, "noted", {"n": 2})
        db.commit()
    assert [job.payload for job in jobs(sessions)] == [{"n": 2}]


def test_the_worker_runs_ready_jobs_in_order_and_marks_them_done(sessions):
    seen = []
    with sessions() as db:
        for n in range(3):
            enqueue(db, "noted", {"n": n})
        db.commit()
    worker = Worker(sessions, {"noted": lambda _, payload: seen.append(payload["n"])})
    assert worker.run_until_idle() == 3
    assert worker.run_once() is False
    assert seen == [0, 1, 2]
    assert {(job.status, job.attempts, job.locked_at) for job in jobs(sessions)} == {("done", 1, None)}


def test_a_follow_up_step_runs_before_slow_jobs_queued_earlier(sessions):
    seen = []
    with sessions() as db:
        enqueue(db, "noted", {"n": "second reading"})
        enqueue(db, "noted", {"n": "third reading"})
        enqueue(db, "noted", {"n": "after the first reading"}, priority=FOLLOW_UP)
        db.commit()
    Worker(sessions, {"noted": lambda _, payload: seen.append(payload["n"])}).run_until_idle()
    assert seen == ["after the first reading", "second reading", "third reading"]


def test_a_handler_can_enqueue_the_next_step(sessions):
    seen = []

    def first(sessions_, payload):
        with sessions_() as db:
            enqueue(db, "second", {"from": payload["n"]})
            db.commit()

    worker = Worker(sessions, {"first": first, "second": lambda _, payload: seen.append(payload)})
    with sessions() as db:
        enqueue(db, "first", {"n": 7})
        db.commit()
    assert worker.run_until_idle() == 2
    assert seen == [{"from": 7}]


def test_a_failing_job_is_retried_later_then_marked_failed(sessions):
    calls = []

    def broken(_, payload):
        calls.append(payload)
        raise RuntimeError("model unreachable")

    with sessions() as db:
        enqueue(db, "broken", {}, max_attempts=2)
        db.commit()
    worker = Worker(sessions, {"broken": broken})
    assert worker.run_once() is True
    [job] = jobs(sessions)
    assert (job.status, job.attempts, job.last_error) == ("queued", 1, "RuntimeError: model unreachable")
    with sessions() as db:
        assert db.scalar(select(Job.run_after > func.now()))  # not ready yet, by the database's clock
    assert worker.run_once() is False
    with sessions() as db:
        db.execute(update(Job).values(run_after=func.now()))
        db.commit()
    assert worker.run_once() is True
    [job] = jobs(sessions)
    assert (job.status, job.attempts) == ("failed", 2)
    assert job.finished_at is not None
    assert len(calls) == 2


def test_a_job_nobody_handles_ends_failed(sessions):
    with sessions() as db:
        enqueue(db, "unknown", {}, max_attempts=1)
        db.commit()
    Worker(sessions, {}).run_once()
    [job] = jobs(sessions)
    assert job.status == "failed"
    assert "no handler" in job.last_error


def test_a_job_left_running_by_a_dead_worker_is_taken_again_after_the_lease(sessions):
    seen = []
    with sessions() as db:
        enqueue(db, "noted", {"n": 1})
        db.commit()
        db.execute(update(Job).values(status="running", attempts=1, locked_at=clock.now() - timedelta(minutes=5)))
        db.commit()
    worker = Worker(sessions, {"noted": lambda _, payload: seen.append(payload)}, lease=timedelta(minutes=10))
    assert worker.run_once() is False  # still within its lease
    with sessions() as db:
        db.execute(update(Job).values(locked_at=clock.now() - timedelta(minutes=11)))
        db.commit()
    assert worker.run_once() is True
    assert seen == [{"n": 1}]
    [job] = jobs(sessions)
    assert (job.status, job.attempts) == ("done", 2)


def test_concurrent_workers_never_run_the_same_job_twice(sessions):
    runs = Counter()
    lock = threading.Lock()

    def count(_, payload):
        with lock:
            runs[payload["n"]] += 1

    with sessions() as db:
        for n in range(40):
            enqueue(db, "count", {"n": n})
        db.commit()
    workers = [Worker(sessions, {"count": count}) for _ in range(4)]
    threads = [threading.Thread(target=worker.run_until_idle) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert runs == Counter({n: 1 for n in range(40)})
