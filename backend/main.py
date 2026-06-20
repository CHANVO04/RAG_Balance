"""
backend/main.py — FastAPI app for Scientific RAG.
Run: uvicorn main:app --reload --port 8000  (from backend/ directory)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import quote
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── Path setup: backend/ must be on sys.path ─────────────────────────────────
_BACKEND = Path(__file__).parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

load_dotenv(_BACKEND / ".env")

from openai import AsyncOpenAI
from schemas import (
    ChatRequest, DocumentInfo, GraphData, IngestResponse,
    SourceInfo, TaskStatus, UMAPPoint, VectorChunkInfo, WorkspaceInfo,
)

# ── Lazy imports (heavy — only loaded when first endpoint is called) ──────────
def _get_rag_prepare():
    from query.engine import rag_prepare
    return rag_prepare

def _get_add_to_cache():
    from query.cache import add_to_cache
    return add_to_cache

def _get_offline_ingest():
    from ingest.pipeline import offline_ingest
    return offline_ingest

def _get_delete_document():
    from ingest.pipeline import delete_document
    return delete_document

def _get_list_documents():
    from ingest.registry import list_ingested_documents
    return list_ingested_documents

def _get_graph_for_viz():
    from kg_neo4j_ops import get_graph_for_viz
    return get_graph_for_viz

def _get_qdrant_client():
    from query.clients import get_qdrant_client
    return get_qdrant_client

def _get_clamp_retrieval_settings():
    from query.retrieval_selection import clamp_retrieval_settings
    return clamp_retrieval_settings


def _is_safe_document_file_name(file_name: str) -> bool:
    if not file_name or file_name in {".", ".."}:
        return False
    if "\x00" in file_name or ":" in file_name:
        return False
    if "/" in file_name or "\\" in file_name:
        return False
    return os.path.basename(file_name) == file_name and Path(file_name).name == file_name


# ── Config ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = "gpt-4.1-mini"
DATA_DIR       = str(_BACKEND / "data")
DB_DIR         = str(_BACKEND / "db")
WORKSPACE_ROOT = _BACKEND / "workspaces"
WORKSPACE_FILE = WORKSPACE_ROOT / "workspaces.json"
SUPPORTED_UPLOAD_EXTS = {".pdf", ".docx", ".pptx", ".html", ".htm"}
SSE_HEARTBEAT_SECONDS = 15.0
_PLAIN_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hello there",
    "hi there",
    "xin chao",
    "chao",
    "chao ban",
    "xin chao ban",
}
_GREETING_RESPONSE = (
    "Xin chào! Bạn có thể upload tài liệu ở Library hoặc hỏi một câu cụ thể "
    "về nội dung tài liệu để mình truy xuất bằng Hybrid Graph RAG."
)
DEFAULT_MAX_INPUT_TOKENS = 8000
MIN_MAX_INPUT_TOKENS = 2048
MAX_MAX_INPUT_TOKENS = 16000

_INGEST_MODE_SETTINGS = {
    "only_vector_fast": {"kg_mode": "none", "skip_visual_analysis": True},
    "only_vector_multimodal": {"kg_mode": "none", "skip_visual_analysis": False},
    "only_vector": {"kg_mode": "none", "skip_visual_analysis": False},
    "vector": {"kg_mode": "none", "skip_visual_analysis": False},  # backward-compatible alias
    "hybrid": {"kg_mode": "light", "skip_visual_analysis": False},
    "only_graph": {"kg_mode": "light", "skip_visual_analysis": False}, # placeholder until graph-only ingest is implemented
}


def _resolve_ingest_settings(ingest_mode: str) -> dict:
    mode = (ingest_mode or "hybrid").strip().lower()
    return _INGEST_MODE_SETTINGS.get(mode, _INGEST_MODE_SETTINGS["hybrid"])


def _resolve_ingest_kg_mode(ingest_mode: str) -> str:
    return _resolve_ingest_settings(ingest_mode)["kg_mode"]


def _resolve_query_mode(query_mode: str) -> dict:
    mode = (query_mode or "hybrid").strip().lower()
    if mode == "only_vector_fast":
        return {"kg_mode": "vector", "use_rerank": False, "use_visuals": False}
    if mode in {"only_vector_multimodal", "only_vector", "vector"}:
        return {"kg_mode": "vector", "use_rerank": False, "use_visuals": True}
    return {"kg_mode": "default", "use_rerank": False, "use_visuals": True}


def _resolve_retrieval_settings(req: ChatRequest) -> tuple[int, float, int]:
    clamp_retrieval_settings = _get_clamp_retrieval_settings()
    requested_limit = req.qdrant_limit if req.qdrant_limit is not None else req.top_k
    qdrant_limit, score_threshold = clamp_retrieval_settings(
        requested_limit,
        req.score_threshold,
    )
    try:
        max_context_chunks = int(req.max_context_chunks or 8)
    except (TypeError, ValueError):
        max_context_chunks = 8
    max_context_chunks = max(2, min(12, max_context_chunks))
    return qdrant_limit, score_threshold, max_context_chunks


def _resolve_generation_settings(req: ChatRequest) -> dict[str, float | int]:
    try:
        temperature = float(req.temperature if req.temperature is not None else 0.2)
    except (TypeError, ValueError):
        temperature = 0.2
    try:
        max_output_tokens = int(req.max_output_tokens or 1024)
    except (TypeError, ValueError):
        max_output_tokens = 1024
    try:
        max_input_tokens = int(req.max_input_tokens or DEFAULT_MAX_INPUT_TOKENS)
    except (TypeError, ValueError):
        max_input_tokens = DEFAULT_MAX_INPUT_TOKENS
    return {
        "temperature": max(0.0, min(0.7, temperature)),
        "max_output_tokens": max(256, min(2048, max_output_tokens)),
        "max_input_tokens": max(MIN_MAX_INPUT_TOKENS, min(MAX_MAX_INPUT_TOKENS, max_input_tokens)),
    }


def _default_workspace() -> WorkspaceInfo:
    created_at = (
        datetime.fromtimestamp((_BACKEND / "data").stat().st_ctime).isoformat()
        if (_BACKEND / "data").exists() else datetime.now().isoformat()
    )
    return WorkspaceInfo(
        id="default",
        name="General Science",
        description="Vector + Visuals workspace",
        strategy="only_vector_multimodal",
        icon="SR",
        collectionName="scientific_papers",
        systemPrompt="You are a helpful scientific research assistant.",
        createdAt=created_at,
        updatedAt=created_at,
        isSetupComplete=True,
    )


def _find_workspace(workspace_id: str) -> WorkspaceInfo:
    normalized_id = _safe_workspace_id(workspace_id)
    for workspace in _load_workspaces():
        if workspace.id == normalized_id:
            return workspace
    return _default_workspace()


def _workspace_strategy(workspace_id: str) -> str:
    workspace = _find_workspace(workspace_id)
    strategy = (workspace.strategy or "only_vector_multimodal").strip().lower()
    if strategy in {"only_vector", "vector"}:
        return "only_vector_multimodal"
    if strategy in _INGEST_MODE_SETTINGS:
        return strategy
    return "only_vector_multimodal"


def _resolve_workspace_ingest_settings(workspace_id: str, requested_ingest_mode: str) -> dict:
    strategy = _workspace_strategy(workspace_id)
    settings = dict(_resolve_ingest_settings(strategy))
    settings["effective_strategy"] = strategy
    settings["requested_ingest_mode"] = requested_ingest_mode
    return settings


def _resolve_workspace_query_settings(workspace_id: str, requested_query_mode: str) -> dict:
    strategy = _workspace_strategy(workspace_id)
    settings = dict(_resolve_query_mode(strategy))
    settings["effective_strategy"] = strategy
    settings["requested_query_mode"] = requested_query_mode
    return settings

_async_openai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ── Task store (in-memory, F5-safe per process) ───────────────────────────────
_tasks:       dict[str, TaskStatus] = {}
_active_task: str | None            = None
_umap_cache:  dict[str, dict]       = {}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Scientific RAG API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve PDF files
os.makedirs(DATA_DIR, exist_ok=True)
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/workspace-data", StaticFiles(directory=str(WORKSPACE_ROOT)), name="workspace-data")
app.mount("/assets", StaticFiles(directory=str(_BACKEND / "db" / "assets")), name="assets")


def _safe_workspace_id(workspace_id: str | None) -> str:
    raw = (workspace_id or "default").strip() or "default"
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in ("-", "_"))
    return safe or "default"


def _workspace_paths(workspace_id: str | None) -> tuple[str, str]:
    wid = _safe_workspace_id(workspace_id)
    if wid == "default":
        return DATA_DIR, DB_DIR
    root = WORKSPACE_ROOT / wid
    data_dir = root / "data"
    db_dir = root / "db"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir), str(db_dir)


def _load_workspaces() -> list[WorkspaceInfo]:
    default = _default_workspace()
    if not WORKSPACE_FILE.exists():
        return [default]
    try:
        raw = json.loads(WORKSPACE_FILE.read_text(encoding="utf-8"))
        loaded = [WorkspaceInfo(**item) for item in raw if item.get("id") != "default"]
        return [default, *loaded]
    except Exception:
        return [default]


def _save_workspaces(workspaces: list[WorkspaceInfo]) -> None:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = [w.model_dump() for w in workspaces if w.id != "default"]
    WORKSPACE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _workspace_file_names(workspace_id: str | None) -> list[str]:
    _, db_dir = _workspace_paths(workspace_id)
    list_docs = _get_list_documents()
    try:
        docs = list_docs(db_dir)
        return [d.get("file_name", "") for d in docs if d.get("file_name")]
    except Exception:
        return []


def _clear_directory_contents(root_dir: str) -> int:
    root = Path(root_dir).resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return 0

    removed = 0
    for item in root.iterdir():
        try:
            if item.is_dir():
                removed += sum(1 for path in item.rglob("*") if path.is_file())
                shutil.rmtree(item)
            else:
                item.unlink()
                removed += 1
        except Exception as exc:
            raise RuntimeError(f"Failed to delete {item}: {exc}") from exc
    return removed


def _delete_remaining_workspace_graph(workspace_id: str) -> dict[str, int]:
    """Delete leftover Neo4j graph records for a workspace after file-scoped cleanup."""
    from kg_neo4j_manager import get_neo4j_manager

    manager = get_neo4j_manager()
    with manager.session() as session:
        rel_result = session.run(
            """
            MATCH ()-[r]->()
            WHERE r.workspace_id = $workspace_id
            WITH collect(r) AS rels, count(r) AS deleted
            FOREACH (r IN rels | DELETE r)
            RETURN deleted
            """,
            workspace_id=workspace_id,
        )
        removed_relationships = int(rel_result.single()["deleted"] or 0)
        node_result = session.run(
            """
            MATCH (n)
            WHERE n.workspace_id = $workspace_id
            WITH collect(n) AS nodes, count(n) AS deleted
            FOREACH (n IN nodes | DETACH DELETE n)
            RETURN deleted
            """,
            workspace_id=workspace_id,
        )
        removed_nodes = int(node_result.single()["deleted"] or 0)

    return {"nodes": removed_nodes, "relationships": removed_relationships}


def _normalize_intent_text(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.lower())
    ascii_text = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", ascii_text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_plain_greeting(question: str) -> bool:
    normalized = _normalize_intent_text(question)
    if not normalized:
        return False
    if len(normalized) > 24:
        return False
    return normalized in _PLAIN_GREETINGS


# ── SSE helper ────────────────────────────────────────────────────────────────
def sse_fmt(event_type: str, data: dict) -> str:
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_heartbeat() -> str:
    return ": heartbeat\n\n"


def _get_token_encoding():
    try:
        import tiktoken

        try:
            return tiktoken.encoding_for_model(LLM_MODEL)
        except KeyError:
            return tiktoken.get_encoding("o200k_base")
    except Exception:
        return None


def _count_text_tokens(text: str) -> int:
    encoding = _get_token_encoding()
    if encoding is not None:
        return len(encoding.encode(text or ""))
    return max(1, (len(text or "") + 3) // 4)


def _trim_text_to_token_limit(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""

    value = text or ""
    encoding = _get_token_encoding()
    if encoding is not None:
        tokens = encoding.encode(value)
        if len(tokens) <= max_tokens:
            return value
        return encoding.decode(tokens[:max_tokens]).rstrip()

    max_chars = max(1, max_tokens * 4)
    return value[:max_chars].rstrip()


def _count_chat_input_tokens(messages: list[dict[str, Any]]) -> int:
    # Mirrors OpenAI chat payload shape closely enough for budget enforcement.
    # The small per-message overhead prevents dashboards from drifting upward.
    return 2 + sum(
        4 + _count_text_tokens(str(message.get("content") or ""))
        for message in messages
    )


def _split_default_user_prompt(user_prompt: str) -> tuple[str, str, str]:
    start_marker = "Context:\n"
    end_marker = "\n\nQuestion:"
    start = user_prompt.find(start_marker)
    end = user_prompt.rfind(end_marker)
    if start < 0 or end <= start:
        return "", user_prompt, ""
    context_start = start + len(start_marker)
    return user_prompt[:context_start], user_prompt[context_start:end], user_prompt[end:]


def _enforce_input_token_budget(
    system_prompt: str,
    user_prompt: str,
    max_input_tokens: int,
) -> tuple[str, str, dict[str, int | bool]]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    original_tokens = _count_chat_input_tokens(messages)
    if original_tokens <= max_input_tokens:
        return system_prompt, user_prompt, {
            "input_tokens_before_trim": original_tokens,
            "input_tokens_after_trim": original_tokens,
            "input_trimmed": False,
        }

    prefix, context, suffix = _split_default_user_prompt(user_prompt)
    fixed_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{prefix}{suffix}"},
    ]
    available_context_tokens = max(0, max_input_tokens - _count_chat_input_tokens(fixed_messages))
    trimmed_context = _trim_text_to_token_limit(context, available_context_tokens)
    trimmed_user_prompt = f"{prefix}{trimmed_context}{suffix}"

    trimmed_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": trimmed_user_prompt},
    ]
    while _count_chat_input_tokens(trimmed_messages) > max_input_tokens and trimmed_context:
        available_context_tokens = max(0, available_context_tokens - 32)
        trimmed_context = _trim_text_to_token_limit(context, available_context_tokens)
        trimmed_user_prompt = f"{prefix}{trimmed_context}{suffix}"
        trimmed_messages[1]["content"] = trimmed_user_prompt

    return system_prompt, trimmed_user_prompt, {
        "input_tokens_before_trim": original_tokens,
        "input_tokens_after_trim": _count_chat_input_tokens(trimmed_messages),
        "input_trimmed": True,
    }


def _query_mode_label(query_mode: str) -> str:
    mode = (query_mode or "hybrid").strip().lower()
    if mode == "only_vector_fast":
        return "Only Vector Fast"
    if mode in {"only_vector_multimodal", "only_vector", "vector"}:
        return "Only Vector Multimodal"
    return "Hybrid Graph + Vector"


def _file_scope_label(selected_files: list[str]) -> str:
    if not selected_files:
        return "Searching all workspace documents."
    if len(selected_files) == 1:
        return "Searching 1 selected document."
    return f"Searching {len(selected_files)} selected documents."


def _stage_timings_to_ms(stage_timings: dict) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for file_name, timings in (stage_timings or {}).items():
        if not isinstance(timings, dict):
            continue
        result[str(file_name)] = {
            str(stage): int(round(float(seconds or 0) * 1000))
            for stage, seconds in timings.items()
        }
    return result

# ── Source builder ────────────────────────────────────────────────────────────
def _build_sources(sources_structured: list[dict], base_url: str, workspace_id: str = "default") -> list[SourceInfo]:
    """
    Convert sources_structured (from rag_prepare) to SourceInfo list.
    sources_structured items have keys: id, file_name, page, score,
    section_label, has_table, has_formula, has_image
    """
    result = []
    for s in sources_structured:
        file_name = s.get("file_name", "")
        encoded_file_name = quote(file_name)
        asset_path = s.get("asset_path", "")
        asset_url = ""
        normalized_asset = str(asset_path or "").replace("\\", "/")
        marker = "backend/db/assets/"
        if marker in normalized_asset:
            asset_url = f"{base_url}/assets/{normalized_asset.split(marker, 1)[1]}"
        result.append(SourceInfo(
            id=s.get("id", 0),
            citation_id=s.get("citation_id", ""),
            ref_id=s.get("ref_id", s.get("citation_id", "")),
            kind=s.get("kind", "text"),
            visual_id=s.get("visual_id", ""),
            asset_path=asset_path,
            asset_url=s.get("asset_url", "") or asset_url,
            content=s.get("content", ""),
            file_name=file_name,
            page=int(s.get("page", 1)),
            score=float(s.get("score", 0.0)),
            section_label=s.get("section_label", ""),
            has_table=bool(s.get("has_table", False)),
            has_formula=bool(s.get("has_formula", False)),
            has_image=bool(s.get("has_image", False)),
            pdf_url=f"{base_url}/data/{encoded_file_name}" if _safe_workspace_id(workspace_id) == "default"
            else f"{base_url}/workspace-data/{_safe_workspace_id(workspace_id)}/data/{encoded_file_name}",
            display="",
        ))
    return result

# ── SSE generator ─────────────────────────────────────────────────────────────
async def _sse_generator(req: ChatRequest, base_url: str):
    workspace_id = _safe_workspace_id(req.workspace_id)
    selected_files = req.selected_files or _workspace_file_names(workspace_id)
    query_settings = _resolve_workspace_query_settings(workspace_id, req.query_mode)
    kg_mode = query_settings["kg_mode"]
    qdrant_limit, score_threshold, max_context_chunks = _resolve_retrieval_settings(req)
    generation_settings = _resolve_generation_settings(req)
    mode_label = _query_mode_label(query_settings["effective_strategy"])

    yield sse_fmt("status", {"step": "Đang phân tích...", "substep": mode_label})
    yield sse_fmt("thought", {"content": "Analyzing question"})
    yield sse_fmt("thought", {
        "content": (
            f"Using {mode_label} retrieval with qdrant_limit={qdrant_limit}, "
            f"score_threshold={score_threshold:.2f}, max_context_chunks={max_context_chunks}, "
            f"temperature={generation_settings['temperature']:.2f}, "
            f"max_input_tokens={generation_settings['max_input_tokens']}, "
            f"max_output_tokens={generation_settings['max_output_tokens']}."
        )
    })
    if query_settings["requested_query_mode"] != query_settings["effective_strategy"]:
        yield sse_fmt("thought", {
            "content": (
                "Workspace strategy overrides requested mode: "
                f"{query_settings['requested_query_mode']} -> {query_settings['effective_strategy']}."
            )
        })

    if _is_plain_greeting(req.question):
        yield sse_fmt("thought", {"content": "Greeting detected; retrieval is not needed."})
        yield sse_fmt("status", {"step": "Đang tạo câu trả lời...", "substep": "Greeting"})
        yield sse_fmt("token", {"content": _GREETING_RESPONSE})
        yield sse_fmt("done", {"kg_context": ""})
        return

    yield sse_fmt("status", {"step": "Đang tìm kiếm...", "substep": mode_label})
    yield sse_fmt("thought", {"content": "Searching workspace evidence"})
    yield sse_fmt("thought", {"content": _file_scope_label(selected_files)})
    yield sse_fmt("thought", {"content": "Retrieving vector evidence."})
    if kg_mode == "default":
        yield sse_fmt("thought", {"content": "Preparing hybrid graph/visual context."})

    try:
        rag_prepare = _get_rag_prepare()
        retrieval_task = asyncio.create_task(asyncio.to_thread(
            rag_prepare,
            req.question,
            qdrant_limit,
            max_context_chunks,
            query_settings["use_rerank"],
            req.use_cache if req.use_cache is not None else True,
            kg_mode,
            selected_files or None,
            workspace_id,
            query_settings["use_visuals"],
            score_threshold,
            req.custom_system_instruction,
            req.user_prompt_template,
        ))
        while not retrieval_task.done():
            try:
                prepared = await asyncio.wait_for(
                    asyncio.shield(retrieval_task),
                    timeout=SSE_HEARTBEAT_SECONDS,
                )
                break
            except asyncio.TimeoutError:
                yield sse_heartbeat()
        else:
            prepared = retrieval_task.result()
    except Exception as e:
        yield sse_fmt("error", {"message": str(e)})
        return

    # Cache hit
    if prepared.get("cache_hit"):
        yield sse_fmt("done", {
            "cached": True,
            "answer": prepared["cached_answer"],
            "sources": [],
            "kg_context": "",
        })
        return

    # Error from retrieval
    if prepared.get("error"):
        yield sse_fmt("error", {"message": prepared["error"]})
        return

    # Build and emit sources early (PDF pre-warm)
    sources = _build_sources(prepared.get("sources_structured", []), base_url, workspace_id)
    yield sse_fmt("thought", {"content": f"Preparing {len(sources)} cited source(s)."})
    yield sse_fmt("early_sources", {"sources": [s.model_dump() for s in sources]})
    yield sse_fmt("status", {"step": "Đang tạo câu trả lời...", "substep": "LLM"})
    yield sse_fmt("thought", {"content": "Generating grounded answer from retrieved sources."})

    full_answer = ""
    try:
        system_prompt, user_prompt, input_budget_trace = _enforce_input_token_budget(
            prepared["system_prompt"],
            prepared["user_prompt"],
            int(generation_settings["max_input_tokens"]),
        )
        stream = await _async_openai.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=int(generation_settings["max_output_tokens"]),
            temperature=float(generation_settings["temperature"]),
            stream=True,
        )
        async for chunk in stream:
            tok = chunk.choices[0].delta.content or ""
            if tok:
                full_answer += tok
                yield sse_fmt("token", {"content": tok})
    except Exception as e:
        yield sse_fmt("error", {"message": str(e)})
        return

    # Cache the answer
    if prepared.get("use_cache", True):
        try:
            add_to_cache = _get_add_to_cache()
            await asyncio.to_thread(
                add_to_cache,
                req.question,
                full_answer,
                workspace_id=workspace_id,
                file_names=selected_files,
            )
        except Exception:
            pass  # cache failure is non-fatal

    retrieval_trace = prepared.get("retrieval_trace", {}) or {}
    if isinstance(retrieval_trace, dict):
        trace_settings = retrieval_trace.setdefault("settings", {})
        if isinstance(trace_settings, dict):
            trace_settings["temperature"] = generation_settings["temperature"]
            trace_settings["max_input_tokens"] = generation_settings["max_input_tokens"]
            trace_settings["max_output_tokens"] = generation_settings["max_output_tokens"]
            trace_settings["workspace_strategy"] = query_settings["effective_strategy"]
            trace_settings["requested_query_mode"] = query_settings["requested_query_mode"]
            trace_settings.update(input_budget_trace)

    yield sse_fmt("done", {
        "kg_context": prepared.get("kg_context", ""),
        "kg_sources": prepared.get("kg_sources", []),
        "retrieval_trace": retrieval_trace,
    })


# ── Ingest background task ────────────────────────────────────────────────────
def _run_ingest(
    file_path: str,
    file_name: str,
    task_id: str,
    data_dir: str = DATA_DIR,
    db_dir: str = DB_DIR,
    ingest_mode: str = "hybrid",
    workspace_id: str = "default",
) -> None:
    global _active_task, _umap_cache
    started_wall = time.time()
    started_perf = time.perf_counter()

    def _log(msg: str, progress: int = -1, step: str = ""):
        task = _tasks[task_id]
        task.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        if progress >= 0:
            task.progress = progress
        if step:
            task.current_step = step

    try:
        _tasks[task_id].status = "processing"
        _tasks[task_id].started_at = started_wall
        _log("Bắt đầu ingest pipeline...", 5, "Khởi tạo")

        offline_ingest = _get_offline_ingest()

        def report_progress(step: str, progress: int) -> None:
            _log(step, progress, step)

        ingest_settings = _resolve_workspace_ingest_settings(workspace_id, ingest_mode)
        if ingest_settings["requested_ingest_mode"] != ingest_settings["effective_strategy"]:
            _log(
                "Workspace strategy overrides requested ingest mode: "
                f"{ingest_settings['requested_ingest_mode']} -> {ingest_settings['effective_strategy']}",
                8,
            )
        result = offline_ingest(
            data_dir=data_dir,
            vector_dir=db_dir,
            force=False,
            kg_mode=ingest_settings["kg_mode"],
            skip_visual_analysis=ingest_settings["skip_visual_analysis"],
            workspace_id=workspace_id,
            progress_callback=report_progress,
            verbose=True,
        )
        completed_wall = time.time()
        _tasks[task_id].completed_at = completed_wall
        _tasks[task_id].elapsed_ms = int(round((time.perf_counter() - started_perf) * 1000))
        _tasks[task_id].stage_timings_ms = _stage_timings_to_ms(result.get("stage_timings", {}))
        if result.get("new_files"):
            try:
                from query.cache import clear_cache_entries
                removed_cache = clear_cache_entries(workspace_id=workspace_id)
                if removed_cache:
                    _log(f"Đã làm mới semantic cache workspace: {removed_cache} entries", 96)
            except Exception as cache_exc:
                _log(f"[WARN] Không thể làm mới semantic cache: {cache_exc}", 96)
        _log(f"Hoàn thành: {result.get('status', 'done')}", 100, "Xong")
        _tasks[task_id].status   = "done"
        _tasks[task_id].progress = 100
        _umap_cache.clear()  # invalidate UMAP cache for all workspace views

    except Exception as e:
        _tasks[task_id].completed_at = time.time()
        _tasks[task_id].elapsed_ms = int(round((time.perf_counter() - started_perf) * 1000))
        _tasks[task_id].status = "error"
        _tasks[task_id].error  = str(e)
        _log(f"LỖI: {e}", step="Lỗi")
    finally:
        _active_task = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/query-default-prompts")
async def query_default_prompts():
    from query.prompt_builder import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT_TEMPLATE

    return {
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "user_prompt_template": DEFAULT_USER_PROMPT_TEMPLATE,
    }


@app.get("/api/workspaces", response_model=List[WorkspaceInfo])
async def list_workspaces():
    return _load_workspaces()


@app.post("/api/workspaces", response_model=WorkspaceInfo)
async def create_workspace(workspace: WorkspaceInfo):
    workspace.id = _safe_workspace_id(workspace.id)
    workspaces = _load_workspaces()
    if any(w.id == workspace.id for w in workspaces):
        raise HTTPException(409, f"Workspace '{workspace.id}' already exists.")
    _workspace_paths(workspace.id)
    workspaces.append(workspace)
    _save_workspaces(workspaces)
    return workspace


@app.put("/api/workspaces/{workspace_id}", response_model=WorkspaceInfo)
async def update_workspace(workspace_id: str, workspace: WorkspaceInfo):
    wid = _safe_workspace_id(workspace_id)
    workspaces = _load_workspaces()
    existing = next((w for w in workspaces if w.id == wid), None)
    if existing is None:
        raise HTTPException(404, f"Workspace '{wid}' not found.")

    if existing.isSetupComplete:
        strategy = existing.strategy or "only_vector_multimodal"
        is_setup_complete = True
    else:
        strategy = workspace.strategy or "only_vector_multimodal"
        is_setup_complete = workspace.isSetupComplete

    updated = workspace.model_copy(update={
        "id": wid,
        "strategy": strategy,
        "isSetupComplete": is_setup_complete,
    })
    next_workspaces = [updated if w.id == wid else w for w in workspaces]
    _save_workspaces(next_workspaces)
    return updated


@app.delete("/api/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    wid = _safe_workspace_id(workspace_id)
    workspaces = _load_workspaces()
    is_registered_workspace = any(w.id == wid for w in workspaces)

    data_dir, db_dir = _workspace_paths(wid)
    source_files = _workspace_file_names(wid)
    report: dict[str, object] = {
        "status": "ok",
        "workspace_id": wid,
        "registered_workspace": is_registered_workspace,
        "source_files": source_files,
        "qdrant": {},
        "removed_kg_edges": 0,
        "removed_kg_nodes": 0,
        "removed_kg_relationships": 0,
        "removed_visual_assets": 0,
        "removed_semantic_cache_entries": 0,
        "removed_local_files": 0,
        "errors": [],
    }

    # 1. Qdrant first. If this fails, keep local files in place for a safe retry.
    try:
        from query.clients import get_qdrant_client
        from ingest.vector_store import delete_workspace_from_qdrant
        qdrant_client = get_qdrant_client()
        qdrant_counts = delete_workspace_from_qdrant(qdrant_client, wid)
        report["qdrant"] = qdrant_counts
    except Exception as e:
        raise HTTPException(500, f"Qdrant workspace cleanup failed: {e}") from e

    # 2. Clean up Neo4j graph only for Hybrid workspaces.
    if _workspace_strategy(wid) == "hybrid":
        try:
            from kg_neo4j_ops import delete_document_kg
            for fname in source_files:
                try:
                    report["removed_kg_edges"] = int(report["removed_kg_edges"]) + int(delete_document_kg(fname, workspace_id=wid) or 0)
                except Exception as e:
                    report["errors"].append(f"Neo4j cleanup failed for {fname}: {e}")
            leftover_graph = _delete_remaining_workspace_graph(wid)
            report["removed_kg_nodes"] = leftover_graph["nodes"]
            report["removed_kg_relationships"] = int(report["removed_kg_relationships"]) + leftover_graph["relationships"]
        except Exception as e:
            report["errors"].append(f"Neo4j driver cleanup failed: {e}")

    # 3. Clean up visual assets that may live in global backend/db/assets.
    try:
        from ingest.registry import load_doc_store, load_registry
        from ingest.pipeline import delete_visual_assets_for_file
        registry = load_registry(db_dir)
        store = load_doc_store(db_dir)
        for fname in source_files:
            report["removed_visual_assets"] = int(report["removed_visual_assets"]) + int(
                delete_visual_assets_for_file(fname, db_dir, registry, store)
            )
    except Exception as e:
        report["errors"].append(f"Visual asset cleanup failed: {e}")

    # 4. Clear semantic cache entries for this workspace, including old legacy entries.
    try:
        from query.cache import clear_cache_entries
        report["removed_semantic_cache_entries"] = clear_cache_entries(workspace_id=wid)
    except Exception as e:
        report["errors"].append(f"Semantic cache cleanup failed: {e}")

    # 5. Clean up physical files on disk.
    if wid == "default":
        try:
            report["removed_local_files"] = _clear_directory_contents(DATA_DIR) + _clear_directory_contents(DB_DIR)
            Path(DB_DIR, "assets").mkdir(parents=True, exist_ok=True)
        except Exception as e:
            report["errors"].append(str(e))
    else:
        root = WORKSPACE_ROOT / wid
        if root.exists():
            try:
                report["removed_local_files"] = sum(1 for path in root.rglob("*") if path.is_file())
                shutil.rmtree(root)
                print(f"[DELETE WORKSPACE] Deleted physical directory: {root}")
            except Exception as e:
                report["errors"].append(f"Failed to delete directory {root}: {e}")

    if report["errors"]:
        raise HTTPException(500, json.dumps(report, ensure_ascii=False))

    # 6. Remove from workspaces.json list.
    next_workspaces = [w for w in workspaces if w.id != wid]
    _save_workspaces(next_workspaces)

    # Clear cache
    _umap_cache.pop(wid, None)

    report["message"] = (
        "Đã reset workspace mặc định." if wid == "default"
        else f"Đã xóa workspace '{wid}' và dữ liệu local liên quan."
    )
    if not is_registered_workspace and wid != "default":
        report["message"] = f"Đã xóa workspace orphan '{wid}' và dữ liệu local liên quan."
    return report


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    base_url = str(request.base_url).rstrip("/")
    return StreamingResponse(
        _sse_generator(req, base_url),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile,
    background: BackgroundTasks,
    workspace_id: str = Query("default"),
    ingest_mode: str = Query("hybrid"),
):
    global _active_task
    file_name = Path(file.filename or "").name
    ext = Path(file_name).suffix.lower()
    if ext not in SUPPORTED_UPLOAD_EXTS:
        allowed = ", ".join(sorted(SUPPORTED_UPLOAD_EXTS))
        raise HTTPException(400, f"Unsupported file type '{ext or 'none'}'. Supported: {allowed}.")

    if _active_task:
        raise HTTPException(409, "Đang có tác vụ ingest đang chạy. Vui lòng đợi.")

    task_id   = str(uuid4())
    data_dir, db_dir = _workspace_paths(workspace_id)
    dest_path = os.path.join(data_dir, file_name)

    # Save uploaded file
    with open(dest_path, "wb") as f:
        f.write(await file.read())

    # Estimate time: ~50KB per page, 2 min per 10 pages
    file_size = os.path.getsize(dest_path)
    est_pages = max(1, file_size // 51200)
    est_mins  = max(2, est_pages // 5)

    _tasks[task_id] = TaskStatus(
        task_id=task_id,
        status="queued",
        progress=0,
        current_step="Chờ xử lý",
        logs=[f"[{datetime.now().strftime('%H:%M:%S')}] File '{file_name}' đã được upload."],
        queued_at=time.time(),
    )
    _active_task = task_id
    background.add_task(
        _run_ingest,
        dest_path,
        file_name,
        task_id,
        data_dir,
        db_dir,
        ingest_mode,
        _safe_workspace_id(workspace_id),
    )

    return IngestResponse(
        task_id=task_id,
        status="queued",
        file_name=file_name,
        estimated_minutes=est_mins,
    )


@app.get("/api/task-status/{task_id}", response_model=TaskStatus)
async def task_status(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(404, f"Task '{task_id}' không tồn tại.")
    return _tasks[task_id]


@app.get("/api/documents", response_model=List[DocumentInfo])
async def list_documents(workspace_id: str = Query("default")):
    data_dir, db_dir = _workspace_paths(workspace_id)
    list_docs = _get_list_documents()
    docs = await asyncio.to_thread(list_docs, db_dir)
    return [
        DocumentInfo(
            file_name=d.get("file_name", ""),
            chunk_count=d.get("total_dedup_chunks", 0),
            ingested_at=d.get("ingested_at", ""),
            sha256=d.get("file_hash", ""),
            total_pages=d.get("total_pages", 0),
            file_size=os.path.getsize(os.path.join(data_dir, d.get("file_name", "")))
            if d.get("file_name") and os.path.exists(os.path.join(data_dir, d.get("file_name", ""))) else None,
            ingest_mode=d.get("ingest_mode", ""),
            processing_time_seconds=d.get("processing_time_seconds"),
            stage_timings=d.get("stage_timings", {}) or {},
            embedding=d.get("embedding"),
            total_tables=int(d.get("total_tables", 0) or 0),
            total_formulas=int(d.get("total_formulas", 0) or 0),
            total_images=int(d.get("total_images", 0) or 0),
        )
        for d in docs
    ]


@app.delete("/api/documents/{file_name}")
async def delete_document_endpoint(file_name: str, workspace_id: str = Query("default")):
    if not _is_safe_document_file_name(file_name):
        raise HTTPException(400, "Invalid document file name.")
    data_dir, db_dir = _workspace_paths(workspace_id)
    delete_doc = _get_delete_document()
    result = await asyncio.to_thread(
        delete_doc,
        file_name,
        db_dir,
        data_dir,
        _safe_workspace_id(workspace_id),
        delete_kg=_workspace_strategy(workspace_id) == "hybrid",
    )
    if result.get("status") == "error":
        raise HTTPException(500, result.get("message", "Delete failed"))
    _umap_cache.clear()
    return result


@app.get("/api/graph", response_model=GraphData)
async def get_graph(
    workspace_id: str = Query("default"),
    source_files: list[str] | None = Query(None),
    include_chunks: bool = Query(False),
):
    graph_fn = _get_graph_for_viz()
    effective_source_files = source_files
    if effective_source_files is None:
        effective_source_files = _workspace_file_names(workspace_id)

    raw = await asyncio.to_thread(
        graph_fn,
        limit=300,
        source_files=effective_source_files,
        workspace_id=_safe_workspace_id(workspace_id),
        include_chunks=include_chunks,
    )
    # Preserve rich Neo4j metadata while keeping React Flow's source/target keys.
    edges = []
    for edge in raw.get("edges", []):
        transformed = dict(edge)
        transformed["source"] = transformed.get("source") or transformed.get("from", "")
        transformed["target"] = transformed.get("target") or transformed.get("to", "")
        edges.append(transformed)
    return GraphData(nodes=raw.get("nodes", []), edges=edges)


def _workspace_qdrant_filter(workspace_id: str):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(must=[
        FieldCondition(
            key="workspace_id",
            match=MatchValue(value=_safe_workspace_id(workspace_id)),
        )
    ])


def _payload_bool(payload: dict, key: str) -> bool:
    value = payload.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _payload_int(payload: dict, key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _vector_chunk_from_point(point) -> VectorChunkInfo:
    payload = point.payload or {}
    return VectorChunkInfo(
        chunk_id=str(payload.get("chunk_id") or point.id),
        file_name=str(payload.get("file_name") or payload.get("source_file") or ""),
        chunk_index=_payload_int(payload, "chunk_index"),
        page=_payload_int(payload, "page", _payload_int(payload, "source_page")),
        section_label=str(payload.get("section_label") or ""),
        doc_type=str(payload.get("doc_type") or "text"),
        content=str(payload.get("document") or ""),
        has_table=_payload_bool(payload, "has_table"),
        has_formula=_payload_bool(payload, "has_formula"),
        has_image=_payload_bool(payload, "has_image"),
    )


def _list_workspace_chunks(workspace_id: str = "default", limit: int = 500) -> list[VectorChunkInfo]:
    client = _get_qdrant_client()()
    safe_limit = max(1, min(limit, 2000))
    points = []
    offset = None

    while len(points) < safe_limit:
        batch, next_offset = client.scroll(
            collection_name="rag_docs",
            limit=min(100, safe_limit - len(points)),
            offset=offset,
            scroll_filter=_workspace_qdrant_filter(workspace_id),
            with_vectors=False,
            with_payload=True,
        )
        points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    chunks = [_vector_chunk_from_point(point) for point in points]
    return sorted(chunks, key=lambda c: (c.file_name.lower(), c.chunk_index, c.page, c.chunk_id))


@app.get("/api/chunks", response_model=List[VectorChunkInfo])
async def get_workspace_chunks(
    workspace_id: str = Query("default"),
    limit: int = Query(500, ge=1, le=2000),
):
    try:
        return await asyncio.to_thread(_list_workspace_chunks, _safe_workspace_id(workspace_id), limit)
    except Exception as e:
        raise HTTPException(500, f"Chunk listing failed: {e}")


def _fallback_umap_layout(points: list) -> list:
    """Use a deterministic tiny layout when UMAP has too few points to fit."""
    if not points:
        return []

    result = []
    for i, p in enumerate(points):
        payload = p.payload or {}
        result.append(UMAPPoint(
            x=float(i),
            y=0.0,
            file_name=payload.get("file_name", ""),
            chunk_id=str(payload.get("chunk_id") or p.id),
            label=(payload.get("document", "") or "")[:100],
        ))
    return result


def _compute_umap_sync(workspace_id: str = "default") -> list:
    import numpy as np
    import umap as umap_lib

    client = _get_qdrant_client()()
    points = []
    offset = None
    while len(points) < 2000:
        batch, next_offset = client.scroll(
            collection_name="rag_docs",
            limit=100,
            offset=offset,
            scroll_filter=_workspace_qdrant_filter(workspace_id),
            with_vectors=True,
            with_payload=True,
        )
        points.extend(batch)
        if next_offset is None:
            break
        offset = next_offset

    if len(points) < 3:
        return _fallback_umap_layout(points)
    if len(points) > 2000:
        points = random.sample(points, 2000)

    vectors = np.array([p.vector for p in points])
    n_neighbors = min(15, max(2, len(points) - 1))
    reducer = umap_lib.UMAP(
        n_neighbors=n_neighbors, min_dist=0.1,
        n_components=2, random_state=42,
    )
    embedding = reducer.fit_transform(vectors)

    result = []
    for i, p in enumerate(points):
        payload = p.payload or {}
        result.append(UMAPPoint(
            x=float(embedding[i, 0]),
            y=float(embedding[i, 1]),
            file_name=payload.get("file_name", ""),
            chunk_id=str(payload.get("chunk_id") or p.id),
            label=(payload.get("document", "") or "")[:100],
        ))
    return result


@app.get("/api/umap", response_model=List[UMAPPoint])
async def get_umap(workspace_id: str = Query("default")):
    wid = _safe_workspace_id(workspace_id)
    cached = _umap_cache.get(wid)
    if cached and cached.get("data") is not None:
        return cached["data"]
    try:
        data = await asyncio.to_thread(_compute_umap_sync, wid)
        _umap_cache[wid] = {"data": data, "computed_at": datetime.now()}
        return data
    except Exception as e:
        raise HTTPException(500, f"UMAP computation failed: {e}")


# Serve React build in production (only if dist/ exists).
# Keep this mount last: StaticFiles at "/" otherwise shadows /api routes.
_dist = _BACKEND.parent / "frontend" / "react-app" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
