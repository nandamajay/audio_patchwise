from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    default_model: str = "gpt-4o"
    max_rounds: int = 5
    db_url: str = "sqlite:///./data/patchwise.db"
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    model_config = SettingsConfigDict(
        env_prefix="PATCHWISE_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
