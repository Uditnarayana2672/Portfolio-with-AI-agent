from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """The single shared base class for every table (model) in the app.

    SQLAlchemy uses Base.metadata as the registry of all tables, which is how
    sessions and Alembic migrations know about your schema. Every model in
    app/models/models.py inherits from this one Base.
    """
    pass
