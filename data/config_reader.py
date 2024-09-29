import os
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings

start_path = os.path.dirname(__file__)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')

horizont_urls = [
    'https://horizon.stellar.org',
    'https://horizon.stellar.lobstr.co',
]


class Settings(BaseSettings):
    bot_token: SecretStr
    test_bot_token: SecretStr
    base_fee: int
    db_dns: str
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
    test_mode: bool = False

    # horizon_url_id: Optional[int] = 0

    class Config:
        env_file = dotenv_path
        env_file_encoding = 'utf-8'


config = Settings()

if os.getenv('ENVIRONMENT', 'test') == 'production':
    config.test_mode = False
    # BOT_TOKEN = os.getenv("BOT_TOKEN")
else:
    config.test_mode = True
    # BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")
