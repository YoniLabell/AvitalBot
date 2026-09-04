"""Application settings, loaded from environment variables / .env."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_API_URL = "https://api.green-api.com"
DEFAULT_MEDIA_URL = "https://media.green-api.com"


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
    green_api_api_url: str = DEFAULT_API_URL
    # Files go to the media host, not the API host. Left blank it is derived
    # from green_api_api_url, so an instance host like
    # https://7105.api.greenapi.com becomes https://7105.media.greenapi.com.
    green_api_media_url: str = ""

    # Key expected in the X-Admin-Key header on /admin/* endpoints.
    admin_api_key: str = ""

    # Temporary customer state. On Render Free the filesystem is ephemeral,
    # so this file is lost on spin-down / restart / redeploy. To move to a
    # persistent disk later, only this value changes:
    #   DATA_FILE_PATH=/var/data/users.json
    data_file_path: str = "data/users.json"

    # Where images sent by the bot live, relative to the repository root.
    assets_dir: str = "assets"

    # Outgoing HTTP timeout, in seconds. Uploads get a longer one: GREEN-API
    # documents 1-20 seconds for a file, depending on its size.
    http_timeout_seconds: float = 15.0
    upload_timeout_seconds: float = 60.0

    # DEBUG also logs the full body of every webhook and GREEN-API response.
    log_level: str = "INFO"

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        """Trim env values so a stray space cannot corrupt a URL or a token."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("green_api_api_url", "green_api_media_url")
    @classmethod
    def _normalize_api_url(cls, value: str) -> str:
        # A blank value means "not set"; _build_settings applies the default.
        if not value:
            return value
        url = value.rstrip("/")
        if not url.startswith(("http://", "https://")):
            # A host pasted without a scheme is a common copy/paste slip.
            url = f"https://{url}"
        return url

    def configuration_problems(self) -> list[str]:
        """Human-readable list of everything that would stop the bot working."""
        problems: list[str] = []
        if not self.green_api_instance_id:
            problems.append("GREEN_API_INSTANCE_ID is not set - the bot cannot send anything.")
        elif not self.green_api_instance_id.isdigit():
            problems.append(
                f"GREEN_API_INSTANCE_ID should be digits only, got {self.green_api_instance_id!r}."
            )
        if not self.green_api_token:
            problems.append("GREEN_API_TOKEN is not set - the bot cannot send anything.")
        if not self.admin_api_key:
            problems.append("ADMIN_API_KEY is not set - the /admin endpoints will answer 503.")
        return problems


def derive_media_url(api_url: str) -> str:
    """The media host that goes with an API host."""
    for api_part, media_part in ((".api.", ".media."), ("//api.", "//media.")):
        if api_part in api_url:
            return api_url.replace(api_part, media_part, 1)
    return DEFAULT_MEDIA_URL


def _build_settings() -> Settings:
    """Blank values fall back to the field defaults rather than to ''."""
    settings = Settings()
    if not settings.green_api_api_url:
        settings.green_api_api_url = DEFAULT_API_URL
    if not settings.green_api_media_url:
        settings.green_api_media_url = derive_media_url(settings.green_api_api_url)
    if not settings.assets_dir:
        settings.assets_dir = "assets"
    if not settings.data_file_path:
        settings.data_file_path = "data/users.json"
    if not settings.log_level:
        settings.log_level = "INFO"
    return settings


settings = _build_settings()
