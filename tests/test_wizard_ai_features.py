from applypilot.wizard import init as wizard


def test_setup_ai_features_writes_multi_provider_env(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(wizard, "ENV_PATH", env_path)

    confirm_answers = iter([True])
    prompt_answers = {
        "Gemini API key (optional, from aistudio.google.com)": "g-key",
        "OpenAI API key (optional)": "",
        "Anthropic API key (optional)": "a-key",
        "Local LLM endpoint URL (optional)": "http://127.0.0.1:8080/v1",
        "LLM model (optional, include provider prefix)": "anthropic/claude-haiku-4-5",
    }

    monkeypatch.setattr(
        wizard.Confirm,
        "ask",
        lambda message, default=True, **_kwargs: next(confirm_answers),
    )
    monkeypatch.setattr(
        wizard.Prompt,
        "ask",
        lambda message, default="", **_kwargs: prompt_answers.get(message, default),
    )

    wizard._setup_ai_features()

    content = env_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=g-key" in content
    assert "ANTHROPIC_API_KEY=a-key" in content
    assert "LLM_URL=http://127.0.0.1:8080/v1" in content
    assert "LLM_MODEL=anthropic/claude-haiku-4-5" in content
    assert "OPENAI_API_KEY" not in content
