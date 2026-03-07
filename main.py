"""
Enterprise Knowledge Assistant — FastAPI Backend Server

Main application entry point providing REST API endpoints:
- POST /upload  — Ingest documents into the knowledge base
- POST /ask     — Ask questions via RAG pipeline
- GET  /health  — Health check and system status
- GET  /stats   — Vector store statistics
- DELETE /session/{id} — Clear conversation history
"""

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import settings
from document_loader import DocumentLoader, validate_file
from rag_pipeline import rag_pipeline
from vector_store import vector_store_manager



logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)



app = FastAPI(
    title="Enterprise Knowledge Assistant API",
    description="RAG-based conversational AI for internal company knowledge",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS + ["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


document_loader = DocumentLoader()




class AskRequest(BaseModel):
    """Request model for the /ask endpoint."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to ask the knowledge assistant",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity. Auto-generated if not provided.",
    )


class AskResponse(BaseModel):
    """Response model for the /ask endpoint."""

    answer: str
    sources: List[dict]
    session_id: str
    has_context: bool
    retrieved_count: int


class UploadResponse(BaseModel):
    """Response model for the /upload endpoint."""

    success: bool
    file_name: str
    chunks_created: int
    total_chunks: int
    message: str


class HealthResponse(BaseModel):
    """Response model for the /health endpoint."""

    status: str
    version: str
    vector_store: dict
    gemini_configured: bool





@app.on_event("startup")
async def startup_event():
    """Run on application startup — validate config and log status."""
    logger.info("=" * 60)
    logger.info("Enterprise Knowledge Assistant API starting...")

    try:
        settings.validate()
        logger.info("✓ Configuration validated")
    except ValueError as e:
        logger.error(f"✗ Configuration error: {e}")
        raise

    stats = vector_store_manager.get_store_stats()
    logger.info(f"✓ Vector store: {stats}")
    logger.info("=" * 60)





@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Returns system status, vector store stats, and configuration status.
    """
    stats = vector_store_manager.get_store_stats()

    return {
        "status": "healthy",
        "version": "1.0.0",
        "vector_store": stats,
        "gemini_configured": bool(settings.GEMINI_API_KEY),
    }


@app.get("/stats", tags=["System"])
async def get_stats():
    """Get detailed vector store statistics."""
    stats = vector_store_manager.get_store_stats()
    return JSONResponse(content={"vector_store": stats})


@app.post("/upload", response_model=UploadResponse, tags=["Documents"])
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and ingest a document into the knowledge base.

    Accepts: PDF, DOCX, TXT, MD files up to 50MB.

    The document is:
    1. Saved to the uploads directory
    2. Loaded and split into chunks
    3. Embedded and stored in the vector database
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")


    file_ext = Path(file.filename).suffix.lower()
    supported = [".pdf", ".docx", ".doc", ".txt", ".md"]
    if file_ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Supported: {', '.join(supported)}",
        )

    
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        logger.info(f"File saved: {safe_filename} ({len(content) / 1024:.1f} KB)")

        
        validate_file(file_path)

        
        chunks, doc_metadata = document_loader.load_and_split(file_path)

        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="Document appears to be empty or could not be parsed",
            )

        
        for chunk in chunks:
            chunk.metadata["original_filename"] = file.filename
            chunk.metadata["source_file"] = file.filename

        
        stored_count = vector_store_manager.create_store(chunks)

        logger.info(
            f"Document ingested: {file.filename} → "
            f"{stored_count} chunks stored in vector DB"
        )

        return {
            "success": True,
            "file_name": file.filename,
            "chunks_created": stored_count,
            "total_chunks": stored_count,
            "message": f"Successfully processed '{file.filename}' into {stored_count} knowledge chunks",
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(e)}",
        )
    finally:
        
        if os.path.exists(file_path):
            os.remove(file_path)


@app.post("/ask", response_model=AskResponse, tags=["Chat"])
async def ask_question(request: AskRequest):
    """
    Ask a question to the knowledge assistant.

    The RAG pipeline:
    1. Embeds your question
    2. Searches the vector database for relevant content
    3. Retrieves top-K matching document chunks
    4. Passes context + history to Gemini for answer generation
    5. Returns answer with source citations
    """
    
    session_id = request.session_id or str(uuid.uuid4())


    stats = vector_store_manager.get_store_stats()
    if not stats.get("is_initialized"):
        return {
            "answer": (
                "The knowledge base is currently empty. Please upload some documents "
                "first using the document upload feature, then I can answer your questions "
                "based on your company's internal knowledge."
            ),
            "sources": [],
            "session_id": session_id,
            "has_context": False,
            "retrieved_count": 0,
        }

    try:
        result = rag_pipeline.ask(
            question=request.question,
            session_id=session_id,
        )
        return result

    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing question: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing your question: {str(e)}",
        )


@app.get("/session/{session_id}/history", tags=["Chat"])
async def get_session_history(session_id: str):
    """Get conversation history for a session."""
    history = rag_pipeline.get_session_history(session_id)
    return {"session_id": session_id, "history": history, "turn_count": len(history) // 2}


@app.delete("/session/{session_id}", tags=["Chat"])
async def clear_session(session_id: str):
    """Clear conversation history for a session."""
    rag_pipeline.clear_session(session_id)
    return {"message": f"Session '{session_id}' cleared successfully"}


@app.delete("/knowledge-base", tags=["Documents"])
async def clear_knowledge_base():
    """
    Clear all documents from the knowledge base.
    WARNING: This removes all indexed documents and cannot be undone.
    """
    vector_store_manager.clear_store()
    return {"message": "Knowledge base cleared successfully"}




if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
