from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loads all secrets/config from the .env file in one place.

    Anywhere in the app you just write:
        from app.infrastructure.config import settings
        settings.DATABASE_URL
    so you never hardcode a password or URL in your code.
    """

    # The two Supabase connection strings from your .env
    DATABASE_URL: str       # app uses this to read/write data (port 6543)
    DIRECT_URL: str = ""    # Alembic uses this for migrations (port 5432)

    # ── Supabase Auth ────────────────────────────────────────────────────
    # SUPABASE_URL: project base URL. Also used to derive the JWKS endpoint.
    # SUPABASE_ANON_KEY: modern publishable key (sb_publishable_...). Safe in
    #   frontend; required for client logins via /auth/v1/token.
    # SUPABASE_JWT_SECRET: legacy HS256 secret. Kept for reference only —
    #   verify_supabase_jwt() uses asymmetric JWKS, not this.
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str = ""

    # JWTs include an "aud" (audience) claim. Supabase sets it to "authenticated"
    # for any logged-in user. We pass this into jose.decode() so a token issued
    # for some other audience (e.g. internal service) is rejected.
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # ── Cloudinary ───────────────────────────────────────────────────────
    # Image/media storage. Set either CLOUDINARY_URL alone, or the three
    # CLOUDINARY_* fields. The CloudinaryImageStorage adapter reads these.
    CLOUDINARY_URL: str = ""
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_DEFAULT_FOLDER: str = "portfolio"

    # Handy flags
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Tell pydantic to read values from the .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# One shared settings object the whole app imports
settings = Settings()
