from typing import Set
from qdrant_client.models import FieldCondition, Filter, MatchAny
from query.clients import get_collection


def retrieve_formulas(pages_needed: Set[int], files_needed: Set[str]) -> str:
    if not pages_needed or not files_needed:
        return ""

    formula_context = ""
    print(f"[FORMULAS] Quét tìm Công thức LaTeX ở trang: {sorted(pages_needed)}...")
    try:
        client, col_name = get_collection("rag_formulas")

        # Bug 3 fix: MatchAny for multi-value filter
        records, _ = client.scroll(
            collection_name=col_name,
            scroll_filter=Filter(
                must=[FieldCondition(
                    key="file_name",
                    match=MatchAny(any=list(files_needed)),
                )]
            ),
            with_payload=True,
            with_vectors=False,
            limit=10000,
        )

        matched_formulas = []
        decoded_count = 0
        for r in records:
            p = r.payload
            # Bug fix in T3: payload now has BOTH "page" AND "source_page"
            # so this filter on "page" works correctly
            if int(p.get("page", -1)) not in pages_needed:
                continue
            formula_id = p.get("formula_id", "")
            is_decoded = p.get("is_decoded", False)
            latex      = p.get("latex_string", p.get("document", ""))
            display    = f"${latex}$" if is_decoded else latex
            matched_formulas.append(f"[{formula_id}] {display}")
            if is_decoded:
                decoded_count += 1

        if matched_formulas:
            formula_context = "\n".join(matched_formulas)
            print(
                f"[FORMULAS] ✅ Kéo thành công {len(matched_formulas)} công thức "
                f"(decoded LaTeX: {decoded_count}/{len(matched_formulas)})."
            )
        else:
            print("[FORMULAS] Không tìm thấy công thức nào ở các trang đã chọn.")
    except Exception as e:
        print(f"[FORMULAS][WARN] Lỗi khi lấy công thức: {e}")

    return formula_context
