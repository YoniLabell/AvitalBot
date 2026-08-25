"""Application settings, loaded from environment variables / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # GREEN-API credentials. Request format is:
    #   {api_url}/waInstance{instance_id}/{method}/{token}
    green_api_instance_id: str = ""
    green_api_token: str = ""
    green_api_api_url: str = "https://api.green-api.com"

    # Key expected in the X-Admin-Key header on /admin/* endpoints.
    admin_api_key: str = ""

    # Temporary customer state. On Render Free the filesystem is ephemeral,
    # so this file is lost on spin-down / restart / redeploy. To move to a
    # persistent disk later, only this value changes:
    #   DATA_FILE_PATH=/var/data/users.json
    data_file_path: str = "data/users.json"

    # Outgoing HTTP timeout, in seconds.
    http_timeout_seconds: float = 15.0


settings = Settings()
