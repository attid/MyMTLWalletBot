import os

from pydantic import BaseSettings, SecretStr

start_path = os.path.dirname(__file__)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')

class Settings(BaseSettings):
    bot_token: SecretStr
    test_bot_token: SecretStr
    base_fee: int
    db_dns: str
    db_user: str
    db_password: SecretStr
    tron_api_key: SecretStr
    tron_master_address: str
    tron_master_key: SecretStr
    thothpay_api: SecretStr
    openai_key: SecretStr

    class Config:
        env_file = dotenv_path
        env_file_encoding = 'utf-8'


config = Settings()
