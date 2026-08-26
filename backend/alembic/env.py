import asyncio

from alembic import context
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
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Imported for its side effect of registering the table on the shared
# metadata below, not for direct use.
from app.modules.accounts.models import User  # noqa: F401
from app.modules.cvs.models import CV  # noqa: F401
from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill  # noqa: F401

config = context.config
target_metadata = Base.metadata

BACKEND_TABLES = frozenset(
    {
        "candidate_profile_skills",
        "candidate_profiles",
        "cvs",
        "users",
    }
)


def database_url() -> str:
    return str(get_settings().database_url)


def include_object(
    _object: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object | None,
) -> bool:
    return type_ != "table" or name in BACKEND_TABLES


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


def configure_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
        version_table="alembic_version",
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
