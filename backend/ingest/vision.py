"""
ingest/vision.py — Vision API helpers, prompts, event loop fix, tenacity retry.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
from typing import Any, Dict, List, Optional

import openai
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type

from ingest.config import IMAGE_VLM_MODEL, FORMULA_VLM_MODEL, TABLE_LLM_MODEL


# ── Retryable error types ────────────────────────────────────────────────────
_RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
)


# ── PIL → base64 ─────────────────────────────────────────────────────────────

def _encode_pil_to_base64(pil_image) -> str:
    """Convert PIL.Image sang base64 PNG string để gửi lên OpenAI Vision API.

    Fix: Pillow >= 10.x strict-validates tile extents khi ghi PNG.
    Ảnh lazy-loaded từ Docling/PyMuPDF đôi khi có tile metadata lệch → SystemError.
    Giải pháp: force-decode qua .copy() rồi convert sang mode sạch (RGBA/RGB).
    Nếu vẫn fail, tái tạo image từ raw pixel bytes để bypass tile metadata hoàn toàn.
    """
    from io import BytesIO
    from PIL import Image as PILImage
    import base64

    buf = BytesIO()
    try:
        safe_img = pil_image.copy()

        if safe_img.mode not in ("RGB", "RGBA", "L", "P"):
            safe_img = safe_img.convert("RGBA")
        elif safe_img.mode == "P":
            safe_img = safe_img.convert("RGBA")

        safe_img.save(buf, format="PNG")

    except (SystemError, AttributeError, OSError) as e:
        buf = BytesIO()
        try:
            w, h = pil_image.size
            mode = pil_image.mode if pil_image.mode in ("RGB", "RGBA", "L") else "RGB"
            raw = pil_image.convert(mode).tobytes()
            rebuilt = PILImage.frombytes(mode, (w, h), raw)
            rebuilt.save(buf, format="PNG")
        except Exception as e2:
            raise RuntimeError(
                f"[VISION] Không encode được PIL image ({pil_image.size}, {pil_image.mode}): {e} → {e2}"
            ) from e2

    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ── LaTeX output cleaner ──────────────────────────────────────────────────────

def _clean_latex_output(raw: str) -> str:
    """
    Strip markdown wrappers và fix common GPT/Docling LaTeX errors.

    Rules (theo thứ tự, mỗi rule độc lập):
    1. Strip code block / dollar delimiters
    2. Fix floor/ceiling Docling encoding (/floorleft → \\lfloor)
    3. Fix hat encoding sai (ˆP → \\hat{P}, P_hat → \\hat{P})
    4. Fix /negationslash, /epsilon Docling artifacts
    5. Strip trailing 1 sau \\rfloor (Docling artifact)
    6. Normalize whitespace
    7. Validate brace balance (auto-close nếu imbalance nhỏ)
    """
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()

    # ── 1. Strip wrappers ──────────────────────────────────────────────────────
    raw = re.sub(r'^```(?:latex|math)?\s*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = re.sub(r'^\$\$?\s*', '', raw)
    raw = re.sub(r'\s*\$\$?$', '', raw)
    raw = re.sub(r'^\\begin\{equation\}\s*', '', raw)
    raw = re.sub(r'\s*\\end\{equation\}$', '', raw)
    raw = raw.strip()

    # ── 2. Fix floor/ceiling (Docling legacy encoding) ─────────────────────────
    raw = re.sub(r'/floorleft\s*', r'\\lfloor ', raw)
    raw = re.sub(r'/floorright(\d?)', lambda m: r'\rfloor' + (m.group(1) if m.group(1) else ''), raw)
    raw = re.sub(r'/ceilingleft\s*', r'\\lceil ', raw)
    raw = re.sub(r'/ceilingright\s*', r'\\rceil ', raw)

    # ── 3. Fix hat encoding sai ────────────────────────────────────────────────
    raw = re.sub(r'ˆ([A-Za-z])', r'\\hat{\1}', raw)      # ˆP → \hat{P}
    raw = re.sub(r'([A-Za-z])_hat\b', r'\\hat{\1}', raw)  # P_hat → \hat{P}

    # ── 4. Fix Docling symbol encoding ────────────────────────────────────────
    raw = raw.replace('/negationslash', r'\neq')
    raw = re.sub(r'/epsilon(\d)', r'\\epsilon_\1', raw)
    raw = raw.replace('/epsilon', r'\epsilon')
    raw = re.sub(r'ε(\d+)', r'\\epsilon_{\1}', raw)   # Unicode ε + digit từ Vision API
    raw = raw.replace('ε', r'\epsilon')                # bất kỳ ε Unicode còn lại

    # ── 5. Strip trailing 1 sau \rfloor (Docling artifact) ────────────────────
    raw = re.sub(r'\\rfloor\s*1\b(?!\s*[,\+\-\*\/=\^\_\}])', r'\\rfloor', raw)

    # ── 6. Normalize whitespace ────────────────────────────────────────────────
    raw = re.sub(r'[ \t]+', ' ', raw).strip()

    # ── 7. Validate brace balance ──────────────────────────────────────────────
    n_open  = raw.count('{')
    n_close = raw.count('}')
    if n_open != n_close:
        diff = abs(n_open - n_close)
        if diff > 3:
            return "[Not Decodable - Unbalanced LaTeX]"
        if n_open > n_close:
            raw = raw + '}' * (n_open - n_close)
        else:
            # n_close > n_open: strip spurious trailing close braces
            raw = raw.rstrip()
            while raw.endswith('}') and raw.count('}') > raw.count('{'):
                raw = raw[:-1].rstrip()

    return raw


# ── Formula image crop ────────────────────────────────────────────────────────

# 20px: at images_scale=2.5, a 8pt formula renders ~20px — enough for GPT-4o to read.
# 40px was too conservative and silently discarded small but valid block formulas.
_FORMULA_MIN_PX      = 20
_SAVE_FORMULA_IMAGES = os.getenv("SAVE_FORMULA_IMAGES", "false").lower() == "true"


def cleanup_formula_debug_images() -> int:
    """
    Xóa tất cả PNG files trong check_formula_image/ directory.

    Được gọi tự động từ offline_ingest() trước mỗi run:
    - Khi SAVE_FORMULA_IMAGES=false: xóa nếu dir tồn tại (dọn dẹp từ run trước).
    - Khi SAVE_FORMULA_IMAGES=true: xóa trước khi run mới để tránh tích lũy.

    Returns: số file đã xóa.
    """
    backend_dir  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(backend_dir)
    target_dir   = os.path.join(project_root, "check_formula_image")

    if not os.path.isdir(target_dir):
        return 0

    removed = 0
    for fname in os.listdir(target_dir):
        if fname.lower().endswith(".png"):
            try:
                os.remove(os.path.join(target_dir, fname))
                removed += 1
            except OSError:
                pass

    if removed:
        print(f"[VISION] Đã dọn {removed} formula debug image(s) từ run trước")
    return removed


def _get_formula_image(item, page_no: int, doc, formula_id: str = "") -> "Optional[Any]":
    """Crop FormulaItem bbox từ Docling page image → PIL.Image.

    Yêu cầu generate_page_images=True trong PdfPipelineOptions.
    """
    try:
        prov = getattr(item, "prov", None)
        if not prov:
            return None

        pages = getattr(doc, "pages", None)
        if not pages:
            return None
        page_obj = pages.get(page_no)
        if page_obj is None or not getattr(page_obj, "image", None):
            return None
        page_pil = getattr(page_obj.image, "pil_image", None)
        if page_pil is None:
            return None

        img_w, img_h = page_pil.size
        page_size = page_obj.size

        bbox = prov[0].bbox
        try:
            from docling_core.types.doc.page import CoordOrigin
            if getattr(bbox, "coord_origin", None) == CoordOrigin.BOTTOMLEFT:
                bbox = bbox.to_top_left_origin(page_size.height)
        except (ImportError, AttributeError):
            pass

        sx = img_w / page_size.width
        sy = img_h / page_size.height
        x0 = max(0, int(bbox.l * sx))
        y0 = max(0, int(bbox.t * sy))
        x1 = min(img_w, int(bbox.r * sx))
        y1 = min(img_h, int(bbox.b * sy))

        if x1 <= x0 or y1 <= y0:
            print(f"[VISION][WARN] p{page_no}: FormulaItem degenerate bbox sau scale "
                  f"({x0},{y0})-({x1},{y1})")
            return None

        crop = page_pil.crop((x0, y0, x1, y1))

        if crop.width < _FORMULA_MIN_PX or crop.height < _FORMULA_MIN_PX:
            print(f"[VISION][WARN] p{page_no}: Formula crop quá nhỏ "
                  f"({crop.width}x{crop.height}px) — bỏ qua Vision API")
            return None

        if _SAVE_FORMULA_IMAGES and formula_id:
            # Lấy đường dẫn tuyệt đối của thư mục dự án (A_RAG_MAIN)
            # __file__ là backend/ingest/vision.py 
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(backend_dir)
            target_dir = os.path.join(project_root, "check_formula_image")
            
            os.makedirs(target_dir, exist_ok=True)
            crop.save(os.path.join(target_dir, f"{formula_id}.png"))

        print(f"[VISION] p{page_no}: Docling native crop OK cho {formula_id} "
              f"— {crop.width}x{crop.height}px")
        return crop

    except Exception as e:
        print(f"[VISION][WARN] Không cắt được formula image trang {page_no}: {e}")
        return None


# ── Prompts ───────────────────────────────────────────────────────────────────

_PICTURE_ANALYSIS_PROMPT_TEMPLATE = """\
You are an expert AI assistant specialized in analyzing figures in academic papers (engineering, science, mathematics). When the figure relates to wireless communications, signal processing, or multiple access (NOMA, OFDM, beamforming), you may use that domain knowledge; otherwise, ignore domain-specific references.
Your goal is to convert the visual information into a highly structured text representation optimized for a RAG pipeline.

