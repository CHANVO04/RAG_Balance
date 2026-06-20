"""
kg_neo4j_config.py — Config constants and all Cypher query strings.
Split from kg_neo4j.py (God Module refactor). kg_neo4j.py remains as backward-compat facade.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION CONFIG
# ══════════════════════════════════════════════════════════════════════════════

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "rag_password")

KG_LLM_PROVIDER    = os.getenv("KG_LLM_PROVIDER",    "openai")
KG_LLM_MODEL       = os.getenv("KG_LLM_MODEL",       "gpt-4.1-mini")
KG_OLLAMA_BASE_URL = os.getenv("KG_OLLAMA_BASE_URL",  "http://localhost:11434")
KG_MAX_TRIPLETS    = int(os.getenv("KG_MAX_TRIPLETS", "10"))
KG_ENABLED         = os.getenv("KG_ENABLED", "true").lower() == "true"
KG_CALL_DELAY_SEC  = float(os.getenv("KG_CALL_DELAY_SEC", "0.1"))

# ══════════════════════════════════════════════════════════════════════════════
# CYPHER QUERY STRINGS
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA_QUERIES = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_node_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT formula_id IF NOT EXISTS FOR (f:Formula) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT image_id IF NOT EXISTS FOR (i:Image) REQUIRE i.id IS UNIQUE",
    "CREATE INDEX chunk_chunk_id IF NOT EXISTS FOR (c:Chunk) ON (c.chunk_id)",
    "CREATE INDEX chunk_workspace_chunk_id IF NOT EXISTS FOR (c:Chunk) ON (c.workspace_id, c.chunk_id)",
    "CREATE INDEX chunk_workspace_id IF NOT EXISTS FOR (c:Chunk) ON (c.workspace_id)",
    "CREATE INDEX entity_workspace_id IF NOT EXISTS FOR (e:Entity) ON (e.workspace_id)",
    "CREATE INDEX entity_label IF NOT EXISTS FOR (e:Entity) ON (e.label)",
    "CREATE INDEX entity_workspace_canonical_key IF NOT EXISTS FOR (e:Entity) ON (e.workspace_id, e.canonical_key)",
    "CREATE INDEX document_workspace_file_name IF NOT EXISTS FOR (d:Document) ON (d.workspace_id, d.file_name)",
]

INIT_SCHEMA_CYPHER = SCHEMA_QUERIES

UPSERT_TRIPLET_CYPHER = """
MERGE (a:Entity {id: $subject_id})
  ON CREATE SET a.label = $subject, a.mentions = 0, a.node_type = 'Concept',
                a.workspace_id = $workspace_id, a.source_files = [], a.pages = []
  ON MATCH  SET a.workspace_id = coalesce(a.workspace_id, $workspace_id),
                a.pages = CASE WHEN $page IN coalesce(a.pages, []) THEN a.pages ELSE coalesce(a.pages, []) + $page END
MERGE (b:Entity {id: $object_id})
  ON CREATE SET b.label = $object, b.mentions = 0, b.node_type = 'Concept',
                b.workspace_id = $workspace_id, b.source_files = [], b.pages = []
  ON MATCH  SET b.workspace_id = coalesce(b.workspace_id, $workspace_id),
                b.pages = CASE WHEN $page IN coalesce(b.pages, []) THEN b.pages ELSE coalesce(b.pages, []) + $page END
MERGE (a)-[r:RELATES_TO {relation: $relation}]->(b)
  ON CREATE SET r.weight = 0, r.workspace_id = $workspace_id,
                r.source_files = [], r.pages = [], r.chunk_ids = [],
                r.evidence_preview = $evidence_preview
WITH a, b, r,
     $source AS source, $page AS page, $chunk_id AS chunk_id,
     $chunk_id IN coalesce(r.chunk_ids, []) AS is_replay
