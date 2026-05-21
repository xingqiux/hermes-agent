"""PackyAPI image generation backend.

PackyAPI exposes an OpenAI-compatible Images API at
``https://www.packyapi.com/v1/images/generations``. This provider presents
``gpt-image-2`` as the same low/medium/high quality tiers used by the bundled
OpenAI image backend, but authenticates with ``PACKYAPI_API_KEY``.

Selection precedence (first hit wins):

1. ``PACKYAPI_IMAGE_MODEL`` env var
2. ``image_gen.packyapi.model`` in ``config.yaml``
3. ``image_gen.model`` in ``config.yaml`` (when it's one of our tier IDs)
4. :data:`DEFAULT_MODEL` -- ``gpt-image-2-medium``
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)

logger = logging.getLogger(__name__)


API_MODEL = "gpt-image-2"
DEFAULT_BASE_URL = "https://www.packyapi.com/v1"

_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2-low": {
        "display": "GPT Image 2 (Low via PackyAPI)",
        "speed": "~15s",
        "strengths": "Fast iteration, lowest cost",
        "quality": "low",
    },
    "gpt-image-2-medium": {
        "display": "GPT Image 2 (Medium via PackyAPI)",
        "speed": "~40s",
        "strengths": "Balanced -- default",
        "quality": "medium",
    },
    "gpt-image-2-high": {
        "display": "GPT Image 2 (High via PackyAPI)",
        "speed": "~2min",
        "strengths": "Highest fidelity, strongest prompt adherence",
        "quality": "high",
    },
}

DEFAULT_MODEL = "gpt-image-2-medium"

_SIZES = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}


def _load_image_gen_config() -> Dict[str, Any]:
    """Read ``image_gen`` from config.yaml (returns {} on any failure)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen config: %s", exc)
        return {}


def _resolve_model() -> Tuple[str, Dict[str, Any]]:
    """Decide which PackyAPI quality tier to use."""
    env_override = os.environ.get("PACKYAPI_IMAGE_MODEL")
    if env_override and env_override in _MODELS:
        return env_override, _MODELS[env_override]

    cfg = _load_image_gen_config()
    packy_cfg = cfg.get("packyapi") if isinstance(cfg.get("packyapi"), dict) else {}
    candidate: Optional[str] = None
    if isinstance(packy_cfg, dict):
        value = packy_cfg.get("model")
        if isinstance(value, str) and value in _MODELS:
            candidate = value
    if candidate is None:
        top = cfg.get("model")
        if isinstance(top, str) and top in _MODELS:
            candidate = top

    if candidate is not None:
        return candidate, _MODELS[candidate]

    return DEFAULT_MODEL, _MODELS[DEFAULT_MODEL]


def _api_key() -> str:
    """Return PackyAPI key from environment or Hermes .env."""
    value = os.environ.get("PACKYAPI_API_KEY")
    if value:
        return value.strip()
    try:
        from hermes_cli.config import get_env_value

        return str(get_env_value("PACKYAPI_API_KEY") or "").strip()
    except Exception:
        return ""


def _base_url() -> str:
    """Return PackyAPI OpenAI-compatible base URL without trailing slash."""
    value = os.environ.get("PACKYAPI_BASE_URL")
    if not value:
        try:
            from hermes_cli.config import get_env_value

            value = get_env_value("PACKYAPI_BASE_URL")
        except Exception:
            value = None
    return str(value or DEFAULT_BASE_URL).strip().rstrip("/")


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
            if message:
                return str(message)
        if isinstance(error, str) and error:
            return error
        message = payload.get("message")
        if message:
            return str(message)
    except Exception:
        pass
    return (response.text or "").strip()[:300] or response.reason or "HTTP error"


def _post_generation(
    url: str,
    *,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: int,
) -> requests.Response:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        # Some OpenAI-compatible proxies still reject response_format for newer
        # image models. Retry once without it before surfacing the error.
        if "response_format" in payload:
            error_text = _extract_error_message(response).lower()
            if (
                response.status_code in {400, 422}
                and "response_format" in error_text
            ):
                retry_payload = dict(payload)
                retry_payload.pop("response_format", None)
                retry = requests.post(
                    url,
                    headers=headers,
                    json=retry_payload,
                    timeout=timeout,
                )
                retry.raise_for_status()
                return retry
        raise exc
    return response


