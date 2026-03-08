#  Enterprise Knowledge Assistant

A production-ready **RAG (Retrieval-Augmented Generation)** system that lets employees ask natural language questions about internal company documents — policies, manuals, procedures, and technical documentation.

Built with **Python + FastAPI + LangChain + Google Gemini + FAISS** and a modern dark-mode chat UI.

---

##  Architecture

```
User Question
      │
      ▼
 [Frontend UI] ──── fetch() ────► [FastAPI Backend]
                                        │
                              ┌─────────┴──────────┐
                              ▼                    ▼
                    [Gemini Embeddings]    [RAG Pipeline]
                              │                    │
                              ▼                    ▼
                       [FAISS Vector DB] ◄── [Similarity Search]
                                                   │
                                          Top-K Relevant Chunks
                                                   │
                                                   ▼
                                         [Gemini 1.5 Flash LLM]
                                          Context + History +
                                             Question
                                                   │
                                                   ▼
                                          Generated Answer +
                                          Source Citations
```

---

##  Project Structure

```
enterprise-knowledge-assistant/
│
├── backend/
│   ├── main.py              # FastAPI server + REST endpoints
│   ├── rag_pipeline.py      # RAG logic + Gemini + conversation memory
│   ├── document_loader.py   # PDF/DOCX/TXT loading + chunking
│   ├── vector_store.py      # FAISS/Chroma vector DB management
│   ├── config.py            # Settings from .env
│   └── requirements.txt     # Python dependencies
│
├── frontend/
│   ├── index.html           # Main UI
│   ├── styles.css           # Dark enterprise theme
│   └── app.js               # Chat logic, upload, sessions
│
├── data/
│   ├── sample_hr_policy.txt     # Example HR policy document
│   └── sample_tech_docs.txt     # Example technical documentation
│
├── .env.example             # Environment variables template
├── run.sh                   # One-command startup script
└── README.md                # This file
```

---

##  Quick Start

### Prerequisites

- Python 3.9 or higher
- Google Gemini API key ([Get one free](https://aistudio.google.com/app/apikey))

### Step 1: Clone & Setup

```bash
# Clone the repository
git clone https://github.com/Barr-ack/AI-Knowledge-OS.git
cd enterprise-knowledge-assistant

# environment template
create a  .env file
```

### Step 2: Configure API Key

Open `.env` and set your Gemini API key:

```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### Step 3: Install Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 4: Start the Backend

```bash
# From the backend/ directory
python main.py
```

The API will be available at: **http://localhost:8000**
API documentation: **http://localhost:8000/docs**

### Step 5: Open the Frontend

Open `frontend/index.html` in your browser directly, OR serve it:

```bash
# From the project root
python -m http.server 5500 --directory frontend
# Then open: http://localhost:5500
```

---

##  Usage

### Uploading Documents

1. Click **"Drop files here"** in the sidebar, or drag and drop files
2. Supported formats: **PDF, DOCX, DOC, TXT, MD**
3. Documents are automatically chunked, embedded, and indexed
4. You'll see a ✓ confirmation when indexing is complete

### Asking Questions

1. Type your question in the chat input
2. Press **Enter** or click the send button
3. The system will:
   - Search the knowledge base for relevant content
   - Generate a contextual answer using Gemini
   - Show source citations with relevance scores
4. Conversations maintain context — ask follow-up questions naturally

### Example Questions (with sample docs)

- *"What is the annual leave policy?"*
- *"How many sick days do I get per year?"*
- *"Explain the code review process"*
- *"What are the API versioning standards?"*
- *"How long is the onboarding probation period?"*
- *"What's the incident response time for P0 issues?"*

---

##  API Reference

### POST `/upload`
Upload a document to the knowledge base.

```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@document.pdf"
```

**Response:**
```json
{
  "success": true,
  "file_name": "document.pdf",
  "chunks_created": 42,
  "message": "Successfully processed 'document.pdf' into 42 knowledge chunks"
}
```

### POST `/ask`
Ask a question.

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the leave policy?", "session_id": "my-session-123"}'
```

**Response:**
```json
{
  "answer": "According to the HR policy...",
  "sources": [
    {
      "document": "hr_policy.pdf",
      "relevance_score": 0.92,
      "page": 3,
      "excerpt": "..."
    }
  ],
  "session_id": "my-session-123",
  "has_context": true,
  "retrieved_count": 5
}
```

### GET `/health`
Check system status.

```bash
curl "http://localhost:8000/health"
```

### DELETE `/session/{session_id}`
Clear conversation history for a session.

### DELETE `/knowledge-base`
Clear all indexed documents.

---

##  Configuration

All settings are in `.env`. Key options:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for generation |
| `VECTOR_STORE_TYPE` | `faiss` | `faiss` or `chroma` |
| `CHUNK_SIZE` | `1000` | Characters per document chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `TOP_K_RESULTS` | `5` | Documents retrieved per query |
| `TEMPERATURE` | `0.3` | LLM temperature (0=factual, 1=creative) |
| `MAX_HISTORY_TURNS` | `10` | Conversation turns to remember |

---

##  Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | Google Gemini 2.5 Flash |
| **Embeddings** | Google Gemini `embedding-001` |
| **Vector DB** | FAISS (default) / Chroma |
| **RAG Framework** | LangChain |
| **Backend** | FastAPI + Python 3.9+ |
| **Document Parsing** | PyPDF, python-docx, Docx2txt |
| **Frontend** | Vanilla HTML/CSS/JavaScript |
| **Fonts** | Syne + DM Sans |

---

##  Security Notes

- Store `GEMINI_API_KEY` only in `.env`, never in code
- Add `.env` to `.gitignore` before committing
- For production, restrict `ALLOWED_ORIGINS` to your domain
- Consider adding authentication middleware for production deployments

---

##  License

MIT License — Free to use and modify for personal and commercial projects.