SET r.weight = CASE WHEN is_replay THEN coalesce(r.weight, 0) ELSE coalesce(r.weight, 0) + 1 END,
    r.workspace_id = $workspace_id,
    r.source_files = CASE WHEN source IN coalesce(r.source_files, []) THEN r.source_files ELSE coalesce(r.source_files, []) + source END,
    r.pages = CASE WHEN page IN coalesce(r.pages, []) THEN r.pages ELSE coalesce(r.pages, []) + page END,
    r.chunk_ids = CASE WHEN chunk_id IN coalesce(r.chunk_ids, []) THEN r.chunk_ids ELSE coalesce(r.chunk_ids, []) + chunk_id END,
    a.mentions = CASE WHEN is_replay THEN coalesce(a.mentions, 0) ELSE coalesce(a.mentions, 0) + 1 END,
    b.mentions = CASE WHEN is_replay THEN coalesce(b.mentions, 0) ELSE coalesce(b.mentions, 0) + 1 END,
    a.source_files = CASE WHEN source IN coalesce(a.source_files, []) THEN a.source_files ELSE coalesce(a.source_files, []) + source END,
    b.source_files = CASE WHEN source IN coalesce(b.source_files, []) THEN b.source_files ELSE coalesce(b.source_files, []) + source END,
    a.pages = CASE WHEN page IN coalesce(a.pages, []) THEN a.pages ELSE coalesce(a.pages, []) + page END,
    b.pages = CASE WHEN page IN coalesce(b.pages, []) THEN b.pages ELSE coalesce(b.pages, []) + page END
"""

BFS_CONTEXT_CYPHER = """
MATCH (seed:Entity)
WHERE seed.id IN $seed_ids AND seed.workspace_id = $workspace_id
OPTIONAL MATCH (seed)-[:RELATES_TO*1..2]-(nb:Entity)
WHERE nb.workspace_id = $workspace_id
WITH collect(DISTINCT seed.id) + collect(DISTINCT nb.id) AS hood
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE a.id IN hood AND b.id IN hood
  AND a.workspace_id = $workspace_id
  AND b.workspace_id = $workspace_id
  AND r.workspace_id = $workspace_id
  AND (
    $selected_files IS NULL
    OR size($selected_files) = 0
    OR any(source IN coalesce(r.source_files, []) WHERE source IN $selected_files)
  )
RETURN a.id AS from_id, a.label AS from_label,
       r.relation AS relation, r.weight AS weight,
       b.id AS to_id, b.label AS to_label,
       r.source_files AS source_files,
       r.pages AS pages,
       r.chunk_ids AS chunk_ids,
       r.evidence_preview AS evidence_preview
ORDER BY r.weight DESC
LIMIT $max_triplets
"""

ENTITY_LOOKUP_CYPHER = """
MATCH (n:Entity) WHERE n.id IN $ids OR n.label IN $ids
RETURN n.id AS id
"""

GET_ALL_ENTITY_IDS_CYPHER = """
MATCH (n:Entity {workspace_id: $workspace_id})
RETURN n.id AS id, n.label AS label
"""

TOP_DEGREE_ENTITIES_CYPHER = """
MATCH (n:Entity)-[r:RELATES_TO]-()
WITH n, count(r) AS deg ORDER BY deg DESC LIMIT $limit
RETURN n.id AS id
"""

GET_GRAPH_VIZ_CYPHER = """
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE r.workspace_id = $workspace_id
  AND a.workspace_id = $workspace_id
  AND b.workspace_id = $workspace_id
RETURN a.id AS from_id, a.label AS from_label, a.mentions AS from_mentions,
       a.node_type AS from_type, a.source_files AS from_source_files,
       a.pages AS from_pages,
       r.relation AS relation, r.weight AS weight,
       r.source_files AS source_files, r.pages AS pages,
       r.chunk_ids AS chunk_ids, r.evidence_preview AS evidence_preview,
       b.id AS to_id, b.label AS to_label, b.mentions AS to_mentions,
       b.node_type AS to_type, b.source_files AS to_source_files,
       b.pages AS to_pages
ORDER BY r.weight DESC
LIMIT $limit
"""

GET_GRAPH_VIZ_BY_SOURCE_CYPHER = """
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE r.workspace_id = $workspace_id
  AND a.workspace_id = $workspace_id
  AND b.workspace_id = $workspace_id
  AND any(source IN coalesce(r.source_files, []) WHERE source IN $source_files)
RETURN a.id AS from_id, a.label AS from_label, a.mentions AS from_mentions,
       a.node_type AS from_type, a.source_files AS from_source_files,
       a.pages AS from_pages,
       r.relation AS relation, r.weight AS weight,
       r.source_files AS source_files, r.pages AS pages,
       r.chunk_ids AS chunk_ids, r.evidence_preview AS evidence_preview,
       b.id AS to_id, b.label AS to_label, b.mentions AS to_mentions,
       b.node_type AS to_type, b.source_files AS to_source_files,
       b.pages AS to_pages
