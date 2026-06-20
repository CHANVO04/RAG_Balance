from typing import List
from query.clients import get_collection
from query.config import IMAGE_TOP_K, IMAGE_SCORE_THRESHOLD


def retrieve_images(q_emb: List[float]) -> str:
    image_context = ""
    try:
        print(f"[IMAGES] Tìm kiếm Hình ảnh liên quan (top-{IMAGE_TOP_K} semantic)...")
        client, col_name = get_collection("rag_images")

        results = client.query_points(
            collection_name=col_name,
            query=q_emb,
            limit=IMAGE_TOP_K,
            with_payload=True,
        )

        # Qdrant trả similarity score [0,1] — cao = liên quan hơn
        relevant_images = [
            point
            for point in results.points
            if float(point.score) >= IMAGE_SCORE_THRESHOLD
        ]

        if relevant_images:
            image_parts = []
            for point in relevant_images:
                p       = point.payload
                img_doc = p.get("document", "")
                img_id  = p.get("image_id", "")
                pg      = p.get("page", "?")
                caption = p.get("caption", "")
                caption_str = f" | Caption: {caption}" if caption else ""
                header = f"[{img_id} | Trang {pg}{caption_str} | Relevance: {point.score:.2f}]"
                image_parts.append(f"{header}\n{img_doc}")
            image_context = "\n\n---\n\n".join(image_parts)
            print(f"[IMAGES] ✅ {len(relevant_images)} hình ảnh liên quan (score >= {IMAGE_SCORE_THRESHOLD}).")
        else:
            print(f"[IMAGES] Không có hình ảnh nào đủ liên quan (threshold={IMAGE_SCORE_THRESHOLD}).")
    except Exception as e:
        print(f"[IMAGES][WARN] Lỗi khi tìm hình ảnh: {e}")

    return image_context
