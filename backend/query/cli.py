import argparse
from query.engine import rag_query
from query.config import DEFAULT_RETRIEVE_K, DEFAULT_TOP_N

def main():
    p = argparse.ArgumentParser(description="Query_Final v4 — Graph-Vector-Formula RAG")
    p.add_argument("--question",   required=True,              help="Câu hỏi cần RAG trả lời")
    p.add_argument("--retrieve-k", default=DEFAULT_RETRIEVE_K, type=int, help="Số lượng vector ban đầu")
    p.add_argument("--top-n",      default=DEFAULT_TOP_N,      type=int, help="Số lượng qua Reranker")
    p.add_argument("--no-rerank",  action="store_true",        help="Tắt Cross-Encoder Reranker")
    p.add_argument("--no-cache",   action="store_true",        help="Tắt Semantic Cache")
    p.add_argument("--kg-mode",    default="default",          help="Chế độ KG (nhập đường dẫn ablation hoặc 'default')")
    args = p.parse_args()

    rag_query(
        question   = args.question,
        retrieve_k = args.retrieve_k,
        top_n      = args.top_n,
        use_rerank = not args.no_rerank,
        use_cache  = not args.no_cache,
        kg_mode    = args.kg_mode
    )

if __name__ == "__main__":
    main()
