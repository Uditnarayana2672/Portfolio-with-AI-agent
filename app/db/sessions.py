from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# The "engine" is the live connection pool to your Supabase database.
# pool_pre_ping=True quietly checks a connection is still alive before using
# it, which avoids errors when Supabase drops idle connections.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# A "session" is one conversation with the database. We open a fresh one for
# each web request and close it when the request finishes.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: gives an endpoint a database session, then makes
    sure it's always closed afterwards — even if an error happens."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
