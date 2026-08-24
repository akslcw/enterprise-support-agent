from pathlib import Path

import chromadb
from langchain_core.documents import Document

from app.rag.embeddings import get_embedding_function


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VECTOR_DB_DIR = PROJECT_ROOT / ".chroma"

# 改用新名称，避免误使用之前可能由默认英文模型创建的旧 collection。
COLLECTION_NAME = "support_knowledge_zh_v1"


def get_collection():
    client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={
            "hnsw:space": "cosine",
        },
    )


def index_chunks(chunks: list[Document]) -> int:
    collection = get_collection()

    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(chunks):
        source = chunk.metadata["source"]

        ids.append(f"{source}:{index}")
        documents.append(chunk.page_content)
        metadatas.append(chunk.metadata)

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return collection.count()