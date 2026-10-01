from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"

    # Storage Paths
    REGULATIONS_DIR: Path = DATA_DIR / "regulations"
    SQLITE_PATH: Path = DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    SQLITE_DB_PATH: Path = DATA_DIR / "regulations" / "sqlite" / "chunks.db"
    JSONL_PATH: Path = DATA_DIR / "regulations" / "canonical.jsonl"
    JSONL_OUTPUT_PATH: Path = DATA_DIR / "regulations" / "canonical.jsonl"
    EMBEDDINGS_DIR: Path = DATA_DIR / "embeddings"
    VECTOR_INDEX_DIR: Path = DATA_DIR / "embeddings"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # LM Studio Local API Config
    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LLM_MODEL_NAME: str = "google/gemma-4-e4b"
    EMBEDDING_MODEL_NAME: str = "text-embedding-kalm-embedding-gemma3-12b-2511"  # or whichever model is loaded in LM Studio
    EMBEDDING_MODEL_VERSION: str = "v1.0"
    EMBEDDING_DIMENSIONS: int = 768  # e.g., 768 for nomic-embed-text, 1024 for bge-large

    class Config:
        env_prefix = "REG_INGEST_"


settings = Settings()

# Ensure required directories exist
settings.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
