from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class GeminiError(RuntimeError):
    pass


def gemini_generate(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.4,
    timeout_s: float = 120.0,
) -> str:
    """
    Minimal Gemini REST call using Google AI Studio Generative Language API.
    """
    # v1beta still used for many Gemini endpoints
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    params = {"key": api_key}

    payload: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]},
        ],
        "generationConfig": {
            "temperature": temperature,
        },
    }

    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, params=params, json=payload)

    if r.status_code >= 400:
        raise GeminiError(f"Gemini error {r.status_code}: {r.text[:500]}")

    data = r.json()
    # Expected shape: candidates[0].content.parts[0].text
    try:
        cands = data.get("candidates") or []
        if not cands:
            raise GeminiError("No candidates in response")
        content = cands[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            raise GeminiError("No parts in response")
        text = parts[0].get("text") or ""
        return str(text)
    except Exception as e:
        raise GeminiError(f"Unexpected Gemini response: {data}") from e

