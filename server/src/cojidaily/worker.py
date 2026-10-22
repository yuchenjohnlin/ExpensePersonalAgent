"""The background worker: `python -m cojidaily.worker`. Runs the jobs every module registers.

COJI_WORKER_THREADS workers (default 2) take jobs side by side, so one reading waiting minutes on
the model does not hold up everything else. Each thread is a Worker with its own name; SKIP LOCKED
keeps them from taking the same job.
"""
import signal
import threading

from .platform import logs
from .platform.blobstore import BlobStore
from .platform.db import make_engine, make_sessions
from .platform.jobs import Handler, Worker
from .platform.settings import Settings


def handlers(settings: Settings) -> dict[str, Handler]:
    """Each module's job handlers, by kind. A module's handlers are made from the settings it needs."""
    from .reading import api as reading
    from .receipts import api as receipts

    blobs = BlobStore(settings.blob_root)
    return {**reading.handlers(settings, blobs), **receipts.handlers(settings)}


def main() -> None:
    logs.configure()
    settings = Settings.from_env()
    count = max(1, settings.worker_threads)
    engine = make_engine(settings.database_url, count + 1)
    sessions, jobs = make_sessions(engine), handlers(settings)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    threads = [threading.Thread(target=Worker(sessions, jobs, name=f"worker-{n}").run_forever, args=(stop,))
               for n in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    engine.dispose()


if __name__ == "__main__":
    main()