{context_block}

**SPECIAL CASE – UNREADABLE IMAGE:** If the image is completely unreadable (too blurry, corrupted, no clear content), output exactly: `[Image unreadable]` and nothing else.

Analyze the provided image and generate a response following this EXACT structure in Markdown. Keep total response under 1500 tokens.

### 1. CAPTION & IMAGE TYPE
- **Caption:** [Use the EXACT Known Caption provided in the context. Do NOT invent a new caption unless completely missing. If still missing, write "Not provided".]
- **Image Type:** [e.g., System Architecture Diagram, Contour/Heatmap, 2D Line Graph, 3D Surface Plot, Flowchart, Block Diagram, Table, Screenshot]
- **Number of Sub-figures:** [e.g., Single figure | Two sub-figures (a) and (b) | Three sub-figures (a, b, c) | ...]

### 2. STRUCTURED KEY ELEMENTS (Crucial for Vector Retrieval)
For EACH sub-figure (a), (b), ... if present, describe SEPARATELY with label e.g. "Sub-figure (a):". If single figure, just start without label.
- **Axis & Legends:**
  - X-Axis Label & Key Values: [...] (or "None" if not applicable)
  - Y-Axis Label & Key Values: [...]
  - Z-Axis (if 3D): [...]
  - Legend items: [list each line/color and its label EXACTLY as written in the image]
