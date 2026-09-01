import os
import math
from typing import Optional
from environs import Env
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

start_path = os.path.dirname(os.path.dirname(__file__))
dotenv_path = os.path.join(start_path, ".env")
env = Env()
env.read_env(dotenv_path)

horizont_urls = [
    "https://horizon.stellar.org",
    "https://horizon.stellar.lobstr.co",
]


class Settings(BaseSettings):
    bot_token: SecretStr
    test_bot_token: SecretStr
    telegram_api_url: Optional[str] = None
    base_fee: int
    db_url: str
    redis_url: str
    tron_api_key: SecretStr
    tron_master_address: str
    tron_master_key: SecretStr
    thothpay_api: SecretStr
    openai_key: SecretStr
    eurmtl_key: str
    sentry_dsn: str
    horizon_url: str
    horizon_url_rw: str
    mongodb_url: Optional[str] = None
    grist_token: str
    grist_base_url: str = "https://grist.eurmtl.me/api/docs"
    tonconsole_token: str
    ton_token: str
    wallet_cost: float
    test_mode: bool = True
    admins: list = []

    # Master Key Encryption Password (defaults to "0" for backward compatibility)
    master_password: SecretStr = SecretStr("0")

    # Wallet crypto v2 KEK (required in production)
    wallet_kek: SecretStr = SecretStr("dev-wallet-kek-change-me")
    wallet_kek_old: Optional[SecretStr] = None

    toncenter_token: Optional[str] = None
    debank: Optional[SecretStr] = None
    start_path: str = start_path

    notifier_url: Optional[str] = "http://operations-notifier:8000"
    webhook_public_url: Optional[str] = "http://mmwb_bot:8081/webhook"
    webhook_port: int = 8081

    # Delayed blockchain notification delivery.
    notification_hold_seconds: int = 120
    notification_delivery_poll_interval_seconds: float = 5.0
    notification_delivery_batch_size: int = 100

    @field_validator("notification_delivery_poll_interval_seconds")
    @classmethod
    def validate_notification_delivery_poll_interval(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "notification_delivery_poll_interval_seconds must be finite and positive"
            )
        return value

    # Security for Notification Service
    notifier_public_key: Optional[str] = (
        None  # Public Key of the Notifier Service to verify webhooks
    )
    service_secret: Optional[SecretStr] = (
        None  # Secret Key to sign requests to Notifier
    )
    notifier_auth_token: Optional[str] = (
        None  # Token for Notifier Authentication (alternative to signature)
    )

    # Web App for biometric signing
    webapp_url: str = "https://webapp.example.com"

    # horizon_url_id: Optional[int] = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False,
        protected_namespaces=(),
    )


config = Settings()
config.admins = env.list("ADMIN_LIST", [84131737])


if os.getenv("ENVIRONMENT", "test") == "production":
    config.test_mode = False
    # BOT_TOKEN = os.getenv("BOT_TOKEN")
else:
    config.test_mode = True
    # BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")
