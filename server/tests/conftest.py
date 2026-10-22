"""Tests run against a real PostgreSQL (server/dev.sh test sets COJI_TEST_DATABASE_URL to a server).

Once per run the database cojidaily_test is made afresh with the migrations; before each test
every table is emptied.
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from cojidaily import cli
from cojidaily.main import create_app
from cojidaily.models import metadata
from cojidaily.platform.jobs import Worker
from cojidaily.platform.settings import Settings
from cojidaily.worker import handlers

from .fake_vllm import MODEL, FakeVllm

SERVER = Path(__file__).resolve().parents[1]
NAME = "cojidaily_test"


def alembic_config(url: str) -> Config:
    config = Config(str(SERVER / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logging"] = False
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    server = os.environ.get("COJI_TEST_DATABASE_URL")
    if not server:
        pytest.exit("COJI_TEST_DATABASE_URL is not set; run the tests with server/dev.sh test", returncode=2)
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {NAME}"))
    admin.dispose()
    url = make_url(server).set(database=NAME).render_as_string(hide_password=False)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture(scope="session")
def engine(database_url):
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def empty_tables(request):
    """Every table emptied before a test that uses the database; tests without one need no server."""
    if "database_url" in request.fixturenames:
        names = ", ".join(table.name for table in metadata.sorted_tables)
        with request.getfixturevalue("engine").begin() as connection:
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def fake_vllm_server():
    server = FakeVllm()
    yield server
    server.server.shutdown()


@pytest.fixture
def vllm(fake_vllm_server):
    """The fake vLLM the app reads with; by default it answers a valid Kroger receipt."""
    fake_vllm_server.reset()
    return fake_vllm_server


@pytest.fixture
def settings(database_url, tmp_path, vllm) -> Settings:
    return Settings(database_url=database_url, secret_key="test secret", blob_root=str(tmp_path / "blobs"),
                    db_pool_size=2, vllm_base_url=vllm.base_url, vllm_model=MODEL, vllm_timeout_seconds="10")


@pytest.fixture
def worker(app, settings):
    """The background worker, run by hand: worker.run_until_idle()."""
    return Worker(app.state.sessions, handlers(settings))


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def sessions(app):
    return app.state.sessions


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


PASSWORD = "correct horse battery"


def make_user(sessions, username="yuchen", password=PASSWORD):
    """An account as the CLI makes it, with what every module gives a new account."""
    with sessions() as db:
        user_id = cli.create_user(db, username, password)
        db.commit()
    return user_id


def sign_in(client, username="yuchen", password=PASSWORD) -> dict:
    """Sign in as the page does, and send the new CSRF token with every later request."""
    token = client.get("/api/session").json()["csrf_token"]
    response = client.post("/api/auth/login", json={"username": username, "password": password},
                           headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


@pytest.fixture
def owner(sessions):
    return make_user(sessions)


@pytest.fixture
def signed(client, owner):
    """A client signed in as `owner`."""
    sign_in(client)
    return client
