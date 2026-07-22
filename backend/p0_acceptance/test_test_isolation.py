"""Acceptance checks that prevent accidental use of deployment credentials/network."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


KEY_VARIABLES = (
    "GOOGLE_API_KEY",
    "LLM_API_KEY",
    "IMAGE_GEN_API_KEY",
    "IMAGE_API_KEY",
    "DASHSCOPE_API_KEY",
)


def test_app_boots_without_any_real_provider_key_or_network(tmp_path):
    """C-Q04: import/configuration must work from an env with no credential file.

    The subprocess runs outside ``backend`` so pydantic-settings cannot locate
    ``backend/.env`` via its relative ``.env`` setting.  It also removes known
    provider variables and blocks sockets before importing the app.
    """
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for key in KEY_VARIABLES:
        env.pop(key, None)
    env["ECOMAGENT_TEST_MODE"] = "1"
    env["PYTHONPATH"] = str(backend_dir)
    program = """
import socket
def blocked(*args, **kwargs):
    raise AssertionError('network access during test app boot')
socket.create_connection = blocked
socket.socket.connect = blocked
from app.core.config import settings
from app.main import app
assert not settings.google_api_key
assert not settings.llm_api_key
assert not settings.image_gen_api_key
assert app is not None
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_normal_application_settings_read_a_local_env_file(tmp_path):
    """Normal startup keeps the deployment .env loading behaviour."""
    backend_dir = Path(__file__).resolve().parents[1]
    (tmp_path / ".env").write_text(
        "LLM_API_KEY=local-config-sentinel\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env.pop("ECOMAGENT_TEST_MODE", None)
    env.pop("LLM_API_KEY", None)
    env["PYTHONPATH"] = str(backend_dir)
    result = subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; assert settings.llm_api_key == 'local-config-sentinel'"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
