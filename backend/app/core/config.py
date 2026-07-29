"""Application configuration loaded from environment variables.

Normal local runtime loads ``backend/.env``. Pytest sets
``ECOMAGENT_TEST_MODE=1`` before importing this module, which disables dotenv
loading so tests cannot inherit a developer Provider credential.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_UPLOAD_DIR = str(Path(__file__).resolve().parents[2] / "uploads")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None if os.getenv("ECOMAGENT_TEST_MODE") == "1" else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "EcomAgent"
    debug: bool = False
    database_url: str = "sqlite:///./ecomagent.db"
    upload_dir: str = _DEFAULT_UPLOAD_DIR
    jwt_secret: str = "ecomagent-local-development-secret"

    llm_provider: str = "qwen"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    google_api_key: str = ""
    google_text_model: str = "gemini-2.5-flash"
    google_image_model: str = "gemini-3.1-flash-image"

    image_provider: str = "qwen"
    image_gen_api_base: str = ""
    image_gen_api_key: str = ""
    image_gen_model: str = "qwen-image-2.0"
    image_gen_output_count: int = 3

    @field_validator("image_gen_model")
    @classmethod
    def validate_image_gen_model(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != "qwen-image-2.0":
            raise ValueError("P0 IMAGE_GEN_MODEL must be qwen-image-2.0")
        return normalized

    @field_validator("image_gen_api_base")
    @classmethod
    def validate_image_gen_api_base(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            return normalized

        parsed = urlsplit(normalized)
        hostname = (parsed.hostname or "").lower()
        if hostname == "dashscope.aliyuncs.com":
            raise ValueError(
                "legacy public DashScope IMAGE_GEN_API_BASE is unsupported; "
                "migrate to the matching cn-beijing Workspace-specific endpoint"
            )
        if parsed.scheme.lower() != "https":
            raise ValueError("P0 IMAGE_GEN_API_BASE must use HTTPS")

        workspace_suffix = ".cn-beijing.maas.aliyuncs.com"
        workspace_id = hostname.removesuffix(workspace_suffix)
        is_workspace_endpoint = (
            hostname.endswith(workspace_suffix)
            and bool(workspace_id)
            and parsed.path.rstrip("/") == "/api/v1"
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
        )
        if not is_workspace_endpoint:
            raise ValueError(
                "P0 IMAGE_GEN_API_BASE must use a cn-beijing Workspace-specific "
                "HTTPS endpoint ending in /api/v1"
            )
        return normalized
    @field_validator("image_gen_output_count")
    @classmethod
    def validate_image_gen_output_count(cls, value: int) -> int:
        if value != 3:
            raise ValueError("P0 IMAGE_GEN_OUTPUT_COUNT must be 3")
        return value

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "google":
            return bool(self.google_api_key and self.google_text_model)
        return bool(self.llm_api_base and self.llm_api_key and self.llm_model)

    @property
    def image_gen_configured(self) -> bool:
        if self.image_provider == "google":
            return bool(self.google_api_key and self.google_image_model)
        return bool(
            self.image_gen_api_base
            and self.image_gen_api_key
            and self.image_gen_model
        )


settings = Settings()