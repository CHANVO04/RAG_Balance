# RAG Balance — PRD (Product Requirements Document)

## What We're Building

A **Hybrid Graph-Vector RAG system** for scientific papers with two capabilities:
1. **Chat** (default view) — Ask questions about ingested documents, get retrieval-augmented answers
2. **Ingestion** — Upload PDF/DOCX files, process them through the pipeline, visualize results

This is a thesis project focused on PB-NOMA (Partial-Beam Non-Orthogonal Multiple Access) papers, demonstrating that combining Vector Search + Knowledge Graph + Vision LLM improves answer quality.

## Target Users

Researchers and students who need to:
- Query scientific papers with complex formulas and tables
- Get accurate answers with source citations
- Visualize document structure via Knowledge Graph
- Compare retrieval strategies (vector-only vs hybrid)

---

## Scope

### In Scope
- ✅ Document ingestion and processing
- ✅ Vector search with Qdrant
- ✅ Hybrid search (keyword + vector)
- ✅ Reranking
- ✅ Metadata extraction
- ✅ Record management (deduplication)
- ✅ Multi-format support (PDF, DOCX, PPTX, HTML/HTM) using Docling
- ✅ Chunking: Hybrid Chunker
- ✅ Image, formula, table processing
- ✅ React-side chat conversations and workspace-local UI state
- ✅ Streaming responses
- ✅ Knowledge graphs / GraphRAG with Neo4j

### Out of Scope
- ❌ Code execution / sandboxing
- ❌ Fine-tuning
- ❌ Multi-tenant admin features
- ❌ Billing/payments
- ❌ Data connectors (Google Drive, SFTP, APIs, webhooks)
- ❌ Scheduled/automated ingestion
- ❌ Admin UI (config via env vars)

---

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | React + Vite + Tailwind CSS + shadcn/ui |
| Backend API | FastAPI (Python) |
| Core RAG | Python (modular packages) |
| PDF Parsing | IBM Docling v2.8+ |
| Formula OCR | Vision-capable OpenAI model, default `gpt-4.1-mini` |
| Embedding | text-embedding-3-small (1536-dim by current config) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Vector DB | Qdrant (`rag_docs`, `rag_visuals` active in current pipeline) |
| Knowledge Graph | Neo4j (Local Docker) |
| LLM | GPT-4.1-mini (via OpenAI SDK) |
| Evaluation | RAGAS |

---

## Module 1: Ingest Pipeline

**Build:** PDF/DOCX/PPTX/HTML parsing (Docling), Vision LLM for formulas/images, HybridChunker, text-embedding-3-small embedding, Qdrant storage (`rag_docs` for dense chunks, `rag_visuals` for full visual payloads), registry & deduplication. OnlyVector ingest maps to `kg_mode=none`; Hybrid ingest builds Neo4j triplets.

**Learn:** Document parsing, chunking strategies, embedding models, vector storage architecture

---

## Module 2: Query Engine

**Build:** Semantic cache for CLI/legacy paths, KG BFS traversal, vector search, optional cross-encoder reranking, conditional table/formula/image payload lookup, prompt building, LLM generation. React/FastAPI chat currently disables global semantic cache to avoid cross-workspace contamination.

**Learn:** Hybrid retrieval, reranking, context augmentation, prompt engineering

---

## Module 3: Knowledge Graph (LightRAG)

**Build:** LLM triplet extraction, entity normalization, Neo4j persistence (Cypher), BFS 2-hop traversal for query, multi-provider support (OpenAI / Ollama)

**Learn:** Knowledge graph construction, entity resolution, graph traversal strategies

---

## Module 4: Premium Decoupled UI (FastAPI + React)

**Build:** FastAPI backend (`main.py`) with SSE streaming, React 19/Vite frontend with workspace layout, `react-flow` for KG, `recharts` for UMAP, native iframe for PDF sync, KaTeX for formulas, Zustand for state management, upload/task polling, and OnlyVector/Hybrid search controls.

**Learn:** Decoupled architecture, Server-Sent Events (SSE), React state management, advanced PDF/Graph visualization in web browsers.

---

## Module 5: Vector DB Migration (Qdrant)

**Build:** Migrate from ChromaDB to Qdrant, update ingest/query pipelines, Docker setup for Qdrant, hybrid search with sparse+dense vectors

**Learn:** Qdrant architecture, hybrid search strategies, migration patterns

---

## Module 6: Evaluation & Ablation

**Build:** RAGAS evaluation suite, ablation experiments (baseline, +formula VLM, +KG, full hybrid), ground truth QA dataset, results comparison

**Learn:** RAG evaluation metrics, ablation study methodology, statistical comparison

---

## Current Retrieval Modes

### OnlyVector

OnlyVector is the default React search mode. During ingest it skips Neo4j KG extraction (`kg_mode=none`) but still parses, chunks, embeds, writes `rag_docs`, and stores full visual payloads in `rag_visuals`. During query it skips KG and CrossEncoder reranking, searches Qdrant `rag_docs` with `workspace_id` and optional `selected_files` filters, and uses Qdrant similarity scores directly.

### Hybrid

Hybrid ingest adds KG triplet extraction and Neo4j persistence. Hybrid query retrieves KG context, performs Qdrant vector retrieval, applies CrossEncoder reranking, optionally pulls detailed visual payloads, then builds the final grounded prompt.

### Known Gaps

- Module 6 evaluation and ablation is not implemented yet.
- OnlyVector has not yet been split into a pure text-only fast baseline versus multimodal vector mode.
- Qdrant payload indexes for `workspace_id` and `file_name` should be added before scaling workspace-filtered retrieval.
- `/api/graph` and `/api/umap` accept `workspace_id`, but graph and UMAP isolation still need hardening.

---

## Success Criteria

By the end, the system should:
- ✅ Ingest PDF papers with formula/table/image extraction
- ✅ Answer questions using hybrid KG + vector retrieval
- ✅ Show source citations and KG context
- ✅ Visualize Knowledge Graph and embedding space
- ✅ Demonstrate measurable improvement over vector-only baseline (via RAGAS)
- ✅ Support multiple KG LLM providers (OpenAI / Ollama)