ORDER BY r.weight DESC
LIMIT $limit
"""

ANCHORED_KG_CONTEXT_CYPHER_TEMPLATE = """
MATCH (c:Chunk)
WHERE c.workspace_id = $workspace_id
  AND c.chunk_id IN $chunk_ids
MATCH (c)<-[fc:FROM_CHUNK {workspace_id: $workspace_id}]-(seed:Entity {workspace_id: $workspace_id})
MATCH path = (seed)-[relList:RELATES_TO*1..$hops]-(nb:Entity)
WHERE nb.workspace_id = $workspace_id
  AND all(r IN relList WHERE r.workspace_id = $workspace_id)
UNWIND relList AS rel
WITH DISTINCT rel, seed, nb, length(path) AS distance
RETURN startNode(rel) AS source,
       rel AS relationship,
       endNode(rel) AS target,
       seed.id AS seed_id,
       distance AS distance
"""


def anchored_kg_context_cypher(hops: int) -> str:
    try:
        safe_hops = int(hops)
    except (TypeError, ValueError):
        safe_hops = 2
    safe_hops = max(1, min(safe_hops, 3))
    return ANCHORED_KG_CONTEXT_CYPHER_TEMPLATE.replace("RELATES_TO*1..$hops", f"RELATES_TO*1..{safe_hops}")


ANCHORED_KG_CONTEXT_CYPHER = anchored_kg_context_cypher(2)


GET_ENTITY_GRAPH_VIZ_CYPHER = """
MATCH (a:Entity {workspace_id: $workspace_id})-[r:RELATES_TO {workspace_id: $workspace_id}]->(b:Entity {workspace_id: $workspace_id})
RETURN a.id AS from_id, a.label AS from_label, a.mentions AS from_mentions,
       a.node_type AS from_type, a.source_files AS from_source_files,
       a.pages AS from_pages,
       r.relation AS relation, r.weight AS weight,
       r.source_files AS source_files, r.pages AS pages,
       r.chunk_ids AS chunk_ids, r.visual_ids AS visual_ids,
       r.evidence_preview AS evidence_preview, r.confidence AS confidence,
       b.id AS to_id, b.label AS to_label, b.mentions AS to_mentions,
       b.node_type AS to_type, b.source_files AS to_source_files,
       b.pages AS to_pages
ORDER BY r.weight DESC
LIMIT $limit
"""

GET_ENTITY_GRAPH_VIZ_BY_SOURCE_CYPHER = """
MATCH (a:Entity {workspace_id: $workspace_id})-[r:RELATES_TO {workspace_id: $workspace_id}]->(b:Entity {workspace_id: $workspace_id})
WHERE any(source IN coalesce(r.source_files, []) WHERE source IN $source_files)
RETURN a.id AS from_id, a.label AS from_label, a.mentions AS from_mentions,
       a.node_type AS from_type, a.source_files AS from_source_files,
       a.pages AS from_pages,
       r.relation AS relation, r.weight AS weight,
       r.source_files AS source_files, r.pages AS pages,
       r.chunk_ids AS chunk_ids, r.visual_ids AS visual_ids,
       r.evidence_preview AS evidence_preview, r.confidence AS confidence,
       b.id AS to_id, b.label AS to_label, b.mentions AS to_mentions,
       b.node_type AS to_type, b.source_files AS to_source_files,
       b.pages AS to_pages
ORDER BY r.weight DESC
LIMIT $limit
"""

GET_GRAPH_WITH_CHUNKS_VIZ_CYPHER = """
MATCH (n {workspace_id: $workspace_id})-[r {workspace_id: $workspace_id}]-(m {workspace_id: $workspace_id})
WHERE (n:Document OR n:Chunk OR n:Entity)
  AND (
    $source_files IS NULL
    OR coalesce(r.file_name, '') IN $source_files
    OR any(file IN coalesce(r.source_files, []) WHERE file IN $source_files)
    OR coalesce(n.file_name, '') IN $source_files
    OR coalesce(m.file_name, '') IN $source_files
    OR any(file IN coalesce(n.source_files, []) WHERE file IN $source_files)
    OR any(file IN coalesce(m.source_files, []) WHERE file IN $source_files)
  )
