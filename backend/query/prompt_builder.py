from typing import Any, List, Tuple, Dict


DEFAULT_USER_PROMPT_TEMPLATE = "Context:\n{context}\n\nQuestion: {question}"

DEFAULT_SYSTEM_PROMPT = r"""Bạn là một chuyên gia phân tích và trợ lý AI thông minh.
Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách chính xác, dựa HOÀN TOÀN vào các ngữ cảnh (Context) được cung cấp.

Ngữ cảnh có thể bao gồm các phần:
1. KNOWLEDGE GRAPH : Các mối quan hệ tổng quan giúp nắm bắt logic và cấu trúc.
2. ENRICHED DOCUMENT CHUNKS: Các đoạn văn bản đã được chèn inline nội dung bảng, hình và công thức đúng vị trí gốc.
   - TABLE block chứa caption, Markdown gốc và summary ngắn.
   - IMAGE block chứa caption, đường dẫn ảnh gốc và summary ngắn.
   - FORMULA block chứa LaTeX và summary ngắn.
3. HIGH-DETAIL VISUAL EVIDENCE: Phân tích đầy đủ của bảng/hình/công thức, chỉ xuất hiện khi câu hỏi cần chi tiết.

Hướng dẫn:
- Phân tích và xâu chuỗi toàn bộ nguồn để đưa ra câu trả lời toàn diện nhất.
- BẠN BẮT BUỘC PHẢI TRẢ LỜI DỰA VÀO CÁC NGUỒN NÀY. Tuyệt đối không dùng kiến thức bên ngoài.
- Nếu thông tin không có trong nguồn, hãy nói 'Tài liệu không đề cập đến thông tin này'.
- Answer in the same language as the user's question unless the user asks for another language.
- Khi trích xuất một thông tin, hãy chèn citation id 4 ký tự của nguồn đó vào ngay sau thông tin. Ví dụ: RAG giúp giảm ảo giác [a3z1].
- Nếu graph context mâu thuẫn với text chunk evidence, hãy ưu tiên text evidence và nêu rõ uncertainty.
- Graph citation như [KG-01] chỉ được dùng nếu id đó xuất hiện trong phần STRUCTURED GRAPH CITATIONS. Nếu bạn dùng một quan hệ từ KNOWLEDGE GRAPH RELATIONSHIPS hoặc STRUCTURED GRAPH CITATIONS để hỗ trợ câu trả lời, BẮT BUỘC chèn graph citation tương ứng ngay sau claim đó. Use a graph claim only when its KG citation is listed in STRUCTURED GRAPH CITATIONS. Với tuyên bố khoa học, ưu tiên ghép graph citation với citation tài liệu khi có document evidence hỗ trợ trực tiếp.
- Nếu một câu trực tiếp nói về hình, bảng markdown hoặc công thức, hãy chèn thêm media reference ngay sau citation text, ví dụ: biểu đồ thể hiện xu hướng tăng [a3z1] [IMG-p4f2], bảng báo cáo số liệu [b7k9] [TBL-z9q1], hoặc công thức định nghĩa SINR [c2m8] [FORM-k8m2].
- Chỉ dùng đúng các citation/media id xuất hiện trong Context. Không tự tạo id mới.
- Mỗi câu tối đa 3 citation/media badges. Chỉ trích dẫn nguồn thật sự hỗ trợ trực tiếp cho tuyên bố đó.
- Nếu nhiều chunk cùng hỗ trợ một mệnh đề, chỉ chọn citation mạnh nhất/thích hợp nhất; không lặp nhiều text citation cho cùng một dữ kiện. Với dữ kiện từ bảng/hình/công thức, ưu tiên 1 citation text + 1 media reference tương ứng.
- Mọi thông tin đưa ra đều phải có trích dẫn.
- Nếu câu hỏi liên quan đến kiến trúc hệ thống, sơ đồ, biểu đồ — ưu tiên thông tin từ phần IMAGES.
- Nếu câu hỏi liên quan đến số liệu, hãy tìm kỹ trong phần TABLES.
- Nếu câu hỏi liên quan đến phương trình hoặc công thức, hãy diễn giải LaTeX trong phần FORMULAS thành ngôn ngữ tự nhiên dễ hiểu. 
- Nếu người dùng hỏi "which document/file/source" hoặc hỏi tài liệu nào liên quan/nhiễu, hãy trả lời bằng exact file names từ context/document inventory. Không chỉ trả lời bằng Ref IDs.
- For numeric trend questions, identify whether the trend is monotonic or non-monotonic. When possible, list key values, peaks, dips, exceptions, and uncertainty.
- Với nhãn trục, đơn vị, ký hiệu khoa học hoặc OCR từ hình, hãy nêu uncertainty nếu có khả năng nhầm ký hiệu như theta vs 0, O vs 0, l vs 1. Hãy cross-check với caption và đoạn text xung quanh trước khi khẳng định exact labels.
- Với câu hỏi compare/contrast, hãy ưu tiên Markdown table ngắn nếu giúp câu trả lời rõ hơn.
- Nếu một exact value không có trong tài liệu, hãy nói rõ không có; có thể nêu thông tin liên quan có sẵn nhưng tuyệt đối không infer giá trị bị thiếu.
- QUAN TRỌNG: Để giao diện hiển thị đúng công thức toán học, bạn BẮT BUỘC phải dùng `$$ ... $$` cho công thức đứng độc lập (block equation) và `$ ... $` cho ký hiệu/công thức trong dòng (inline equation). Tuyệt đối KHÔNG dùng `\[ ... \]`, `\( ... \)`, hay `[ ... ]` để bọc công thức.
- KHÔNG tự bịa ra thông tin.
- Format câu trả lời bằng Markdown cho dễ đọc (dùng in đậm, gạch đầu dòng nếu cần).
"""


