# Current Project State

Last updated: 2026-06-02

This file is the quick-start state snapshot for future development sessions. Read it before deeper files when you need to understand where RAG Balance currently stands.

## System Summary

RAG Balance is a decoupled Hybrid Graph-Vector RAG system for scientific papers. The development path is FastAPI + React.

Main capabilities implemented:

- Document upload and background ingest.
- Docling-based parsing for PDF, DOCX, PPTX, HTML/HTM.
- Vision-assisted formula/image/table processing.
- Hybrid chunking, deduplication, OpenAI embeddings, and Qdrant indexing.
- OnlyVector and Hybrid query modes.
- SSE chat streaming with early source delivery.
- PDF citation sync, document management, KG panel, UMAP panel, workspace/search state in React.

Main capabilities still pending:

- Module 6 evaluation and ablation.
- Pure text-only fast OnlyVector baseline.
- Full workspace isolation for Neo4j graph visualization and UMAP computation.
- Frontend production polish and bundle/code-splitting.

## Current Tech Stack

| Layer | Current Implementation |
| --- | --- |
| Frontend | React 19 + Vite + TypeScript + Zustand + Tailwind |
| Backend | FastAPI in `backend/main.py` |
| Vector DB | Qdrant Docker |
| Active Qdrant collections | `rag_docs`, `rag_visuals` |
| Knowledge Graph | Neo4j Docker, accessed through raw Neo4j/Cypher helpers |
| Embedding | `text-embedding-3-small`, 1536 dimensions by config |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2`, Hybrid mode only |
| Generator | `gpt-4.1-mini` |

Note: older docs mentioned `rag_tables`, `rag_formulas`, and `rag_images` as active collections. Their helper functions still exist in `backend/ingest/vector_store.py`, but the current main ingest path stores full table/image/formula evidence in `rag_visuals`.

## Important Files

- `backend/main.py`: FastAPI routes, SSE generator, workspace path resolution, ingest task orchestration.
- `backend/schemas.py`: Pydantic API schemas.
- `backend/ingest/pipeline.py`: `offline_ingest()` orchestrator.
- `backend/ingest/vector_store.py`: Qdrant collection and payload builders.
- `backend/query/engine.py`: `rag_prepare()` and `rag_query()`.
- `backend/query/vector_retriever.py`: Qdrant dense search with workspace/file filters.
- `backend/query/reranker.py`: CrossEncoder reranking.
- `backend/query/visuals.py`: conditional full visual payload lookup from `rag_visuals`.
- `frontend/react-app/src/store/searchStore.ts`: default search mode and Top-K settings.
- `frontend/react-app/src/hooks/useChat.ts`: SSE chat orchestration.
- `frontend/react-app/src/components/docs/DocumentManagement.tsx`: main upload/document UI.

## Retrieval Modes

### OnlyVector

OnlyVector is the current frontend default.

Ingest path:

```text
Upload -> FastAPI /api/ingest?ingest_mode=only_vector
       -> _resolve_ingest_kg_mode() maps mode to kg_mode="none"
       -> parse_document
       -> chunk_document
       -> dedup_chunks
       -> embed_chunks
       -> upsert_to_qdrant(rag_docs)
       -> upsert_visuals_to_qdrant(rag_visuals)
       -> registry/doc store update
       -> skip run_kg_step()
```

Query path:

```text
React useChat -> POST /api/chat/stream with query_mode="only_vector"
              -> _resolve_query_mode() maps to kg_mode="vector", use_rerank=False
              -> rag_prepare()
              -> retrieve_kg() returns empty context
              -> retrieve_vectors() searches Qdrant rag_docs
              -> rerank_results() keeps Qdrant similarity order
              -> retrieve_full_visual_context() only if visual keywords match
              -> build_prompt()
              -> streamed OpenAI completion
