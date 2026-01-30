"""Configuration module using Pydantic settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Folders
    watch_folder: Path = Path("data/incoming")
    archive_folder: Path = Path("data/archive")

    # Gmail OAuth
    gmail_credentials_file: Path = Path("config/credentials.json")
    gmail_token_file: Path = Path("config/token.json")
    oauth_callback_host: str = "localhost"  # For redirect URI (use VM IP in production)
    oauth_callback_port: int = 8080

    # Telegram
    telegram_bot_token: str
    telegram_bot_name: str = "InvoiceBot"
    telegram_chat_id: int

    # Email addresses
    from_email: str
    manager_email: str
    invoicing_dept_email: str
    accountant_email: str

    # Invoice settings
    hourly_rate: int = 10
    currency: str = "EUR"

    # LLM
    gemini_api_key: str

    # Email monitoring
    gmail_poll_interval: int = 60  # Seconds between email checks

    # Email matching
    approval_keywords: str = "approved,schvalene,schvalujem,suhlasim,ok,v poriadku"

    @property
    def approval_keywords_list(self) -> list[str]:
        """Parse approval keywords into a list."""
        return [kw.strip().lower() for kw in self.approval_keywords.split(",")]


# Global settings instance
settings = Settings()
