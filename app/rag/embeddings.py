from functools import lru_cache
from typing import Any, cast

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings, Images
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

EmbeddingInput = Documents | Images


@lru_cache(maxsize=1)
def get_bge_model() -> SentenceTransformer:
    return SentenceTransformer(
        MODEL_NAME,
        local_files_only=True,
    )


class ChineseBGEEmbeddingFunction(EmbeddingFunction[EmbeddingInput]):
    def __init__(self) -> None:
        self.model = get_bge_model()

    def __call__(self, input: EmbeddingInput) -> Embeddings:
        if input and not isinstance(input[0], str):
            raise ValueError("当前 BGE embedding 仅支持文本，不支持图片。")

        documents = cast(Documents, input)

        vectors = self.model.encode(
            documents,
            normalize_embeddings=True,
        )

        return cast(Embeddings, vectors.tolist())

    @staticmethod
    def name() -> str:
        return "bge-small-zh-v1.5"

    def get_config(self) -> dict[str, Any]:
        return {
            "model_name": MODEL_NAME,
        }

    @staticmethod
    def build_from_config(
        config: dict[str, Any],
    ) -> EmbeddingFunction[EmbeddingInput]:
        return ChineseBGEEmbeddingFunction()


@lru_cache(maxsize=1)
def get_embedding_function() -> EmbeddingFunction[EmbeddingInput]:
    return ChineseBGEEmbeddingFunction()
