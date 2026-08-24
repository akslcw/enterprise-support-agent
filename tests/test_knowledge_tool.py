from app.tools import search_knowledge


def test_search_knowledge_tool_returns_evidence(monkeypatch):
    def fake_retrieve(question: str, limit: int):
        assert question == "数字商品可以退款吗？"
        assert limit == 2

        return [
            {
                "text": "已经使用或激活的数字商品不可退款。",
                "source": "refund-policy.md",
                "distance": 0.2627,
            }
        ]

    monkeypatch.setattr(
        "app.tools.retrieve_knowledge",
        fake_retrieve,
    )

    result = search_knowledge.invoke(
        {"question": "数字商品可以退款吗？"}
    )

    assert "来源：refund-policy.md" in result
    assert "数字商品不可退款" in result


def test_search_knowledge_tool_reports_no_evidence(monkeypatch):
    def fake_retrieve(question: str, limit: int):
        return []

    monkeypatch.setattr(
        "app.tools.retrieve_knowledge",
        fake_retrieve,
    )

    result = search_knowledge.invoke(
        {"question": "北京今天天气怎么样？"}
    )

    assert result == "知识库中没有找到相关资料。"