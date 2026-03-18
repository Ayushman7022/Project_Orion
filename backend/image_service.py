from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

import httpx

from config import get_cloud_config


class ImageGenerationError(RuntimeError):
    pass


def _image_data_url_from_b64(b64: str, *, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{b64}"


async def generate_image_openai_compatible(
    *,
    prompt: str,
    size: str = "1024x1024",
    model_candidates: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calls OpenAI-compatible image generation endpoint and returns:
      - image_data_url (data:image/png;base64,...)
      - revised_prompt (if available)
      - model_used
    """
    api_key, base_url, _ = get_cloud_config()
    if not api_key:
        raise ImageGenerationError("Cloud API key is not set. Save your OpenAI API key first.")
    if not base_url:
        raise ImageGenerationError("Cloud base URL is not configured.")

    if model_candidates is None:
        model_candidates = ["gpt-image-1", "dall-e-3"]

    url = f"{base_url.rstrip('/')}/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}"}

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=180) as client:
        for model in model_candidates:
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "size": size,
                    "n": 1,
                    "response_format": "b64_json",
                }

                r = await client.post(url, headers=headers, json=payload)
                if r.status_code >= 400:
                    raise ImageGenerationError(f"image gen failed ({model}): {r.status_code} {r.text[:300]}")

                data = r.json() or {}
                items = data.get("data") or []
                if not items:
                    raise ImageGenerationError(f"No image data in response for model={model}")

                item = items[0] or {}
                b64 = item.get("b64_json") or ""
                revised = data.get("revised_prompt") or item.get("revised_prompt") or None

                if b64:
                    return {
                        "image_data_url": _image_data_url_from_b64(b64),
                        "revised_prompt": revised,
                        "model_used": model,
                    }

                # If b64_json wasn't returned, try url.
                img_url = item.get("url")
                if img_url:
                    img_resp = await client.get(img_url)
                    img_resp.raise_for_status()
                    mime = img_resp.headers.get("content-type", "image/png").split(";")[0].strip() or "image/png"
                    b64_bytes = base64.b64encode(img_resp.content).decode("utf-8")
                    return {
                        "image_data_url": _image_data_url_from_b64(b64_bytes, mime=mime),
                        "revised_prompt": revised,
                        "model_used": model,
                    }

                raise ImageGenerationError(f"Response missing b64_json/url for model={model}")
            except Exception as e:
                last_err = e
                continue

    raise ImageGenerationError(f"All image generation attempts failed: {last_err}")

