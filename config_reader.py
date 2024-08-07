import os

from pydantic import SecretStr
from pydantic_settings import BaseSettings

start_path = os.path.dirname(__file__)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')

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

    class Config:
        env_file = dotenv_path
        env_file_encoding = 'utf-8'


config = Settings()