RETURN n.id AS from_id,
       coalesce(n.label, n.chunk_id, n.file_name, n.id) AS from_label,
       coalesce(n.mentions, 1) AS from_mentions,
       coalesce(n.node_type, labels(n)[0]) AS from_type,
       coalesce(n.source_files, CASE WHEN n.file_name IS NULL THEN [] ELSE [n.file_name] END) AS from_source_files,
       coalesce(n.pages, CASE WHEN n.page IS NULL THEN [] ELSE [n.page] END) AS from_pages,
       type(r) AS relation,
       coalesce(r.weight, 1) AS weight,
       coalesce(r.source_files, CASE WHEN r.file_name IS NULL THEN [] ELSE [r.file_name] END) AS source_files,
       coalesce(r.pages, CASE WHEN r.page IS NULL THEN [] ELSE [r.page] END) AS pages,
       coalesce(r.chunk_ids, CASE WHEN r.chunk_id IS NULL THEN [] ELSE [r.chunk_id] END) AS chunk_ids,
       coalesce(r.evidence_preview, '') AS evidence_preview,
       m.id AS to_id,
       coalesce(m.label, m.chunk_id, m.file_name, m.id) AS to_label,
       coalesce(m.mentions, 1) AS to_mentions,
       coalesce(m.node_type, labels(m)[0]) AS to_type,
       coalesce(m.source_files, CASE WHEN m.file_name IS NULL THEN [] ELSE [m.file_name] END) AS to_source_files,
       coalesce(m.pages, CASE WHEN m.page IS NULL THEN [] ELSE [m.page] END) AS to_pages
LIMIT $limit
"""

DELETE_EDGES_CYPHER = """
MATCH ()-[r:RELATES_TO]->()
WHERE r.workspace_id = $workspace_id
  AND $file_name IN coalesce(r.source_files, [])
  AND size(coalesce(r.source_files, [])) <= 1
DELETE r
"""
REMOVE_DOCUMENT_FROM_EDGES_CYPHER = """
MATCH ()-[r:RELATES_TO]->()
WHERE r.workspace_id = $workspace_id
  AND $file_name IN coalesce(r.source_files, [])
  AND size(coalesce(r.source_files, [])) > 1
WITH r, [source IN coalesce(r.source_files, []) WHERE source <> $file_name] AS remaining_sources
SET r.source_files = remaining_sources,
    r.weight = size(remaining_sources),
    r.pages = [],
    r.chunk_ids = [],
    r.evidence_preview = ''
RETURN count(r) AS updated_count
"""
DELETE_ORPHANS_CYPHER = """
MATCH (n:Entity {workspace_id: $workspace_id})
WHERE NOT (n)-[:RELATES_TO]-() AND NOT ()-[:RELATES_TO]->(n)
DELETE n
"""
DELETE_VISUAL_CYPHER  = """
MATCH (n)-[:APPEARS_IN {workspace_id: $workspace_id}]->(d:Document {id: $document_id, workspace_id: $workspace_id})
DETACH DELETE n
"""
DELETE_DOCUMENT_CYPHER = """
MATCH (d:Document {id: $document_id, workspace_id: $workspace_id})
DETACH DELETE d
"""

DELETE_DOCUMENT_GRAPH_CYPHER = """
MATCH (d:Document {workspace_id: $workspace_id, file_name: $file_name})
OPTIONAL MATCH (d)-[:HAS_CHUNK {workspace_id: $workspace_id}]->(c:Chunk {workspace_id: $workspace_id})
WITH d, collect(DISTINCT c) AS chunks
WITH d, chunks, [chunk IN chunks WHERE chunk.chunk_id IS NOT NULL | chunk.chunk_id] AS deleted_chunk_ids, size(chunks) AS chunk_count
FOREACH (c IN chunks | DETACH DELETE c)
DETACH DELETE d
WITH chunk_count, deleted_chunk_ids
OPTIONAL MATCH ()-[r:RELATES_TO {workspace_id: $workspace_id}]->()
WHERE $file_name IN coalesce(r.source_files, [])
  AND size(coalesce(r.source_files, [])) > 1
WITH chunk_count, deleted_chunk_ids, collect(DISTINCT r) AS multi_source_relations
FOREACH (rel IN multi_source_relations |
  SET rel.source_files = [source IN coalesce(rel.source_files, []) WHERE source <> $file_name],
      rel.chunk_ids = [chunk_id IN coalesce(rel.chunk_ids, []) WHERE NOT chunk_id IN deleted_chunk_ids],
      rel.pages = [],
      rel.weight = size([source IN coalesce(rel.source_files, []) WHERE source <> $file_name]),
      rel.evidence_preview = ''
)
WITH chunk_count, size(multi_source_relations) AS updated_relation_count
OPTIONAL MATCH ()-[r:RELATES_TO {workspace_id: $workspace_id}]->()
WHERE $file_name IN coalesce(r.source_files, [])
  AND size(coalesce(r.source_files, [])) <= 1
