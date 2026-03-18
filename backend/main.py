from __future__ import annotations

from pathlib import Path
import logging

import asyncio
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from agent import run_agent
from config import (
    set_runtime_cloud_provider,
    set_runtime_sarvam_api_key,
    settings,
)
from fs_service import FsSandboxError, delete_path, list_dir, make_dir, read_text, write_text
from fs_search_service import search_fs
from sarvamai import AsyncSarvamAI
from config import get_sarvam_api_key
from tts_service import synthesize_sarvam
from tools.web_search import web_search_tool
from tools.shell_tools import shell_run_tool
from image_service import generate_image_openai_compatible, ImageGenerationError


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("orion-backend")


app = FastAPI(title="Orion Local Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    logger.info("Health check")
    return {"status": "ok"}


@app.post("/config")
async def set_config(
    sarvam_api_key: str | None = Form(None, description="Sarvam API key (local-only)"),
    cloud_provider: str | None = Form(None, description="Cloud LLM provider"),
    cloud_api_key: str | None = Form(None, description="Cloud LLM API key (OpenAI-compatible)"),
    cloud_base_url: str | None = Form(None, description="Cloud LLM base URL (OpenAI-compatible)"),
    cloud_model: str | None = Form(None, description="Cloud LLM model (OpenAI-compatible)"),
) -> JSONResponse:
    """
    Local-only runtime configuration set by the frontend.
    Stored in memory (process lifetime).
    """
    if sarvam_api_key is not None:
        set_runtime_sarvam_api_key(sarvam_api_key)
    if cloud_provider is not None:
        set_runtime_cloud_provider(cloud_provider)
    if cloud_api_key is not None or cloud_base_url is not None or cloud_model is not None:
        from config import set_runtime_cloud_config

        set_runtime_cloud_config(api_key=cloud_api_key, base_url=cloud_base_url, model=cloud_model)
    return JSONResponse({"ok": True})


@app.post("/tools/web_search")
async def web_search(q: str = Form(..., description="Search query")) -> JSONResponse:
    try:
        return JSONResponse({"results": web_search_tool.invoke({"query": q})})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"web_search error: {e}") from e


@app.post("/tools/shell")
async def shell(
    cmd: str = Form(..., description="Shell command to run (read-only)"),
    cwd: str | None = Form(None, description="Optional working directory (inside sandbox)"),
) -> JSONResponse:
    """
    Run a guarded shell command inside the sandbox root.
    Intended only for read-only commands like 'dir', 'git status', 'pip list'.
    Dangerous commands (delete/format/shutdown) are rejected.
    """
    try:
        raw = shell_run_tool.invoke({"command": cmd, "cwd": cwd or ""})
        import json  # local import

        data = json.loads(raw)
        return JSONResponse(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"shell error: {e}") from e


@app.get("/fs/list")
async def fs_list(path: str = "") -> JSONResponse:
    try:
        entries = list_dir(path)
        return JSONResponse(
            {
                "root": str(settings.fs_root),
                "path": path,
                "entries": [e.__dict__ for e in entries],
            }
        )
    except FsSandboxError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail="Not a directory")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fs_list error: {e}") from e


@app.post("/fs/read")
async def fs_read(path: str = Form(...), max_chars: int = Form(200_000)) -> JSONResponse:
    try:
        content = read_text(path, max_chars=max_chars)
        return JSONResponse({"path": path, "content": content})
    except FsSandboxError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="Is a directory")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fs_read error: {e}") from e


@app.post("/fs/write")
async def fs_write(
    path: str = Form(...),
    content: str = Form(""),
) -> JSONResponse:
    try:
        write_text(path, content)
        return JSONResponse({"ok": True, "path": path})
    except FsSandboxError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fs_write error: {e}") from e


@app.post("/fs/delete")
async def fs_delete(path: str = Form(...)) -> JSONResponse:
    try:
        delete_path(path)
        return JSONResponse({"ok": True, "path": path})
    except FsSandboxError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except IsADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fs_delete error: {e}") from e


