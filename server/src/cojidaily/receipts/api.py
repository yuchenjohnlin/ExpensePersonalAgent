"""What the rest of the app uses from receipts: the worker's handler. (Nothing depends on receipts yet.)"""
from functools import partial

from ..platform.jobs import Handler
from ..platform.settings import Settings
from . import service


def handlers(settings: Settings) -> dict[str, Handler]:
    return {service.AFTER_READING: partial(service.after_reading, settings=settings)}
