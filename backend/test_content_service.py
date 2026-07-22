"""Edge case tests for content generation service (template fallback)."""

import json


class TestTemplateFallback:
    """Verify _template_fallback handles missing fields gracefully."""

    BASE_ARGS = {
        "product_name": "测试商品",
        "category": "服装",
        "brand": "",
        "description": "",
        "selling_points": "",
        "parameters_json": "{}",
        "content_type": "title",
        "platform": "taobao",
        "style_hint": None,
    }

    def _call(self, **kwargs):
        from app.services.llm_service import _template_fallback

        args = {**self.BASE_ARGS, **kwargs}
        return _template_fallback(**args)

    def test_title_missing_brand(self):
        result = self._call(
            product_name="防晒衣", category="运动户外", brand="", content_type="title"
        )
        assert "热卖" in result["title"]  # fallback when brand is missing

    def test_title_with_style_hint(self):
        result = self._call(
            product_name="跑鞋", brand="Nike", content_type="title",
            style_hint="专业跑步"
        )
        assert "专业跑步" in result["title"]

    def test_selling_points_falls_back_to_description(self):
        result = self._call(
            selling_points="", description="这是一款很棒的防晒衣",
            content_type="selling_points"
        )
        assert result["selling_points"] == "这是一款很棒的防晒衣"

    def test_selling_points_empty_all(self):
        result = self._call(
            selling_points="", description="", content_type="selling_points"
        )
        assert result["selling_points"] == ""

    def test_faq_missing_data(self):
        result = self._call(
            selling_points="", description="", content_type="faq"
        )
        assert len(result["faq"]) == 2
        assert "请查看商品详情" in result["faq"][0]["a"]

    def test_script_missing_selling_points(self):
        result = self._call(
            product_name="好物推荐", selling_points="", content_type="script"
        )
        assert "好物推荐" in result["script"]
        assert "性价比超高" in result["script"]  # fallback phrase

    def test_description_includes_parameters(self):
        result = self._call(
            description="详细描述",
            parameters_json=json.dumps({"材质": "棉", "重量": "200g"}),
            content_type="description",
        )
        assert "棉" in result["parameters"]

    def test_keywords_includes_brand_fallback(self):
        result = self._call(
            product_name="T恤", category="上衣", brand="", content_type="keywords",
            platform="taobao",
        )
        assert "T恤" in result["keywords"]
        assert "taobao" in result["keywords"]

    def test_all_content_types_return_dict(self):
        for ct in ["title", "selling_points", "description", "faq", "script", "keywords"]:
            result = self._call(content_type=ct)
            assert isinstance(result, dict), f"Expected dict for {ct}"
            assert "product_name" in result