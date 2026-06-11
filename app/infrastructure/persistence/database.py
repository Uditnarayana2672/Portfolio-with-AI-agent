"""Database engine, session factory, and the declarative Base.

Infrastructure layer — the SQLAlchemy / Supabase Postgres adapter. Only
infrastructure (ORM models, repositories) and the API composition root import
from here; the domain and application layers never do.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.infrastructure.config import settings


class Base(DeclarativeBase):
    """The single shared base class for every table (model) in the app.

    SQLAlchemy uses Base.metadata as the registry of all tables, which is how
    sessions and Alembic migrations know about your schema. Every ORM model in
    app/infrastructure/persistence/orm/ inherits from this one Base.
    """
    pass


# The "engine" is the live connection pool to your Supabase database.
# pool_pre_ping=True quietly checks a connection is still alive before using
# it, which avoids errors when Supabase drops idle connections.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# A "session" is one conversation with the database. We open a fresh one for
# each web request and close it when the request finishes.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: gives an endpoint a database session, commits on a
    clean request, rolls back if anything raised, and always closes.

    Making the request the transaction boundary keeps the domain/application
    layers free of commit/rollback concerns — repositories only add & flush.
    Read-only endpoints commit a no-op, which is harmless.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
