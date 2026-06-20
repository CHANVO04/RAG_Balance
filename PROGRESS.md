# Progress

Track progress through the RAG Balance project. Update this file as you complete modules — Claude Code reads this to understand where you are.

## Convention
- `[ ]` = Not started
- `[-]` = In progress
- `[x]` = Completed

---

## Module 1: Ingest Pipeline
- [x] PDF parsing with Docling (multi-format: PDF, DOCX, PPTX, HTML/HTM)
- [x] Vision LLM for formula extraction (default model: `gpt-4.1-mini`, two-pass async)
- [x] Vision LLM for image analysis (default model: `gpt-4.1-mini`)
- [x] HybridChunker with deduplication
- [x] text-embedding-3-small embedding (1536-dim by current config)
- [x] Qdrant storage (`rag_docs` for dense chunk search, `rag_visuals` for full table/image/formula payload lookup)
- [x] Qdrant payload indexes for workspace/file/visual filtered retrieval
- [x] Registry & record management (content hashing, skip duplicates)
- [x] CLI interface (ingest / list / delete actions)
- [x] KG extraction modes (none / light / full / ablation)
- [x] OnlyVector ingest mode maps to `kg_mode=none` and skips Neo4j triplet extraction

**Status: COMPLETE ✓**

---

## Module 2: Query Engine
- [x] Semantic cache (cosine similarity threshold)
- [x] Knowledge Graph BFS traversal (2-hop, weight-sorted)
- [x] Vector search with Qdrant
- [x] Cross-encoder reranking (ms-marco-MiniLM-L-6-v2)
- [x] Conditional visual evidence lookup from `rag_visuals` when query asks about table/formula/image details
- [x] Prompt builder (KG + formula + table + image + vector context)
- [x] LLM generation (GPT-4.1-mini)
- [x] Strict Grounding & Inline Citations (NotebookLM style, anti-hallucination)
- [x] Source Filtering (Query selected documents only)
- [x] OnlyVector query mode skips KG and reranker, then uses Qdrant similarity scores directly

**Status: COMPLETE ✓**

---

## Module 3: Knowledge Graph (LightRAG)
- [x] LLM triplet extraction (generic + telecom domain prompts)
- [x] Entity normalization (NFKC, singular form, acronym detection)
- [x] Graph persistence (Neo4j / Cypher)
- [x] Edge deduplication with weight accumulation
- [x] BFS 2-hop traversal for query
- [x] LLM entity extraction from questions
- [x] Keyword fallback matching
- [x] Multi-provider support (OpenAI / Ollama)
- [x] Batch extraction mode (multiple chunks per LLM call)

**Status: COMPLETE ✓**

---

## Module 4: Streamlit UI (Legacy / Fallback)
- [x] Chat interface with message history
- [x] Document upload & ingest (sidebar)
- [x] KG LLM provider switch (OpenAI / Ollama)
- [x] Live ingest log & query log
- [x] Question history & document history
- [x] Vector DB explorer (chunk cards, type filter, stats)
- [x] Knowledge Graph visualization (pyvis, degree filter)
- [x] UMAP embedding space visualization
- [x] Formula context display (LaTeX rendering)
- [x] Source citation display (Tooltip UI for inline [ID] citations)
- [x] Notes & Auto-Synthesis (NotebookLM style "Bảng Ghi Chú")

**Status: COMPLETE ✓ (Maintained as Fallback)**

---

## Module 7: Premium Decoupled UI (FastAPI + React)
- [x] Phase 1: FastAPI Backend (`main.py`) with SSE streaming & REST endpoints
- [x] Phase 2: React workspace layout, Zustand stores, Tailwind styling
- [x] Phase 3: Chat Feature (SSE hook, StreamBuffer FSM, KaTeX/citation rendering)
- [x] Phase 4: PDF Sync (SourcePill, backend `pdf_url`, native iframe page hash)
- [x] Phase 5: KG + UMAP panels (React Flow, Recharts)
- [x] Phase 6: Ingest Panel and Document Management (background task polling)
- [-] Phase 7: Polish & Production Scripts

**Status: IN PROGRESS - Core React/FastAPI flow implemented; polish, E2E validation, and optimization remain**

---

## Module 5: Vector DB Migration (Qdrant)
- [x] Docker setup for Qdrant (qdrant-server/)
- [x] Update ingest pipeline for Qdrant client
- [x] Update query pipeline for Qdrant search
- [x] Dense vector search with Qdrant `query_points()` and payload filters
- [x] Migration script from ChromaDB → Qdrant
- [x] Update frontend to use Qdrant

**Status: COMPLETE ✓**

---

## Module 6: Evaluation & Ablation
- [ ] Create ground truth QA dataset
- [ ] RAGAS evaluation script
- [ ] Baseline experiment (vector-only)
- [ ] Ablation 1: + Formula VLM
- [ ] Ablation 2: + KG LightRAG
- [ ] Ablation 3: Full hybrid system
- [ ] Results comparison & analysis

**Status: NOT STARTED**

---

- [x] Docker setup for Neo4j local
- [x] Update LightRAG extraction to support Cypher / Neo4j driver
- [x] Migrate NetworkX GraphML to Neo4j DB
- [x] Update query pipeline to use Neo4j for BFS traversal/Graph search
- [x] Update UI visualization to query Neo4j

**Status: COMPLETE ✓**

---

## Workspace Restructure
- [x] Created `.agent/plans/` and `.agent/validation/`
- [x] Created `.claude/commands/` (build.md, onboard.md, settings.json)
- [x] Created CLAUDE.md, PRD.md, PROGRESS.md
- [x] Move backend code into `backend/` folder
- [x] Move frontend code into `frontend/` folder
- [x] Rename vector_store → db
- [x] Update import paths
- [x] Clean up old folders

**Status: COMPLETE ✓**

---

## Notes
- Qdrant successfully migrated from ChromaDB
- Neo4j local migration for Knowledge Graph is COMPLETE
- KG LLM supports OpenAI and Ollama providers
- Formula extraction uses two-pass async Vision API
- Active Qdrant collections in current pipeline: `rag_docs`, `rag_visuals`
- Legacy helper functions for `rag_tables`, `rag_formulas`, and `rag_images` still exist, but the current ingest path stores full visual evidence in `rag_visuals`
- React/FastAPI dev command: backend `python main.py`, frontend `npm.cmd run dev` from `frontend/react-app`
- Streamlit fallback command: `streamlit run frontend/app.py`
- Backend commands run from `backend/` directory
- Integrated NotebookLM UX features (Source filter, inline citations, Notes & Study Guide synthesis)
- Current priority: optimize and evaluate OnlyVector before extending Graph flow further
