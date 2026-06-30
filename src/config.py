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

    # Watch source: "gdrive" (Google Drive folder) or "local" (folder watcher)
    watch_source: str = "gdrive"

    # Google Drive watcher
    gdrive_watch_path: str = "_documents_intake/techlab/invoicing_automation"
    gdrive_poll_interval_seconds: int = 30
    gdrive_db_path: Path = Path("data/gdrive.db")
    gdrive_processed_subfolder: str = "processed"
    gdrive_errors_subfolder: str = "errors"

    # Gmail OAuth
    gmail_credentials_file: Path = Path("config/credentials.json")
    gmail_token_file: Path = Path("config/token.json")
    oauth_callback_host: str = "localhost"  # For redirect URI (use VM IP in production)
    oauth_callback_port: int = 8080

    # Telegram
    telegram_bot_token: str
    telegram_bot_name: str = "InvoiceBot"
    telegram_chat_id: int
    telegram_debug_menu: bool = False  # Show debug keyboard with test buttons

    # Email addresses
    from_email: str
    manager_email: str
    invoicing_dept_email: str
    accountant_email: str

    # Invoice settings
    company_name: str = "YourCompany inc."
    hourly_rate: float = 10
    currency: str = "EUR"

    # LLM
    llm_provider: str = "gemini"  # "gemini" or "openai"
    llm_model: str = "gemini-2.0-flash-lite"
    llm_base_url: str = "https://ollama.lacny.me/v1"  # For openai provider
    llm_api_key: str = "ollama"  # For openai provider (Ollama ignores this)
    gemini_api_key: str = ""  # For gemini provider

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
