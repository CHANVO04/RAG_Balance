"""
schemas.py — Pydantic models for FastAPI endpoints.
All models follow the API contract in docs/superpowers/specs/2026-05-12-react-fastapi-migration-design.md.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, Field


class SourceInfo(BaseModel):
    id: int                  # matches [N] citation in answer text
    citation_id: str = ""    # opaque 4-char citation id, e.g. a3z1
    ref_id: str = ""         # rendered inline token, e.g. a3z1 or IMG-p4f2
    kind: str = "text"       # text | image | formula | table
    visual_id: str = ""
    asset_path: str = ""
    asset_url: str = ""
    content: str = ""
    file_name: str
    page: int                # 1-based, used for iframe hash navigation
    score: float
    section_label: str = ""
    has_table: bool = False
    has_formula: bool = False
    has_image: bool = False
    pdf_url: str = ""        # "http://localhost:8000/data/paper.pdf"
    display: str = ""        # legacy string fallback for Streamlit


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    workspace_id: str = "default"
    query_mode: str = "hybrid"
    qdrant_limit: Optional[int] = None
    score_threshold: Optional[float] = None
    max_context_chunks: Optional[int] = None
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    max_input_tokens: Optional[int] = None
    custom_system_instruction: Optional[str] = None
    user_prompt_template: Optional[str] = None
    top_k: int = 5
    selected_files: Optional[List[str]] = None
    use_cache: Optional[bool] = True


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]
    kg_context: str = ""


class IngestResponse(BaseModel):
    task_id: str
    status: str              # "queued"
    file_name: str
    estimated_minutes: int


class TaskStatus(BaseModel):
    task_id: str
    status: str              # queued | processing | done | error
    progress: int            # 0–100
    current_step: str
    logs: List[str]          # full log history, F5-safe (persisted in server dict)
    error: Optional[str] = None
    queued_at: Optional[float] = None       # Unix timestamp when task was queued
    started_at: Optional[float] = None      # Unix timestamp when backend ingest started
    completed_at: Optional[float] = None    # Unix timestamp when backend ingest stopped
    elapsed_ms: Optional[int] = None        # measured backend ingest duration
    stage_timings_ms: Dict[str, Dict[str, int]] = Field(default_factory=dict)


class DocumentInfo(BaseModel):
    file_name: str
    chunk_count: int
    ingested_at: str
    sha256: str
    total_pages: int = 0
    file_size: Optional[int] = None
    status: str = "ready"
    ingest_mode: str = ""
    processing_time_seconds: Optional[float] = None
    stage_timings: Dict[str, float] = Field(default_factory=dict)
    embedding: Optional[Dict[str, Any]] = None
    total_tables: int = 0
    total_formulas: int = 0
    total_images: int = 0


class WorkspaceInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    strategy: str = "only_vector_multimodal"
    icon: str = "SR"
    collectionName: str = "scientific_papers"
    systemPrompt: str = "You are a helpful scientific research assistant."
    createdAt: str = Field(default="", validation_alias=AliasChoices("createdAt", "created_at"))
    updatedAt: str = Field(default="", validation_alias=AliasChoices("updatedAt", "updated_at"))
    isSetupComplete: bool = Field(
        default=False,
        validation_alias=AliasChoices("isSetupComplete", "is_setup_complete"),
    )


class KGEvidenceInfo(BaseModel):
    id: str
    subject: str
    relation: str
    object: str
    subject_id: str = ""
    object_id: str = ""
    edge_id: str = ""
    source_file: str = ""
    page: int = 0
    chunk_id: str = ""
    weight: float = 1.0
    evidence_preview: str = ""
    has_document_evidence: bool = False


class GraphNodeInfo(BaseModel):
    id: str
    label: str
    type: str = "Concept"
    mentions: int = 1
    degree: int = 0
    source_files: List[str] = []
    pages: List[int] = []


class GraphEdgeInfo(BaseModel):
    id: str = ""
    source: str
    target: str
    relation: str
    weight: float = 1.0
    source_file: str = ""
    page: int = 0
    chunk_ids: List[str] = []
    evidence_preview: str = ""


class GraphData(BaseModel):
    nodes: List[Dict[str, Any]]  # {id, label, type, mentions, degree}
    edges: List[Dict[str, Any]]  # {from, to, relation, weight}


class UMAPPoint(BaseModel):
    x: float
    y: float
    file_name: str
    chunk_id: str
    label: str = ""


class VectorChunkInfo(BaseModel):
    chunk_id: str
    file_name: str
    chunk_index: int = 0
    page: int = 0
    section_label: str = ""
    doc_type: str = "text"
    content: str = ""
    has_table: bool = False
    has_formula: bool = False
    has_image: bool = False


class HealthResponse(BaseModel):
    status: str
    qdrant: str
    neo4j: str
    version: str = "1.0.0"
