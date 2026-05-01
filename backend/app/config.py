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
    llm_provider: str = "mock"
    llm_model: str = "local"
    llm_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    qualcomm_api_key: str = ""

    model_config = SettingsConfigDict(
        env_prefix="PATCHWISE_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
