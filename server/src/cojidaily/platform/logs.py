"""Logging for the API and the worker: INFO and up, one line each on stderr.

Under `opentelemetry-instrument` with logs on (deploy/compose.yaml) the SDK has already put its own
handler on the root logger before our code runs. logging.basicConfig() then does nothing and the
root stays at WARNING, so the INFO lines would reach neither the console nor the collector. This
sets the level and adds the console handler beside whatever is there.
"""
import logging

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(type(handler) is logging.StreamHandler for handler in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(console)
