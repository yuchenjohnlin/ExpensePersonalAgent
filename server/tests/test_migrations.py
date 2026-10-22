"""The hand-written migrations make exactly the schema the models describe."""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from cojidaily.models import metadata


def test_migrations_match_the_models(engine):
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), metadata)
    assert differences == []


def test_the_app_answers(client):
    assert client.get("/api/health").json() == {"ok": True}
    unknown = client.get("/api/nothing-here")
    assert unknown.status_code == 404
    assert unknown.json() == {"error": "找不到資源。"}
