"""
RAG Pipeline module for Enterprise Knowledge Assistant.

Implements the Retrieval-Augmented Generation pipeline:
1. Embed user question
2. Semantic search in vector store
3. Retrieve top-K relevant document chunks
4. Build context-aware prompt with conversation history
5. Generate answer using Google Gemini LLM
6. Return answer with source citations
"""

import logging
from typing import Dict, List, Optional, Tuple

from langchain.schema import Document
from langchain_google_genai import ChatGoogleGenerativeAI

from config import settings
from vector_store import vector_store_manager

logger = logging.getLogger(__name__)


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Enterprise Knowledge Assistant for a company's internal knowledge base.
Your role is to help employees find accurate information from company documents including:
- HR policies and procedures
- Technical documentation  
- Training manuals
- Company guidelines
- Product documentation
- Internal knowledge bases

INSTRUCTIONS:
1. Answer questions ONLY based on the provided document context
2. If the context doesn't contain enough information, clearly state that
3. Always cite the source documents you used in your answer
4. Be concise, professional, and helpful
5. For multi-part questions, address each part systematically
6. If asked about something outside the provided context, say so honestly
7. Use bullet points and headers to structure complex answers

IMPORTANT: Never make up information. Only use what's in the provided context."""


# ─── Conversation Memory ───────────────────────────────────────────────────────

