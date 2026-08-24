from app.rag.retriever import search_knowledge


def main() -> None:
    question = "北京今天天气怎么样？"

    print(f"问题：{question}")

    results = search_knowledge(question)

    if not results:
        print("\n知识库中没有足够相关的资料。")
        return

    for index, item in enumerate(results, start=1):
        print(f"\n===== 命中结果 {index} =====")
        print(f"来源：{item['source']}")
        print(f"距离：{item['distance']}")
        print("内容：")
        print(item["text"])


if __name__ == "__main__":
    main()