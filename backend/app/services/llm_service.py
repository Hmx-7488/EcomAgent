"""Runtime LLM provider integration for structured e-commerce content."""

import json
import logging
from typing import Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


def _get_qwen_response(messages: list[dict], max_tokens: int = 2048) -> str:
    """Call Qwen via DashScope API and return the text response."""
    try:
        import dashscope
    except ImportError:
        raise RuntimeError(
            "dashscope package is not installed. Run: pip install dashscope"
        )

    response = dashscope.Generation.call(
        model=settings.llm_model or "qwen-plus",
        api_key=settings.llm_api_key,
        messages=messages,
        result_format="message",
        max_tokens=max_tokens,
    )

    if response.status_code != 200:
        error_msg = f"Qwen API error: code={response.code}, message={response.message}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    return response.output.choices[0].message.content


def _get_google_response(messages: list[dict], max_tokens: int = 2048) -> str:
    """Call Gemini's text endpoint and return the first text response."""
    system_parts = [item["content"] for item in messages if item["role"] == "system"]
    user_parts = [item["content"] for item in messages if item["role"] != "system"]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "\n\n".join(user_parts)}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "responseMimeType": "application/json"},
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.google_text_model}:generateContent",
        params={"key": settings.google_api_key},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Gemini response did not contain text content") from exc


def _get_llm_response(messages: list[dict], max_tokens: int = 2048) -> str:
    if settings.llm_provider == "google":
        return _get_google_response(messages, max_tokens)
    if settings.llm_provider == "qwen":
        return _get_qwen_response(messages, max_tokens)
    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")


def generate_product_content(
    product_name: str,
    category: str,
    brand: str,
    description: str,
    selling_points: str,
    parameters_json: str,
    content_type: str,
    platform: str,
    style_hint: Optional[str] = None,
) -> dict:
    """Generate product content using the configured LLM provider.

    Falls back to template-based generation when LLM is not configured.
    """
    if not settings.llm_configured:
        logger.warning("LLM not configured, using template fallback")
        return _template_fallback(
            product_name, category, brand, description, selling_points,
            parameters_json, content_type, platform, style_hint,
        )

    prompts = {
        "title": f"""你是一个电商文案专家。请为以下商品生成标题和短标题。

商品名称：{product_name}
类目：{category}
品牌：{brand or '无'}
核心卖点：{selling_points or description or '无'}
目标平台：{platform}
风格要求：{style_hint or '专业、吸引人'}

请返回 JSON 格式：
{{"title": "完整商品标题（30字以内）", "short_title": "短标题（15字以内）"}}

只返回 JSON，不要其他内容。""",

        "selling_points": f"""提炼以下商品的核心卖点，用简洁有力的短句表达。

商品名称：{product_name}
类目：{category}
现有描述：{description or '无'}
现有卖点：{selling_points or '无'}

返回 JSON：{{"selling_points": "提炼后的卖点文案"}}""",

        "description": f"""为以下商品撰写详情页文案。

商品名称：{product_name}
类目：{category}
品牌：{brand or '无'}
卖点：{selling_points or '无'}
参数：{parameters_json or '{}'}
平台：{platform}

返回 JSON：{{"detail": "详情页文案", "parameters": "格式化后的参数说明"}}""",

        "faq": f"""为以下商品生成常见FAQ。

商品名称：{product_name}
卖点：{selling_points or description or '无'}

返回 JSON：{{"faq": [{{"q": "问题", "a": "回答"}}, ...]}}（3-5条）""",

        "script": f"""为以下商品写一段直播带货话术。

商品名称：{product_name}
卖点：{selling_points or '品质优良'}
平台：{platform}

返回 JSON：{{"script": "直播话术文本"}}""",

        "keywords": f"""为以下商品生成平台搜索关键词。

商品名称：{product_name}
类目：{category}
品牌：{brand or ''}
平台：{platform}

返回 JSON：{{"keywords": ["关键词1", "关键词2", ...]}}（8-12个）""",
    }

    system_prompt = "你是一个专业的电商内容生成助手。请只返回要求的 JSON 格式，不要附加解释。"

    prompt = prompts.get(content_type, prompts["title"])
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    raw = _get_llm_response(messages)

    # Parse JSON response; fall back to raw text if parsing fails
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM response was not valid JSON, using raw text")
        result = {"raw_output": raw}

    result["product_name"] = product_name
    result["category"] = category
    result["brand"] = brand or ""
    result["platform"] = platform

    return result


def _template_fallback(
    product_name: str, category: str, brand: str, description: str,
    selling_points: str, parameters_json: str, content_type: str,
    platform: str, style_hint: Optional[str],
) -> dict:
    """Template-based fallback when LLM is not configured."""
    base = {
        "product_name": product_name,
        "category": category,
        "brand": brand or "",
        "platform": platform,
    }

    if content_type == "title":
        hint = f" | {style_hint}" if style_hint else ""
        base["title"] = f"【{brand or '热卖'}】{product_name} {category}{hint}"
        base["short_title"] = product_name

    elif content_type == "selling_points":
        base["selling_points"] = selling_points or description or ""

    elif content_type == "description":
        base["detail"] = description or ""
        try:
            base["parameters"] = json.dumps(
                json.loads(parameters_json or "{}"), ensure_ascii=False
            )
        except (TypeError, json.JSONDecodeError):
            base["parameters"] = parameters_json or "{}"

    elif content_type == "faq":
        base["faq"] = [
            {"q": "这款商品有什么特点？", "a": selling_points or description or "请查看商品详情"},
            {"q": "支持退换货吗？", "a": "请查看商品售后规则"},
        ]

    elif content_type == "script":
        base["script"] = f"欢迎各位宝宝！今天给大家带来的是{product_name}，{selling_points or '品质有保障，性价比超高！'}"

    elif content_type == "keywords":
        base["keywords"] = [product_name, category, brand or "", platform]

    return base
