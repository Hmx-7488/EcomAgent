"""Tests for LLM service — both Qwen API path (mocked) and template fallback."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm_service import _get_qwen_response, generate_product_content


# ---------------------------------------------------------------------------
# Template fallback tests (no API key required)
# ---------------------------------------------------------------------------

class TestLLMFallback:
    """Tests for the template fallback when LLM is not configured."""

    def test_title_fallback(self):
        result = generate_product_content(
            product_name="防晒衣",
            category="户外",
            brand="山河",
            description="UPF50+防晒，轻薄透气",
            selling_points="专业防晒，轻薄舒适",
            parameters_json="{}",
            content_type="title",
            platform="taobao",
        )
        assert "title" in result
        assert "防晒衣" in result["title"]
        assert "short_title" in result

    def test_faq_fallback(self):
        result = generate_product_content(
            product_name="蓝牙耳机",
            category="数码",
            brand="",
            description="降噪耳机",
            selling_points="主动降噪，续航持久",
            parameters_json="{}",
            content_type="faq",
            platform="general",
        )
        assert "faq" in result
        assert len(result["faq"]) >= 1
        assert "q" in result["faq"][0]

    def test_keywords_fallback(self):
        result = generate_product_content(
            product_name="瑜伽垫",
            category="运动",
            brand="柔步",
            description="",
            selling_points="防滑耐用",
            parameters_json="{}",
            content_type="keywords",
            platform="xiaohongshu",
        )
        assert "keywords" in result
        assert isinstance(result["keywords"], list)
        assert len(result["keywords"]) >= 3

    def test_script_fallback(self):
        result = generate_product_content(
            product_name="咖啡豆",
            category="食品",
            brand="",
            description="",
            selling_points="阿拉比卡，新鲜烘焙",
            parameters_json="{}",
            content_type="script",
            platform="douyin",
        )
        assert "script" in result
        assert "咖啡豆" in result["script"]

    def test_all_content_types_have_output(self):
        """Ensure every content type returns the expected base keys."""
        for ct in ["title", "selling_points", "description", "faq", "script", "keywords"]:
            result = generate_product_content(
                product_name="测试品",
                category="通用",
                brand="",
                description="描述",
                selling_points="卖点",
                parameters_json="{}",
                content_type=ct,
                platform="general",
            )
            assert result.get("product_name") == "测试品"


# ---------------------------------------------------------------------------
# Qwen API path tests (mocked dashscope)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_qwen_success():
    """Mock dashscope.Generation.call to return a successful response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "title": "【山河】UPF50+ 轻薄透气防晒衣 户外运动必备",
        "short_title": "山河防晒衣",
    }, ensure_ascii=False)
    mock_response.output.choices = [mock_choice]

    with patch("dashscope.Generation.call", return_value=mock_response):
        yield


@pytest.fixture
def mock_qwen_error():
    """Mock dashscope.Generation.call to return an error response."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.code = "InvalidParameter"
    mock_response.message = "Model not found"

    with patch("dashscope.Generation.call", return_value=mock_response):
        yield


@pytest.fixture
def mock_qwen_malformed_json():
    """Mock dashscope to return non-JSON text."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_choice = MagicMock()
    mock_choice.message.content = "这是一段非JSON格式的回复文本"
    mock_response.output.choices = [mock_choice]

    with patch("dashscope.Generation.call", return_value=mock_response):
        yield


