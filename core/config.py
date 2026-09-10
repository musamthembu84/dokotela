from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    #DATABASE_URL: str = "jdbc:postgresql://localhost:5432/postgres"
    DATABASE_URL: str
    REDIS_URL: str

    PAYFAST_MERCHANT_ID: str
    PAYFAST_MERCHANT_KEY: str
    PAYFAST_PASSPHRASE: str = ""

    PAYFAST_SANDBOX: bool = True
    APP_BASE_URL: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@dokotela.com"

    AGORA_APP_ID: str = ""
    AGORA_APP_CERTIFICATE: str = ""

    # NOTE: kept as the previous hardcoded value so existing tokens/sessions
    # remain valid after this refactor. Override via .env in real deployments.
    SECRET_KEY: str = "YmM4NzY0ZDVjZGI3MmRmZjRhOTk5ZWMyNjliMWE5MDViMjZlMTBhYWQzYWJkMTlhYzQ5MGI3NTVhYWQ2NDY4Ng=="
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Give .env file values priority over ambient shell environment
        # variables (e.g. a stale/placeholder AGORA_APP_ID exported in the
        # shell) so local development always reflects the .env file.
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            file_secret_settings,
        )


settings = Settings()
