from pydantic_settings import BaseSettings
from typing import Optional
from qdrant_client import QdrantClient


class Settings(BaseSettings):

    model_config = {
        # Direkt .env dosyasını oku
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    # Database (Defaults for local development - override in .env)
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "defaultdb"
    DB_SCHEMA: str = "defaultschema"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_USE_GRPC: bool = False
    
    # Qdrant Collection Names
    QDRANT_SCHEMA_COLLECTION: str = "schema_embeddings"
    QDRANT_KEYWORDS_COLLECTION: str = "schema_keywords"
    QDRANT_DATA_SAMPLES_COLLECTION: str = "data_samples"
    QDRANT_LEXICAL_COLLECTION: str = "lexical_embeddings"

    # Models
    EMBEDDING_MODEL_NAME: str = "emrecan/bert-base-turkish-cased-mean-nli-stsb-tr"
    SEMANTIC_MODEL_NAME: Optional[str] = None
    LEXICAL_FASTTEXT_PATH: str = "./models/fasttext_lexical_model.model"
    TFIDF_VECTORIZER_PATH: str = "./models/tfidf_vectorizer.joblib"

    # LLM
    LLM_MODEL_PATH: str = "./models/OpenR1-Qwen-7B-Turkish-Q4_K_M.gguf"
    LLM_N_CTX: int = 8192  # Extended context window
    LLM_N_THREADS: int = 8
    LLM_N_BATCH: int = 512  
    LLM_LOW_VRAM: bool = False
    LLM_VERBOSE: bool = False
    
    # GPU Settings (automatic detection if not specified)
    USE_GPU: Optional[bool] = True  # GPU'yu zorla kullan
    LLM_N_GPU_LAYERS: int = 35  # RTX 4060 için optimize (tümü yerine 35 katman)

    # App tuning
    MAX_PATH_HOPS: int = 2
    MAX_INITIAL_RESULTS: int = 15
    
    # Vector & Embedding Settings
    SEMANTIC_VECTOR_SIZE: int = 768
    LEXICAL_VECTOR_SIZE: int = 1000
    BATCH_SIZE: int = 128
    
    # Search Thresholds
    SEMANTIC_THRESHOLD: float = 0.5
    LEXICAL_THRESHOLD: float = 0.4
    KEYWORD_THRESHOLD: float = 0.4
    DATA_VALUES_THRESHOLD: float = 0.5

    # If set to true (or 1), skip loading the local LLM model (useful for testing)
    SKIP_LLM: bool = False


settings = Settings()


def create_qdrant_client():
    kwargs = {}
    if settings.QDRANT_API_KEY:
        kwargs["api_key"] = settings.QDRANT_API_KEY

    # Build an explicit HTTP URL to avoid the client attempting TLS on an
    # HTTP-only Qdrant server (which causes WRONG_VERSION_NUMBER errors).
    url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
    try:
        return QdrantClient(
            url=url,
            prefer_grpc=settings.QDRANT_USE_GRPC,
            **kwargs,
        )
    except TypeError:
        # Older qdrant-client versions may not accept `prefer_grpc`/`url` kwarg
        try:
            return QdrantClient(url=url, **kwargs)
        except TypeError:
            # Final fallback to host/port form
            return QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                **kwargs,
            )


def get_db_conn_kwargs():
    return {
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "dbname": settings.DB_NAME,
    }
