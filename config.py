"""
Configuration module for Enterprise Knowledge Assistant.
Loads settings from environment variables using python-dotenv.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Google Gemini API Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_EMBEDDING_MODEL: str = os.getenv(
        "GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001"
    )

    # Vector Store Configuration
    VECTOR_STORE_TYPE: str = os.getenv("VECTOR_STORE_TYPE", "faiss")  # faiss or chroma
    VECTOR_STORE_PATH: str = os.getenv("VECTOR_STORE_PATH", "./data/vector_store")
    CHROMA_COLLECTION_NAME: str = os.getenv(
        "CHROMA_COLLECTION_NAME", "enterprise_knowledge"
    )

    # Document Processing Configuration
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

    # RAG Configuration
    TOP_K_RESULTS: int = int(os.getenv("TOP_K_RESULTS", "5"))
    MAX_CONTEXT_LENGTH: int = int(os.getenv("MAX_CONTEXT_LENGTH", "8000"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))
    MAX_OUTPUT_TOKENS: int = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))

    # Conversation Memory
    MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "10"))

    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    ALLOWED_ORIGINS: list = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:5500,null"
    ).split(",")

    # Data Directories
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self):
        """Validate required settings are present."""
        if not self.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is required. Please set it in your .env file."
            )
        return True


# Singleton settings instance
settings = Settings()
