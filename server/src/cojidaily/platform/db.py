"""The database: one declarative Base for every module's tables, the engine, and a session per request.

Each module's tables carry the module's name as a prefix (auth_user, ledger_expense, ...), and a
table belongs to exactly one module. A foreign key between modules only points the way the
modules depend on each other (receipts -> ledger, never ledger -> receipts).

Services commit their own work: a request's session is opened by `get_db` and closed (rolling
back anything uncommitted) when the request ends.
"""
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Named constraints, so migrations can refer to them and autogenerate stays stable.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def make_engine(url: str, pool_size: int = 5) -> Engine:
    # A small pool: PostgreSQL gives every connection its own process (pm/decisions/rebuild-postgresql.md).
    return create_engine(url, pool_size=pool_size, max_overflow=pool_size, pool_pre_ping=True)


def make_sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as db:
        yield db


Db = Annotated[Session, Depends(get_db)]


# Work to undo when a transaction does not commit, such as files written before the rows that
# point at them (photos.service). Registered on the session inside a transaction; run once when
# that transaction ends without a commit (rollback, an error, or closing the session), forgotten
# when it commits.

def on_rollback(db: Session, undo: Callable[[], None]) -> None:
    db.info.setdefault("on_rollback", []).append(undo)


@event.listens_for(Session, "after_commit")
def _forget(db: Session) -> None:
    db.info.pop("on_rollback", None)


@event.listens_for(Session, "after_transaction_end")
def _undo(db: Session, transaction) -> None:
    if transaction.parent is None:  # the outermost transaction, and after_commit did not clear it
        for undo in reversed(db.info.pop("on_rollback", [])):
            undo()
