"""Application configuration loaded from environment variables.

All values are sourced from environment variables with `.env` file support.
Production deployments MUST set all required variables explicitly;
defaults exist for local development convenience only.
"""

import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "EcomAgent"
    debug: bool = False

    # Database — default SQLite for local dev; override via DATABASE_URL env var
    database_url: str = "sqlite:///./ecomagent.db"

    # Redis (optional for P0-core, required for P0-extended image tasks)
    redis_url: str = "redis://localhost:6379/0"

    # LLM — must be configured via environment for actual LLM usage
    # Provider selection is explicit, while credentials remain empty by
    # default.  This preserves deterministic mocked-Qwen test paths without
    # permitting a real call.
    llm_provider: str = "qwen"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # Google Gemini is the development default for text and image generation.
    google_api_key: str = ""
    google_text_model: str = "gemini-2.5-flash"
    google_image_model: str = "gemini-3.1-flash-image"

    # Image generation provider. Qwen remains available for later production use.
    image_provider: str = "qwen"
    image_gen_api_base: str = ""
    image_gen_api_key: str = ""

    @property
    def llm_configured(self) -> bool:
        """Check whether LLM API credentials have been set."""
        if self.llm_provider == "google":
            return bool(self.google_api_key and self.google_text_model)
        return bool(self.llm_api_base and self.llm_api_key and self.llm_model)

    @property
    def image_gen_configured(self) -> bool:
        """Check whether image generation API credentials have been set."""
        if self.image_provider == "google":
            return bool(self.google_api_key and self.google_image_model)
        return bool(self.image_gen_api_base and self.image_gen_api_key)

    class Config:
        # Secrets are injected by the deployment environment.  Loading a local
        # .env implicitly made tests capable of using a developer's real key.
        env_file = None if os.getenv("ECOMAGENT_TEST_MODE") == "1" else ".env"
        env_file_encoding = "utf-8"
        # Allow reading from OS environment (takes precedence over .env file)
        case_sensitive = False


settings = Settings()
