# AGENTS.md

Welcome! This is the ultimate developer and AI agent handbook for **RAG Balance**, a decoupled **Hybrid Graph-Vector RAG system** designed for scientific papers (specifically focusing on *PB-NOMA - Partial-Beam Non-Orthogonal Multiple Access* research).

This document serves as the **source of truth** for any AI coder (like Antigravity, Claude Code, or Cursor) to understand system architecture, directory layouts, coding standards, gotchas, and execution rules.

---

## 🚀 1. Agent Behavior & Karpathy-Style Rules

To maintain extreme code quality and system simplicity, you **must** adhere to these core operating philosophies:

### 1.1 Think Step-by-Step Explicitly

* Before writing any code, analyze the existing project structure, imports, and typings.
* Clearly formulate a mental model of the data flow. If a change touches multiple layers (e.g., Database -> FastAPI -> React), trace the types from backend models (`schemas.py`) all the way to frontend state store (`store/`).

### 1.2 Simplicity Over Hype (Zero LangChain / Zero LangGraph)

* **Do not use AI frameworks like LangChain, LangGraph, or LlamaIndex.**
* Maintain a lightweight core by interacting directly with raw drivers and SDKs: `openai` client, `qdrant-client`, and the official `neo4j` driver.
* Writing clear, readable Python code with standard loops and native structures is far superior to nesting complex framework abstractions.

### 1.3 Validation-First Development

* Every plan must contain explicit, measurable verification steps.
* Update `.agent/validation/` or run tests located in `backend/tests/` immediately after implementing any database schema, API route, or parser modification.
* Always test edge cases (e.g., uploading an empty PDF, query with special characters, network dropouts on stream, workspace swapping).

### 1.4 Respect Code Integrity & Context

* **Never purge or shorten** existing comments, logging, or docstrings unless explicitly asked.
* Keep helper methods focused. Use functional programming or decoupled classes rather than monoliths.
* Prioritize local variables and robust exception handling with `tenacity` retries for external APIs.

---

## 🛠️ 2. Comprehensive Tech Stack (2026 Edition)

| Component                   | Technology                            | Detail / Configuration                                                                                                                                                                                                                                |
| :-------------------------- | :------------------------------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Frontend UI**       | **React + Vite + TypeScript**   | Port `5173`. Uses Zustand for state, Tailwind + shadcn/ui for UI.                                                                                                                                                                                   |
| **Legacy UI**         | **Streamlit Fallback**          | `frontend/app.py` for debugging/legacy evaluation visualizers.                                                                                                                                                                                      |
| **Backend API**       | **FastAPI (Python 3.10+)**      | Port `8000`. Async controllers, SSE for chat, Static file mount for data.                                                                                                                                                                           |
| **Vector DB**         | **Qdrant (Docker)**             | Current active collections:`rag_docs` for embedded chunks and `rag_visuals` for full table/image/formula payload lookup. Legacy helpers for `rag_tables`, `rag_formulas`, and `rag_images` still exist but are not on the main ingest path. |
| **Knowledge Graph**   | **Neo4j (Docker)**              | Local Docker on Bolt. Cypher queries for 2-hop entity-relation traversal.                                                                                                                                                                             |
| **PDF Layout Engine** | **IBM Docling v2.8+**           | Highly structured parser for multi-format layout and tables.                                                                                                                                                                                          |
| **Formula & OCR**     | **Vision-capable OpenAI model** | Env-configurable; current defaults use `gpt-4.1-mini` for formula, image, and table analysis.                                                                                                                                                       |
| **Embeddings**        | **text-embedding-3-small**      | OpenAI SDK, 1536-dimensional vectors by current config.                                                                                                                                                                                               |
| **Reranking**         | **ms-marco-MiniLM-L-6-v2**      | Cross-encoder sequence classification for dense context scoring.                                                                                                                                                                                      |
| **LLM Generator**     | **GPT-4.1-mini**                | Main generator for strict grounded responses (async streaming).                                                                                                                                                                                       |
| **Evaluation**        | **RAGAS**                       | Evaluates response groundings, faithfulness, and retrieval recall.                                                                                                                                                                                    |

---

## 📂 3. Project Structure & Directory Layout

Use this directory map to understand where to read, write, and modify code:

