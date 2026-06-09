# Immutable Workspace Strategy Design

## Goal

Lock each workspace to one retrieval strategy selected during workspace setup. A user cannot change the strategy after setup. To use another strategy for the same documents, the user creates a new workspace and ingests the documents there.

This keeps ingestion, query, cleanup, and required database services consistent:

- `only_vector_fast` uses Qdrant text chunks only.
- `only_vector_multimodal` uses Qdrant text chunks plus visual payloads.
- `hybrid` uses Qdrant plus Neo4j graph data.

## Current Problem

The frontend currently stores a workspace `strategy`, but chat settings still allow changing `query_mode` dynamically. Ingest also reads the current search mode. This creates ambiguous behavior:

- A file ingested with `only_vector_multimodal` can later be queried as `hybrid`.
- Re-ingesting the same file after switching modes can be skipped by file hash, so KG may not be created.
- Workspace deletion currently attempts Neo4j cleanup even for non-hybrid workspaces, forcing users to run a database they never used for that workspace.

## Proposed Behavior

### Workspace Setup

Workspace setup requires selecting a strategy. Once setup completes:

- `workspace.strategy` becomes immutable in the UI.
- Existing workspace edit flows must not expose strategy changes.
- The default workspace keeps its current default strategy unless explicitly migrated.

### Ingest

Ingest must use `workspace.strategy`, not a mutable chat/search setting.

Expected mapping:

| Workspace strategy | Ingest `kg_mode` | Visual analysis |
| --- | --- | --- |
| `only_vector_fast` | `none` | skipped |
| `only_vector_multimodal` | `none` | enabled |
| `hybrid` | `light` | enabled |

### Query

Chat query mode is locked to `workspace.strategy`.

The chat settings panel should no longer offer mode toggles. It may show a read-only strategy badge and still allow settings that are safe across modes, such as `top_k` and selected files.

Expected mapping:

| Workspace strategy | Query `kg_mode` | Rerank | Full visual lookup |
| --- | --- | --- | --- |
| `only_vector_fast` | `vector` | false | false |
| `only_vector_multimodal` | `vector` | false | true |
| `hybrid` | `default` | true | true |

### Delete Workspace

Workspace cleanup should only call services required by the workspace strategy:

| Workspace strategy | Qdrant cleanup | Neo4j cleanup | Local files/cache |
| --- | --- | --- | --- |
| `only_vector_fast` | yes | no | yes |
| `only_vector_multimodal` | yes | no | yes |
| `hybrid` | yes | yes | yes |

For vector-only workspaces, delete must succeed without Neo4j Docker running.

For hybrid workspaces, delete requires Qdrant and Neo4j. If Neo4j cleanup fails, the backend should return a clear error so the user can start Neo4j and retry safely.

### Delete Document

Document deletion follows the same dependency rule:

- Non-hybrid workspaces delete Qdrant points, local registry entries, visual assets, and cache only.
- Hybrid workspaces additionally delete Neo4j graph evidence for that document.

## Architecture Changes

### Backend

Add a small resolver near workspace helpers:

- `get_workspace_strategy(workspace_id) -> QueryMode-like string`
- `workspace_requires_neo4j(strategy) -> bool`
- `resolve_workspace_ingest_settings(workspace_id)`
- `resolve_workspace_query_settings(workspace_id)`

These helpers keep strategy decisions centralized and avoid scattered string checks.

Update endpoints:

- `POST /api/ingest`: ignore or remove client-provided `ingest_mode`; derive mode from workspace strategy.
- `POST /api/chat/stream`: ignore or remove client-provided `query_mode`; derive mode from workspace strategy.
- `DELETE /api/workspaces/{workspace_id}`: skip Neo4j cleanup unless strategy is `hybrid`.
- `DELETE /api/documents/{file_name}`: pass enough strategy context to skip Neo4j cleanup for non-hybrid workspaces.

### Frontend

Update workspace strategy UX:

- Keep strategy selection in `WorkspaceSetupWizard`.
- Remove query mode toggles from `SearchSettings`.
- Show read-only strategy label, for example `Strategy: Vector + Visuals`.
- Ingest requests should use `activeWorkspace.strategy`, not `search.mode`.
- Chat requests should use `activeWorkspace.strategy`, not `search.mode`.

Keep `topK` and `selectedFiles` in the search store because they are valid per-workspace query preferences.

## Error Handling

- If a workspace has no strategy, normalize to `only_vector_multimodal` for backward compatibility.
- If a client sends a mismatched `query_mode` or `ingest_mode`, backend should ignore it and use the workspace strategy.
- If Hybrid cleanup cannot connect to Neo4j, return a clear retryable error.
- If Vector cleanup cannot connect to Qdrant, keep local files in place so cleanup can be retried safely.

## Testing

Backend tests:

- `only_vector_multimodal` workspace delete does not import/call Neo4j cleanup.
- `only_vector_fast` workspace delete does not import/call Neo4j cleanup.
- `hybrid` workspace delete calls Neo4j cleanup.
- Chat request with mismatched `query_mode` still uses workspace strategy.
- Ingest request with mismatched `ingest_mode` still uses workspace strategy.
- Document delete skips Neo4j for non-hybrid workspaces.

Frontend tests or manual validation:

- Workspace setup still requires selecting a strategy.
- Chat settings no longer allow changing strategy.
- Upload uses workspace strategy.
- Chat uses workspace strategy.

## Non-Goals

- No automatic upgrade from Vector + Visuals to Hybrid inside the same workspace.
- No graph-only workspace mode.
- No migration of already-ingested workspaces beyond defaulting missing strategy values.

