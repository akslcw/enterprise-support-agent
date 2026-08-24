from app.rag.chunker import load_markdown_documents, split_documents
from app.rag.store import index_chunks


documents = load_markdown_documents()
chunks = split_documents(documents)
stored_count = index_chunks(chunks)

print(f"本次写入 chunk 数：{len(chunks)}")
print(f"向量库当前 chunk 总数：{stored_count}")