from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    POSTGRES_USER: str = "bazarfutures"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "bazarfutures"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "changeme_secret_key_min_32_chars_please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # Admin seed
    ADMIN_EMAIL: str = "admin@bazarfutures.com"
    ADMIN_PASSWORD: str = "admin123"

    # Business rules
    SECURITY_DEPOSIT_RATE: float = 0.15
    PLATFORM_COMMISSION_RATE: float = 0.01

    # Chaldal
    CHALDAL_BASE_URL: str = "https://chaldal.com"
    SCRAPE_SCHEDULE_HOUR: int = 9
    SCRAPE_SCHEDULE_MINUTE: int = 0

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
