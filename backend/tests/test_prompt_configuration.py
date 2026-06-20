from query.prompt_builder import build_prompt


def _sample_ranked_results():
    return [
        (
            "The paper introduces a cable safety predictor.",
            {
                "file_name": "paper.pdf",
                "page": 1,
                "section_label": "abstract",
                "citation_id": "abcd",
            },
            0.42,
        )
    ]


def test_custom_prompt_configuration_is_applied_to_llm_prompts():
    system_prompt, user_prompt, _sources = build_prompt(
        question="What is the contribution?",
        kg_context="",
        formula_context="",
        table_context="",
        image_context="",
        ranked_results=_sample_ranked_results(),
        custom_system_instruction="Answer as a thesis defense assistant.",
        user_prompt_template="Evidence:\n{context}\n\nTask:\n{question}",
    )

    assert "### USER CUSTOM ANSWER INSTRUCTIONS" in system_prompt
    assert "Answer as a thesis defense assistant." in system_prompt
    assert user_prompt.startswith("Evidence:\n### TEXT DOCUMENTS")
    assert "Task:\nWhat is the contribution?" in user_prompt


def test_invalid_user_prompt_template_falls_back_to_default_shape():
    _system_prompt, user_prompt, _sources = build_prompt(
        question="Summarize it.",
        kg_context="",
        formula_context="",
        table_context="",
        image_context="",
        ranked_results=_sample_ranked_results(),
        user_prompt_template="Question only: {question}",
    )

    assert user_prompt.startswith("Context:\n### TEXT DOCUMENTS")
    assert user_prompt.endswith("\n\nQuestion: Summarize it.")