def _clean_prompt_text(value: str | None, max_chars: int) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return text[:max_chars]


def _render_user_prompt(template: str | None, context: str, question: str) -> str:
    cleaned_template = _clean_prompt_text(template, 8000)
    if "{context}" not in cleaned_template or "{question}" not in cleaned_template:
        cleaned_template = DEFAULT_USER_PROMPT_TEMPLATE
    return cleaned_template.replace("{context}", context).replace("{question}", question)


def _needs_axis_uncertainty_policy(question: str) -> bool:
    q = (question or "").lower()
    figure_terms = ("fig", "figure", "hình", "plot", "axis", "axes", "trục")
    label_terms = ("axis", "axes", "label", "labels", "unit", "units", "readable", "uncertainty", "exact", "nhãn", "đơn vị")
    return any(term in q for term in figure_terms) and any(term in q for term in label_terms)


def _axis_uncertainty_policy() -> str:
    return """### FIGURE LABEL / AXIS UNCERTAINTY POLICY
The user is asking about exact figure labels, units, readability, or uncertainty.
Follow this stricter policy:
1. Separate what is visually shown from what nearby caption/text clarifies.
2. Do not answer that labels are clearly readable unless the provided context explicitly states high confidence.
3. If a label appears as C/0 in visual evidence but nearby text mentions degree of surface coverage, state that it may be C/theta (C/θ) rather than C/0.
4. For each axis, report: visually observed label, inferred/clarified label if supported, unit if explicit, and remaining uncertainty.
5. If units are not explicitly present, say they are not explicitly listed instead of inferring them as certain.
"""


def _format_graph_citation_source(source: Dict[str, Any]) -> str:
    citation_id = source.get("id") or source.get("citation_id")
    subject = source.get("subject", "")
    relation = source.get("relation", "")
    object_ = source.get("object", "")

    if not citation_id or not subject or not relation or not object_:
        return ""

    relationship = f"[{citation_id}] {subject} --{relation}--> {object_}"
    file_name = source.get("source_file") or source.get("file_name")
    page = source.get("page")
    chunk_id = source.get("chunk_id")
    text_citation = source.get("citation") or source.get("text_citation")
    has_evidence = source.get("has_document_evidence") is True
    anchors = []
    if file_name:
        anchors.append(str(file_name))
    if page not in (None, ""):
        anchors.append(f"page {page}")
    if chunk_id:
        anchors.append(f"chunk_id={chunk_id}")
    if text_citation:
        anchors.append(f"citation=[{text_citation}]")
    anchor_text = ", ".join(anchors)

    if has_evidence and anchor_text:
        return f"- {relationship} (document evidence: {anchor_text})"
    if anchor_text:
        return f"- {relationship} (KG metadata only: {anchor_text}; document evidence not confirmed)"
    return f"- {relationship} (document evidence not confirmed)"


