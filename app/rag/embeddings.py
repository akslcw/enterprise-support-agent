from functools import lru_cache

from chromadb import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-zh-v1.5"


@lru_cache(maxsize=1)
def get_bge_model() -> SentenceTransformer:
    return SentenceTransformer(
        MODEL_NAME,
        local_files_only=True,
    )


class ChineseBGEEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self) -> None:
        self.model = get_bge_model()
    def __call__(self, input: Documents) -> Embeddings:
        vectors = self.model.encode(
            list(input),
            normalize_embeddings=True,
        )

        return vectors.tolist()

    @staticmethod
    def name() -> str:
        return "bge-small-zh-v1.5"

    def get_config(self) -> dict:
        return {
            "model_name": MODEL_NAME,
        }

    @staticmethod
    def build_from_config(config: dict) -> "ChineseBGEEmbeddingFunction":
        return ChineseBGEEmbeddingFunction()


@lru_cache(maxsize=1)
def get_embedding_function() -> ChineseBGEEmbeddingFunction:
    return ChineseBGEEmbeddingFunction()