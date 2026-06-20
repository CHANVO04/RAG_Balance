"""
Validate the enriched ingest Vision API flow without touching Qdrant/registry/KG.

This script calls ingest.parser.parse_document() for a real PDF, captures the
Vision/Text LLM inputs and outputs for tables, images, and formulas, then writes
per-item artifacts plus timing/cost reports into a validation folder.

Usage:
  python scripts/test_vision_api_ingest_flow.py
  python scripts/test_vision_api_ingest_flow.py --pdf "DATASET/file.pdf"
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import shutil
import sys
import time
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


DEFAULT_PDF = (
    ROOT
    / "DATASET"
    / "A_Basic_ICCE_2026__A_Stay_Cable_Safety_Predictor_Enabling_Edge_Computing_for_IoT_Systems.pdf"
)
DEFAULT_OUTPUT = (
    ROOT
    / ".agent"
    / "validation"
    / "Ingest"
    / "A_Result_Test_ParsingDocument"
    / "A2_VisionAPI"
)

DEFAULT_PRICING = {
    "gpt-4.1-mini": {
        "input_per_1m": 0.40,
        "cached_input_per_1m": 0.10,
        "output_per_1m": 1.60,
    }
}


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_pricing(path: Optional[str]) -> Dict[str, Dict[str, float]]:
    if not path:
        return DEFAULT_PRICING
    with open(path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError("--pricing-json must contain an object")
    merged = dict(DEFAULT_PRICING)
    merged.update(loaded)
    return merged


def sanitize_visual(v: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, value in v.items():
        if key == "pil_image":
            try:
                out["pil_image_size"] = list(value.size) if value is not None else None
                out["pil_image_mode"] = getattr(value, "mode", None)
            except Exception:
                out["pil_image_size"] = None
            continue
        if key == "markdown" and isinstance(value, str):
            out[key] = value
            out["markdown_chars"] = len(value)
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)
    return out


def response_usage_to_dict(usage: Any) -> Dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return dict(usage)
    result = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_details"):
        if hasattr(usage, name):
            value = getattr(usage, name)
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            result[name] = value
    return result


def cached_tokens_from_usage(usage: Dict[str, Any]) -> int:
    details = usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        return 0
    value = details.get("cached_tokens", 0)
    try:
        return int(value or 0)
    except Exception:
        return 0


def estimate_cost_usd(usage: Dict[str, Any], model: str, pricing: Dict[str, Dict[str, float]]) -> Optional[float]:
    rates = pricing.get(model)
    if not rates:
        return None
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    cached_tokens = min(cached_tokens_from_usage(usage), prompt_tokens)
    uncached_tokens = max(0, prompt_tokens - cached_tokens)
    cost = (
        uncached_tokens * float(rates.get("input_per_1m", 0.0))
        + cached_tokens * float(rates.get("cached_input_per_1m", rates.get("input_per_1m", 0.0)))
        + completion_tokens * float(rates.get("output_per_1m", 0.0))
    ) / 1_000_000
    return round(cost, 8)


def classify_vision_call(prompt: str, model: str, max_tokens: int, detail: str) -> str:
    if detail == "auto":
        return "formula_ocr_pass1_auto"
    if detail == "high" and max_tokens == 800:
        return "formula_ocr_pass2_high"
    if detail == "high" and max_tokens == 1800:
        return "image_analysis_pass1_high"
    return f"vision_{detail}_{max_tokens}"


def classify_text_call(prompt: str, model: str, max_tokens: int) -> str:
    if "TABLE MARKDOWN:" in prompt:
        return "table_analysis_text"
    if "LATEX:" in prompt and "FORMULA PURPOSE" in prompt:
        return "formula_semantic_analysis_text"
    return f"text_{max_tokens}"


class ApiUsageRecorder:
    def __init__(self, pricing: Dict[str, Dict[str, float]]):
        self.pricing = pricing
        self.calls: List[Dict[str, Any]] = []
        self._seq = 0

    def next_id(self) -> str:
        self._seq += 1
        return f"api_call_{self._seq:04d}"

    def record(
        self,
        *,
        call_id: str,
        kind: str,
        model: str,
        max_tokens: int,
        started_perf: float,
        ended_perf: float,
        started_at: str,
        ended_at: str,
        usage: Dict[str, Any],
        detail: str = "",
        error: str = "",
    ) -> None:
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        cached_tokens = cached_tokens_from_usage(usage)
        self.calls.append({
            "call_id": call_id,
            "kind": kind,
            "model": model,
            "detail": detail,
            "max_tokens": max_tokens,
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_seconds": round(max(0.0, ended_perf - started_perf), 4),
            "prompt_tokens": prompt_tokens,
            "cached_input_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimate_cost_usd(usage, model, self.pricing),
            "usage": usage,
            "error": error,
        })


def summarize_usage(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_kind: Dict[str, Dict[str, Any]] = {}
    started_values = [c["started_at"] for c in calls if c.get("started_at")]
    ended_values = [c["ended_at"] for c in calls if c.get("ended_at")]

    def add(target: Dict[str, Any], call: Dict[str, Any]) -> None:
        target["calls"] += 1
        target["prompt_tokens"] += int(call.get("prompt_tokens") or 0)
        target["cached_input_tokens"] += int(call.get("cached_input_tokens") or 0)
        target["completion_tokens"] += int(call.get("completion_tokens") or 0)
        target["total_tokens"] += int(call.get("total_tokens") or 0)
        target["latency_sum_seconds"] += float(call.get("latency_seconds") or 0.0)
        cost = call.get("estimated_cost_usd")
        if cost is not None:
            target["estimated_cost_usd"] += float(cost)
        target.setdefault("_latencies", []).append(float(call.get("latency_seconds") or 0.0))

    total = {
        "calls": 0,
        "prompt_tokens": 0,
        "cached_input_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_sum_seconds": 0.0,
        "estimated_cost_usd": 0.0,
    }
    for call in calls:
        add(total, call)
        kind = call.get("kind", "unknown")
        bucket = by_kind.setdefault(kind, {
            "calls": 0,
            "prompt_tokens": 0,
            "cached_input_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_sum_seconds": 0.0,
            "estimated_cost_usd": 0.0,
        })
        add(bucket, call)

    for bucket in [total, *by_kind.values()]:
        latencies = bucket.pop("_latencies", [])
        bucket["estimated_cost_usd"] = round(bucket["estimated_cost_usd"], 8)
        bucket["latency_sum_seconds"] = round(bucket["latency_sum_seconds"], 4)
        bucket["latency_avg_seconds"] = round(sum(latencies) / len(latencies), 4) if latencies else 0.0
        bucket["latency_min_seconds"] = round(min(latencies), 4) if latencies else 0.0
        bucket["latency_max_seconds"] = round(max(latencies), 4) if latencies else 0.0

    return {
        "total": total,
        "by_kind": by_kind,
        "first_call_started_at": min(started_values) if started_values else None,
        "last_call_ended_at": max(ended_values) if ended_values else None,
        "note": "Costs are estimated from API usage tokens and configured pricing.",
    }


def write_usage_csv(path: Path, calls: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "call_id",
        "kind",
        "model",
        "detail",
        "max_tokens",
        "started_at",
        "ended_at",
        "latency_seconds",
        "prompt_tokens",
        "cached_input_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for call in calls:
            writer.writerow({key: call.get(key, "") for key in fieldnames})


def write_cost_report(
    path: Path,
    *,
    pdf_path: Path,
    parsed_summary: Dict[str, Any],
    usage_summary: Dict[str, Any],
    total_script_seconds: float,
    parse_document_seconds: float,
    chunk_seconds: Optional[float],
    run_dir: Path,
    calls: List[Dict[str, Any]],
) -> None:
    total = usage_summary["total"]
    lines = [
        "# Vision API Cost and Timing Report",
        "",
        f"- PDF: `{pdf_path}`",
        f"- Output folder: `{run_dir}`",
        f"- Tables analyzed: `{parsed_summary['tables']['analyzed']}/{parsed_summary['tables']['total']}`",
        f"- Images analyzed: `{parsed_summary['images']['analyzed']}/{parsed_summary['images']['total']}`",
        f"- Formulas decoded: `{parsed_summary['formulas']['decoded']}/{parsed_summary['formulas']['total']}`",
        f"- Script wall time: `{total_script_seconds:.2f}s`",
        f"- parse_document wall time: `{parse_document_seconds:.2f}s`",
        f"- chunk_document wall time: `{chunk_seconds:.2f}s`" if chunk_seconds is not None else "- chunk_document wall time: `skipped`",
        f"- API call latency sum: `{total['latency_sum_seconds']:.2f}s`",
        f"- API calls: `{total['calls']}`",
        f"- Prompt tokens: `{total['prompt_tokens']}`",
        f"- Cached input tokens: `{total['cached_input_tokens']}`",
        f"- Completion tokens: `{total['completion_tokens']}`",
        f"- Total tokens: `{total['total_tokens']}`",
        f"- Estimated cost: `${total['estimated_cost_usd']:.6f}`",
        "",
        "## By Call Type",
        "",
        "| Kind | Calls | Prompt | Cached | Output | Total | Latency Sum | Avg Latency | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for kind, bucket in sorted(usage_summary["by_kind"].items()):
        lines.append(
            f"| `{kind}` | {bucket['calls']} | {bucket['prompt_tokens']} | "
            f"{bucket['cached_input_tokens']} | {bucket['completion_tokens']} | "
            f"{bucket['total_tokens']} | {bucket['latency_sum_seconds']:.2f}s | "
            f"{bucket['latency_avg_seconds']:.2f}s | ${bucket['estimated_cost_usd']:.6f} |"
        )

    slowest = sorted(calls, key=lambda c: float(c.get("latency_seconds") or 0.0), reverse=True)[:10]
    priciest = sorted(calls, key=lambda c: float(c.get("estimated_cost_usd") or 0.0), reverse=True)[:10]
    lines.extend(["", "## Slowest Calls", ""])
    for call in slowest:
        lines.append(
            f"- `{call['call_id']}` `{call['kind']}` {call['latency_seconds']}s "
            f"tokens={call['total_tokens']} cost=${float(call.get('estimated_cost_usd') or 0):.6f}"
        )
    lines.extend(["", "## Most Expensive Calls", ""])
    for call in priciest:
        lines.append(
            f"- `{call['call_id']}` `{call['kind']}` cost=${float(call.get('estimated_cost_usd') or 0):.6f} "
            f"tokens={call['total_tokens']} latency={call['latency_seconds']}s"
        )
    write_text(path, "\n".join(lines) + "\n")


def parsed_summary(parsed: Any, chunks: Optional[List[Any]]) -> Dict[str, Any]:
    tables = parsed.tables or []
    images = parsed.images or []
    formulas = parsed.formulas or []
    return {
        "file_name": parsed.file_name,
        "file_path": parsed.file_path,
        "file_hash": parsed.file_hash,
        "doc_type": parsed.doc_type,
        "metadata": parsed.metadata,
        "raw_blocks": len(parsed.raw_blocks or []),
        "chunks": {
            "total": len(chunks or []),
            "with_table": sum(1 for c in (chunks or []) if c.has_table),
            "with_image": sum(1 for c in (chunks or []) if c.has_image),
            "with_formula": sum(1 for c in (chunks or []) if c.has_formula),
        },
        "tables": {
            "total": len(tables),
            "analyzed": sum(1 for t in tables if t.get("analysis_markdown")),
        },
        "images": {
            "total": len(images),
            "analyzed": sum(1 for i in images if i.get("analysis_markdown")),
            "with_asset": sum(1 for i in images if i.get("asset_path") or i.get("path")),
        },
        "formulas": {
            "total": len(formulas),
            "decoded": sum(1 for f in formulas if f.get("is_decoded")),
            "with_analysis": sum(1 for f in formulas if f.get("analysis_markdown")),
            "with_asset": sum(1 for f in formulas if f.get("asset_path")),
        },
    }


def chunk_to_dict(chunk: Any) -> Dict[str, Any]:
    data = asdict(chunk)
    data["text_chars"] = len(data.get("text") or "")
    return data


def copy_asset(asset_path: str, target_dir: Path, target_name: str) -> str:
    if not asset_path:
        return ""
    src = Path(asset_path)
    if not src.is_absolute():
        src = ROOT / asset_path
    if not src.exists():
        return ""
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / target_name
    shutil.copy2(src, dst)
    return str(dst)


def write_item_artifacts(run_dir: Path, parsed: Any) -> None:
    tables_dir = run_dir / "tables"
    images_dir = run_dir / "images"
    formulas_dir = run_dir / "formulas"

    for table in parsed.tables or []:
        tid = table["table_id"]
        write_text(tables_dir / f"{tid}.input.md", table.get("markdown", ""))
        write_text(tables_dir / f"{tid}.analysis.md", table.get("analysis_markdown", ""))
        write_json(tables_dir / f"{tid}.record.json", table)

    for image in parsed.images or []:
        iid = image["image_id"]
        asset = image.get("asset_path") or image.get("path") or ""
        copied = copy_asset(asset, images_dir, f"{iid}.png")
        record = dict(image)
        record["copied_asset"] = copied
        write_text(images_dir / f"{iid}.analysis.md", image.get("analysis_markdown", ""))
        write_json(images_dir / f"{iid}.record.json", record)

    for formula in parsed.formulas or []:
        fid = formula["formula_id"]
        copied = copy_asset(formula.get("asset_path", ""), formulas_dir, f"{fid}.png")
        record = dict(formula)
        record["copied_asset"] = copied
        write_text(formulas_dir / f"{fid}.latex.txt", formula.get("latex_string", ""))
        write_text(formulas_dir / f"{fid}.analysis.md", formula.get("analysis_markdown", ""))
        write_json(formulas_dir / f"{fid}.record.json", record)


def write_chunk_artifacts(run_dir: Path, chunks: List[Any]) -> None:
    lines = ["# Enriched Chunks", ""]
    for idx, chunk in enumerate(chunks, start=1):
        lines.extend([
            f"---\n## Chunk {idx}",
            f"- chunk_id: `{chunk.chunk_id}`",
            f"- page: `{chunk.page}`",
            f"- refs: tables={chunk.table_refs}, images={chunk.image_refs}, formulas={chunk.formula_refs}",
            "",
            "```text",
            chunk.text,
            "```",
            "",
        ])
    write_text(run_dir / "chunks_enriched.md", "\n".join(lines))
    write_json(run_dir / "chunks_enriched.json", [chunk_to_dict(c) for c in chunks])


def assert_no_main_store_touched(run_dir: Path) -> Dict[str, Any]:
    return {
        "qdrant_called": False,
        "registry_written": False,
        "kg_called": False,
        "embedding_called": False,
        "isolated_db": str(run_dir / "isolated_db"),
        "note": "This script does not import/call offline_ingest, vector upsert, registry save, KG, or embedding.",
    }


@contextmanager
def patched_validation_runtime(run_dir: Path, recorder: ApiUsageRecorder):
    import ingest.parser as parser_mod
    import ingest.vision as vision_mod

    original_vector_dir = parser_mod.VECTOR_DIR
    original_parser_async = parser_mod.asyncio_process_visuals
    original_vision_call = vision_mod._call_vision_api_async
    original_text_call = vision_mod._call_text_api_async

    captured_inputs: List[Dict[str, Any]] = []
    captured_results: Dict[str, Any] = {}

    async def capture_process_visuals(visuals: List[Dict[str, Any]], *args, **kwargs):
        captured_inputs[:] = [sanitize_visual(v) for v in visuals]
        write_json(run_dir / "vision_inputs.json", captured_inputs)
        result = await original_parser_async(visuals, *args, **kwargs)
        captured_results.clear()
        captured_results.update(result or {})
        write_json(run_dir / "vision_api_results_raw.json", captured_results)
        return result

    async def measured_vision_call(client, prompt: str, b64_image: str, model: str, max_tokens: int, detail: str = "high") -> str:
        from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

        call_id = recorder.next_id()
        kind = classify_vision_call(prompt, model, max_tokens, detail)
        started_perf = time.perf_counter()
        started_at = now_iso()
        usage: Dict[str, Any] = {}
        error = ""
        try:
            response = None
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),
                wait=wait_exponential(multiplier=1, min=2, max=16),
                retry=retry_if_exception_type(vision_mod._RETRYABLE_ERRORS),
                reraise=True,
            ):
                with attempt:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {
                                    "url": f"data:image/png;base64,{b64_image}",
                                    "detail": detail,
                                }},
                            ],
                        }],
                        max_tokens=max_tokens,
                        temperature=0.1,
                    )
            usage = response_usage_to_dict(getattr(response, "usage", None))
            return response.choices[0].message.content
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            recorder.record(
                call_id=call_id,
                kind=kind,
                model=model,
                detail=detail,
                max_tokens=max_tokens,
                started_perf=started_perf,
                ended_perf=time.perf_counter(),
                started_at=started_at,
                ended_at=now_iso(),
                usage=usage,
                error=error,
            )

    async def measured_text_call(client, prompt: str, model: str, max_tokens: int) -> str:
        from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

        call_id = recorder.next_id()
        kind = classify_text_call(prompt, model, max_tokens)
        started_perf = time.perf_counter()
        started_at = now_iso()
        usage: Dict[str, Any] = {}
        error = ""
        try:
            response = None
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),
                wait=wait_exponential(multiplier=1, min=2, max=16),
                retry=retry_if_exception_type(vision_mod._RETRYABLE_ERRORS),
                reraise=True,
            ):
                with attempt:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=0.1,
                    )
            usage = response_usage_to_dict(getattr(response, "usage", None))
            return response.choices[0].message.content
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            recorder.record(
                call_id=call_id,
                kind=kind,
                model=model,
                detail="text-only",
                max_tokens=max_tokens,
                started_perf=started_perf,
                ended_perf=time.perf_counter(),
                started_at=started_at,
                ended_at=now_iso(),
                usage=usage,
                error=error,
            )

    parser_mod.VECTOR_DIR = str(run_dir / "isolated_db")
    parser_mod.asyncio_process_visuals = capture_process_visuals
    vision_mod._call_vision_api_async = measured_vision_call
    vision_mod._call_text_api_async = measured_text_call
    try:
        yield {
            "vision_inputs": captured_inputs,
            "vision_api_results": captured_results,
        }
    finally:
        parser_mod.VECTOR_DIR = original_vector_dir
        parser_mod.asyncio_process_visuals = original_parser_async
        vision_mod._call_vision_api_async = original_vision_call
        vision_mod._call_text_api_async = original_text_call


def run(args: argparse.Namespace) -> Path:
    from ingest.parser import parse_document
    from ingest.chunker import chunk_document

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing. Load it in .env or the environment before running.")

    output_root = Path(args.output).resolve()
    run_dir = output_root / pdf_path.stem / timestamp()
    run_dir.mkdir(parents=True, exist_ok=False)
    for subdir in ("tables", "images", "formulas"):
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)

    pricing = load_pricing(args.pricing_json)
    recorder = ApiUsageRecorder(pricing)
    run_started_at = now_iso()
    script_start = time.perf_counter()
    parse_seconds = 0.0
    chunk_seconds: Optional[float] = None
    parsed = None
    doc_obj = None
    chunks: List[Any] = []

    log_path = run_dir / "run.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        tee_out = Tee(sys.stdout, log_file)
        tee_err = Tee(sys.stderr, log_file)
        with redirect_stdout(tee_out), redirect_stderr(tee_err):
            print(f"[VALIDATION] PDF: {pdf_path}")
            print(f"[VALIDATION] Output: {run_dir}")
            print("[VALIDATION] Running parse_document() with test-only API instrumentation...")
            try:
                with patched_validation_runtime(run_dir, recorder):
                    t0 = time.perf_counter()
                    result = parse_document(str(pdf_path))
                    parse_seconds = time.perf_counter() - t0
                    if result is None:
                        raise RuntimeError("parse_document returned None")
                    parsed, doc_obj = result

                print(f"[VALIDATION] parse_document completed in {parse_seconds:.2f}s")

                if not args.no_chunks:
                    print("[VALIDATION] Running chunk_document() for enriched chunk inspection only...")
                    t1 = time.perf_counter()
                    chunks = chunk_document(parsed, doc_obj=doc_obj)
                    chunk_seconds = time.perf_counter() - t1
                    print(f"[VALIDATION] chunk_document completed in {chunk_seconds:.2f}s")
                else:
                    print("[VALIDATION] --no-chunks set; skipping chunk_document().")

                write_item_artifacts(run_dir, parsed)
                if chunks:
                    write_chunk_artifacts(run_dir, chunks)

                summary = parsed_summary(parsed, chunks)
                summary["side_effect_guard"] = assert_no_main_store_touched(run_dir)
                summary["run"] = {
                    "pdf": str(pdf_path),
                    "output_dir": str(run_dir),
                    "started_at": run_started_at,
                    "ended_at": now_iso(),
                    "parse_document_wall_seconds": round(parse_seconds, 4),
                    "chunk_document_wall_seconds": round(chunk_seconds, 4) if chunk_seconds is not None else None,
                }
                write_json(run_dir / "parsed_document_summary.json", summary)

                usage_summary = summarize_usage(recorder.calls)
                total_script_seconds = time.perf_counter() - script_start
                usage_summary["timing"] = {
                    "total_script_wall_seconds": round(total_script_seconds, 4),
                    "parse_document_wall_seconds": round(parse_seconds, 4),
                    "chunk_document_wall_seconds": round(chunk_seconds, 4) if chunk_seconds is not None else None,
                }
                usage_summary["pricing"] = pricing
                write_json(run_dir / "api_usage_raw.json", recorder.calls)
                write_usage_csv(run_dir / "api_usage_by_call.csv", recorder.calls)
                write_json(run_dir / "api_usage_summary.json", usage_summary)
                write_cost_report(
                    run_dir / "cost_timing_report.md",
                    pdf_path=pdf_path,
                    parsed_summary=summary,
                    usage_summary=usage_summary,
                    total_script_seconds=total_script_seconds,
                    parse_document_seconds=parse_seconds,
                    chunk_seconds=chunk_seconds,
                    run_dir=run_dir,
                    calls=recorder.calls,
                )

                total = usage_summary["total"]
                print("\nVISION API COST/TIMING SUMMARY")
                print("-" * 40)
                print(f"- PDF: {pdf_path.name}")
                print(f"- Tables analyzed: {summary['tables']['analyzed']}/{summary['tables']['total']}")
                print(f"- Images analyzed: {summary['images']['analyzed']}/{summary['images']['total']}")
                print(f"- Formulas decoded: {summary['formulas']['decoded']}/{summary['formulas']['total']}")
                print(f"- API calls: {total['calls']}")
                print(f"- API call latency sum: {total['latency_sum_seconds']:.2f}s")
                print(f"- Total tokens: {total['total_tokens']}")
                print(f"- Estimated cost: ${total['estimated_cost_usd']:.6f}")
                print(f"- Output folder: {run_dir}")

            except Exception:
                print("[VALIDATION][ERROR] Run failed:")
                traceback.print_exc()
                write_json(run_dir / "api_usage_raw.json", recorder.calls)
                write_usage_csv(run_dir / "api_usage_by_call.csv", recorder.calls)
                write_json(run_dir / "api_usage_summary.json", summarize_usage(recorder.calls))
                raise

    return run_dir


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ingest Vision API flow without Qdrant side effects.")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help="PDF to parse and analyze.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Validation output root.")
    parser.add_argument("--pricing-json", default="", help="Optional pricing override JSON.")
    parser.add_argument("--no-chunks", action="store_true", help="Skip chunk_document() inspection.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    run_dir = run(args)
    print(f"\n[DONE] Validation artifacts written to:\n{run_dir}")


if __name__ == "__main__":
    main()