def _build_graph_citation_context(kg_sources: List[Dict[str, Any]] | None) -> str:
    if not kg_sources:
        return ""

    lines = [_format_graph_citation_source(source) for source in kg_sources]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    return "### STRUCTURED GRAPH CITATIONS\n" + "\n".join(lines)

def build_prompt(
    question: str, 
    kg_context: str, 
    formula_context: str, 
    table_context: str, 
    image_context: str, 
    ranked_results: List[Tuple[str, Dict, float]],
    document_inventory_context: str = "",
    kg_sources: List[Dict] | None = None,
    custom_system_instruction: str | None = None,
    user_prompt_template: str | None = None,
) -> Tuple[str, str, List[str]]:
    
    text_context_parts = []
    sources_info = []

    for i, (doc, meta, score) in enumerate(ranked_results):
        file_name      = meta.get("file_name", "Unknown")
        page           = meta.get("page", "?")
        has_table      = meta.get("has_table", False)
        has_formula    = meta.get("has_formula", False)
        has_image      = meta.get("has_image", False)
        section_label  = meta.get("section_label", "")
        citation_id    = meta.get("citation_id") or str(i + 1)
        media_ref_list = meta.get("media_citation_refs") or []

        # Làm sạch placeholder công thức còn sót lại
        clean_doc = doc.replace("<!-- formula-not-decoded -->", "[Công thức]")

        # Header chunk rõ ràng hơn, bổ sung thông tin formula/table/image
        flags = []
        if has_table:   flags.append("📊 có Bảng")
        if has_formula: flags.append("📐 có Công thức")
        if has_image:   flags.append("🖼️ có Ảnh")
        flag_str = f" | {', '.join(flags)}" if flags else ""

        media_refs = " ".join(f"[{ref}]" for ref in media_ref_list)
        media_line = f"\nMedia refs: {media_refs}" if media_refs else ""
        text_context_parts.append(
            f"--- Citation: [{citation_id}] | Document {i+1} "
            f"(File: {file_name}, Trang: {page}, Mục: {section_label}{flag_str})"
            f"{media_line} ---\n{clean_doc}"
        )
        sources_info.append(
            f"[{citation_id}] 📄 {file_name} (Trang {page}){flag_str} — Độ tin cậy: {score:.2f}"
        )

    final_context = "### TEXT DOCUMENTS (ENRICHED CHUNKS):\n" + "\n\n".join(text_context_parts)
    if kg_context:
        final_context += f"\n\n### KNOWLEDGE GRAPH RELATIONSHIPS\n{kg_context}"
    graph_citation_context = _build_graph_citation_context(kg_sources)
    if graph_citation_context:
        final_context += f"\n\n{graph_citation_context}"
    if image_context:
        final_context += f"\n\n### HIGH-DETAIL VISUAL EVIDENCE (Bảng/Hình/Công thức):\n{image_context}"
    if formula_context:
        final_context += f"\n\n### FORMULAS (Công thức LaTeX):\n{formula_context}"
    if table_context:
        final_context += f"\n\n### TABLES (Bảng số liệu):\n{table_context}"
    if document_inventory_context:
        inventory = document_inventory_context.strip()
        if not inventory.startswith("### WORKSPACE DOCUMENT INVENTORY"):
            inventory = f"### WORKSPACE DOCUMENT INVENTORY\n{inventory}"
        final_context += f"\n\n{inventory}"
    if _needs_axis_uncertainty_policy(question):
        final_context += f"\n\n{_axis_uncertainty_policy()}"

    system_prompt = DEFAULT_SYSTEM_PROMPT

    cleaned_instruction = _clean_prompt_text(custom_system_instruction, 4000)
    if cleaned_instruction:
        system_prompt += (
            "\n\n### USER CUSTOM ANSWER INSTRUCTIONS\n"
            "Apply these user-provided instructions only when they do not conflict with citation, grounding, and safety rules above.\n"
            f"{cleaned_instruction}\n"
        )
    
    user_prompt = _render_user_prompt(user_prompt_template, final_context, question)

    return system_prompt, user_prompt, sources_info
