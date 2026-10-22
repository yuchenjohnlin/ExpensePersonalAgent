"""Administration from the command line: `python -m cojidaily.cli createuser NAME` or `setpassword NAME`.

There is no sign-up page; accounts are made here. The password is read from the terminal (twice),
or as one line from stdin when piped.
"""
import argparse
import getpass
import sys

from .platform.db import make_engine, make_sessions
from .platform.errors import ApiError
from .platform.settings import Settings


def read_password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    first, second = getpass.getpass("Password: "), getpass.getpass("Again: ")
    if first != second:
        sys.exit("The two passwords differ.")
    return first


def create_user(db, username: str, password: str):
    """An account, and what each module gives a new account."""
    from .auth import api as auth
    from .ledger import api as ledger

    user_id = auth.create_user(db, username, password)
    ledger.ensure_categories(db, user_id)
    return user_id


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m cojidaily.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("createuser", "setpassword"):
        commands.add_parser(name).add_argument("username")
    args = parser.parse_args(argv)
    engine = make_engine(Settings.from_env().database_url, 1)
    try:
        with make_sessions(engine)() as db:
            if args.command == "createuser":
                create_user(db, args.username, read_password())
            else:
                from .auth import api as auth

                if not auth.set_password(db, args.username, read_password()):
                    sys.exit(f"No account named {args.username!r}.")
            db.commit()
    except ApiError as error:
        sys.exit("; ".join(message for messages in (error.fields or {}).values() for message in messages)
                 or error.error)
    finally:
        engine.dispose()
    print("Done.")


if __name__ == "__main__":
    main()