- **Key Components/Nodes (for block diagrams/flowcharts):**
  - List the main operational blocks, layers, or modules.
- **Connections/Workflow:**
  - Explain the directional flow.
- **Prominent Numbers/Data Points:**
  - List 2-3 most critical numeric values visible.

### 3. COMPREHENSIVE SEMANTIC SUMMARY
Write a rich paragraph (3-5 sentences) explaining the overall meaning and key takeaways.
CRITICAL RULES — failure to follow these causes incorrect RAG retrieval:
- Report ONLY what is visually observable. Do NOT infer beyond what is shown.
- You MUST explicitly scan the entire image for all sub-figure labels (e.g., (a), (b)). Do NOT skip any.
- Distinguish carefully between Greek letters (e.g., \\epsilon vs \\alpha). Pay extreme attention to small subscripts. Do not hallucinate variables.
- For line graphs: state which lines are HIGHER/LOWER based purely on visual position, using EXACT legend labels.
- Do NOT make domain assumptions about the physics unless the graph explicitly shows it.
- If multiple sub-figures exist, summarize EACH separately before giving an overall conclusion.
- If any element is partially visible or uncertain, append `[?]` to that element.

### 4. RAW TEXT / OCR (Verbatim)
List ALL text, labels, numbers, and mathematical symbols visible in the image exactly as they appear. **For mathematical symbols, output raw LaTeX without any delimiters** (no $, no $$, no `\\[` or `\\]`). Examples: `\\alpha_1`, `\\epsilon_{k}`, `x_{i}^{(t)}`, `\\frac{1}{2}`. Do not convert numbers to words.

