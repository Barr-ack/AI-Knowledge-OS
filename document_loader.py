"""
Document Loader module for Enterprise Knowledge Assistant.

Handles loading and chunking of various document formats:
- PDF files (using pypdf via LangChain)
- DOCX files (using python-docx via LangChain)
- TXT files (plain text)

Documents are split into overlapping chunks for optimal RAG performance.
"""

import logging
import os
from pathlib import Path
from typing import List, Tuple

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)

from config import settings

logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF Document",
    ".docx": "Word Document",
    ".doc": "Word Document",
    ".txt": "Text File",
    ".md": "Markdown File",
}


class DocumentLoader:
    """
    Handles loading documents from various formats and splitting them
    into chunks suitable for embedding and vector storage.
    """

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        """
        Initialize DocumentLoader with chunking configuration.

        Args:
            chunk_size: Maximum number of characters per chunk
            chunk_overlap: Number of overlapping characters between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def load_document(self, file_path: str) -> List[Document]:
        """
        Load a single document from file path.

        Args:
            file_path: Path to the document file

        Returns:
            List of LangChain Document objects

        Raises:
            ValueError: If file format is not supported
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        extension = path.suffix.lower()

        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format: {extension}. "
                f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS.keys())}"
            )

        logger.info(f"Loading {SUPPORTED_EXTENSIONS[extension]}: {path.name}")

        try:
            if extension == ".pdf":
                documents = self._load_pdf(file_path)
            elif extension in (".docx", ".doc"):
                documents = self._load_docx(file_path)
            elif extension in (".txt", ".md"):
                documents = self._load_txt(file_path)
            else:
                raise ValueError(f"No loader configured for extension: {extension}")

            
            for doc in documents:
                doc.metadata["source_file"] = path.name
                doc.metadata["file_type"] = SUPPORTED_EXTENSIONS[extension]
                doc.metadata["file_path"] = str(file_path)

            logger.info(f"Loaded {len(documents)} pages/sections from {path.name}")
            return documents

        except Exception as e:
            logger.error(f"Error loading document {file_path}: {str(e)}")
            raise

    def _load_pdf(self, file_path: str) -> List[Document]:
        """Load PDF document using PyPDFLoader."""
        loader = PyPDFLoader(file_path)
        return loader.load()

    def _load_docx(self, file_path: str) -> List[Document]:
        """Load DOCX document using Docx2txtLoader."""
        loader = Docx2txtLoader(file_path)
        return loader.load()

    def _load_txt(self, file_path: str) -> List[Document]:
        """Load plain text document."""
        loader = TextLoader(file_path, encoding="utf-8")
        return loader.load()

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into smaller chunks for embedding.

        Args:
            documents: List of loaded Document objects

        Returns:
            List of chunked Document objects with updated metadata
        """
        if not documents:
            return []

        chunks = self.text_splitter.split_documents(documents)

        
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            
            chunk.metadata["content_preview"] = chunk.page_content[:200].strip()

        logger.info(
            f"Split {len(documents)} documents into {len(chunks)} chunks "
            f"(chunk_size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return chunks

    def load_and_split(self, file_path: str) -> Tuple[List[Document], dict]:
        """
        Load a document and split it into chunks in one step.

        Args:
            file_path: Path to the document file

        Returns:
            Tuple of (chunks list, metadata dict with stats)
        """
        documents = self.load_document(file_path)
        chunks = self.split_documents(documents)

        metadata = {
            "file_name": Path(file_path).name,
            "file_type": Path(file_path).suffix.lower(),
            "total_pages": len(documents),
            "total_chunks": len(chunks),
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }

        return chunks, metadata

    def load_directory(self, directory_path: str) -> List[Document]:
        """
        Load all supported documents from a directory.

        Args:
            directory_path: Path to directory containing documents

        Returns:
            List of all chunks from all documents
        """
        dir_path = Path(directory_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        all_chunks = []
        loaded_files = []
        failed_files = []

        for file_path in dir_path.iterdir():
            if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    chunks, _ = self.load_and_split(str(file_path))
                    all_chunks.extend(chunks)
                    loaded_files.append(file_path.name)
                except Exception as e:
                    logger.error(f"Failed to load {file_path.name}: {str(e)}")
                    failed_files.append(file_path.name)

        logger.info(
            f"Directory load complete: {len(loaded_files)} files loaded, "
            f"{len(failed_files)} failed, {len(all_chunks)} total chunks"
        )

        return all_chunks


def validate_file(file_path: str, max_size_mb: int = settings.MAX_FILE_SIZE_MB) -> bool:
    """
    Validate that a file exists, has a supported format, and is within size limits.

    Args:
        file_path: Path to validate
        max_size_mb: Maximum allowed file size in megabytes

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    path = Path(file_path)

    if not path.exists():
        raise ValueError(f"File does not exist: {file_path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {path.suffix}. "
            f"Allowed types: {', '.join(SUPPORTED_EXTENSIONS.keys())}"
        )

    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > max_size_mb:
        raise ValueError(
            f"File too large: {file_size_mb:.1f}MB. Maximum allowed: {max_size_mb}MB"
        )

    return True
