"""
ingest — Modular RAG ingest package.
Public interface: offline_ingest, delete_document, list_ingested_documents.
"""

from ingest.pipeline import offline_ingest, delete_document
from ingest.registry import list_ingested_documents

__all__ = ["offline_ingest", "delete_document", "list_ingested_documents"]