```
A_RAG_MAIN/
├── .agent/                    # AI Agent Workspace Logs
│   ├── plans/                 # Architectural & feature implementation plans
│   └── validation/            # Verification suites and end-to-end logs
├── backend/                   # FastAPI Backend
│   ├── main.py                # FastAPI entry point, SSE generator, REST routes
│   ├── schemas.py             # Pydantic models (Single source of truth for API types)
│   ├── requirements.txt       # Python backend dependencies
│   ├── conftest.py            # Pytest configuration
│   ├── ingest/                # Document Ingestion Pipeline (Module 1)
│   │   ├── parser.py          # PDF/DOCX/HTML extraction with Docling
│   │   ├── vision.py          # Vision model integration for tables, images, and equations
│   │   ├── chunker.py         # Hybrid chunking strategies & deduplication
│   │   ├── embedder.py        # text-embedding-3-small API client
│   │   ├── vector_store.py    # Qdrant client connection & collection CRUD
│   │   ├── kg.py              # LightRAG metadata generator
│   │   ├── registry.py        # Content hashing & ingestion status tracking
│   │   ├── config.py          # Ingest settings, collections, and prompt configs
│   │   └── pipeline.py        # Main ingest orchestrator (runs `offline_ingest`)
│   ├── query/                 # Retrieval & LLM Generation Engine (Module 2)
│   │   ├── engine.py          # Ingest-ready RAG coordinator (`rag_prepare`)
│   │   ├── prompt_builder.py  # Structured prompt context builder
│   │   ├── vector_retriever.py# Dense search in Qdrant collections
│   │   ├── kg_retriever.py    # Cypher traversal in Neo4j Knowledge Graph
│   │   ├── reranker.py        # Cross-encoder MS-Marco ranker
│   │   ├── generator.py       # Async GPT completions caller
│   │   ├── cache.py           # Semantic cache (cosine similarity index)
│   │   ├── clients.py         # Lazy database client initializers
│   │   ├── config.py          # Retrieval hyperparameters (k-nearest, top-n)
│   │   └── cli.py             # Command-Line Query debugger
│   ├── db/                    # Local storage (Semantic cache metadata, local registry)
│   ├── data/                  # Default PDF/DOCX papers stored as static assets
│   ├── workspaces/            # Workspace data directories (`/data` and `/db` per tenant)
│   ├── tests/                 # Unit & Integration test suites
│   ├── qdrant-server/         # Qdrant Docker Compose configuration
│   └── neo4j-server/          # Neo4j Docker Compose configuration
├── frontend/                  # Decoupled UIs (Module 4 & 7)
│   ├── react-app/             # Modern SPA Frontend
│   │   ├── src/
│   │   │   ├── main.tsx       # Entry point
│   │   │   ├── App.tsx        # Layout & Pane coordinator
│   │   │   ├── index.css      # Custom global variables & Tailwind CSS
│   │   │   ├── store/         # Zustand global states (active workspace, active PDF)
│   │   │   ├── api/           # SSE client stream hook & API handlers
│   │   │   ├── components/    # 3-Pane interface: Chat, Ingest list, Flow, UMAP
│   │   │   └── hooks/         # Custom hooks (StreamBuffer FSM, PDF scrolls)
│   │   ├── package.json       # React Vite manifest
│   │   └── vite.config.ts     # Proxy configuration for Port 8000
│   └── app.py                 # Legacy Streamlit fallback UI
├── docs/                      # Technical System Documentation
│   └── superpowers/specs/     # E2E Test & React-FastAPI migration specs
├── AGENTS.md                  # This file (AI Guide)
├── PRD.md                     # Product Requirements Document
├── PROGRESS.md                # Progress tracker for modules
└── scripts/                   # System automation scripts (PowerShell)
```

---

## 🔄 4. RAG Architecture & Data Flow

```mermaid
graph TD
    User([User Prompt]) -->|POST /api/chat/stream| API[FastAPI: backend/main.py]
  
    %% Ingestion Pipeline
    subgraph Ingestion_Pipeline [Ingestion Pipeline (Module 1)]
        PDF[PDF Scientific Papers] -->|IBM Docling| Parser[parser.py]
        Parser -->|Formula & Table Elements| VLM[vision.py: Vision VLM OCR]
        VLM --> Chunker[chunker.py: Hybrid Chunker & Dedup]
      
        Chunker -->|Dense Text Embeddings| QDocs[(Qdrant: rag_docs)]
        VLM -->|Full Visual Payloads| QVisuals[(Qdrant: rag_visuals)]
        Chunker -->|Hybrid mode only: Cypher Extractor| Neo4j[(Neo4j KG)]
    end

    %% Retrieval Pipeline
    subgraph Retrieval_Engine [Retrieval Engine (Module 2)]
        API -->|rag_prepare| QE[engine.py]
      
        QE -->|Semantic Cache Check| Cache{Cache Hit?}
        Cache -->|Yes| FastResponse[Done: Return Cache]
      
        Cache -->|No| Search[Retrieval Coordinator]
        Search -->|OnlyVector/Hybrid: Vector Search| QDocs
        Search -->|Hybrid only: Cypher Entity Query| Neo4j
        Search -->|Conditional table/formula/image questions| QVisuals
      
        QDocs -->|Context Chunks| Rerank[reranker.py: Cross-Encoder]
        Neo4j -->|2-Hop Traversal| Traversal[kg_retriever.py]
      
        Rerank -->|Top-N Scored Chunks| Prompt[prompt_builder.py]
        Traversal -->|Weight-Sorted Graph Context| Prompt
        QVisuals -->|High-detail Visual Evidence| Prompt
      
        Prompt -->|Augmented Prompt| Gen[generator.py: Async GPT-4.1-mini]
    end

    Gen -->|SSE Token Stream| API
    API -->|SSE Protocol Stream| User
```

