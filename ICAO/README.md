# ICAO Document Intelligence & Hybrid Search Engine

A high-performance Python library, CLI, and REST API to **parse**, **filter**, **chunk**, **embed**, and **search** official International Civil Aviation Organization (ICAO) documentation using modern Information Retrieval (IR) and Retrieval-Augmented Generation (RAG) best practices.

Indexed core documents in this repository (**7,572 chunks across 12 documents**):
- **ICAO Doc 9562**: *Airport Economics Manual*
- **ICAO Doc 9750**: *Global Air Navigation Plan for CNS/ATM Systems*
- **ICAO Annex 2**: *Rules of the Air*
- **ICAO Annex 12**: *Search and Rescue*
- **ICAO Annex 13**: *Aircraft Accident and Incident Investigation*
- **ICAO Annex 17**: *Security — Safeguarding International Civil Aviation*
- **ICAO Annex 18**: *The Safe Transport of Dangerous Goods by Air*
- **ICAO Doc 4444**: *PANS-ATM: Air Traffic Management*
- **ICAO Doc 9432**: *Manual of Radiotelephony*
- **ICAO Doc 9574**: *Implementation of Vertical Separation Minimum (RVSM)*
- **ICAO Doc 9613**: *Performance-based Navigation (PBN) Manual*
- **ICAO Doc 9859**: *Safety Management Manual (SMM)*

