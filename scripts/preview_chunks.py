from app.rag.chunker import load_markdown_documents, split_documents


documents = load_markdown_documents()
chunks = split_documents(documents)

print(f"原始文档数：{len(documents)}")
print(f"切分后 chunk 数：{len(chunks)}")

for index, chunk in enumerate(chunks, start=1):
    print(f"\n===== Chunk {index} =====")
    print(f"来源：{chunk.metadata['source']}")
    print(chunk.page_content)