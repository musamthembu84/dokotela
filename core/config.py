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
    # 20 minutes was too short: patients/doctors often schedule a visit well
    # ahead of time and only come back at the appointed slot to join, so a
    # short-lived token with no refresh flow would silently expire and
    # produce a hard 401 on /visits/{id}/join. Bump this to a full day so a
    # normal login stays valid for the whole session (book -> wait -> join).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

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