class ConversationMemory:
    """
    Manages conversation history for multi-turn conversations.
    Keeps a rolling window of the last N conversation turns.
    """

    def __init__(self, max_turns: int = settings.MAX_HISTORY_TURNS):
        self.max_turns = max_turns
        self.history: List[Dict[str, str]] = []

    def add_turn(self, user_message: str, assistant_message: str):
        """Add a conversation turn to history."""
        self.history.append({
            "role": "user",
            "content": user_message
        })
        self.history.append({
            "role": "assistant",
            "content": assistant_message
        })

        
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-(self.max_turns * 2):]

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history."""
        return self.history.copy()

    def clear(self):
        """Clear conversation history."""
        self.history = []

    def format_for_prompt(self) -> str:
        """Format history as a readable string for inclusion in prompts."""
        if not self.history:
            return ""

        formatted = "PREVIOUS CONVERSATION:\n"
        for msg in self.history:
            role = "User" if msg["role"] == "user" else "Assistant"
            formatted += f"{role}: {msg['content']}\n\n"
        return formatted




class RAGPipeline:
    """
    Complete RAG pipeline that retrieves relevant documents and generates
    contextually-aware answers using Google Gemini.
    """

    def __init__(self):
        """Initialize RAG pipeline with Gemini LLM and conversation memories."""
        self.llm = self._initialize_llm()
        
        self.sessions: Dict[str, ConversationMemory] = {}

        logger.info(
            f"RAG Pipeline initialized with model: {settings.GEMINI_MODEL}"
        )

    def _initialize_llm(self) -> ChatGoogleGenerativeAI:
        """Initialize Google Gemini LLM."""
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=settings.TEMPERATURE,
            max_output_tokens=settings.MAX_OUTPUT_TOKENS,
        )

    def get_or_create_session(self, session_id: str) -> ConversationMemory:
        """Get existing session memory or create a new one."""
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationMemory()
            logger.info(f"Created new conversation session: {session_id}")
        return self.sessions[session_id]

    def clear_session(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self.sessions:
            self.sessions[session_id].clear()
            logger.info(f"Cleared session: {session_id}")

    def _retrieve_relevant_documents(
        self, query: str
    ) -> List[Tuple[Document, float]]:
        """
        Retrieve most relevant document chunks for the query.

        Args:
            query: User's question

        Returns:
            List of (Document, relevance_score) tuples
        """
        results = vector_store_manager.similarity_search(
            query=query,
            k=settings.TOP_K_RESULTS,
        )
        return results

    def _build_context(
        self, retrieved_docs: List[Tuple[Document, float]]
    ) -> Tuple[str, List[Dict]]:
        """
        Build context string from retrieved documents and collect source info.

        Args:
            retrieved_docs: List of (Document, score) tuples

        Returns:
            Tuple of (context_string, sources_list)
        """
        if not retrieved_docs:
            return "", []

        context_parts = []
        sources = []

        for i, (doc, score) in enumerate(retrieved_docs):
            # Extract metadata
            source_file = doc.metadata.get("source_file", "Unknown Document")
            page = doc.metadata.get("page", None)
            chunk_idx = doc.metadata.get("chunk_index", i)

            
            snippet = f"[Document {i+1}: {source_file}"
            if page is not None:
                snippet += f", Page {page + 1}"
            snippet += f"]\n{doc.page_content}\n"
            context_parts.append(snippet)

            
            source_info = {
                "document": source_file,
                "relevance_score": round(score, 3),
                "excerpt": doc.page_content[:300].strip() + "..."
                if len(doc.page_content) > 300
                else doc.page_content.strip(),
            }
            if page is not None:
                source_info["page"] = page + 1

            
            if not any(s["document"] == source_file for s in sources):
                sources.append(source_info)

        context = "\n---\n".join(context_parts)

        
        if len(context) > settings.MAX_CONTEXT_LENGTH:
            context = context[: settings.MAX_CONTEXT_LENGTH] + "\n[Context truncated...]"

        return context, sources

    def _build_prompt(
        self,
        query: str,
        context: str,
        conversation_history: str,
    ) -> str:
        """
        Build the complete prompt for Gemini including system instructions,
        conversation history, retrieved context, and user question.

        Args:
            query: Current user question
            context: Retrieved document context
            conversation_history: Formatted previous conversation

        Returns:
            Complete prompt string
        """
        prompt_parts = [SYSTEM_PROMPT, "\n\n"]

        
        if conversation_history:
            prompt_parts.append(conversation_history)
            prompt_parts.append("\n")

    
        if context:
            prompt_parts.append("RELEVANT KNOWLEDGE BASE CONTEXT:\n")
            prompt_parts.append(context)
            prompt_parts.append("\n\n")
        else:
            prompt_parts.append(
                "NOTE: No relevant documents found in the knowledge base "
                "for this question.\n\n"
            )

        
        prompt_parts.append(f"CURRENT QUESTION: {query}\n\n")
        prompt_parts.append(
            "Please provide a helpful, accurate answer based on the context above. "
            "Cite the source documents where relevant."
        )

        return "".join(prompt_parts)

    def ask(
        self,
        question: str,
        session_id: str = "default",
    ) -> Dict:
        """
        Process a user question through the complete RAG pipeline.

        Args:
            question: User's natural language question
            session_id: Session identifier for conversation memory

        Returns:
            Dict containing:
                - answer: Generated response text
                - sources: List of source documents used
                - session_id: Session identifier
                - has_context: Whether relevant docs were found
        """
        logger.info(
            f"Processing question for session '{session_id}': "
            f"'{question[:80]}...'" if len(question) > 80 else
            f"Processing question for session '{session_id}': '{question}'"
        )

        
        memory = self.get_or_create_session(session_id)

        
        retrieved_docs = self._retrieve_relevant_documents(question)
        has_context = len(retrieved_docs) > 0

        
        context, sources = self._build_context(retrieved_docs)

        
        conversation_history = memory.format_for_prompt()

        
        prompt = self._build_prompt(question, context, conversation_history)

        
        try:
            response = self.llm.invoke(prompt)
            answer = response.content

        except Exception as e:
            logger.error(f"Error generating response from Gemini: {str(e)}")
            raise RuntimeError(f"Failed to generate response: {str(e)}")

        
        memory.add_turn(question, answer)

        logger.info(
            f"Response generated for session '{session_id}': "
            f"{len(answer)} chars, {len(sources)} sources cited"
        )

        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_id,
            "has_context": has_context,
            "retrieved_count": len(retrieved_docs),
        }

    def get_session_history(self, session_id: str) -> List[Dict]:
        """Get conversation history for a session."""
        memory = self.get_or_create_session(session_id)
        return memory.get_history()



rag_pipeline = RAGPipeline()
