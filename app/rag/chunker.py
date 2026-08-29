from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "raw"


def load_markdown_documents() -> list[Document]:
    documents = []

    for path in RAW_DOCUMENTS_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": path.name,
                },
            )
        )

    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=80,
        chunk_overlap=10,
        separators=["\n\n", "\n", "。", " ", ""],
    )

    return splitter.split_documents(documents)