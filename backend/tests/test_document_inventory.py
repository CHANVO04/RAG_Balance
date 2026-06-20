from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_inventory_files(tmp_path: Path) -> None:
    registry = {
        "documents": [
            {
                "file_name": "embedded-images-tables (1).pdf",
                "workspace_id": "default",
                "total_pages": 1,
                "total_dedup_chunks": 6,
            },
            {
                "file_name": "Get_Started_With_Smallpdf.pdf",
                "workspace_id": "default",
                "total_pages": 1,
                "total_dedup_chunks": 9,
            },
        ]
    }
    store = {
        "documents": [
            {
                "text": "Potentiodynamic polarization data for stainless steel in 0.5 M H2SO4 with egg shell inhibitor.",
                "metadata": {"file_name": "embedded-images-tables (1).pdf", "page": 1},
            },
            {
                "text": "Fig. 5 shows Langmuir adsorption isotherm of ES on stainless steel surface.",
                "metadata": {"file_name": "embedded-images-tables (1).pdf", "page": 1},
            },
            {
                "text": "Smallpdf lets users upload, organize, share digital documents, and request e-signatures.",
                "metadata": {"file_name": "Get_Started_With_Smallpdf.pdf", "page": 1},
            },
        ]
    }
    (tmp_path / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / "documents_store.json").write_text(json.dumps(store), encoding="utf-8")


def test_document_inventory_intent_detects_document_noise_questions():
    from query.document_inventory import should_include_document_inventory

    assert should_include_document_inventory("Which document is relevant and which document is noise?")
    assert should_include_document_inventory("Does the Smallpdf document provide evidence?")
    assert should_include_document_inventory("Which file discusses e-signatures?")
    assert not should_include_document_inventory("Using Table 1, compare corrosion rate at 0 g and 10 g ES.")


def test_document_inventory_context_names_files_and_representative_snippets(tmp_path):
    from query.document_inventory import build_document_inventory_context

    _write_inventory_files(tmp_path)

    context = build_document_inventory_context("default", vector_dir=str(tmp_path))

    assert "### WORKSPACE DOCUMENT INVENTORY" in context
    assert "embedded-images-tables (1).pdf" in context
    assert "Get_Started_With_Smallpdf.pdf" in context
    assert "stainless steel" in context
    assert "e-signatures" in context
    assert len(context) < 2500


def test_prompt_includes_inventory_and_scientific_quality_policies():
    from query.prompt_builder import build_prompt

    system_prompt, user_prompt, _sources = build_prompt(
        question="Which document is relevant and which document is noise?",
        kg_context="",
        formula_context="",
        table_context="",
        image_context="",
        ranked_results=[
            (
                "Corrosion data for stainless steel.",
                {
                    "file_name": "embedded-images-tables (1).pdf",
                    "page": 1,
                    "section_label": "general",
                    "citation_id": "abcd",
                },
                0.91,
            )
        ],
        document_inventory_context="- embedded-images-tables (1).pdf: corrosion paper\n- Get_Started_With_Smallpdf.pdf: file sharing guide",
    )

    assert "WORKSPACE DOCUMENT INVENTORY" in user_prompt
    assert "Get_Started_With_Smallpdf.pdf" in user_prompt
    assert "exact file names" in system_prompt
    assert "non-monotonic" in system_prompt
    assert "theta" in system_prompt
    assert "Markdown table" in system_prompt


def test_prompt_adds_axis_uncertainty_guard_for_exact_figure_label_questions():
    from query.prompt_builder import build_prompt

    _system_prompt, user_prompt, _sources = build_prompt(
        question="What are the exact axis labels and units in Fig. 5? If they are not fully readable, state the uncertainty.",
        kg_context="",
        formula_context="",
        table_context="",
        image_context="[image img_1_2 | Page 1]\nY-axis appears as C/0. Caption: Langmuir adsorption isotherm of ES.",
        ranked_results=[
            (
                "The plot of inhibitor concentration over degree of surface coverage versus inhibitor concentration gives a straight line as shown in Fig. 5.",
                {
                    "file_name": "embedded-images-tables (1).pdf",
                    "page": 1,
                    "section_label": "general",
                    "citation_id": "axis",
                    "has_image": True,
                },
                0.88,
            )
        ],
    )

    assert "FIGURE LABEL / AXIS UNCERTAINTY POLICY" in user_prompt
    assert "Do not answer that labels are clearly readable" in user_prompt
    assert "C/0" in user_prompt
    assert "C/theta" in user_prompt
    assert "degree of surface coverage" in user_prompt


def test_rag_prepare_injects_document_inventory_for_document_questions(monkeypatch):
    import query.engine as engine

    captured = {}

    def fake_retrieve_vectors(*_args, **_kwargs):
        return (
            ["Corrosion data for stainless steel."],
            [{"file_name": "embedded-images-tables (1).pdf", "page": 1, "section_label": "general"}],
            [0.91],
            [0.1, 0.2],
        )

    def fake_build_prompt(*args, **kwargs):
        captured["document_inventory_context"] = kwargs.get("document_inventory_context", "")
        return "system", "user", ["source"]

    monkeypatch.setattr(engine, "retrieve_kg", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(engine, "retrieve_vectors", fake_retrieve_vectors)
    monkeypatch.setattr(engine, "retrieve_full_visual_context", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(engine, "build_document_inventory_context", lambda workspace_id: "### WORKSPACE DOCUMENT INVENTORY\n- Get_Started_With_Smallpdf.pdf: e-signatures")
    monkeypatch.setattr(engine, "build_prompt", fake_build_prompt)

    prepared = engine.rag_prepare(
        "Which document discusses e-signatures?",
        retrieve_k=1,
        top_n=1,
        use_rerank=False,
        use_cache=False,
        kg_mode="vector",
        workspace_id="default",
    )

    assert "Get_Started_With_Smallpdf.pdf" in captured["document_inventory_context"]
    assert prepared["retrieval_trace"]["context_used"]["document_inventory"] is True
