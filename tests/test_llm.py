import app.llm as llm


class FakeChatOpenAI:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def test_create_chat_model_passes_timeout_setting(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv(
        "DEEPSEEK_BASE_URL",
        "https://example.com/v1",
    )
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setattr(llm, "ChatOpenAI", FakeChatOpenAI)

    model = llm.create_chat_model(
        thinking="disabled"
    )

    assert model.kwargs["timeout"] == 45
    assert model.kwargs["extra_body"] == {
        "thinking": {
            "type": "disabled",
        }
    }