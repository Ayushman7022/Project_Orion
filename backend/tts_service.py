from __future__ import annotations

from pathlib import Path
from typing import Literal

from sarvamai import SarvamAI
from sarvamai.play import save
from sarvamai.errors.forbidden_error import ForbiddenError

from config import get_sarvam_api_key


VoiceLang = Literal["en-IN", "hi-IN", "mr-IN"]

# Sarvam validates `speaker` against an allowlist. If the UI is cached/outdated
# and sends an invalid speaker, we safely fall back instead of 400'ing.
_ALLOWED_SPEAKERS: set[str] = {
    "aditya",
    "ritu",
    "ashutosh",
    "priya",
    "neha",
    "rahul",
    "pooja",
    "rohan",
    "simran",
    "kavya",
    "amit",
    "dev",
    "ishita",
    "shreya",
    "ratan",
    "varun",
    "manan",
    "sumit",
    "roopa",
    "kabir",
    "aayan",
    "shubh",
    "advait",
    "amelia",
    "sophia",
    "anand",
    "tanya",
    "tarun",
    "sunny",
    "mani",
    "gokul",
    "vijay",
    "shruti",
    "suhani",
    "mohit",
    "kavitha",
    "rehan",
    "soham",
    "rupali",
}


_client: SarvamAI | None = None


def _get_client() -> SarvamAI:
    global _client
    if _client is None:
        api_key = get_sarvam_api_key()
        if not api_key:
            raise RuntimeError(
                "SARVAM_API_KEY is not set. Open the UI and save your Sarvam key."
            )
        _client = SarvamAI(api_subscription_key=api_key)
    return _client


async def synthesize_sarvam(
    text: str,
    language_code: VoiceLang = "hi-IN",
    speaker: str = "amelia",
    speech_rate: float = 1.0,
    out_dir: Path | None = None,
) -> Path:
    """
    Call Sarvam AI TTS (Bulbul v3) using official SDK and save audio to a file.
    Returns path to the saved WAV file.
    """
    client = _get_client()

    spk = (speaker or "").strip().lower() or "amelia"
    if spk not in _ALLOWED_SPEAKERS:
        spk = "amelia"

    if out_dir is None:
        out_dir = Path("audio_outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"tts_{abs(hash((text, language_code, spk))) % 10_000}.wav"

    try:
        response = client.text_to_speech.convert(
            text=text,
            target_language_code=language_code,
            model="bulbul:v3",
            speaker=spk,
            pace=speech_rate,
            output_audio_codec="wav",
        )
    except ForbiddenError as e:
        # Common case: invalid/expired API key for Sarvam.
        raise RuntimeError(
            "Sarvam TTS authentication failed. SARVAM_API_KEY is invalid/expired. Open the UI and save a valid key."
        ) from e

    save(response, str(out_path))
    return out_path



