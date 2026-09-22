from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str

    PAYFAST_MERCHANT_ID: str
    PAYFAST_MERCHANT_KEY: str
    PAYFAST_PASSPHRASE: str = ""
    PAYFAST_SANDBOX: bool = True

    APP_BASE_URL: str
    FRONTEND_BASE_URL: str

    SMTP_HOST: str = "kregg.aserv.co.za"
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = "admin@dokotela-ai.com"
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "admin@dokotela-ai.com"

    AGORA_APP_ID: str = ""
    AGORA_APP_CERTIFICATE: str = ""

    # Remote GPU inference service
    LLM_SERVICE_URL: str
    LLM_MODEL_NAME: str = "google/medgemma-27b-text-it"
    RUNPOD_API_KEY: str
    #LLM_MODEL_NAME: str = "mlx-community/medgemma-27b-text-it-4bit"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    # Access tokens stay short-lived on purpose (stateless, no Redis cost).
    # Session "staying alive" is handled by the refresh token below, which
    # slides forward on activity - so an active user is never logged out,
    # but a genuinely idle user is kicked out after REFRESH_TOKEN_EXPIRE_MINUTES.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20

    # Idle timeout: refresh token TTL resets on every successful refresh, so
    # it only expires after this many minutes of *inactivity*.
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 20

    # Absolute safety-net cap on total session length regardless of activity
    # (defense in depth against an indefinitely-renewed stolen refresh token).
    REFRESH_TOKEN_ABSOLUTE_EXPIRE_HOURS: int = 24

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
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            file_secret_settings,
        )


settings = Settings()