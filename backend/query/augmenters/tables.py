from typing import Set
from qdrant_client.models import FieldCondition, Filter, MatchAny
from query.clients import get_collection


def retrieve_tables(pages_needed: Set[int], files_needed: Set[str]) -> str:
    if not pages_needed or not files_needed:
        return ""

    table_context = ""
    print(f"[TABLES] Quét tìm Bảng số liệu ở trang: {sorted(pages_needed)}...")
    try:
        client, col_name = get_collection("rag_tables")

        # Bug 3 fix: use MatchAny (not MatchValue) for multi-value filter
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

        matched_tables = [
            r.payload.get("document", "")
            for r in records
            if int(r.payload.get("page", -1)) in pages_needed
            and r.payload.get("document")
        ]

        if matched_tables:
            table_context = "\n\n".join(matched_tables)
            print(f"[TABLES] ✅ Kéo thành công {len(matched_tables)} Bảng vào Context.")
        else:
            print("[TABLES] Không tìm thấy bảng nào ở các trang đã chọn.")
    except Exception as e:
        print(f"[TABLES][WARN] Lỗi khi lấy bảng: {e}")

    return table_context
