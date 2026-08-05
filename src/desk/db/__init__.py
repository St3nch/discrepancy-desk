"""Database access — SQLAlchemy Core only."""

from desk.db.engine import apply_connection_pragmas, create_db_engine
from desk.db.schema import metadata

__all__ = ["create_db_engine", "apply_connection_pragmas", "metadata"]
