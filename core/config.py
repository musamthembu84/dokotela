from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "jdbc:postgresql://localhost:5432/postgres"

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

    SECRET_KEY: str = "changeme"
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
