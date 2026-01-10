import asyncio
from logging.config import fileConfig
from typing import Iterable, Optional, Union

from alembic import context
from alembic.operations import MigrationScript
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import AppConfig
from src.infrastructure.database.models.sql import BaseSql

config = context.config
app_config = AppConfig.get()
db_config = app_config.database

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = BaseSql.metadata


def process_revision_directives(
    context: MigrationContext,
    revision: Union[str, Iterable[Optional[str]], Iterable[str]],
    directives: list[MigrationScript],
) -> None:
    migration_script = directives[0]

    script_directory = ScriptDirectory.from_config(config)
    head_revision = script_directory.get_current_head()

    if head_revision is None:
        new_rev_id = 1
    else:
        last_rev_id = int(head_revision.lstrip("0"))
        new_rev_id = last_rev_id + 1

    migration_script.rev_id = f"{new_rev_id:04}"


def run_migrations_offline() -> None:
    url = db_config.dsn
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
        crypt_key=app_config.crypt_key.get_secret_value(),
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        process_revision_directives=process_revision_directives,
        crypt_key=app_config.crypt_key.get_secret_value(),
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    configuration = context.config
    
    configuration.set_main_option(
        "sqlalchemy.url",
        db_config.dsn
    )

    connectable = create_async_engine(
        db_config.dsn,
        future=True,
        echo=False,
    )

    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
