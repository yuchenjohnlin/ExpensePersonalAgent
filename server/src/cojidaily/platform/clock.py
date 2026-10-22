"""Time. Stored times are UTC; "today" is the ledger's date in the app's timezone (Settings.timezone)."""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def now() -> datetime:
    return datetime.now(UTC)


def today(timezone: str) -> date:
    return now().astimezone(ZoneInfo(timezone)).date()
