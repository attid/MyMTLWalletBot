from pydantic import BaseSettings, SecretStr


class Settings(BaseSettings):
    bot_token: SecretStr
    test_bot_token: SecretStr
    base_fee: int

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


config = Settings()
