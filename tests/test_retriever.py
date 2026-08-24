from app.rag.retriever import search_knowledge


class FakeCollection:
    def query(self, **kwargs):
        assert kwargs["query_texts"] == ["数字商品可以退款吗？"]
        assert kwargs["n_results"] == 2

        return {
            "documents": [
                [
                    "已经使用或激活的数字商品不可退款。",
                    "退款审核通过后，款项将在 3 到 5 个工作日内原路退回。",
                ]
            ],
            "metadatas": [
                [
                    {"source": "refund-policy.md"},
                    {"source": "refund-policy.md"},
                ]
            ],
            "distances": [[0.2627, 0.3436]],
        }


def test_search_knowledge_returns_normalized_matches(monkeypatch):
    fake_collection = FakeCollection()

    monkeypatch.setattr(
        "app.rag.retriever.get_collection",
        lambda: fake_collection,
    )

    results = search_knowledge("数字商品可以退款吗？", limit=2)

    assert results == [
        {
            "text": "已经使用或激活的数字商品不可退款。",
            "source": "refund-policy.md",
            "distance": 0.2627,
        },
        {
            "text": "退款审核通过后，款项将在 3 到 5 个工作日内原路退回。",
            "source": "refund-policy.md",
            "distance": 0.3436,
        },
    ]

def test_search_knowledge_discards_distant_matches(monkeypatch):
    class DistantFakeCollection:
        def query(self, **kwargs):
            return {
                "documents": [["退款政策内容"]],
                "metadatas": [[{"source": "refund-policy.md"}]],
                "distances": [[0.7857]],
            }

    monkeypatch.setattr(
        "app.rag.retriever.get_collection",
        lambda: DistantFakeCollection(),
    )

    results = search_knowledge("北京今天天气怎么样？", limit=1)

    assert results == []