class PackyAPIImageGenProvider(ImageGenProvider):
    """PackyAPI ``gpt-image-2`` backend."""

    @property
    def name(self) -> str:
        return "packyapi"

    @property
    def display_name(self) -> str:
        return "PackyAPI"

    def is_available(self) -> bool:
        return bool(_api_key())

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
                "price": "varies",
            }
            for model_id, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "PackyAPI",
            "badge": "paid",
            "tag": "OpenAI-compatible gpt-image-2 image generation via PackyAPI",
            "env_vars": [
                {
                    "key": "PACKYAPI_API_KEY",
                    "prompt": "PackyAPI API key",
                    "url": "https://www.packyapi.com/",
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)

        if not prompt:
            return error_response(
                error="Prompt is required and must be a non-empty string",
                error_type="invalid_argument",
                provider="packyapi",
                aspect_ratio=aspect,
            )

        key = _api_key()
        if not key:
            return error_response(
                error=(
                    "PACKYAPI_API_KEY not set. Run `hermes tools` -> Image "
                    "Generation -> PackyAPI to configure, or set it with "
                    "`hermes config set PACKYAPI_API_KEY <key>`."
                ),
                error_type="auth_required",
                provider="packyapi",
                aspect_ratio=aspect,
            )

        tier_id, meta = _resolve_model()
        size = _SIZES.get(aspect, _SIZES["square"])
        timeout = int(kwargs.get("timeout") or os.environ.get("PACKYAPI_TIMEOUT") or 180)

        payload: Dict[str, Any] = {
            "model": API_MODEL,
            "prompt": prompt,
            "size": size,
            "n": 1,
            "quality": meta["quality"],
            "response_format": "b64_json",
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        url = f"{_base_url()}/images/generations"

        try:
            response = _post_generation(
                url,
                headers=headers,
                payload=payload,
                timeout=timeout,
            )
        except requests.HTTPError as exc:
            response = exc.response
            status = response.status_code if response is not None else 0
            err_msg = _extract_error_message(response) if response is not None else str(exc)
            logger.debug("PackyAPI image generation failed (%s): %s", status, err_msg)
            return error_response(
                error=f"PackyAPI image generation failed ({status}): {err_msg}",
                error_type="api_error",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except requests.Timeout:
            return error_response(
                error=f"PackyAPI image generation timed out ({timeout}s)",
                error_type="timeout",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except requests.ConnectionError as exc:
            return error_response(
                error=f"PackyAPI connection error: {exc}",
                error_type="connection_error",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except requests.RequestException as exc:
            return error_response(
                error=f"PackyAPI request failed: {exc}",
                error_type="api_error",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        try:
            result = response.json()
        except Exception as exc:
            return error_response(
                error=f"PackyAPI returned invalid JSON: {exc}",
                error_type="invalid_response",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        data = result.get("data", [])
        if not data:
            return error_response(
                error="PackyAPI returned no image data",
                error_type="empty_response",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        first = data[0] if isinstance(data[0], dict) else {}
        b64 = first.get("b64_json")
        url_result = first.get("url")
        revised_prompt = first.get("revised_prompt")

        if b64:
            try:
                saved_path = save_b64_image(b64, prefix=f"packyapi_{tier_id}")
            except Exception as exc:
                return error_response(
                    error=f"Could not save image to cache: {exc}",
                    error_type="io_error",
                    provider="packyapi",
                    model=tier_id,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
            image_ref = str(saved_path)
        elif url_result:
            image_ref = str(url_result)
        else:
            return error_response(
                error="PackyAPI response contained neither b64_json nor URL",
                error_type="empty_response",
                provider="packyapi",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        extra: Dict[str, Any] = {"size": size, "quality": meta["quality"]}
        if revised_prompt:
            extra["revised_prompt"] = revised_prompt

        return success_response(
            image=image_ref,
            model=tier_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="packyapi",
            extra=extra,
        )


def register(ctx: Any) -> None:
    """Plugin entry point -- wire ``PackyAPIImageGenProvider`` into Hermes."""
    ctx.register_image_gen_provider(PackyAPIImageGenProvider())
