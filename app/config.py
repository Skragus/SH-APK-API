from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY: str
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str
    DB_WRITE_LOG_FILE: str = "logs/db_writes.log"

    class Config:
        env_file = ".env"


settings = Settings()