---

## ⚖️ 5. Coding Conventions & Strict Rules

All code updates **must** satisfy the following patterns to prevent regression and maintain system compatibility.

### 5.1 The Server-Sent Events (SSE) Protocol Contract

The FastAPI chat streaming endpoint (`/api/chat/stream`) and the React frontend state machines coordinate via discrete SSE events. Never return direct raw strings inside SSE! Follow this exact event sequence:

1. `status`: Dynamic task messages updating the user on the step.
   * *Format:* `sse_fmt("status", {"step": "Đang tìm kiếm...", "substep": "KG + Vector"})`
2. `thought`: Logical chains of thoughts or search criteria used for observability.
   * *Format:* `sse_fmt("thought", {"content": "Searching workspace..."})`
3. `early_sources` *(Crucial for fast UI loading)*: Delivers JSON containing exact PDF file names, pages, and bounding scores before the LLM generates a single word. This enables the UI to preload and synchronize the PDF viewer early.
   * *Format:* `sse_fmt("early_sources", {"sources": [...]})`
4. `token`: Chunks of generated answers from LLM streaming.
   * *Format:* `sse_fmt("token", {"content": "Answer token..."})`
5. `done`: Emits final data like extracted Graph relationships or extra visual contexts.
   * *Format:* `sse_fmt("done", {"kg_context": "..."})`
6. `error`: Catch-all for API or retrieval exception handling.
   * *Format:* `sse_fmt("error", {"message": "..."})`

### 5.2 Structured Schema Binding

* Every FastAPI request, response, and inner database handler payload **must** inherit from a Pydantic model defined in `backend/schemas.py`.
* Direct access of JSON dictionaries or typing with `Dict[str, Any]` inside controllers is highly discouraged unless wrapping dynamic database payloads. Ensure strict typing constraints: `List[SourceInfo]`, `TaskStatus`, `DocumentInfo`.

### 5.3 Observability (Traceable Context)

* Current code relies mostly on structured logs, task logs, and tests. If adding tracing later, decorate core business logic functions in `backend/query/engine.py` and `backend/ingest/pipeline.py` with `@traceable` or an equivalent lightweight tracer.

### 5.4 State-free (Statelessness) Architecture

* The Backend **does not store conversation histories**.
* Current `ChatRequest` sends the active `question`, optional `conversation_id`, `workspace_id`, `query_mode`, `top_k`, and optional `selected_files`. It does **not** send full chat history yet.
* The React frontend keeps conversations and active workspace UI state locally with Zustand.
* The backend remains stateless for chat generation and does not persist user message history.

### 5.5 Multi-Tenant Workspace Isolation

* Never hardcode file paths to `backend/data/` or `backend/db/`.
* Use `main.py:_workspace_paths(workspace_id)` to resolve isolated subdirectory locations dynamically for the active workspace context:
  * Workspace data dir: `backend/workspaces/{workspace_id}/data/`
  * Workspace metadata registry dir: `backend/workspaces/{workspace_id}/db/`
* Qdrant payloads include `workspace_id`; vector retrieval filters by `workspace_id` and optional `selected_files`.
* Current known gap: `/api/graph` and `/api/umap` accept `workspace_id`, but graph visualization remains backed by the shared Neo4j view and UMAP computation still scrolls the shared `rag_docs` collection. Treat full graph/UMAP tenant isolation as pending work.

### 5.6 Retrieval Modes

* Frontend search mode defaults to `only_vector` in `frontend/react-app/src/store/searchStore.ts`.
* OnlyVector ingest sends `ingest_mode=only_vector`, which backend maps to `kg_mode="none"` and therefore skips Neo4j triplet extraction.
* OnlyVector query sends `query_mode=only_vector`, which backend maps to `kg_mode="vector"` and `use_rerank=False`; query then uses Qdrant similarity scores directly.
* Hybrid query maps to `kg_mode="default"` and `use_rerank=True`, so it uses KG retrieval plus CrossEncoder reranking.
* Current OnlyVector is multimodal-light, not text-only: ingest still stores `rag_visuals`, and query can fetch full visual payloads if the question asks about tables, formulas, or images.

---

## 📈 6. Context Window Management (How to read this project)