WITH chunk_count, updated_relation_count, collect(DISTINCT r) AS stale_relations
WITH chunk_count, updated_relation_count, stale_relations, size(stale_relations) AS deleted_relation_count
FOREACH (rel IN stale_relations | DELETE rel)
WITH chunk_count, updated_relation_count + deleted_relation_count AS relation_count
OPTIONAL MATCH (e:Entity {workspace_id: $workspace_id})
WHERE NOT (e)-[:FROM_CHUNK {workspace_id: $workspace_id}]->(:Chunk {workspace_id: $workspace_id})
  AND NOT (e)-[:RELATES_TO {workspace_id: $workspace_id}]-(:Entity {workspace_id: $workspace_id})
WITH chunk_count, relation_count, collect(DISTINCT e) AS orphan_entities
WITH chunk_count, relation_count, orphan_entities, size(orphan_entities) AS entity_count
FOREACH (e IN orphan_entities | DETACH DELETE e)
RETURN chunk_count + relation_count + entity_count + 1 AS removed
"""



UPSERT_DOCUMENT_CYPHER = """
MERGE (d:Document {id: $id})
SET d.label = $label,
    d.node_type = 'Document',
    d.workspace_id = $workspace_id,
    d.file_name = $file_name,
    d.source_file = $file_name,
    d.file_hash = $file_hash,
    d.total_pages = $total_pages,
    d.created_at = coalesce(d.created_at, $created_at),
    d.updated_at = $updated_at
RETURN d.id AS id
"""

UPSERT_CHUNK_CYPHER = """
MATCH (d:Document {id: $document_id, workspace_id: $workspace_id})
MERGE (c:Chunk {id: $id})
SET c.chunk_id = $chunk_id,
    c.label = 'Chunk',
    c.node_type = 'Chunk',
    c.workspace_id = $workspace_id,
    c.document_id = $document_id,
    c.file_name = $file_name,
    c.page = $page,
    c.section_label = $section_label,
    c.content_type = $content_type,
    c.text_preview = $text_preview,
    c.tokens = $tokens,
    c.has_table = $has_table,
    c.has_formula = $has_formula,
    c.has_image = $has_image,
    c.created_at = coalesce(c.created_at, $created_at),
    c.updated_at = $updated_at
MERGE (d)-[hc:HAS_CHUNK {workspace_id: $workspace_id, chunk_id: $chunk_id}]->(c)
SET hc.file_name = $file_name,
    hc.page = $page
RETURN c.id AS id
"""

UPSERT_ENTITY_RELATION_CYPHER = """
MATCH (c:Chunk {workspace_id: $workspace_id, chunk_id: $chunk_id})
MERGE (s:Entity {id: $subject_id})
SET s.label = $subject,
    s.node_type = $subject_type,
    s.workspace_id = $workspace_id,
    s.canonical_key = $subject_key,
    s.description = coalesce(s.description, $subject_description),
    s.source_files = CASE WHEN $file_name IN coalesce(s.source_files, []) THEN coalesce(s.source_files, []) ELSE coalesce(s.source_files, []) + $file_name END,
    s.pages = CASE WHEN $page IS NULL OR $page IN coalesce(s.pages, []) THEN coalesce(s.pages, []) ELSE coalesce(s.pages, []) + $page END,
    s.aliases = reduce(items = coalesce(s.aliases, []), alias IN $subject_aliases | CASE WHEN alias IN items THEN items ELSE items + alias END)
MERGE (o:Entity {id: $object_id})
SET o.label = $object,
    o.node_type = $object_type,
    o.workspace_id = $workspace_id,
    o.canonical_key = $object_key,
    o.description = coalesce(o.description, $object_description),
    o.source_files = CASE WHEN $file_name IN coalesce(o.source_files, []) THEN coalesce(o.source_files, []) ELSE coalesce(o.source_files, []) + $file_name END,
    o.pages = CASE WHEN $page IS NULL OR $page IN coalesce(o.pages, []) THEN coalesce(o.pages, []) ELSE coalesce(o.pages, []) + $page END,
    o.aliases = reduce(items = coalesce(o.aliases, []), alias IN $object_aliases | CASE WHEN alias IN items THEN items ELSE items + alias END)
