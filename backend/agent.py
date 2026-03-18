from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import get_cloud_config, get_cloud_provider, settings
from openai_compatible_llm import OpenAICompatibleError, chat_completion
from tools.fs_tools import (
    fs_delete_tool,
    fs_list_tool,
    fs_mkdir_tool,
    fs_read_tool,
    fs_search_tool,
    fs_write_tool,
)
from tools.web_search import web_search_tool
from tools.web_crawl import web_crawl_tool
from tools.shell_tools import shell_run_tool
from tools.system_tools import system_open_tool
from tools.find_tools import system_find_app_tool, system_find_tool

logger = logging.getLogger("orion-backend")


def _build_llm() -> ChatOllama:
    """
    Local LLM wrapper (tool-capable).
    """
    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=0.4,
    )


_llm: ChatOllama | None = None


def _get_llm() -> ChatOllama:
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm


def run_agent(text: str, language: str | None = None) -> Dict[str, Any]:
    """
    ReAct-style local agent (ACTION/INPUT/OBSERVATION/FINAL).
    This avoids relying on model-specific function calling support.
    """
    lang = (language or "en").lower()
    system_hint = (
        "You are ORION, a local AI assistant running on the user's Windows PC. "
        "You can understand and respond in Hindi, English and Marathi. "
        f"The user's current language code is '{lang}'. "
        "Always reply in that language (hi / en / mr) unless specifically asked to translate."
        "\n\nYou have tools you can use. You MUST follow this exact format:"
        "\n\nACTION: <tool_name>"
        "\nINPUT: <single line input>"
        "\n\nWhen you have the final answer, respond with:"
        "\nFINAL: <answer>"
        "\n\nAvailable tools:"
        "\n- web_search: search the web for current info"
        "\n- web_crawl: download top links and extract page text (for summarizing news/current info)"
        "\n- system_open: open an app, url, or a sandbox file/folder (Windows)"
        "\n- system_find: find a file anywhere on this PC (by filename)"
        "\n- system_find_app: find an installed app (shortcuts/exe)"
        "\n- fs_list: list a directory under the sandbox"
        "\n- fs_search: search files by name/content under the sandbox"
        "\n- fs_mkdir: create a directory under the sandbox"
        "\n- fs_read: read a text file under the sandbox"
        "\n- fs_write: write a text file under the sandbox (ONLY if user explicitly asks to write/change files)"
        "\n- fs_delete: delete a file under the sandbox (ONLY if user explicitly asks)"
        "\n- shell_run: run safe read-only shell commands (dir, git status, pip list, etc.)"
        "\n\nRules:"
        "\n- If user asks for current/trending/latest or asks for sources/links, use ACTION: web_search."
        "\n- If user asks to open/launch/start an app/website/file, use ACTION: system_open."
        "\n- If user asks to find/locate a file on the whole PC, use ACTION: system_find."
        "\n- If user asks to find an app/program, use ACTION: system_find_app."
        "\n- Never claim you read/edited files unless you used fs_* tools."
        "\n- If a tool returns 'No results found.' or errors, say you could not retrieve results; do not make up sources."
        "\n- If the user asks for N items, you MUST return N items in FINAL."
        "\n- In FINAL, use this format for lists: 'Topic — <link>' (one per line)."
        "\n- Keep answers concise."
    )

    cloud_key, cloud_base_url, cloud_model = get_cloud_config()
    cloud_provider = (get_cloud_provider() or "").lower()

    lower_q = text.lower()

    # Fast-path: greetings / acknowledgements should never trigger web search or tools.
    # This avoids cases where local LLM outputs ACTION:web_search for "hello".
    def _is_greeting(t: str) -> bool:
        s = (t or "").strip().lower()
        if not s:
            return False
        s = re.sub(r"[^\w\s]", "", s)
        return s in {
            "hi",
            "hello",
            "hey",
            "hii",
            "hlo",
            "yo",
            "good morning",
            "good afternoon",
            "good evening",
            "gm",
            "gn",
            "thanks",
            "thank you",
        }

    if _is_greeting(lower_q):
        if (language or "en").lower().startswith("hi"):
            return {"output": "नमस्ते! मैं Orion हूँ। आप क्या करना चाहते हैं?"}
        if (language or "en").lower().startswith("mr"):
            return {"output": "नमस्कार! मी Orion आहे. तुम्हाला काय करायचं आहे?"}
        return {"output": "Hi! I’m Orion. What can I help you with?"}
    # Router: local-system tasks should be planned/executed by the local Ollama model.
    # This reduces “I can't access your files” refusal patterns with cloud models.
    local_task = any(
        k in lower_q
        for k in [
            "local file",
            "local system",
            "my files",
            "my desktop",
            "desktop",
            "documents",
            "downloads",
            "read ",
            "open ",
            "show ",
            "list ",
            "ls ",
            "dir ",
            "search my files",
            "find in files",
            "find in my files",
            "search in my files",
            "scan ",
            "create folder",
            "create directory",
            "make folder",
            "make directory",
            "mkdir",
            "write file",
            "edit file",
            "update file",
            "delete file",
            "remove file",
            "run command",
            "shell",
            "pip list",
            "git status",
            "command",
        ]
    )

    def _llm_text(prompt: str, *, system_override: str | None = None) -> str:
        if local_task:
            logger.info("LLM backend (forced local): ollama model=%s", settings.ollama_model)
            llm = _get_llm()
            ai = llm.invoke(
                [SystemMessage(content=system_override or system_hint), HumanMessage(content=prompt)]
            )
            return str(getattr(ai, "content", ai))

        # Non-local tasks: prefer OpenAI-compatible cloud if configured, otherwise local Ollama.
        if cloud_key:
            logger.info(
                "LLM backend: openai_compatible model=%s base_url=%s",
                cloud_model,
                cloud_base_url,
            )
            try:
                return chat_completion(
                    api_key=cloud_key,
                    base_url=cloud_base_url,
                    model=cloud_model,
                    system=system_override or system_hint,
                    user=prompt,
                    temperature=0.4,
                )
            except OpenAICompatibleError as e:
                logger.error("OpenAI-compatible error, falling back to Ollama: %s", e)
            except Exception:
                logger.exception("Unexpected OpenAI-compatible error, falling back to Ollama")

        logger.info("LLM backend fallback: ollama model=%s", settings.ollama_model)
        llm = _get_llm()
        ai = llm.invoke(
            [SystemMessage(content=system_override or system_hint), HumanMessage(content=prompt)]
        )
        return str(getattr(ai, "content", ai))

    def _explicit_write_requested(user_text: str) -> bool:
        t = (user_text or "").lower()
        # Regex so both "make folder" and "make a folder" are recognized.
        if re.search(r"\b(create|make)\s+(a\s+)?(folder|directory|dir)\b", t):
            return True
        if re.search(r"\bmkdir\b", t):
            return True
        return any(
            k in t
            for k in [
                "write ",
                "save ",
                "delete ",
                "remove ",
                "edit ",
                "overwrite ",
                "update file",
                "create file",
                "create directory",
                "create folder",
            ]
        )

    allow_writes = _explicit_write_requested(text)

    def _requested_count(user_text: str) -> Optional[int]:
        m = re.search(r"(?i)\b(?:provide|list|give|show)\s+(\d{1,2})\b", user_text)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        return None

    desired_n = _requested_count(text)

    # Deterministic fast-path for "trending/current topics" style queries.
    # Local models can be inconsistent about tool loops; this ensures the capability works.
    if any(k in lower_q for k in ["trending topic", "trending topics", "what's trending", "whats trending", "current trending"]):
        try:
            ws = str(web_search_tool.invoke({"query": text}))
            # Parse the formatted results: blocks like "1. Title\nURL\nBody"
            items: list[tuple[str, str]] = []
            for block in ws.split("\n\n"):
                lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
                if len(lines) >= 2 and lines[0][0].isdigit() and lines[1].startswith("http"):
                    title = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
                    url = lines[1].strip()
                    items.append((title, url))
            n = desired_n or 5
            if not items:
                return {"output": "I could not retrieve results for trending topics from the internet."}
            out_lines = [f"{t} — {u}" for t, u in items[:n]]
            return {"output": "\n".join(out_lines)}
        except Exception:
            return {"output": "I could not retrieve results for trending topics from the internet."}

    # Deterministic fast-path for "crawl the link(s) and summarize".
    # If the user asks for latest/current/trending/news/today + (summary intent OR "what happened"),
    # we fetch the pages and summarize extracted text (instead of returning only snippets/links).
    has_current = any(k in lower_q for k in ["latest", "current", "trending", "news", "today"])
    # Handles common ASR typo "happend" as well as "happened"/"happening"/"happen".
    has_happen = bool(
        re.search(r"\bwhat\s+happ\w*\b", lower_q)
        or re.search(r"\bhapp\w*\s+today\b", lower_q)
        or re.search(r"\bhapp\w*\b", lower_q) and ("today" in lower_q)
    )
    has_summary_intent = any(
        k in lower_q
        for k in [
            "information",
            "summary",
            "summarize",
            "summarise",
            "explain",
            "overview",
            "what happened",
        ]
    )
    if has_current and (has_summary_intent or has_happen):
        try:
            crawled = str(web_crawl_tool.invoke({"query": text}))
            urls = re.findall(r"^URL:\s*(\S+)$", crawled, flags=re.MULTILINE)

            summary_system = (
                "You are ORION. Create a clear, concise summary using the provided extracted web text. "
                "Return ONLY the summary (no ACTION/INPUT, no JSON, no extra labels)."
            )
            summary_prompt = (
                f"User question: {text}\n\n"
                f"Extracted web content (may be partial):\n{crawled}\n\n"
                "Write a short summary (5-10 bullet points) and a final 1-line takeaway."
            )

            out = _llm_text(summary_prompt, system_override=summary_system).strip()
            if urls:
                sources = "\n".join([f"- {u}" for u in urls[:5]])
                out = out + "\n\nSources:\n" + sources
            return {"output": out}
        except Exception as e:
            return {"output": f"I could not crawl and summarize the links: {e}"}

    # Deterministic fast-path for "search my files / find in files" requests.
    # This makes it Cursor-like even if the model doesn't choose fs_search.
    if any(k in lower_q for k in ["search my files", "find in my files", "search in my files", "find in files", "search in files"]):
        # Try to extract query after "for ..."
        q = ""
        m = re.search(r"(?i)\bfor\s+(.+)$", text.strip())
        if m:
            q = m.group(1).strip().rstrip(".")
        if not q:
            q = text.strip()
        try:
            raw = str(fs_search_tool.invoke({"name": "", "q": q, "max_hits": 50}))
            # raw is JSON string
            import json  # local import to keep top clean

            data = json.loads(raw)
            hits = data.get("hits") or []
            if not hits:
                return {"output": f"No matches found for: {q!r}"}
            lines: list[str] = []
            for h in hits[:20]:
                p = h.get("path")
                kind = h.get("kind")
                prev = h.get("preview") or ""
                if kind == "content" and prev:
                    lines.append(f"{p} — {prev[:140]}")
                else:
                    lines.append(str(p))
            return {"output": "Matches:\n" + "\n".join(lines)}
        except Exception as e:
            return {"output": f"File search failed: {e}"}

    # Deterministic fast-path for creating a folder + writing a file + opening it.
    # Example: "create a folder in desktop and write something in it and open it after writing"
    def _looks_like_create_write_open_folder_request(t: str) -> bool:
        return bool(
            re.search(r"\b(create|make|mkdir)\b", t)
            and re.search(r"\b(folder|directory|dir)\b", t)
            and re.search(r"\b(write|save|create file|update file)\b", t)
            and re.search(r"\b(open|launch|start|show)\b", t)
        )

    if _looks_like_create_write_open_folder_request(lower_q):
        if not allow_writes:
            return {"output": 'You need to explicitly ask me to create/write. Example: "Create a folder named X on my desktop and write: hello in it, then open it."' }

        # Destination mapping under the sandbox root.
        dest = ""
        if re.search(r"\bdesktop\b", lower_q):
            dest = "Desktop"
        elif re.search(r"\bdocuments?\b", lower_q):
            dest = "Documents"
        elif re.search(r"\bdownloads?\b", lower_q):
            dest = "Downloads"

        # Extract folder name; if missing, use a safe default.
        folder_name = ""
        m_named = re.search(
            r"(?i)\b(?:named|called)\s+(.+?)(?=\s+(?:in|on|i)\b|[.!?]|$)",
            text.strip(),
        )
        if m_named:
            folder_name = m_named.group(1).strip()
        else:
            m_folder = re.search(
                r"(?i)\b(?:folder|directory|dir)\b\s*(?:named|called)?\s*(.+?)(?=\s+(?:in|on|i)\b|[.!?]|$)",
                text.strip(),
            )
            if m_folder:
                folder_name = m_folder.group(1).strip()

        folder_name = (folder_name.split()[0] if folder_name else "").strip().strip("'\"")
        if not folder_name:
            folder_name = "Orion_Folder"

        # Extract target filename (optional). Default: notes.txt
        file_name = "notes.txt"
        m_file = re.search(
            r"(?i)\b(?:file|document)\b\s*(?:named|called)?\s*([^\n,]+?\.(?:txt|md|log|json|csv))\b",
            text.strip(),
        )
        if m_file:
            file_name = m_file.group(1).strip().strip("'\"")
            # Keep simple (avoid accidental huge/unsafe strings)
            if len(file_name) > 60:
                file_name = file_name[-60:]

        # Extract content to write (optional). If "something" or empty, write a default.
        content = "Created by Orion."
        m_quote = re.search(r"['\"](.{1,1200})['\"]", text)
        if m_quote:
            candidate = (m_quote.group(1) or "").strip()
            if candidate and candidate.lower() not in {"something", "some", "some text"}:
                content = candidate
        else:
            m_after_write = re.search(
                r"(?is)\b(?:write|save)\s+(.+?)(?=\s+(?:in|inside|into|on)\b|[.!?]|$)",
                text.strip(),
            )
            if m_after_write:
                candidate = (m_after_write.group(1) or "").strip()
                if candidate and candidate.lower() not in {"something", "some", "some text", "text", "content"}:
                    content = candidate[:2000]

        # Create folder, write file, then open folder.
        target_dir = f"{dest}/{folder_name}" if dest else folder_name
        target_file = f"{target_dir}/{file_name}" if target_dir else file_name

        try:
            fs_mkdir_tool.invoke({"path": target_dir})
            fs_write_tool.invoke({"path": target_file, "content": content})
            system_open_tool.invoke({"target": target_dir})
            return {"output": f"Created folder '{target_dir}', wrote '{file_name}', and opened it."}
        except Exception as e:
            return {"output": f"Create/write/open failed: {e}"}

    # Deterministic fast-path for directory creation.
    def _looks_like_mkdir_request(t: str) -> bool:
        return bool(re.search(r"\b(mkdir|create|make)\b", t) and re.search(r"\b(folder|directory|dir)\b", t))

    if _looks_like_mkdir_request(lower_q):
        if not allow_writes:
            return {
                "output": 'You need to explicitly ask me to create a folder/directory. Example: "Create a new folder named asp on my desktop".'
            }

        # Destination mapping under the sandbox root.
        dest = ""
        if re.search(r"\bdesktop\b", lower_q):
            dest = "Desktop"
        elif re.search(r"\bdocuments?\b", lower_q):
            dest = "Documents"
        elif re.search(r"\bdownloads?\b", lower_q):
            dest = "Downloads"

        # Extract folder name after "named/called", or after "folder/directory" if present.
        # Also handle ASR slip: "in" -> "i".
        name = ""
        m_named = re.search(
            r"(?i)\b(?:named|called)\s+(.+?)(?=\s+(?:in|on|i)\b|[.!?]|$)",
            text.strip(),
        )
        if m_named:
            name = m_named.group(1).strip()
        else:
            m_folder = re.search(
                r"(?i)\b(?:folder|directory|dir)\b\s*(?:named|called)?\s*(.+?)(?=\s+(?:in|on|i)\b|[.!?]|$)",
                text.strip(),
            )
            if m_folder:
                name = m_folder.group(1).strip()

        # Voice cleanup: keep only first token for safety.
        if name:
            name = name.split()[0].strip("'\"")
        if not name:
            return {"output": "Please tell me the folder name (e.g., 'asp') and where (e.g., 'on my desktop')."}

        target_path = f"{dest}/{name}" if dest else name

        try:
            fs_mkdir_tool.invoke({"path": target_path})
            return {"output": f"Created folder: {target_path}"}
        except Exception as e:
            return {"output": f"Folder creation failed: {e}"}

    # Deterministic fast-path for opening apps/urls/files.
    # Examples: "open calculator", "launch chrome", "open https://...", "open Documents/notes.txt"
    # Avoid interfering with create+write+open requests (handled above).
    if re.search(r"\b(open|launch|start)\b", lower_q) and not (
        re.search(r"\b(create|make|mkdir)\b", lower_q)
        and re.search(r"\b(folder|directory|dir)\b", lower_q)
        and re.search(r"\b(write|save|edit|update file)\b", lower_q)
    ):
        def _to_url(q: str) -> str:
            s = (q or "").strip().strip('"').strip("'").rstrip(".")
            if not s:
                return ""
            if s.lower().startswith(("http://", "https://")):
                return s
            # If it looks like a domain, treat as URL.
            if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", s, flags=re.IGNORECASE):
                return "https://" + s
            # Otherwise treat as a google query.
            from urllib.parse import quote_plus

            return "https://www.google.com/search?q=" + quote_plus(s)

        # Handle: "open <app> and search <query/url>"
        m_combo = re.search(
            r"(?is)\b(?:open|launch|start)\s+(.+?)\s+\b(?:and\s+)?(?:search|google|find)\s+(.+)$",
            text.strip(),
        )
        if m_combo:
            app = m_combo.group(1).strip().strip("'\"").rstrip(".")
            q = m_combo.group(2).strip()
            url = _to_url(q)
            try:
                import json  # local import

                app_raw = str(system_open_tool.invoke({"target": app}))
                app_data = json.loads(app_raw)
                if not app_data.get("ok"):
                    return {
                        "output": f"Could not open: {app_data.get('target')}. {app_data.get('detail') or ''}".strip()
                    }
                if url:
                    system_open_tool.invoke({"target": url})
                    return {"output": f"Opened {app_data.get('target')} and searched: {url}"}
                return {"output": f"Opened: {app_data.get('target')}"}
            except Exception as e:
                return {"output": f"Open/search failed: {e}"}

        # Try to extract the target after the verb.
        m = re.search(r"(?i)\b(?:open|launch|start)\s+(.+)$", text.strip())
        target = (m.group(1).strip().strip("'\"") if m else "").rstrip(".")
        if target:
            try:
                raw = str(system_open_tool.invoke({"target": target}))
                import json  # local import

                data = json.loads(raw)
                if data.get("ok"):
                    return {"output": f"Opened: {data.get('target')}"}
                return {"output": f"Could not open: {data.get('target')}. {data.get('detail') or ''}".strip()}
            except Exception as e:
                return {"output": f"Open failed: {e}"}

    # Deterministic fast-path for finding a file anywhere on the PC.
    # Examples: "find resume.pdf", "locate *.docx", "search file named report"
    if re.search(r"\b(find|locate)\b", lower_q) and re.search(r"\b(file|folder|document|pdf|docx|xlsx|pptx|png|jpg|jpeg|zip|mp3|mp4|txt)\b", lower_q):
        m = re.search(r"(?i)\b(?:find|locate)\s+(?:a\s+)?(?:file\s+)?(.+)$", text.strip())
        pat = (m.group(1).strip().strip("'\"") if m else "").rstrip(".")
        if pat:
            try:
                raw = str(system_find_tool.invoke({"name": pat, "max_hits": 25}))
                import json  # local import

                data = json.loads(raw)
                hits = data.get("hits") or []
                if not hits:
                    return {"output": f"No matches found for: {pat!r}"}
                lines = [h.get("path") for h in hits[:25] if h.get("path")]
                return {"output": "Found:\n" + "\n".join(lines)}
            except Exception as e:
                return {"output": f"Find failed: {e}"}

    # Deterministic fast-path for finding installed apps.
    if re.search(r"\b(find|locate)\b", lower_q) and re.search(r"\b(app|application|program|software)\b", lower_q):
        m = re.search(r"(?i)\b(?:find|locate)\s+(.+)$", text.strip())
        q = (m.group(1).strip().strip("'\"") if m else "").rstrip(".")
        if q:
            try:
                raw = str(system_find_app_tool.invoke({"name": q, "max_hits": 25}))
                import json  # local import

                data = json.loads(raw)
                hits = data.get("hits") or []
                if not hits:
                    return {"output": f"No app matches found for: {q!r}"}
                lines = [h.get("path") for h in hits[:25] if h.get("path")]
                return {"output": "App matches:\n" + "\n".join(lines)}
            except Exception as e:
                return {"output": f"App find failed: {e}"}

    def _parse_react(reply: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Returns (action, tool_input, final).
        Accepts slightly messy outputs as long as markers exist.
        """
        if not reply:
            return None, None, None
        final_m = re.search(r"(?is)^\s*FINAL\s*:\s*(.+?)\s*$", reply, re.MULTILINE)
        if final_m:
            return None, None, final_m.group(1).strip()
        action_m = re.search(r"(?im)^\s*ACTION\s*:\s*([a-zA-Z0-9_]+)\s*$", reply)
        input_m = re.search(r"(?im)^\s*INPUT\s*:\s*(.+?)\s*$", reply)
        action = action_m.group(1).strip() if action_m else None
        tool_input = input_m.group(1).strip() if input_m else ""
        return action, tool_input, None

    def _count_items(final_text: str) -> int:
        # Count lines that look like "something — http..."
        n = 0
        for line in (final_text or "").splitlines():
            if "—" in line and "http" in line:
                n += 1
        return n

    def _run_tool(action: str, tool_input: str) -> str:
        if action == "web_search":
            # Tool expects {"query": "..."}
            return str(web_search_tool.invoke({"query": tool_input}))
        if action == "system_open":
            # Tool expects {"target": "..."}
            return str(system_open_tool.invoke({"target": tool_input}))
        if action == "system_find":
            # Tool expects {"name": "..."}
            return str(system_find_tool.invoke({"name": tool_input, "max_hits": 25}))
        if action == "system_find_app":
            return str(system_find_app_tool.invoke({"name": tool_input, "max_hits": 25}))
        if action == "fs_list":
            return str(fs_list_tool.invoke({"path": tool_input or ""}))
        if action == "fs_search":
            # Expect "name=<glob> | q=<text>" OR just a raw query string.
            name = ""
            q = ""
            if "|" in tool_input:
                parts = [p.strip() for p in tool_input.split("|")]
                for p in parts:
                    if p.lower().startswith("name="):
                        name = p.split("=", 1)[1].strip()
                    elif p.lower().startswith("q="):
                        q = p.split("=", 1)[1].strip()
            else:
                q = tool_input.strip()
            return str(fs_search_tool.invoke({"name": name, "q": q, "max_hits": 50}))
        if action == "fs_mkdir":
            if not allow_writes:
                return "ERROR: mkdir requested but user did not explicitly ask to create a folder."
            return str(fs_mkdir_tool.invoke({"path": tool_input}))
        if action == "fs_read":
            return str(fs_read_tool.invoke({"path": tool_input, "max_chars": 200_000}))
        if action == "fs_write":
            if not allow_writes:
                return "ERROR: write requested but user did not explicitly ask to write/change files."
            # Expect "path | content" convention
            if "|" not in tool_input:
                return "ERROR: fs_write INPUT must be: <path> | <content>"
            path, content = tool_input.split("|", 1)
            return str(fs_write_tool.invoke({"path": path.strip(), "content": content.lstrip()}))
        if action == "fs_delete":
            if not allow_writes:
                return "ERROR: delete requested but user did not explicitly ask to delete files."
            return str(fs_delete_tool.invoke({"path": tool_input}))
        if action == "shell_run":
            # Interpret tool_input as the full command; cwd left empty to default to fs_root.
            return str(shell_run_tool.invoke({"command": tool_input, "cwd": ""}))
        return f"ERROR: unknown tool '{action}'"

    scratchpad = ""
    user_msg = f"User ({lang}): {text}"

    max_steps = 8
    for _ in range(max_steps):
        prompt = (
            f"{system_hint}\n\n"
            f"{user_msg}\n\n"
            f"{scratchpad}\n"
            "Respond with either an ACTION/INPUT pair or FINAL.\n"
        )
        content = _llm_text(prompt)

        action, tool_input, final = _parse_react(content)
        if final is not None:
            if desired_n is not None and _count_items(final) < desired_n:
                scratchpad += (
                    f"\nOBSERVATION: Your FINAL did not include {desired_n} items in the required "
                    "format 'Topic — <link>'. Try again.\n"
                )
                continue
            return {"output": final}

        if not action:
            # Model didn't follow format; return raw content as best effort.
            return {"output": content or "No response."}

        observation = ""
        try:
            observation = _run_tool(action, tool_input or "")
        except Exception as e:
            observation = f"ERROR running {action}: {e}"

        scratchpad += f"\nACTION: {action}\nINPUT: {tool_input}\nOBSERVATION: {observation}\n"

    return {"output": "I couldn't complete the task within the tool step limit."}

