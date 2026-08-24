from app.rag.store import get_collection


MAX_DISTANCE = 0.50

def search_knowledge(
    query: str,
    limit: int = 2,
    max_distance: float = MAX_DISTANCE,
) -> list[dict]:
    """根据用户问题返回相关知识；过滤距离过大的无关结果。"""

    collection = get_collection()

    result = collection.query(
        query_texts=[query],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    matches = []

    for document, metadata, distance in zip(documents, metadatas, distances):
        if distance > max_distance:
            continue

        matches.append(
            {
                "text": document,
                "source": metadata["source"],
                "distance": round(distance, 4),
            }
        )

    return matches