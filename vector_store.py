
import logging
import os
import pickle
from pathlib import Path
from typing import List, Optional, Tuple

from langchain.schema import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import settings

logger = logging.getLogger(__name__)


class VectorStoreManager:
    

    def __init__(self):
        """Initialize VectorStoreManager with embedding model and storage config."""
        self.embeddings = self._initialize_embeddings()
        self.vector_store = None
        self.store_type = settings.VECTOR_STORE_TYPE.lower()
        self.store_path = settings.VECTOR_STORE_PATH

        
        Path(self.store_path).mkdir(parents=True, exist_ok=True)

        
        self._try_load_existing_store()

    def _initialize_embeddings(self) -> GoogleGenerativeAIEmbeddings:
       
        logger.info(
            f"Initializing embeddings with model: {settings.GEMINI_EMBEDDING_MODEL}"
        )
        return GoogleGenerativeAIEmbeddings(
            model=settings.GEMINI_EMBEDDING_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )

    def _try_load_existing_store(self):
        """Attempt to load an existing vector store from disk."""
        try:
            if self.store_type == "faiss":
                faiss_path = os.path.join(self.store_path, "faiss_index")
                if os.path.exists(faiss_path):
                    self.load_store()
                    logger.info("Loaded existing FAISS vector store")
            elif self.store_type == "chroma":
                chroma_path = os.path.join(self.store_path, "chroma")
                if os.path.exists(chroma_path):
                    self.load_store()
                    logger.info("Loaded existing Chroma vector store")
        except Exception as e:
            logger.warning(f"Could not load existing vector store: {str(e)}")

    def create_store(self, documents: List[Document]) -> int:
        """
        Create a new vector store from documents.
        If a store already exists, new documents are added to it.

        Args:
            documents: List of Document chunks to embed and store

        Returns:
            Number of documents added to the store
        """
        if not documents:
            logger.warning("No documents provided to create vector store")
            return 0

        logger.info(
            f"Creating/updating {self.store_type.upper()} vector store "
            f"with {len(documents)} chunks..."
        )

        try:
            if self.store_type == "faiss":
                self._create_or_update_faiss(documents)
            elif self.store_type == "chroma":
                self._create_or_update_chroma(documents)
            else:
                raise ValueError(f"Unsupported vector store type: {self.store_type}")

            
            self.save_store()

            logger.info(
                f"Vector store updated successfully with {len(documents)} new chunks"
            )
            return len(documents)

        except Exception as e:
            logger.error(f"Error creating vector store: {str(e)}")
            raise

    def _create_or_update_faiss(self, documents: List[Document]):
        """Create or update FAISS index with new documents."""
        from langchain_community.vectorstores import FAISS

        if self.vector_store is None:
            
            self.vector_store = FAISS.from_documents(documents, self.embeddings)
        else:
            
            self.vector_store.add_documents(documents)

    def _create_or_update_chroma(self, documents: List[Document]):
        """Create or update Chroma collection with new documents."""
        from langchain_community.vectorstores import Chroma

        chroma_path = os.path.join(self.store_path, "chroma")

        if self.vector_store is None:
            
            self.vector_store = Chroma.from_documents(
                documents=documents,
                embedding=self.embeddings,
                collection_name=settings.CHROMA_COLLECTION_NAME,
                persist_directory=chroma_path,
            )
        else:
            
            self.vector_store.add_documents(documents)

    def save_store(self):
        """Persist vector store to disk."""
        if self.vector_store is None:
            return

        try:
            if self.store_type == "faiss":
                faiss_path = os.path.join(self.store_path, "faiss_index")
                self.vector_store.save_local(faiss_path)
                logger.info(f"FAISS index saved to {faiss_path}")

            elif self.store_type == "chroma":
                
                self.vector_store.persist()
                logger.info("Chroma store persisted")

        except Exception as e:
            logger.error(f"Error saving vector store: {str(e)}")
            raise

    def load_store(self):
        
        try:
            if self.store_type == "faiss":
                from langchain_community.vectorstores import FAISS

                faiss_path = os.path.join(self.store_path, "faiss_index")
                self.vector_store = FAISS.load_local(
                    faiss_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                logger.info(f"FAISS index loaded from {faiss_path}")

            elif self.store_type == "chroma":
                from langchain_community.vectorstores import Chroma

                chroma_path = os.path.join(self.store_path, "chroma")
                self.vector_store = Chroma(
                    collection_name=settings.CHROMA_COLLECTION_NAME,
                    embedding_function=self.embeddings,
                    persist_directory=chroma_path,
                )
                logger.info("Chroma store loaded")

        except Exception as e:
            logger.error(f"Error loading vector store: {str(e)}")
            raise

    def similarity_search(
        self,
        query: str,
        k: int = settings.TOP_K_RESULTS,
        score_threshold: float = 0.3,
    ) -> List[Tuple[Document, float]]:
        """
        Perform semantic similarity search in the vector store.

        Args:
            query: Natural language query string
            k: Number of top results to retrieve
            score_threshold: Minimum similarity score (0-1) to include result

        Returns:
            List of (Document, score) tuples sorted by relevance
        """
        if self.vector_store is None:
            logger.warning("Vector store is empty — no documents have been uploaded yet")
            return []

        try:
            
            results = self.vector_store.similarity_search_with_relevance_scores(
                query, k=k
            )

            
            filtered_results = [
                (doc, score) for doc, score in results if score >= score_threshold
            ]

            logger.info(
                f"Similarity search: query='{query[:50]}...', "
                f"found {len(results)} results, "
                f"{len(filtered_results)} above threshold {score_threshold}"
            )

            return filtered_results

        except Exception as e:
            logger.error(f"Error during similarity search: {str(e)}")
            raise

    def get_store_stats(self) -> dict:
        """
        Get statistics about the current vector store.

        Returns:
            Dict with store statistics
        """
        stats = {
            "store_type": self.store_type,
            "is_initialized": self.vector_store is not None,
            "store_path": self.store_path,
        }

        if self.vector_store is not None:
            try:
                if self.store_type == "faiss":
                    
                    stats["total_vectors"] = self.vector_store.index.ntotal
                elif self.store_type == "chroma":
                    
                    stats["total_vectors"] = (
                        self.vector_store._collection.count()
                    )
            except Exception:
                stats["total_vectors"] = "unknown"

        return stats

    def clear_store(self):
        """Clear all documents from the vector store."""
        self.vector_store = None
        logger.info("Vector store cleared from memory")

        
        store_path = Path(self.store_path)
        if store_path.exists():
            import shutil

            if self.store_type == "faiss":
                faiss_path = store_path / "faiss_index"
                if faiss_path.exists():
                    shutil.rmtree(faiss_path)
            elif self.store_type == "chroma":
                chroma_path = store_path / "chroma"
                if chroma_path.exists():
                    shutil.rmtree(chroma_path)

        logger.info("Vector store files cleared from disk")



vector_store_manager = VectorStoreManager()
