# 07. Operations, Setup & Developer Onboarding

## 1. Prerequisites & Environment

### Hardware Requirements:
- **RAM**: 16 GB minimum (32 GB recommended when running local 12B models)
- **VRAM / GPU**: 8 GB+ VRAM recommended for GPU-accelerated embedding inference via LM Studio (CPU inference is also supported)
- **Storage**: ~5 GB free disk space for SQLite database, XML archives, and FAISS indices

### Software Requirements:
- **Python**: 3.10, 3.11, or 3.12
- **Node.js**: v18+ and npm
- **LM Studio**: v0.3+ running local inference server on port `1234`

---

## 2. LM Studio Configuration

1. Launch **LM Studio**.
2. Download and load the official embedding model:
   - **Model Identifier**: `text-embedding-kalm-embedding-gemma3-12b-2511`
   - **Model Architecture**: Gemma-3 12B (3,840 hidden dimensions)
3. Under the **Local Server** tab in LM Studio:
   - Port: `1234`
   - CORS: Enabled (`*`)
   - Start the server (`http://localhost:1234/v1`)
4. Verify with PowerShell:
   ```powershell
   curl http://localhost:1234/v1/models
   ```

---

## 3. Installation Steps

### Step 1: Clone and Install Python Dependencies
```powershell
git clone <repository_url>
cd Regs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 2: Install Frontend Dependencies
```powershell
cd frontend
npm install
cd ..
```

---

## 4. Running the Application

A convenience orchestrator script (`start.py`) is provided at the repository root.

```powershell
python start.py
```

This launches:
1. **FastAPI Backend**: `http://localhost:8000` (API docs at `http://localhost:8000/docs`)
2. **Vite Frontend Server**: `http://localhost:5173`

---

## 5. Rebuilding Data & Embeddings

If you add new XML packages to `ingestion/data/regulation_xml/`:

### 1. Incremental Ingestion:
```powershell
python -m ingestion.pipelines.ingest_formex "ingestion/data/regulation_xml"
```

### 2. Standalone Vector Embedding & Stakeholder Anchor Refresh:
```powershell
python -m ingestion.retrieval.embed_chunks
```

### 3. Full Database & Vector Reset (Warning: takes ~8 minutes):
```powershell
python -m ingestion.pipelines.ingest_formex "ingestion/data/regulation_xml" --reset --defrag
```

---

## 6. Project Directory Layout

```text
Regs/
├── api/                             # FastAPI application & routers
│   ├── main.py                      # Core search & LLM endpoints
│   ├── regulations.py               # Catalog, batch, qualifiers, workspace-fts
│   ├── research.py                  # Deep research engine
│   └── utils.py                     # Cosine similarity & logging
├── frontend/                        # React + TypeScript + Vite SPA
│   ├── src/
│   │   ├── components/              # Workspace, DocViewerModal, AskAssistant
│   │   ├── services/apiClient.ts    # Typed API client with IndexedDB cache
│   │   └── types.ts                 # Full TypeScript schemas
├── ingestion/
│   ├── core/                        # Configuration & Pydantic data models
│   │   ├── config.py                # LM Studio URL, 3840D dimensions
│   │   ├── formex_package.py        # Package classifier & streaming generator
│   │   └── models.py                # LegalFragment, EmbeddingRecord
│   ├── parsers/                     # Euroform & Formex XML parsers
│   ├── pipelines/                   # Chunking & Formex ingestion pipeline
│   │   ├── chunking_pipeline.py     # SQLite chunk storage & qualifiers table
│   │   └── ingest_formex.py         # End-to-end streaming package ingest
│   └── retrieval/                   # FAISS vector store & FTS5 search
│       ├── embed_chunks.py          # ACT/CHUNK embedding & Stakeholder scoring
│       ├── faiss_index.py           # Multi-partition FAISS IndexFlatIP
│       ├── hybrid_search.py         # Reciprocal Rank Fusion (RRF)
│       └── search_chunks.py         # Hierarchical search & HyDE
├── Project_specification/           # Complete technical documentation suite
└── start.py                         # Unified launch script
```
