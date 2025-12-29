from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Canonical database
    database_url: str = (
        "postgresql+psycopg://monassmat:monassmat@localhost:5432/monassmat"
    )

    app_name: str = "MonAssmat"
    debug: bool = True


settings = Settings()