```

OnlyVector is currently "multimodal-light": it skips Graph and rerank, but still has access to visual payloads when needed. It is not yet a pure text-only baseline.

### Hybrid

Hybrid ingest maps to `kg_mode="light"`, runs KG triplet extraction, and persists KG data to Neo4j. Hybrid query maps to `kg_mode="default"` and `use_rerank=True`, so it retrieves KG context, runs Qdrant vector search, reranks with CrossEncoder, conditionally pulls visual payloads, and builds the final prompt.

## API Contract

Key endpoints:

- `GET /api/health`
- `GET /api/workspaces`
- `POST /api/workspaces`
- `PUT /api/workspaces/{workspace_id}`
- `DELETE /api/workspaces/{workspace_id}`
- `POST /api/chat/stream`
- `POST /api/ingest`
- `GET /api/task-status/{task_id}`
- `GET /api/documents`
- `DELETE /api/documents/{file_name}`
- `GET /api/graph`
- `GET /api/umap`

SSE event order:

```text
status -> thought -> early_sources -> token* -> done
```

Error path emits:

```text
error
```

`early_sources` must arrive before tokens so the React UI can preload source pills and PDF state.

## Workspace Isolation

Implemented:

- `main.py:_workspace_paths(workspace_id)` maps workspace files and registry DBs to `backend/workspaces/{workspace_id}/data` and `backend/workspaces/{workspace_id}/db`.
- `rag_docs` and `rag_visuals` payloads include `workspace_id`.
- Vector search filters by `workspace_id`.
- Ingest setup creates Qdrant payload indexes for high-traffic filters such as `workspace_id`, `file_name`, `visual_id`, `visual_type`, `content_type`, and `page`.
- Frontend upload/query/list/delete paths pass the active workspace.
- React Query invalidation keys include active workspace ID.

Known gaps:

- `/api/graph` accepts `workspace_id`, but Neo4j visualization is still effectively global.
- `/api/umap` accepts `workspace_id`, but `_compute_umap_sync()` currently scrolls shared `rag_docs`.
- Semantic cache is disabled for React/FastAPI chat to avoid cross-workspace contamination. CLI/legacy paths may still use it.

## Running Locally

Start Qdrant:

```powershell
cd backend/qdrant-server
docker compose up -d
```

Start Neo4j for Hybrid/Graph work:

```powershell
cd backend/neo4j-server
docker compose up -d
```

Start backend:

```powershell
cd backend
venv\Scripts\activate
python main.py
```

Start frontend in PowerShell:

```powershell
cd frontend/react-app
npm run dev
```

Start frontend in CMD:

```bat
cd frontend/react-app
npm run dev
```

Local URLs:

- FastAPI: http://localhost:8000
- React: http://localhost:5173
- Qdrant dashboard: http://localhost:6333/dashboard
- Neo4j browser: http://localhost:7474

## Current Verification Baseline

Known passing checks from the last audit:

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q tests\test_api_integration.py
```

Result observed: `8 passed`, with a OneDrive `.pytest_cache` permission warning.

Frontend build:

```powershell
cd frontend\react-app
npm run build
```

Result observed: build passed outside the sandbox, with a large chunk warning around the main JS bundle.

## OnlyVector Optimization Notes

The current OnlyVector flow is reasonable for a multimodal vector baseline, but not yet optimal for speed/cost or clean ablation.

Evidence-backed improvement directions:

- OpenAI documents `text-embedding-3-small` as 1536 dimensions by default and allows a `dimensions` parameter when lower-dimensional vectors are desired: https://platform.openai.com/docs/guides/embeddings
- Qdrant recommends payload indexes for fields used in filters; this project filters by `workspace_id` and often `file_name`: https://qdrant.tech/documentation/manage-data/indexing/
- Qdrant low-latency guidance also calls out payload indexes for filtered search: https://qdrant.tech/documentation/search/low-latency-search/
- Qdrant multitenancy docs recommend a single collection per embedding model with payload partitioning for most multi-tenant cases, plus tenant-aware payload indexing: https://qdrant.tech/documentation/guides/multitenancy/
- Qdrant quantization can reduce memory and speed search at scale with recall tradeoffs: https://qdrant.tech/documentation/manage-data/quantization/

Recommended next work for OnlyVector:

1. Split modes into `only_vector_fast` and `only_vector_multimodal`.
2. Build a small ground-truth QA set and benchmark Top-K values before changing defaults.
3. Consider dynamic retrieval depth: retrieve more for broad questions, fewer for precise citation questions.
4. Consider optional lightweight rerank or MMR only when similarity scores are close, instead of always disabling all post-processing.

## Recommended Next Direction

Do this before Graph expansion:

1. Stabilize OnlyVector as a clean baseline.
2. Add `only_vector_fast` for text-only ingest/query ablation.
3. Create a 20-50 question QA set from scientific papers.
4. Measure retrieval recall, citation accuracy, latency, and answer groundedness.
5. Then compare against Hybrid with KG and rerank enabled.