@app.post("/fs/mkdir")
async def fs_mkdir(path: str = Form(...)) -> JSONResponse:
    try:
        created = make_dir(path, parents=True)
        return JSONResponse({"ok": True, "path": created})
    except FsSandboxError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fs_mkdir error: {e}") from e


@app.get("/fs/search")
async def fs_search(
    name: str = "",
    q: str = "",
    max_hits: int = 50,
) -> JSONResponse:
    """
    Search files under sandbox root by name pattern and/or content substring.
    Example: /fs/search?name=*.py&q=uvicorn
    """
    try:
        hits = search_fs(name_pattern=name or None, content_query=q or None, max_hits=max_hits)
        return JSONResponse({"root": str(settings.fs_root), "name": name, "q": q, "hits": [h.__dict__ for h in hits]})
    except FsSandboxError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fs_search error: {e}") from e

@app.post("/chat")
async def chat(
    message: str = Form(..., description="User text"),
    language: str = Form("en"),
) -> JSONResponse:
    """
    Main text chat endpoint. Frontend sends plain text here.
    """
    logger.info("CHAT request language=%s text=%r", language, message[:120])
    try:
        result = run_agent(message, language=language)
        output_text = str(result.get("output") or result)
    except Exception as e:
        logger.exception("Agent error")
        raise HTTPException(status_code=500, detail=f"Agent error: {e}") from e

    return JSONResponse({"text": output_text, "language": language or "en"})


@app.post("/stt")
async def stt(
    audio: UploadFile = File(...),
    language_hint: str | None = Form(None),
) -> JSONResponse:
    """
    Sarvam batch/non-streaming Speech-to-Text.
    Frontend uploads short audio (typically webm) and gets a final transcript.
    """
    sarvam_key = get_sarvam_api_key()
    if not sarvam_key:
        raise HTTPException(status_code=500, detail="SARVAM_API_KEY is not set")

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="No audio data received")

    lang = (language_hint or "en").lower()
    language_code = "en-IN"
    if lang.startswith("hi"):
        language_code = "hi-IN"
    elif lang.startswith("mr"):
        language_code = "mr-IN"

    try:
        client = AsyncSarvamAI(api_subscription_key=sarvam_key)
        filename = audio.filename or "speech.webm"
        content_type = audio.content_type or "audio/webm"

        # Sarvam batch/REST supports webm/wav/etc (unlike streaming).
        resp = await client.speech_to_text.transcribe(
            file=(filename, raw, content_type),
            model="saaras:v3",
            mode="transcribe",
            language_code=language_code,
        )

        transcript = getattr(resp, "transcript", "") or ""
        detected_language = getattr(resp, "language_code", None) or language_hint or "en"
        return JSONResponse({"text": transcript, "detected_language": detected_language})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {e}") from e


@app.post("/tts")
async def tts(
    text: str = Form(..., description="Text to speak"),
    language_code: str = Form("hi-IN"),
    speaker: str = Form("amelia"),
) -> FileResponse:
    """
    Text‑to‑speech using Sarvam Bulbul v3.
    Returns a WAV file.
    """
    logger.info("TTS request language_code=%s speaker=%s text_len=%d", language_code, speaker, len(text))
    try:
        audio_path = await synthesize_sarvam(
            text=text,
            language_code=language_code,  # type: ignore[arg-type]
            speaker=speaker,
        )
    except Exception as e:
        logger.exception("TTS error")
        raise HTTPException(status_code=500, detail=f"TTS error: {e}") from e

    return FileResponse(
        path=audio_path,
        media_type="audio/wav",
        filename=audio_path.name,
    )


@app.post("/image/generate")
async def image_generate(
    prompt: str = Form(..., description="Image prompt"),
    size: str = Form("1024x1024", description="OpenAI image size (e.g., 1024x1024)"),
) -> JSONResponse:
    """
    Generate an image using OpenAI-compatible image generation API.
    Returns a data URL so the frontend can display immediately.
    """
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    try:
        result = await generate_image_openai_compatible(prompt=prompt.strip(), size=size)
        return JSONResponse(result)
    except ImageGenerationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation error: {e}") from e

