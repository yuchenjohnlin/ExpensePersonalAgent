"""Migrations are written by hand; tests/test_migrations.py checks they make exactly the models' schema.

PostgreSQL runs each migration's DDL inside the transaction, so a failed migration leaves nothing behind.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from cojidaily.models import metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name)

url = config.get_main_option("sqlalchemy.url") or os.environ["COJI_DATABASE_URL"]

if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
