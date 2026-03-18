import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


class Settings:
    # Ollama / LLM
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

    # Cloud LLM (OpenAI-compatible)
    cloud_base_url: str = os.getenv("CLOUD_BASE_URL", "https://api.openai.com")
    cloud_model: str = os.getenv("CLOUD_MODEL", "gpt-4o-mini")
    cloud_api_key: str | None = os.getenv("CLOUD_API_KEY")
    cloud_provider: str = os.getenv("CLOUD_PROVIDER", "openai_compatible")

    # Sarvam TTS
    sarvam_api_key: str | None = os.getenv("SARVAM_API_KEY")
    sarvam_tts_url: str = os.getenv(
        "SARVAM_TTS_URL", "https://api.sarvam.ai/text-to-speech"
    )

    # Whisper STT
    whisper_model: str = os.getenv("WHISPER_MODEL", "small")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    # File system sandbox
    fs_root: Path = Path(
        os.getenv("JARVIS_FS_ROOT", str(Path.home()))
    ).resolve()


settings = Settings()

# Runtime overrides (local-only UI can set these)
_runtime_sarvam_api_key: str | None = None
_runtime_cloud_api_key: str | None = None
_runtime_cloud_base_url: str | None = None
_runtime_cloud_model: str | None = None
_runtime_cloud_provider: str | None = None


def set_runtime_sarvam_api_key(key: str | None) -> None:
    global _runtime_sarvam_api_key
    k = (key or "").strip()
    _runtime_sarvam_api_key = k or None


def get_sarvam_api_key() -> str | None:
    return _runtime_sarvam_api_key or settings.sarvam_api_key


def set_runtime_cloud_config(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> None:
    global _runtime_cloud_api_key, _runtime_cloud_base_url, _runtime_cloud_model, _runtime_cloud_provider
    if api_key is not None:
        k = (api_key or "").strip()
        _runtime_cloud_api_key = k or None
    if base_url is not None:
        b = (base_url or "").strip().rstrip("/")
        _runtime_cloud_base_url = b or None
    if model is not None:
        m = (model or "").strip()
        _runtime_cloud_model = m or None
    # If someone passes "gemini" here as base_url accidentally, ignore; provider is separate.


def set_runtime_cloud_provider(provider: str | None) -> None:
    global _runtime_cloud_provider
    p = (provider or "").strip().lower()
    _runtime_cloud_provider = p or None


def get_cloud_config() -> tuple[str | None, str, str]:
    api_key = _runtime_cloud_api_key or settings.cloud_api_key
    base_url = _runtime_cloud_base_url or settings.cloud_base_url
    model = _runtime_cloud_model or settings.cloud_model
    return api_key, base_url, model


def get_cloud_provider() -> str:
    return _runtime_cloud_provider or settings.cloud_provider

