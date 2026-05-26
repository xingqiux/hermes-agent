"""Tests for the bundled PackyAPI image_gen plugin."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

import plugins.image_gen.packyapi as packyapi_plugin


_PNG_HEX = (
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
    "ae426082"
)


def _b64_png() -> str:
    import base64

    return base64.b64encode(bytes.fromhex(_PNG_HEX)).decode()


def _response(payload: dict, *, status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode()
    response.headers["Content-Type"] = "application/json"
    return response


@pytest.fixture(autouse=True)
def _tmp_hermes_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("PACKYAPI_API_KEY", "test-key")
    monkeypatch.delenv("PACKYAPI_BASE_URL", raising=False)
    monkeypatch.delenv("PACKYAPI_IMAGE_MODEL", raising=False)
    yield tmp_path


@pytest.fixture
def provider():
    return packyapi_plugin.PackyAPIImageGenProvider()


class TestMetadata:
    def test_name(self, provider):
        assert provider.name == "packyapi"

    def test_display_name(self, provider):
        assert provider.display_name == "PackyAPI"

    def test_default_model(self, provider):
        assert provider.default_model() == "gpt-image-2-medium"

    def test_list_models_three_tiers(self, provider):
        ids = [m["id"] for m in provider.list_models()]
        assert ids == ["gpt-image-2-low", "gpt-image-2-medium", "gpt-image-2-high"]

    def test_setup_schema_prompts_for_packyapi_key(self, provider):
        schema = provider.get_setup_schema()
        assert schema["name"] == "PackyAPI"
        assert schema["env_vars"][0]["key"] == "PACKYAPI_API_KEY"


class TestAvailability:
    def test_api_key_set_available(self, provider):
        assert provider.is_available() is True

    def test_no_api_key_unavailable(self, monkeypatch):
        monkeypatch.delenv("PACKYAPI_API_KEY", raising=False)
        assert packyapi_plugin.PackyAPIImageGenProvider().is_available() is False


class TestModelResolution:
    def test_default_is_medium(self):
        model_id, meta = packyapi_plugin._resolve_model()
        assert model_id == "gpt-image-2-medium"
        assert meta["quality"] == "medium"

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("PACKYAPI_IMAGE_MODEL", "gpt-image-2-high")
        model_id, meta = packyapi_plugin._resolve_model()
        assert model_id == "gpt-image-2-high"
        assert meta["quality"] == "high"

    def test_config_packyapi_model(self, tmp_path):
        import yaml

        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump({"image_gen": {"packyapi": {"model": "gpt-image-2-low"}}})
        )
        model_id, meta = packyapi_plugin._resolve_model()
        assert model_id == "gpt-image-2-low"
        assert meta["quality"] == "low"

    def test_config_top_level_model(self, tmp_path):
        import yaml

        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump({"image_gen": {"model": "gpt-image-2-high"}})
        )
        model_id, meta = packyapi_plugin._resolve_model()
        assert model_id == "gpt-image-2-high"
        assert meta["quality"] == "high"


class TestGenerate:
    def test_empty_prompt_rejected(self, provider):
        result = provider.generate("", aspect_ratio="square")
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("PACKYAPI_API_KEY", raising=False)
        result = packyapi_plugin.PackyAPIImageGenProvider().generate("a cat")
        assert result["success"] is False
        assert result["error_type"] == "auth_required"
        assert "PACKYAPI_API_KEY" in result["error"]

    def test_b64_saves_to_cache(self, provider, tmp_path, monkeypatch):
        png_bytes = bytes.fromhex(_PNG_HEX)
        mock_post = MagicMock(return_value=_response({"data": [{"b64_json": _b64_png()}]}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat", aspect_ratio="landscape")

        assert result["success"] is True
        assert result["provider"] == "packyapi"
        assert result["model"] == "gpt-image-2-medium"
        assert result["quality"] == "medium"
        assert result["size"] == "1536x1024"

        saved = Path(result["image"])
        assert saved.exists()
        assert saved.parent == tmp_path / "cache" / "images"
        assert saved.read_bytes() == png_bytes

        assert mock_post.call_args.args[0] == "https://www.packyapi.com/v1/images/generations"
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-key"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "gpt-image-2"
        assert payload["quality"] == "medium"
        assert payload["size"] == "1536x1024"
        assert payload["response_format"] == "b64_json"

    @pytest.mark.parametrize(
        ("tier", "expected_quality"),
        [
            ("gpt-image-2-low", "low"),
            ("gpt-image-2-medium", "medium"),
            ("gpt-image-2-high", "high"),
        ],
    )
    def test_tier_maps_to_quality(self, provider, monkeypatch, tier, expected_quality):
        monkeypatch.setenv("PACKYAPI_IMAGE_MODEL", tier)
        mock_post = MagicMock(return_value=_response({"data": [{"url": "https://img.test/a.png"}]}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat")

        assert result["success"] is True
        assert result["model"] == tier
        assert result["quality"] == expected_quality
        assert mock_post.call_args.kwargs["json"]["quality"] == expected_quality
        assert mock_post.call_args.kwargs["json"]["model"] == "gpt-image-2"

    def test_explicit_quality_overrides_configured_tier(self, provider, monkeypatch):
        monkeypatch.setenv("PACKYAPI_IMAGE_MODEL", "gpt-image-2-medium")
        mock_post = MagicMock(return_value=_response({"data": [{"url": "https://img.test/a.png"}]}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat", quality="high")

        assert result["success"] is True
        assert result["model"] == "gpt-image-2-high"
        assert result["quality"] == "high"
        assert mock_post.call_args.kwargs["json"]["quality"] == "high"

    @pytest.mark.parametrize("quality", ["auto", "ultra", "", None])
    def test_auto_or_invalid_quality_keeps_configured_tier(self, provider, monkeypatch, quality):
        monkeypatch.setenv("PACKYAPI_IMAGE_MODEL", "gpt-image-2-low")
        mock_post = MagicMock(return_value=_response({"data": [{"url": "https://img.test/a.png"}]}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat", quality=quality)

        assert result["success"] is True
        assert result["model"] == "gpt-image-2-low"
        assert result["quality"] == "low"
        assert mock_post.call_args.kwargs["json"]["quality"] == "low"

    @pytest.mark.parametrize(
        ("aspect", "expected_size"),
        [
            ("landscape", "1536x1024"),
            ("square", "1024x1024"),
            ("portrait", "1024x1536"),
        ],
    )
    def test_aspect_ratio_mapping(self, provider, monkeypatch, aspect, expected_size):
        mock_post = MagicMock(return_value=_response({"data": [{"url": "https://img.test/a.png"}]}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        provider.generate("a cat", aspect_ratio=aspect)

        assert mock_post.call_args.kwargs["json"]["size"] == expected_size

    def test_url_fallback(self, provider, monkeypatch):
        mock_post = MagicMock(
            return_value=_response({"data": [{"url": "https://packyapi.test/img.png"}]})
        )
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat")

        assert result["success"] is True
        assert result["image"] == "https://packyapi.test/img.png"

    def test_base_url_override(self, provider, monkeypatch):
        monkeypatch.setenv("PACKYAPI_BASE_URL", "https://proxy.example/v1/")
        mock_post = MagicMock(return_value=_response({"data": [{"url": "https://img.test/a.png"}]}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        provider.generate("a cat")

        assert mock_post.call_args.args[0] == "https://proxy.example/v1/images/generations"

    def test_retries_without_response_format_when_proxy_rejects_it(self, provider, monkeypatch):
        first = _response(
            {"error": {"message": "Unknown parameter: response_format"}},
            status=400,
        )
        second = _response({"data": [{"url": "https://img.test/retry.png"}]})
        mock_post = MagicMock(side_effect=[first, second])
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat")

        assert result["success"] is True
        assert result["image"] == "https://img.test/retry.png"
        assert mock_post.call_count == 2
        assert "response_format" in mock_post.call_args_list[0].kwargs["json"]
        assert "response_format" not in mock_post.call_args_list[1].kwargs["json"]

    def test_api_error_returns_error_response(self, provider, monkeypatch):
        mock_post = MagicMock(
            return_value=_response({"error": {"message": "Invalid API key"}}, status=401)
        )
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat")

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "Invalid API key" in result["error"]

    def test_timeout(self, provider, monkeypatch):
        mock_post = MagicMock(side_effect=requests.Timeout())
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat")

        assert result["success"] is False
        assert result["error_type"] == "timeout"

    def test_empty_response(self, provider, monkeypatch):
        mock_post = MagicMock(return_value=_response({"data": []}))
        monkeypatch.setattr(packyapi_plugin.requests, "post", mock_post)

        result = provider.generate("a cat")

        assert result["success"] is False
        assert result["error_type"] == "empty_response"


class TestRegistration:
    def test_register(self):
        mock_ctx = MagicMock()
        packyapi_plugin.register(mock_ctx)
        mock_ctx.register_image_gen_provider.assert_called_once()
        provider = mock_ctx.register_image_gen_provider.call_args[0][0]
        assert isinstance(provider, packyapi_plugin.PackyAPIImageGenProvider)
        assert provider.name == "packyapi"