MERGE (s)-[sf:FROM_CHUNK {workspace_id: $workspace_id, chunk_id: $chunk_id}]->(c)
SET sf.file_name = $file_name,
    sf.page = $page
MERGE (o)-[of:FROM_CHUNK {workspace_id: $workspace_id, chunk_id: $chunk_id}]->(c)
SET of.file_name = $file_name,
    of.page = $page
MERGE (s)-[r:RELATES_TO {workspace_id: $workspace_id, relation: $relation, target_id: $object_id}]->(o)
WITH s, o, r, $file_name AS file_name, $page AS page, $chunk_id AS chunk_id,
     $visual_ids AS visual_ids, $evidence_preview AS evidence_preview,
     $confidence AS confidence,
     $chunk_id IN coalesce(r.chunk_ids, []) AS is_replay
SET r.weight = CASE WHEN is_replay THEN coalesce(r.weight, 0) ELSE coalesce(r.weight, 0) + 1 END,
    s.mentions = CASE WHEN is_replay THEN coalesce(s.mentions, 0) ELSE coalesce(s.mentions, 0) + 1 END,
    o.mentions = CASE WHEN is_replay THEN coalesce(o.mentions, 0) ELSE coalesce(o.mentions, 0) + 1 END,
    r.source_files = CASE WHEN file_name IN coalesce(r.source_files, []) THEN coalesce(r.source_files, []) ELSE coalesce(r.source_files, []) + file_name END,
    r.pages = CASE WHEN page IS NULL OR page IN coalesce(r.pages, []) THEN coalesce(r.pages, []) ELSE coalesce(r.pages, []) + page END,
    r.chunk_ids = CASE WHEN chunk_id IN coalesce(r.chunk_ids, []) THEN coalesce(r.chunk_ids, []) ELSE coalesce(r.chunk_ids, []) + chunk_id END,
    r.visual_ids = reduce(items = coalesce(r.visual_ids, []), visual_id IN visual_ids | CASE WHEN visual_id IN items THEN items ELSE items + visual_id END),
    r.evidence_preview = evidence_preview,
    r.confidence = CASE WHEN coalesce(r.confidence, 0.0) > confidence THEN r.confidence ELSE confidence END
RETURN id(r) AS relationship_id
"""
UPSERT_FORMULA_CYPHER = """
MERGE (f:Formula {id: $id})
  ON CREATE SET f.label = $label, f.latex = $latex, f.node_type = 'Formula',
                f.workspace_id = $workspace_id, f.source_file = $source_file,
                f.page = $page
  ON MATCH SET f.latex = $latex,
               f.workspace_id = $workspace_id,
               f.source_file = $source_file,
               f.page = $page
MERGE (d:Document {id: $document_id})
  ON CREATE SET d.label = $document_label, d.node_type = 'Document',
                d.workspace_id = $workspace_id, d.source_file = $source_file
  ON MATCH SET d.workspace_id = $workspace_id,
               d.source_file = $source_file
MERGE (f)-[r:APPEARS_IN]->(d)
  ON CREATE SET r.workspace_id = $workspace_id, r.source_file = $source_file, r.pages = [$page]
  ON MATCH SET r.workspace_id = $workspace_id,
               r.source_file = $source_file,
               r.pages = CASE WHEN $page IN coalesce(r.pages, []) THEN r.pages ELSE coalesce(r.pages, []) + $page END
"""
UPSERT_IMAGE_CYPHER = """
MERGE (i:Image {id: $id})
  ON CREATE SET i.label = $label, i.caption = $caption, i.node_type = 'Image',
                i.workspace_id = $workspace_id, i.source_file = $source_file,
                i.page = $page
  ON MATCH SET i.caption = $caption,
               i.workspace_id = $workspace_id,
               i.source_file = $source_file,
               i.page = $page
MERGE (d:Document {id: $document_id})
  ON CREATE SET d.label = $document_label, d.node_type = 'Document',
                d.workspace_id = $workspace_id, d.source_file = $source_file
  ON MATCH SET d.workspace_id = $workspace_id,
               d.source_file = $source_file
MERGE (i)-[r:APPEARS_IN]->(d)
  ON CREATE SET r.workspace_id = $workspace_id, r.source_file = $source_file, r.pages = [$page]
  ON MATCH SET r.workspace_id = $workspace_id,
               r.source_file = $source_file,
               r.pages = CASE WHEN $page IN coalesce(r.pages, []) THEN r.pages ELSE coalesce(r.pages, []) + $page END
"""
