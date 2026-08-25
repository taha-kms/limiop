from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata base for application models and Alembic."""
