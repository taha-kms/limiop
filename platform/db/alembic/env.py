import asyncio
import os

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from platform_db.base import Base
from platform_db.models import (  # noqa: F401
    Company,
    Job,
    JobProvenance,
    JobSkill,
    JobSkillMention,
    JobSource,
    SkillAliasVersion,
    SkillConcept,
    SkillSurfaceForm,
)

config = context.config
target_metadata = Base.metadata

PLATFORM_TABLES = frozenset(
    {
        "companies",
        "job_provenance",
        "job_skill_mentions",
        "job_skills",
        "job_sources",
        "jobs",
        "skill_alias_versions",
        "skill_concepts",
        "skill_surface_forms",
    }
)


def database_url() -> str:
    return os.environ.get(
        "SKILLSYNC_DATABASE_URL",
        config.get_main_option("sqlalchemy.url"),
    )


def include_object(
    _object: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object | None,
) -> bool:
    return type_ != "table" or name in PLATFORM_TABLES


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
        version_table="alembic_version_platform",
    )

    with context.begin_transaction():
        context.run_migrations()


def configure_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
        version_table="alembic_version_platform",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(configure_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