### 5. AMBIGUOUS ELEMENTS (if any)
List any symbol, label, or text that is partially visible or uncertain, each followed by `[?]`. If everything is clear, write `None`.

Remember: use the EXACT structure above. Do not include extra commentary. If in doubt, mark with [?].\
"""


def _build_image_prompt(caption: str = "", page: int = 0,
                        context_text: str = "", figure_number: str = "") -> str:
    """Build prompt động với context cụ thể của từng ảnh."""
    parts = []
    if figure_number:
        parts.append(f"- **Figure Reference in paper:** {figure_number}")
    if page:
        parts.append(f"- **Page in paper:** {page}")
    if caption:
        parts.append(f"- **Known Caption (extracted from document):** {caption}")
    if context_text:
        ctx = context_text.strip()[:800]
        parts.append(
            f"- **Surrounding text from the paper (use to disambiguate axes/variables):**\n"
            f"  ```\n  {ctx}\n  ```"
        )
    if parts:
        context_block = (
            "CONTEXT FROM THE PAPER (prioritize this to resolve ambiguities in axes, legends, and variable names):\n"
            + "\n".join(parts)
        )
    else:
        context_block = "CONTEXT: No additional context available. Analyze the image alone."
    return _PICTURE_ANALYSIS_PROMPT_TEMPLATE.replace("{context_block}", context_block)


_TABLE_ANALYSIS_PROMPT_TEMPLATE = """\
You are an expert assistant for academic RAG ingestion.
Analyze the Markdown table below. Preserve exact facts and do not infer beyond the table/context.

{context_block}

TABLE MARKDOWN:
```markdown
{table_markdown}
```

Return Markdown with this exact structure, under 900 tokens:

### 1. TABLE IDENTITY
- **Caption:** [known caption, or Not provided]
- **Purpose:** [what the table directly reports]
- **Rows/Columns:** [visible row and column count if clear]

### 2. HEADERS AND METRICS
- List all column headers exactly.
- Identify numeric metrics, units, symbols, and parameter names exactly as written.

### 3. KEY VALUES AND COMPARISONS
- List the most important direct observations from the table.
- Copy exact values; do not round or estimate.

### 4. SEMANTIC SUMMARY
Write 2-4 concise sentences optimized for retrieval.

### 5. RAW TABLE TEXT
Include compact verbatim content only when it helps retrieval; keep Markdown structure recognizable.\
"""


def _build_table_prompt(markdown: str, caption: str = "", page: int = 0, context_text: str = "") -> str:
    parts = []
    if page:
        parts.append(f"- **Page in paper:** {page}")
    if caption:
        parts.append(f"- **Known Caption:** {caption}")
    if context_text:
        parts.append(
            "- **Nearby text from the paper:**\n"
            f"  ```\n  {context_text.strip()[:800]}\n  ```"
        )
    context_block = "CONTEXT FROM THE PAPER:\n" + "\n".join(parts) if parts else "CONTEXT: No additional context available."
    return (
        _TABLE_ANALYSIS_PROMPT_TEMPLATE
        .replace("{context_block}", context_block)
        .replace("{table_markdown}", (markdown or "").strip()[:6000])
    )


def _build_formula_analysis_prompt(latex: str, context_text: str = "") -> str:
    ctx = (context_text or "").strip()[:1000]
    context_block = f"\nCONTEXT FROM PAPER:\n```\n{ctx}\n```\n" if ctx else ""
    return f"""\
You are preparing a formula explanation for a scientific RAG system.
Explain only what can be supported by the LaTeX and context. Do not invent variable meanings.

LATEX:
```latex
{latex}
```
{context_block}
Return Markdown with this exact structure, under 700 tokens:

### 1. FORMULA PURPOSE
[One concise sentence about what the formula represents.]

### 2. VARIABLES AND SYMBOLS
- List visible variables/symbols and meanings if context supports them.
- If a meaning is unclear, write "not specified".

### 3. RETRIEVAL SUMMARY
[2-3 sentences describing the formula for semantic search.]\
"""


_FORMULA_EXTRACTION_PROMPT = """\
You are an expert LaTeX OCR system for IEEE academic papers across all fields \
(wireless communications, signal processing, deep learning, optimization, statistics).