To optimize your token usage and grasp implementation details as efficiently as possible, read files in this precise hierarchical order:

1. **High Priority (Core System Rules & Types)**:
   * [AGENTS.md](file:///c:/Users/admin/OneDrive/Desktop/A1_MinhChan/A_KLTN_RAG/ALL_ABOUT_RAG/A_RAG_MAIN/AGENTS.md) (This guide)
   * [backend/schemas.py](file:///c:/Users/admin/OneDrive/Desktop/A1_MinhChan/A_KLTN_RAG/ALL_ABOUT_RAG/A_RAG_MAIN/backend/schemas.py) (API Models)
   * [backend/main.py](file:///c:/Users/admin/OneDrive/Desktop/A1_MinhChan/A_KLTN_RAG/ALL_ABOUT_RAG/A_RAG_MAIN/backend/main.py) (Server controllers and stream loops)
2. **Logic Priority (RAG & Ingestion Engines)**:
   * [backend/query/engine.py](file:///c:/Users/admin/OneDrive/Desktop/A1_MinhChan/A_KLTN_RAG/ALL_ABOUT_RAG/A_RAG_MAIN/backend/query/engine.py) (Core retrieval flow)
   * [backend/ingest/pipeline.py](file:///c:/Users/admin/OneDrive/Desktop/A1_MinhChan/A_KLTN_RAG/ALL_ABOUT_RAG/A_RAG_MAIN/backend/ingest/pipeline.py) (Pipeline orchestrator)
3. **Config & Setup (Env & Dependencies)**:
   * `backend/requirements.txt` (Dependencies check)
   * `.env.example` or `backend/.env` (API keys, ports config)
4. **Ignore (Do not read to save context)**:
   * `**/venv/**`, `**/node_modules/**`, `**/__pycache__/**` (Binary folders)
   * `backend/data/**`, `backend/db/**` (Raw document chunks and caches)

---

## ⚠️ 7. Gotchas & Common Pitfalls (Anti-Patterns)

Avoid these recurrent developer errors:

* **Vite Proxy Bypass (CORS Lỗi)**:
  * *Anti-pattern:* Setting the frontend base URL directly to `http://localhost:8000` in browser calls.
  * *Correction:* Always route API calls through `/api` (proxied by Vite automatically to `8000` via `vite.config.ts`) to avoid CORS warnings and dynamic origin issues.
* **Synchronous SSE Blockages**:
  * *Anti-pattern:* Invoking heavy synchronous parsing or file processing tasks directly inside async endpoints.
  * *Correction:* Offload compute-heavy methods like `rag_prepare` or `offline_ingest` to separate threads using `asyncio.to_thread` or schedule them using `BackgroundTasks` as done in `main.py:_run_ingest`.
* **Static Asset Accessibility for PDF Syncing**:
  * FastAPI mounts static paths. Ensure `backend/data/` (or dynamic workspace folders) is mapped appropriately: `app.mount("/data", StaticFiles(directory=DATA_DIR))` is required so the React iframe can navigate to `http://localhost:8000/data/paper.pdf#page=N`.
* **Thread Safety in Background Ingest Task Stores**:
  * Ingestion processes use a global task dictionary (`_tasks`) inside `main.py`. Be mindful that this dict is in-memory and will reset if the Uvicorn process restarts or scales to multiple processes.

---

## 💻 8. Running & Service Management

Ensure Docker is running before executing backend databases.

### 8.1 Docker Containers (Qdrant & Neo4j DBs)

```powershell
# Start Qdrant server container
cd backend/qdrant-server
docker compose up -d

# Start Neo4j server container
cd backend/neo4j-server
docker compose up -d
```

### 8.2 Decoupled Execution (Preferred Dev Mode)

```powershell
# Terminal 1: FastAPI Backend
cd backend
venv\Scripts\activate      # Or .venv\Scripts\activate if that is the env you use
pip install -r requirements.txt
python main.py

# Terminal 2: React Vite UI
cd frontend/react-app
npm install
npm run dev                # PowerShell may require npm.cmd or execution policy adjustment
```

### 8.3 Single Command Service Orchestrator (PowerShell)

You can run the entire decoupled cluster automatically:

```powershell
powershell -File scripts/start-all.ps1
```

### 8.4 Legacy Streamlit GUI Fallback

If you need local evaluation utilities or quick legacy UI testing:

```powershell
cd backend
.venv\Scripts\activate
streamlit run ../frontend/app.py
```

---

*“Simplicity is the ultimate sophistication. Think deeply, keep your abstractions thin, and double-check validation scripts before deployment.”
Bạn hãy tìm kiếm các giao diện web đẹp, tinh tế từng nút, chữ, kiểu, màu sắc từ đó dùng mcp stich chụp lại rồi hoàn thiện frontend hiện tại của tôi hơn*
