from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loads all secrets/config from the .env file in one place.

    Anywhere in the app you just write:
        from app.core.config import settings
        settings.DATABASE_URL
    so you never hardcode a password or URL in your code.
    """

    # The two Supabase connection strings from your .env
    DATABASE_URL: str       # app uses this to read/write data (port 6543)
    DIRECT_URL: str = ""    # Alembic uses this for migrations (port 5432)

    # Handy flags
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Tell pydantic to read values from the .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# One shared settings object the whole app imports
settings = Settings()
