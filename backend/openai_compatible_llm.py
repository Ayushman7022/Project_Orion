from __future__ import annotations

from typing import Any, Dict, List

import httpx


class OpenAICompatibleError(RuntimeError):
    pass


def chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.4,
    timeout_s: float = 120.0,
) -> str:
    """
    Call an OpenAI-compatible Chat Completions API.
    Default OpenAI base_url: https://api.openai.com
    Endpoint used: {base_url}/v1/chat/completions
    """
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, headers=headers, json=payload)

    if r.status_code >= 400:
        raise OpenAICompatibleError(f"OpenAI-compatible error {r.status_code}: {r.text[:500]}")

    data = r.json()
    try:
        choices = data.get("choices") or []
        if not choices:
            raise OpenAICompatibleError("No choices in response")
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        return str(content)
    except Exception as e:
        raise OpenAICompatibleError(f"Unexpected response: {data}") from e