*Additional documents can be downloaded or uploaded via [`scripts/download_icao.py`](file:///c:/Projects/ICAO/scripts/download_icao.py) or the UI Import Manager.*

---

## Key Features & Architecture

```
                 [ ICAO PDF Documents ]
                           │
                           ▼
                  [ 1. PDF Parser ]
          PyMuPDF block layout extraction &
          running header/footer identification
                           │
                           ▼
                 [ 2. Filter Engine ]
         Boilerplate cleaning, blank page pruning,
          noise suppression & search constraints
                           │
                           ▼
               [ 3. Hierarchical Chunker ]
         Paragraph/sentence semantic chunking with
        contextual metadata prefixes ([Doc | Chap | Page])
                           │
                           ▼
                [ 4. Embedding Engine ]
          all-MiniLM-L6-v2 (384d normalized) with
          extensible fallback & batch processing
                           │
                           ▼
                [ 5. Persistent Index ]
      NumPy Dense Vector Store  +  BM25 Inverted Index
                           │
                           ▼
             [ 6. Hybrid Retrieval & RRF ]
       Reciprocal Rank Fusion + Dynamic Score Weighting
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
 [ FastAPI REST API & Web UI ]           [ CLI Tool ]
```

### 1. Document-Aware Parsing ([`PDFParser`](file:///c:/Projects/ICAO/icao_rag/parser.py))
- Uses PyMuPDF (`fitz`) block and layout extraction.
- Isolates and separates running chapter headers, document titles, and page numbers from body text.
- Reconstructs hyphenated words broken across line wraps (e.g., `implemen-\ntation` → `implementation`).
- Classifies pages into `cover`, `front_matter`, `content`, and `blank`.

### 2. Intelligent Filtering ([`FilterEngine`](file:///c:/Projects/ICAO/icao_rag/filter.py))
- Prunes blank back-pages and boilerplate front-matter.
- Strips dot-leader artifacts and lone Roman numerals.
- Validates chunk text quality (character length thresholds, alphabetic word density, and noise ratios).
- Supports runtime metadata filtering by `doc_id`, page range (`min_page`, `max_page`), and `chapter_keyword`.

### 3. Hierarchical Contextual Chunking ([`HierarchicalChunker`](file:///c:/Projects/ICAO/icao_rag/chunker.py))
- Paragraph-aware sliding window splitting with sentence-level boundaries for oversized paragraphs.
- **Context Prefix Injection**: Every chunk embedding prepends document and section hierarchy:
  ```
  [Document: ICAO Doc 9562: Airport Economics Manual | Chapter: Chapter 4. The process of setting airport charges | Page: 82]
  ```
  This prevents contextual drift during vector search and empowers BM25 keyword matching for chapter-level queries.

### 4. Dense Embeddings ([`SentenceTransformerEmbedder`](file:///c:/Projects/ICAO/icao_rag/embedder.py))
- Powered by `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions, L2-normalized).
- In-memory NumPy cosine similarity matching via matrix dot-product.
- Fallback embedder using scikit-learn `HashingVectorizer` for zero-model environments.

### 5. Hybrid Search with RRF Fusion ([`HybridSearchEngine`](file:///c:/Projects/ICAO/icao_rag/retriever.py))
- Fuses **Dense Semantic Vectors** (deep conceptual meaning) with **Sparse BM25** (exact acronyms, Article numbers, and regulation codes).
- Uses Reciprocal Rank Fusion (RRF, $k=60$) alongside normalized linear combination:
  $$\text{RRF Score}(d) = \frac{w_{\text{dense}}}{k + \text{rank}_{\text{dense}}(d)} + \frac{w_{\text{bm25}}}{k + \text{rank}_{\text{bm25}}(d)}$$
- Automatically extracts the most relevant snippet with matched query term highlighting (`<mark>`).

---

## Installation & Setup

Ensure Python 3.9+ is installed.

```bash
# Clone or navigate to the project directory
cd c:\Projects\ICAO

# Install package dependencies
pip install -r requirements.txt

# Or install as an editable package
pip install -e .
```

---

## Command-Line Interface (CLI)

The CLI tool allows you to index, query, inspect stats, or launch the API server directly from your terminal:

### 1. Search the Documents
```bash
python -m icao_rag.cli search "airport charging principles Article 15" --top-k 3
```

**Filter by document or chapter:**
```bash
# Only search Doc 9750 (CNS/ATM)
python -m icao_rag.cli search "GNSS satellite navigation" --doc-id doc_9750 --top-k 5

# Only search Doc 9562 within Chapter 4
python -m icao_rag.cli search "cost recovery and concession fees" --chapter "Chapter 4"
```

**Adjust hybrid retrieval balance:**
```bash
# 80% Dense semantic vectors, 20% BM25 keyword matching
python -m icao_rag.cli search "single-till vs dual-till approaches" --dense-weight 0.8 --bm25-weight 0.2
```

### 2. View Corpus Statistics
```bash
python -m icao_rag.cli stats
```

### 3. Re-index Documents
```bash
python -m icao_rag.cli index --dir . --force
```

### 4. Check for New or Updated Import PDFs
```bash
python -m icao_rag.cli check-imports
```

### 5. Synchronize & Re-parse Import PDFs
```bash
python -m icao_rag.cli sync
```

### 6. Start the API Server & Interactive Web UI
```bash
python -m icao_rag.cli serve --port 8000
```

---

## PDF Import & Change Detection (`import_pdfs/`)

The system includes a dedicated drop folder: [`import_pdfs/`](file:///c:/Projects/ICAO/import_pdfs).

1. **Automatic Detection**:
   - Any PDF copied into `import_pdfs/` or updated in-place is automatically compared against the active index cache using file metadata (filename, modification timestamp, and byte size).
   - The engine flags documents as:
     - `NEW`: PDF not yet present in the search index.
     - `UPDATED`: PDF exists in the index but has been modified since it was parsed.
     - `UP_TO_DATE`: PDF is fully parsed and in sync with the index.
2. **Proactive Frontend Notifications**:
   - The frontend automatically polls `/api/import/status` every 15 seconds (and whenever the browser tab regains focus).
   - If new or modified PDFs are detected, an animated glowing amber banner appears across the top of the interface:
     > *"⚡ 1 document update(s) available for re-parsing. Click 'Review & Sync' to update the search index."*
   - A pulsing notification dot appears on the **Import PDFs** navigation button.
3. **In-Browser Upload & Sync**:
   - Users can drag & drop PDFs directly into the Import Manager modal, upload them into `import_pdfs/`, and trigger re-parsing with a single click without restarting the server.
   - Clean re-indexing: Previous chunk vectors and BM25 postings for updated documents are safely purged before new chunks are ingested.

---

---

## Python Library API Usage

You can import and use the components directly in any Python script or application:

```python
from icao_rag import ICAOPipeline, SearchFilter

# 1. Initialize the master pipeline
# (Automatically loads pre-computed index cache from icao_rag/storage/index_cache)
pipeline = ICAOPipeline()

# 2. Execute a hybrid search query
response = pipeline.search(
    query="cost allocation principles for airport charges",
    top_k=5,
    dense_weight=0.65,
    bm25_weight=0.35,
    filter_criteria=SearchFilter(
        doc_id="doc_9562",      # Limit to Airport Economics Manual
        min_page=20,            # Page range filter
        max_page=120
    )
)

print(f"Retrieved {response.total_results} matches in {response.time_taken_ms}ms:")
for hit in response.results:
    print(f"\n[{hit.score:.3f}] {hit.doc_title} (Page {hit.page_number})")
    print(f"Chapter: {hit.chapter}")
    print(f"Snippet: {hit.snippet}")
```

### Modular Component Usage

```python
from icao_rag import PDFParser, FilterEngine, HierarchicalChunker, SentenceTransformerEmbedder

# Parse document
parser = PDFParser()
metadata, pages = parser.parse_document("9562_cons_en.pdf")

# Filter content pages
filter_engine = FilterEngine()
content_pages = filter_engine.filter_pages(pages)

# Chunk pages into hierarchical blocks
chunker = HierarchicalChunker(filter_engine=filter_engine)
chunks = chunker.chunk_document(metadata, content_pages)

# Embed chunk texts
embedder = SentenceTransformerEmbedder()
embeddings = embedder.embed_texts([c.embedding_text for c in chunks])

print(f"Generated {len(chunks)} chunks with shape: {embeddings.shape}")
```

---

## REST API Specification

Run the server with `python -m icao_rag.cli serve --port 8000`.

- **Web Dashboard**: `http://localhost:8000/`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc API Reference**: `http://localhost:8000/redoc`

### Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Health check, version, and embedder status |
| `GET` | `/api/stats` | Indexed documents, total chunks, content pages |
| `GET` | `/api/documents` | List loaded documents with page counts |
| `POST` | `/api/search` | Execute hybrid search with filters and weights |
| `GET` | `/api/chunk/{chunk_id}` | Fetch full chunk context, prefix, and raw text |
| `POST` | `/api/index` | Trigger parsing, filtering, and embedding |
| `GET` | `/api/import/status` | Detect new or modified PDFs in `import_pdfs/` |
| `POST` | `/api/import/sync` | Parse and re-index pending import PDFs |
| `POST` | `/api/import/upload` | Upload PDF file directly into `import_pdfs/` |

#### Sample Search Request (`POST /api/search`):
```json
{
  "query": "CNS/ATM global air navigation plan transition",
  "top_k": 3,
  "dense_weight": 0.65,
  "bm25_weight": 0.35,
  "filter": {
    "doc_id": "doc_9750",
    "min_page": 20,
    "max_page": 100
  }
}
```

#### Sample Response:
```json
{
  "query": "CNS/ATM global air navigation plan transition",
  "total_results": 3,
  "results": [
    {
      "chunk_id": "doc_9750_p57_c532",
      "doc_id": "doc_9750",
      "doc_title": "ICAO Doc 9750: Global Air Navigation Plan for CNS/ATM Systems",
      "filename": "9750_2ed_en.pdf",
      "page_number": 57,
      "chapter": "Part I.",
      "score": 0.9513,
      "dense_score": 0.7295,
      "bm25_score": 9.5252,
      "snippet": "4.59 The transition from today's ATM structure to one of collaborative air traffic management...",
      "text": "..."
    }
  ],
  "retrieval_mode": "hybrid (dense_w=0.65, bm25_w=0.35)",
  "time_taken_ms": 37.6
}
```

---

## Interactive Web UI

The built-in web dashboard provides:
1. **Instant Search**: Search with live autocomplete and query suggestions.
2. **Hybrid Weights Slider**: Adjust the balance between Dense Semantic Vectors and Sparse BM25 Keyword Matching in real time.
3. **Faceted Filtering**: Filter by target document, chapter keyword, and page range.
4. **Context Inspector**: Click "Inspect Full Context" on any result card to view the complete passage, context prefix, and copy a formatted citation to your clipboard.

---

## Automated Test Suite

Run the full pytest suite:

```bash
python -m pytest tests/ -v
```

Test coverage includes:
- `test_parser.py`: PDF layout parsing, running header detection, and page categorization.
- `test_filter.py`: Page-level filtering, chunk cleaning, noise rejection, and filter criteria evaluation.
- `test_chunker.py`: Semantic sliding-window chunking and context prefix generation.
- `test_embedder.py`: Dense SentenceTransformer vectors and fallback HashingVectorizer.
- `test_retriever.py`: BM25 exact matching, cosine similarity, and hybrid RRF retrieval.
- `test_api.py`: FastAPI TestClient integration tests across endpoints.
