from app.rag.chunker import load_markdown_documents, split_documents


def test_load_markdown_documents_keeps_source() -> None:
    documents = load_markdown_documents()

    assert len(documents) == 1
    assert documents[0].metadata["source"] == "refund-policy.md"


def test_split_documents_keeps_all_refund_rules() -> None:
    documents = load_markdown_documents()
    chunks = split_documents(documents)

    combined_content = "\n".join(chunk.page_content for chunk in chunks)

    assert len(chunks) >= 2
    assert "7 天" in combined_content
    assert "数字商品不可退款" in combined_content
    assert "3 到 5 个工作日" in combined_content