from types import SimpleNamespace

import kg_neo4j_extractor as extractor
from kg_scientific_schema import (
    ALLOWED_ENTITY_TYPES,
    canonical_entity_key,
    normalize_entity_label,
    normalize_entity_type,
    normalize_relation_name,
)


def test_allowed_entity_types_match_research_graph_contract():
    assert "Model" in ALLOWED_ENTITY_TYPES
    assert "Dataset" in ALLOWED_ENTITY_TYPES
    assert "Formula" in ALLOWED_ENTITY_TYPES
    assert "Concept" in ALLOWED_ENTITY_TYPES


def test_entity_type_falls_back_to_concept():
    assert normalize_entity_type("Model") == "Model"
    assert normalize_entity_type("UnknownType") == "Concept"
    assert normalize_entity_type("") == "Concept"


def test_relation_normalization_rejects_vague_edges():
    assert normalize_relation_name("runs on") == "RUNS_ON"
    assert normalize_relation_name("is trained-on") == "TRAINED_ON"
    assert normalize_relation_name("associated with") is None
    assert normalize_relation_name("uses") is None


def test_entity_label_and_key_are_deterministic():
    assert normalize_entity_label("  ResNet-50  ") == "ResNet-50"
    assert canonical_entity_key("ResNet-50") == "resnet_50"
    assert canonical_entity_key("Convolutional Neural Network") == "convolutional_neural_network"


def test_scientific_extractor_skips_vague_relation(monkeypatch):
    chunk = SimpleNamespace(
        text="The CNN model runs on the K210 KPU. " * 8,
        page=3,
        chunk_id="chunk-1",
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
    )

    monkeypatch.setattr(
        extractor,
        "_call_llm",
        lambda *_args, **_kwargs: '{"triplets":[{"subject":"CNN","subject_type":"Model","relation":"associated with","object":"K210 KPU","object_type":"Hardware","evidence":"CNN model runs on the K210 KPU.","chunk_id":"chunk-1","confidence":0.8}]}',
    )

    assert extractor.extract_triplets_llm(chunk) == []


def test_scientific_extractor_returns_typed_evidence_triplet(monkeypatch):
    chunk = SimpleNamespace(
        text="The CNN model runs on the K210 KPU. " * 8,
        page=3,
        chunk_id="chunk-1",
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
    )

    monkeypatch.setattr(
        extractor,
        "_call_llm",
        lambda *_args, **_kwargs: '{"triplets":[{"subject":"CNN","subject_type":"Model","relation":"runs on","object":"K210 KPU","object_type":"Hardware","evidence":"CNN model runs on the K210 KPU.","chunk_id":"chunk-1","confidence":0.8,"visual_ids":["fig-1"]}]}',
    )

    triplets = extractor.extract_triplets_llm(chunk)

    assert len(triplets) == 1
    assert triplets[0].subject == "CNN"
    assert triplets[0].subject_type == "Model"
    assert triplets[0].relation == "RUNS_ON"
    assert triplets[0].object_type == "Hardware"
    assert triplets[0].subject_key == "cnn"
    assert triplets[0].object_key == "k210_kpu"
    assert triplets[0].evidence_preview == "CNN model runs on the K210 KPU."
    assert triplets[0].chunk_id == "chunk-1"
    assert triplets[0].workspace_id == "hybrid_ws"
    assert triplets[0].confidence == 0.8
    assert triplets[0].visual_ids == ["fig-1"]


def test_scientific_extractor_uses_real_chunk_id_over_llm_placeholder(monkeypatch):
    chunk = SimpleNamespace(
        text="The CNN model runs on the K210 KPU. " * 8,
        page=3,
        chunk_id="chunk-real",
        file_name="paper.pdf",
        workspace_id="hybrid_ws",
    )

    monkeypatch.setattr(
        extractor,
        "_call_llm",
        lambda *_args, **_kwargs: '{"triplets":[{"subject":"CNN","subject_type":"Model","relation":"runs on","object":"K210 KPU","object_type":"Hardware","evidence":"CNN model runs on the K210 KPU.","chunk_id":"placeholder","confidence":0.8}]}',
    )

    triplets = extractor.extract_triplets_llm(chunk)

    assert len(triplets) == 1
    assert triplets[0].chunk_id == "chunk-real"


def test_scientific_batch_extractor_uses_typed_evidence_triplets(monkeypatch):
    chunk = SimpleNamespace(
        text="The model is evaluated on the CIFAR-10 dataset. " * 8,
        page=4,
        chunk_id="chunk-batch",
        source_file="paper.pdf",
        workspace_id="hybrid_ws",
        title="Generic Vision Paper",
    )

    captured = {}

    def fake_call_llm(prompt, *_args, **_kwargs):
        captured["prompt"] = prompt
        return '{"triplets":[{"subject":"Model","subject_type":"Model","relation":"evaluated on","object":"CIFAR-10","object_type":"Dataset","evidence":"The model is evaluated on the CIFAR-10 dataset.","chunk_id":"chunk-batch","confidence":0.7}]}'

    monkeypatch.setattr(extractor, "_call_llm", fake_call_llm)

    triplets = extractor.extract_triplets_batch_llm([chunk])

    assert "PB-NOMA" not in captured["prompt"]
    assert len(triplets) == 1
    assert triplets[0].relation == "EVALUATED_ON"
    assert triplets[0].object_type == "Dataset"
    assert triplets[0].chunk_id == "chunk-batch"


def test_scientific_batch_extractor_skips_missing_chunk_id(monkeypatch):
    chunk = SimpleNamespace(
        text="The model is evaluated on the CIFAR-10 dataset. " * 8,
        page=4,
        chunk_id="chunk-batch",
        source_file="paper.pdf",
        workspace_id="hybrid_ws",
    )

    monkeypatch.setattr(
        extractor,
        "_call_llm",
        lambda *_args, **_kwargs: '{"triplets":[{"subject":"Model","subject_type":"Model","relation":"evaluated on","object":"CIFAR-10","object_type":"Dataset","evidence":"The model is evaluated on the CIFAR-10 dataset.","confidence":0.7}]}',
    )

    assert extractor.extract_triplets_batch_llm([chunk]) == []


def test_scientific_batch_extractor_skips_unknown_chunk_id(monkeypatch):
    chunk = SimpleNamespace(
        text="The model is evaluated on the CIFAR-10 dataset. " * 8,
        page=4,
        chunk_id="chunk-batch",
        source_file="paper.pdf",
        workspace_id="hybrid_ws",
    )

    monkeypatch.setattr(
        extractor,
        "_call_llm",
        lambda *_args, **_kwargs: '{"triplets":[{"subject":"Model","subject_type":"Model","relation":"evaluated on","object":"CIFAR-10","object_type":"Dataset","evidence":"The model is evaluated on the CIFAR-10 dataset.","chunk_id":"unknown-chunk","confidence":0.7}]}',
    )

    assert extractor.extract_triplets_batch_llm([chunk]) == []