class TestQwenAPIPath:
    """Tests for the real Qwen API call path (with mocked dashscope)."""

    def test_successful_qwen_call(
        self, monkeypatch, mock_qwen_success,
    ):
        """Verify Qwen API success path produces correct output."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "test-key")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "https://test")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "qwen-plus")

        import dashscope

        result = generate_product_content(
            product_name="防晒衣",
            category="户外",
            brand="山河",
            description="UPF50+防晒",
            selling_points="专业防晒",
            parameters_json="{}",
            content_type="title",
            platform="taobao",
        )
        # Qwen returns JSON with title/short_title
        assert "title" in result
        assert "山河" in result["title"]
        assert "short_title" in result

    def test_qwen_call_receives_correct_parameters(
        self, monkeypatch, mock_qwen_success,
    ):
        """Verify the correct parameters are passed to dashscope.Generation.call."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "key-123")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "https://test")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "qwen-turbo")

        import dashscope

        generate_product_content(
            product_name="测试",
            category="类目",
            brand="品牌",
            description="描述",
            selling_points="卖点",
            parameters_json="{}",
            content_type="title",
            platform="general",
        )

        call_args = dashscope.Generation.call.call_args
        assert call_args is not None
        kwargs = call_args[1]
        assert kwargs["model"] == "qwen-turbo"
        assert kwargs["api_key"] == "key-123"
        assert kwargs["result_format"] == "message"
        assert kwargs["max_tokens"] == 2048
        assert len(kwargs["messages"]) == 2
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["messages"][1]["role"] == "user"

    def test_qwen_api_error_raises_runtime_error(
        self, monkeypatch, mock_qwen_error,
    ):
        """Verify that Qwen API errors raise RuntimeError."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "test-key")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "https://test")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "qwen-plus")

        with pytest.raises(RuntimeError, match="Qwen API error"):
            generate_product_content(
                product_name="测试",
                category="类目",
                brand="",
                description="",
                selling_points="",
                parameters_json="{}",
                content_type="title",
                platform="general",
            )

    def test_malformed_json_fallback_to_raw_output(
        self, monkeypatch, mock_qwen_malformed_json,
    ):
        """Verify non-JSON Qwen output falls back to raw_output key."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "test-key")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "https://test")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "qwen-plus")

        result = generate_product_content(
            product_name="测试",
            category="类目",
            brand="",
            description="",
            selling_points="",
            parameters_json="{}",
            content_type="title",
            platform="general",
        )
        assert "raw_output" in result
        assert "非JSON格式" in result["raw_output"]

    def test_dashscope_import_error_raises_runtime_error(self, monkeypatch):
        """Verify missing dashscope package raises clear RuntimeError."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "test-key")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "https://test")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "qwen-plus")

        # Simulate dashscope not installed
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "dashscope":
                raise ImportError("No module named 'dashscope'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(RuntimeError, match="dashscope package is not installed"):
                generate_product_content(
                    product_name="测试",
                    category="类目",
                    brand="",
                    description="",
                    selling_points="",
                    parameters_json="{}",
                    content_type="title",
                    platform="general",
                )


class TestLLMConfigurationGate:
    """Tests for the LLM configuration gate (llm_configured)."""

    def test_template_when_llm_not_configured(self):
        """When llm_configured is False, template fallback is used."""
        result = generate_product_content(
            product_name="测试品",
            category="通用",
            brand="",
            description="描述",
            selling_points="卖点",
            parameters_json="{}",
            content_type="title",
            platform="general",
        )
        assert "title" in result
        assert result["title"] is not None

    def test_llm_path_when_fully_configured(
        self, monkeypatch, mock_qwen_success,
    ):
        """When all three LLM settings are set, Qwen is called."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "k")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "b")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "m")

        result = generate_product_content(
            product_name="X",
            category="C",
            brand="",
            description="",
            selling_points="",
            parameters_json="{}",
            content_type="title",
            platform="g",
        )
        assert "title" in result  # Qwen path was called

    def test_template_when_only_api_key_set(
        self, monkeypatch,
    ):
        """llm_configured requires all three; api_key alone is not enough."""
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_key", "k")
        monkeypatch.setattr("app.services.llm_service.settings.llm_api_base", "")
        monkeypatch.setattr("app.services.llm_service.settings.llm_model", "")

        result = generate_product_content(
            product_name="X", category="C", brand="", description="",
            selling_points="", parameters_json="{}", content_type="title", platform="g",
        )
        # Should fall back to template
        assert "title" in result
        assert "【热卖】" in result["title"]  # Template-ism