Convert the mathematical formula in the image to precise LaTeX.

OUTPUT RULES (follow strictly):
1. Output ONLY the raw inner LaTeX expression — no $$, no $, no ``` delimiters, no explanation text.
2. Do NOT wrap with \\begin{equation}, \\end{equation}, or any environment unless the formula itself uses one.
3. Standard LaTeX conventions:
   - Floor: \\lfloor x \\rfloor   (NEVER /floorleft or /floorright)
   - Ceiling: \\lceil x \\rceil
   - Hat/accent: \\hat{x}, \\widehat{X}, \\tilde{x}, \\bar{x}, \\overline{x}, \\vec{x}
   - Bold matrix/vector: \\mathbf{x}, \\mathbf{W}
   - Calligraphic: \\mathcal{L}, \\mathcal{H}, \\mathcal{N}
   - Double-struck: \\mathbb{E}[\\cdot], \\mathbb{R}^n, \\mathbb{1}[\\cdot]
   - Fractions: \\frac{numerator}{denominator}
   - Subscript/superscript: x_{i,j}^{(k)}, P_{g,n}^{\\star}
   - Greek: \\alpha, \\beta, \\gamma, \\delta, \\epsilon, \\lambda, \\mu, \\sigma, \\theta, \\phi, \\pi, \\omega
   - Norm: \\|\\mathbf{x}\\|_2^2
   - Summation/product: \\sum_{i=1}^{N}, \\prod_{k=1}^{K}
   - Integral: \\int_{0}^{\\infty}
   - Limit/argmax: \\lim_{n \\to \\infty}, \\arg\\max_{x}
   - Log: \\log_2(1 + x), \\ln(x), \\log(x)
   - Operator text: \\text{SNR}, \\text{SINR}, \\text{Tr}(\\cdot), \\text{rank}(\\cdot)
   - Piecewise: \\begin{cases} f_1(x) & \\text{if } x > 0 \\\\ f_2(x) & \\text{otherwise} \\end{cases}
   - Aligned multi-line: \\begin{aligned} ... \\end{aligned}
4. Piecewise functions: count the EXACT number of cases visible in the image.
   Do NOT add, infer, or invent cases not visible. Use:
   \\begin{cases} expr_1 & \\text{if cond_1} \\\\ expr_2 & \\text{if cond_2} \\end{cases}
   Only as many lines as are SHOWN — no more.
5. Character disambiguation (crucial for IEEE papers):
   - Uppercase I (capital letter) vs lowercase l (ell): choose based on context.
     \\hat{I} = power/interference variable (common), \\hat{l} = length index (rare).
   - \\epsilon_{g'} NOT "ε1 g" — always use LaTeX subscript notation.
   - \\overline{P}, \\hat{I}, \\widetilde{h} — use correct accent command.
6. Phantom variable prohibition:
   Output ONLY symbols visually present in the image.
   Do NOT hallucinate variables (e.g., P_{\\alpha}, S_{t,f}) not shown.
   If uncertain about a subscript, use the most visually plausible reading.
7. CRITICAL - CROP HANDLING: The image is a tight crop of the formula bounding box with \
NO padding — characters at the very edges (top/bottom/left/right) are part of the formula. \
Do NOT ignore edge characters. Transcribe ALL visible symbols including those at the boundary.
8. If the image is genuinely unreadable (too blurry, too small, no math content): output exactly: [Not Decodable]\
"""


# ── LaTeX validation helper ───────────────────────────────────────────────────

def _is_valid_latex(output: str) -> bool:
    """Heuristic: kiểm tra output có phải LaTeX hợp lệ không.

    Returns False nếu:
    - Quá ngắn (< 3 chars)
    - Bắt đầu bằng "[" (failure marker)
    - Không có ký tự math nào VÀ quá ngắn (< 20 chars) → likely plain text
    """
    s = (output or "").strip()
    if len(s) < 3:
        return False
    if s.startswith("["):
        return False
    math_chars = set("\\^_{}")
    if not any(c in math_chars for c in s) and len(s) < 20:
        return False
    return True


# ── Formula retry prompt builder ──────────────────────────────────────────────

def _build_formula_retry_prompt(context_text: str) -> str:
    """Prompt retry cho formula: general + context từ surrounding text của paper.

    Dùng khi attempt 1 trả về output không hợp lệ. Context giúp GPT
    disambiguate tên biến và ký hiệu domain-specific mà không hardcode.
    """
    ctx = (context_text or "").strip()[:600]
    if not ctx:
        return _FORMULA_EXTRACTION_PROMPT
    return (
        _FORMULA_EXTRACTION_PROMPT
        + f"\n\nCONTEXT from the paper surrounding this formula "
          f"(use to disambiguate variable names and notation — do NOT blindly copy symbols):\n"
          f"```\n{ctx}\n```"
    )


# ── Vision API call with tenacity retry ──────────────────────────────────────

async def _call_vision_api_async(
    client,
    prompt: str,
    b64_image: str,
    model: str,
    max_tokens: int,
    detail: str = "high",
) -> str:
    """
    Gọi 1 OpenAI Vision API call với tenacity retry.

    Args:
        detail: "high" | "low" | "auto"
            - "high"  : full-tile processing — dùng cho ảnh/biểu đồ cần độ chi tiết cao
            - "auto"  : OpenAI tự chọn dựa trên kích thước ảnh — dùng cho formula crops
                        (crop nhỏ → chọn "low" = 85 tokens thay vì 255, tiết kiệm ~33%)
            - "low"   : luôn dùng 85 tokens/ảnh, nhanh hơn nhưng kém chi tiết
    Retry strategy:
    - Retryable: RateLimitError, APIConnectionError, APITimeoutError
      → Exponential backoff: attempt 1→2s, 2→4s, 3→8s, tối đa 4 lần thử
    - Fatal (không retry): AuthenticationError, BadRequestError → raise ngay
    """
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
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
            return response.choices[0].message.content
    # Unreachable: tenacity reraise=True always raises before this point.
    return ""


async def _call_text_api_async(
    client,
    prompt: str,
    model: str,
    max_tokens: int,
) -> str:
    """Gọi OpenAI text-only chat completion với retry giống Vision call."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    ):
        with attempt:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            return response.choices[0].message.content
    return ""


# ── Event loop isolation fix ──────────────────────────────────────────────────

def _run_async_in_new_loop(coro) -> Any:
    """
    Chạy coroutine trong thread mới với event loop hoàn toàn độc lập.
    An toàn hơn asyncio.run() khi đang trong Streamlit/Jupyter event loop.
    """
    result_box: list = [None]
    error_box:  list = [None]

    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_box[0] = loop.run_until_complete(coro)
        except Exception as e:
            error_box[0] = e
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=600)

    if t.is_alive():
        raise TimeoutError("[VISION][ERR] Vision API thread timeout sau 300s")
    if error_box[0]:
        raise error_box[0]
    return result_box[0]


# ── Batch visual processing with two-pass formula retry ───────────────────────

async def asyncio_process_visuals(
    visuals: List[Dict[str, Any]],
    model: str = IMAGE_VLM_MODEL,
) -> Dict[str, Any]:
    """
    Xử lý batch visuals (ảnh + công thức + bảng markdown) qua OpenAI async.
    Model routing strategy:
      Pass 1A: asyncio.gather() tất cả formula tasks → FORMULA_VLM_MODEL, max_tokens=800
      Pass 1B: asyncio.gather() tất cả image tasks   → IMAGE_VLM_MODEL (model param), max_tokens=1800
      Pass 1C: asyncio.gather() tất cả table tasks   → TABLE_LLM_MODEL, text-only
      Pass 2:  asyncio.gather() formula retry         → FORMULA_VLM_MODEL, max_tokens=800
      Pass 3:  asyncio.gather() formula analysis      → TABLE_LLM_MODEL, text-only

    Args:
        visuals: List[Dict] với keys:
            - "type"         : "image" | "formula" | "table"
            - "pil_image"    : PIL.Image.Image (image/formula only)
            - "markdown"     : str (table only)
            - "id"           : str
            - "page"         : int
            - "context_text" : str (formula only, dùng cho retry)
        model: fallback model cho image tasks (default=IMAGE_VLM_MODEL)

    Returns:
        Dict[str, Any] — {id: result_text}
        Special keys (consumed by parser.py, not formula results):
          "_formula_stats" : dict với total/decoded/retried/retry_success/failed
          "_retry_{id}"    : True nếu formula đó dùng retry
    """
    from openai import AsyncOpenAI
    if not visuals:
        return {}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[VISION][ERR] OPENAI_API_KEY không tìm thấy trong .env")
        return {
            v["id"]: ("[Formula - No API Key]" if v["type"] == "formula" else "")
            for v in visuals
        }

    client = AsyncOpenAI(api_key=api_key)

    # ── Encode tất cả PIL images một lần (reuse cho retry) ───────────────────
    failed: Dict[str, Any] = {}
    encoded: Dict[str, str] = {}
    for v in visuals:
        if v["type"] == "table":
            continue
        try:
            encoded[v["id"]] = _encode_pil_to_base64(v["pil_image"])
        except Exception as enc_err:
            print(f"[VISION][WARN] Không encode được {v['id']} (trang {v['page']}): {enc_err}")
            failed[v["id"]] = "[Formula - Encode Error]" if v["type"] == "formula" else ""

    output: Dict[str, Any] = {}
    n_retried = 0
    n_retry_success = 0

    try:
        # ── Pass 1A: formula tasks → FORMULA_VLM_MODEL ───────────────────────
        # max_tokens=512: đủ cho LaTeX phức tạp nhất (<300 tokens thực tế),
        # tránh lãng phí nếu model sinh thêm text không cần thiết.
        # detail="auto": cho ảnh crop nhỏ → OpenAI chọn "low" (85 tokens thay
        # vì 255 ở "high"), tiết kiệm ~$0.000068/call × 40 formulas ≈ $0.003/doc.
        tasks_1a: List = []
        valid_1a: List[Dict] = []
        for v in visuals:
            if v["id"] in failed or v["type"] != "formula":
                continue
            prompt = _build_formula_retry_prompt(v.get("context_text", ""))
            tasks_1a.append(
                _call_vision_api_async(
                    client, prompt,
                    encoded[v["id"]], FORMULA_VLM_MODEL, 512, "auto",
                )
            )
            valid_1a.append(v)

        results_1a = await asyncio.gather(*tasks_1a, return_exceptions=True)

        # ── Pass 1B: image tasks → IMAGE_VLM_MODEL, max_tokens=1800 ──────────
        # detail="high" bắt buộc: figures/diagrams cần tile đầy đủ để đọc trục,
        # chú thích và số liệu nhỏ. Không dùng "auto" cho loại ảnh này.
        tasks_1b: List = []
        valid_1b: List[Dict] = []
        for v in visuals:
            if v["id"] in failed or v["type"] != "image":
                continue
            prompt = _build_image_prompt(
                caption       = v.get("caption", ""),
                page          = v.get("page", 0),
                context_text  = v.get("context_text", ""),
                figure_number = v.get("figure_number", ""),
            )
            tasks_1b.append(
                _call_vision_api_async(
                    client, prompt, encoded[v["id"]], model, 1800, "high",
                )
            )
            valid_1b.append(v)

        results_1b = await asyncio.gather(*tasks_1b, return_exceptions=True)

        # ── Pass 1C: table markdown tasks → TABLE_LLM_MODEL, text-only ───────
        tasks_1c: List = []
        valid_1c: List[Dict] = []
        for v in visuals:
            if v["id"] in failed or v["type"] != "table":
                continue
            prompt = _build_table_prompt(
                markdown     = v.get("markdown", ""),
                caption      = v.get("caption", ""),
                page         = v.get("page", 0),
                context_text = v.get("context_text", ""),
            )
            tasks_1c.append(
                _call_text_api_async(client, prompt, TABLE_LLM_MODEL, 1000)
            )
            valid_1c.append(v)

        results_1c = await asyncio.gather(*tasks_1c, return_exceptions=True)

        # ── Collect Pass 1A+1B+1C results & identify formula failures ─────────
        output = {**failed}

        for v, res in zip(valid_1a, results_1a):
            if isinstance(res, BaseException):
                print(f"[VISION][WARN] Formula API fail {v['id']} (trang {v['page']}): {res}")
                output[v["id"]] = "[Not Decodable]"
            else:
                result_str = res.strip()
                if not _is_valid_latex(result_str):
                    output[v["id"]] = "[Not Decodable]"
                else:
                    output[v["id"]] = result_str

        for v, res in zip(valid_1b, results_1b):
            if isinstance(res, BaseException):
                print(f"[VISION][WARN] Pass1B API fail {v['id']} (trang {v['page']}): {res}")
                output[v["id"]] = ""
            else:
                output[v["id"]] = res.strip()

        for v, res in zip(valid_1c, results_1c):
            if isinstance(res, BaseException):
                print(f"[VISION][WARN] Table LLM fail {v['id']} (trang {v['page']}): {res}")
                output[v["id"]] = ""
            else:
                output[v["id"]] = res.strip()

        # ── Pass 2: retry [Not Decodable] formulas with detail="high" ────────────
        # Pass 1A uses detail="auto" → OpenAI picks "low" for small crops.
        # "low" = single 512×512 tile (85 tokens): sufficient for large formulas but
        # fails for small ones (inline-size blocks, subscript-only equations).
        # detail="high" tiles the image at full resolution (~765 tokens per 512px tile)
        # and dramatically improves OCR accuracy for small/dense formula crops.
        formula_retry_candidates = [
            v for v in valid_1a
            if output.get(v["id"]) == "[Not Decodable]"
        ]
        n_retried = len(formula_retry_candidates)
        n_retry_success = 0

        if formula_retry_candidates:
            print(f"[VISION] Pass 2 retry {n_retried} formula(s) với detail='high'")
            tasks_2: List = []
            valid_2: List[Dict] = []
            for v in formula_retry_candidates:
                prompt = _build_formula_retry_prompt(v.get("context_text", ""))
                tasks_2.append(
                    _call_vision_api_async(
                        client, prompt,
                        encoded[v["id"]], FORMULA_VLM_MODEL, 800, "high",
                    )
                )
                valid_2.append(v)

            results_2 = await asyncio.gather(*tasks_2, return_exceptions=True)

            for v, res in zip(valid_2, results_2):
                if isinstance(res, BaseException):
                    print(f"[VISION][WARN] Pass2 retry fail {v['id']} (trang {v['page']}): {res}")
                else:
                    result_str = res.strip()
                    if _is_valid_latex(result_str):
                        output[v["id"]] = result_str
                        output[f"_retry_{v['id']}"] = True
                        n_retry_success += 1
            print(f"[VISION] Pass 2 hoàn tất: {n_retry_success}/{n_retried} recovered")
        else:
            n_retried = 0
            n_retry_success = 0

        # ── Pass 3: formula semantic analysis from decoded LaTeX + context ───
        formula_analysis_candidates = [
            v for v in valid_1a
            if _is_valid_latex(str(output.get(v["id"], "")))
        ]
        if formula_analysis_candidates:
            tasks_3: List = []
            valid_3: List[Dict] = []
            for v in formula_analysis_candidates:
                prompt = _build_formula_analysis_prompt(
                    latex=str(output.get(v["id"], "")),
                    context_text=v.get("context_text", ""),
                )
                tasks_3.append(
                    _call_text_api_async(client, prompt, TABLE_LLM_MODEL, 800)
                )
                valid_3.append(v)

            results_3 = await asyncio.gather(*tasks_3, return_exceptions=True)
            for v, res in zip(valid_3, results_3):
                if isinstance(res, BaseException):
                    print(f"[VISION][WARN] Formula analysis fail {v['id']} (trang {v['page']}): {res}")
                    output[f"_analysis_{v['id']}"] = ""
                else:
                    output[f"_analysis_{v['id']}"] = res.strip()

    finally:
        try:
            await client.close()
        except Exception:
            pass

    # ── Formula stats ──────────────────────────────────────────────────────────
    formula_visuals = [v for v in visuals if v["type"] == "formula"]
    n_decoded = sum(1 for v in formula_visuals if _is_valid_latex(str(output.get(v["id"], ""))))
    n_failed  = len(formula_visuals) - n_decoded

    output["_formula_stats"] = {
        "total":         len(formula_visuals),
        "decoded":       n_decoded,
        "failed":        n_failed,
        "retried":       n_retried,
        "retry_success": n_retry_success,
    }

    retry_note = f", Pass2 recovered {n_retry_success}/{n_retried}" if n_retried else ""
    print(
        f"[VISION] Hoàn tất: {len(visuals)} visuals | "
        f"formulas: {n_decoded}/{len(formula_visuals)} decoded "
        f"({n_failed} failed{retry_note})"
    )
    return output
