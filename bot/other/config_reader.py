import os
import math
from typing import Optional
from environs import Env
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.constants import (  # type: ignore[import-untyped]
    DEFAULT_NETWORK_PASSPHRASE,
)

start_path = os.path.dirname(os.path.dirname(__file__))
dotenv_path = os.path.join(start_path, ".env")
env = Env()
env.read_env(dotenv_path)

READ_ONLY_ENDPOINT_SUFFIX = "|ro"


def parse_horizon_endpoints(raw: str) -> list[str]:
    """Split ``HORIZON_URLS`` into endpoints preserving priority order.

    Empty items are dropped and duplicates keep their first position. A trailing
    ``|ro`` marks a read-only node: it is never used for transaction submission.
    """
    endpoints: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        is_read_only = value.lower().endswith(READ_ONLY_ENDPOINT_SUFFIX)
        key = (
            value[: -len(READ_ONLY_ENDPOINT_SUFFIX)].strip() if is_read_only else value
        ).rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        endpoints.append(value)
    return endpoints


class Settings(BaseSettings):
    bot_token: SecretStr
    test_bot_token: SecretStr
    telegram_api_url: Optional[str] = None
    base_fee: int
    db_url: str
    redis_url: str
    network_passphrase: str = DEFAULT_NETWORK_PASSPHRASE
    tron_api_key: SecretStr
    tron_master_address: str
    tron_master_key: SecretStr
    thothpay_api: SecretStr
    openai_key: SecretStr
    eurmtl_key: str
    sentry_dsn: str
    # Horizon endpoint pool: comma-separated, priority order, primary first.
    # A trailing "|ro" marks a read-only node (never used for submission).
    # There is no hardcoded fallback: a missing value fails startup on purpose.
    horizon_urls: str
    horizon_endpoints: list[str] = []
    # Horizon failover tuning (see infrastructure/services/horizon_pool.py).
    horizon_failover_budget_seconds: float = 25.0
    horizon_failover_max_attempts: int = 3
    horizon_request_timeout_seconds: float = 8.0
    horizon_post_timeout_seconds: float = 15.0
    horizon_rate_limit_cooldown_seconds: float = 60.0
    horizon_server_error_cooldown_seconds: float = 30.0
    horizon_max_cooldown_seconds: float = 600.0
    horizon_sticky_seconds: float = 60.0
    horizon_freeze_switch_threshold: int = 5
    horizon_freeze_window_seconds: float = 600.0
    grist_token: str
    grist_base_url: str = "https://grist.eurmtl.me/api/docs"
    tonconsole_token: str
    ton_token: str
    wallet_cost: float
    test_mode: bool = True
    # E2E harness switches: default keeps production behaviour (workers running).
    disable_workers: bool = False
    disable_scheduler: bool = False
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
    # Outbound chat pacing: Telegram per-chat flood limits are the bottleneck.
    notification_chat_min_interval_seconds: float = 1.0
    notification_chat_cooldown_max_seconds: float = 3600.0
    # One message per transaction: keep the first N fills and the remaining count.
    notification_bundle_max_lines: int = 15

    @model_validator(mode="after")
    def parse_horizon_url_pool(self):
        endpoints = parse_horizon_endpoints(self.horizon_urls)
        if not endpoints:
            raise ValueError("HORIZON_URLS must list at least one horizon endpoint")
        self.horizon_endpoints = endpoints
        return self

    @field_validator(
        "horizon_failover_budget_seconds",
        "horizon_request_timeout_seconds",
        "horizon_post_timeout_seconds",
        "horizon_rate_limit_cooldown_seconds",
        "horizon_server_error_cooldown_seconds",
        "horizon_max_cooldown_seconds",
        "horizon_sticky_seconds",
        "horizon_freeze_window_seconds",
    )
    @classmethod
    def validate_horizon_positive_seconds(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("horizon timing settings must be finite and positive")
        return value

    @field_validator("horizon_failover_max_attempts", "horizon_freeze_switch_threshold")
    @classmethod
    def validate_horizon_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("horizon pool counters must be positive")
        return value

    @field_validator("notification_delivery_poll_interval_seconds")
    @classmethod
    def validate_notification_delivery_poll_interval(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "notification_delivery_poll_interval_seconds must be finite and positive"
            )
        return value

    @field_validator("notification_chat_min_interval_seconds")
    @classmethod
    def validate_notification_chat_min_interval(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "notification_chat_min_interval_seconds must be finite and positive"
            )
        return value

    @field_validator("notification_chat_cooldown_max_seconds")
    @classmethod
    def validate_notification_chat_cooldown_max(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "notification_chat_cooldown_max_seconds must be finite and positive"
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

    # Internal read-only API (username -> address) for trusted local services.
    internal_api_host: str = "127.0.0.1"
    internal_api_port: int = 8082
    internal_api_token: Optional[SecretStr] = None

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
