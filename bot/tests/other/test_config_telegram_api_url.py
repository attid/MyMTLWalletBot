import pytest

from other.config_reader import Settings


@pytest.fixture
def required_env(monkeypatch):
    defaults = {
        "BOT_TOKEN": "0:test",
        "TEST_BOT_TOKEN": "0:test",
        "BASE_FEE": "100",
        "DB_URL": "sqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379/0",
        "TRON_API_KEY": "x",
        "TRON_MASTER_ADDRESS": "x",
        "TRON_MASTER_KEY": "x",
        "THOTHPAY_API": "x",
        "OPENAI_KEY": "x",
        "EURMTL_KEY": "x",
        "SENTRY_DSN": "",
        "HORIZON_URL": "https://horizon.stellar.org",
        "HORIZON_URL_RW": "https://horizon.stellar.org",
        "GRIST_TOKEN": "x",
        "TONCONSOLE_TOKEN": "x",
        "TON_TOKEN": "x",
        "WALLET_COST": "1.0",
    }
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("TELEGRAM_API_URL", raising=False)


def test_telegram_api_url_defaults_to_none(required_env):
    settings = Settings(_env_file=None)
    assert settings.telegram_api_url is None


def test_telegram_api_url_reads_from_env(required_env, monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_URL", "http://telegram-bot-api:8081")
    settings = Settings(_env_file=None)
    assert settings.telegram_api_url == "http://telegram-bot-api:8081"
