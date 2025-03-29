import os
from typing import List
from environs import Env
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

start_path = os.path.dirname(os.path.dirname(__file__))
dotenv_path = os.path.join(start_path, '.env')
env = Env()
env.read_env(dotenv_path)

horizont_urls = [
    'https://horizon.stellar.org',
    'https://horizon.stellar.lobstr.co',
]

class Settings(BaseSettings):
    bot_token: SecretStr
    test_bot_token: SecretStr
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
    mongodb_url: str
    grist_token: str
    tonconsole_token: str
    ton_token: str
    wallet_cost: float
    test_mode: bool = True
    fest_menu: dict = {}
    admins: list = []

    # horizon_url_id: Optional[int] = 0

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='allow',
        case_sensitive=False
    )


config = Settings()
config.admins = env.list("ADMIN_LIST", [84131737])


if os.getenv('ENVIRONMENT', 'test') == 'production':
    config.test_mode = False
    # BOT_TOKEN = os.getenv("BOT_TOKEN")
else:
    config.test_mode = True
    # BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")
