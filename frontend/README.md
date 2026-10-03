# AeroLex — Aviation Regulation Assistant (Frontend)

A modern, high-performance web interface for querying local and cloud LLMs and semantic search knowledge bases over **Global Aviation Regulations** (EASA Easy Access Rules, EU Formex standards, FAA Title 14 CFR regulations, and custom user-authored flight manuals), featuring deep research workflows, persistent query memory, and structured data extraction.

---

## Features

- **Multi-Origin Hybrid Search (`GET /search`, `GET /search/keyword`)**:
  - High-speed SQLite FTS5 BM25 search with Porter stemming and FAISS dense vector retrieval.
  - Multi-origin filtering: `ALL`, `EASA`, `EU`, `FAA` (Title 14 CFR), and `MANUAL` (custom manuals/SOPs).
  - Tailored for aviation acronyms (e.g., `ATSEP`, `AMC-20`, `FTL`, `SMS`, `FAR`), part numbers, and clause codes (`CAT.OP.MPA`, `§ 25.1309`, `§ 121.311`).
  - Optional local LLM query expansion (`use_llm=true`) generating synonyms and domain terms.
- **Context Expansion & Implications ("Get Context")**:
  - Fetch immediate preceding and subsequent provisions (window ±2) from the same regulation.
  - AI-powered synthesis explains legal prerequisites, scope boundaries, and operational compliance implications.
- **Document-Scoped Search ("Focus Document")**:
  - Click to isolate any regulation and re-query exclusively within that specific act.
- **Autonomous Deep Research Studio (`/research/*`)**:
  - Multi-turn recursive exploration with depth levels 1 to 3.
  - Scientific Adversarial Falsification Gate rejecting out-of-scope provisions.
  - Surrounding sequence fact extraction incorporating preceding and subsequent provisions into LLM reasoning.
  - Dual-Tab Chunk Inspector Modal (Focal Provision vs. Surrounding Sequence & AI Implications).
  - Scientific Evidence & Negation Audit Ledger with one-click surrounding context access.
- **Dedicated Multi-Regulation Workspace (`RegulationsWorkspace.tsx`)**:
  - Title-level catalog supporting 1,400+ EU acts, EASA Easy Access Rules, and FAA 14 CFR regulations.
  - Multi-regulation selection and cross-document overlap analysis with multi-column comparison matrix.
  - Requirement Lens (normative modal verb analysis: SHALL, MUST, SHOULD, MAY).
  - Word-by-word diff drawer and compliance working dossier.
- **Manual Document Builder (`DocumentBuilder.tsx`)**:
  - Interactive authoring studio for custom company manuals, SOPs, and flight ops procedures.
  - Real-time hierarchy simulation and automated regulatory chunking matching EASA/FAA standards.
  - Instant SQLite FTS5 indexing and catalog cache synchronization.
- **Local LLM Regulatory Assistant (`POST /llm/ask`)**:
  - Context-aware natural language Q&A with targeted chunks or automated retrieval.
- **Settings & Connection Manager**:
  - Configure local LM Studio (`/v1`) or Google Gemini Cloud API keys and models.
  - Configurable LM Studio timeout settings with safe fallback against GPU cold-starts.

---

## Prerequisites

Before running the application locally, make sure you have:

- **Node.js**: `v18.0.0` or higher (Node 20+ recommended)
- **Package Manager**: `npm` (comes with Node), `pnpm`, or `yarn`
- **FastAPI Backend**: Python 3.9+ with your existing regulation assistant API running locally.

---

## 1. Frontend Local Installation

### Step 1: Clone or navigate to the project directory

```bash
cd /path/to/aerolex-eu
```

### Step 2: Install dependencies

```bash
npm install
```

### Step 3: Configure environment variables (optional)

Copy `.env.example` to `.env` if you wish to configure environment defaults:

```bash
cp .env.example .env
```

### Step 4: Start the development server

```bash
npm run dev
```

The frontend will start on **`http://localhost:3000`** (or the port specified in terminal output). Open this URL in your web browser.

---

## 2. Setting Up Your Local FastAPI Backend

The frontend communicates directly with your FastAPI server endpoints:
- `GET /search?query={query}&top_k={k}&origin={origin}` (Semantic dense vector search)
- `GET /search/keyword?query={query}&top_k={k}&origin={origin}&use_llm={use_llm}` (SQLite FTS5 BM25 keyword search)
- `GET /search/docs?query={query}&top_k={k}&origin={origin}` (Contextual search with full Markdown documents)
- `POST /llm/ask` (`{"prompt": "...", "chunk_ids": [...]}`)
- `POST /llm/extract` (`{"text": "...", "json_schema": {...}}`)

### Step 1: Enable CORS in your FastAPI app

Because the frontend runs in a browser (e.g. `http://localhost:3000`), your FastAPI server must allow Cross-Origin Resource Sharing (CORS). Add the following middleware to your FastAPI app:

> **CRITICAL**: In FastAPI / Starlette, `app.add_middleware(CORSMiddleware, ...)` must be placed **BEFORE** any `app.include_router(...)`.
> Also, if `allow_origins=["*"]`, `allow_credentials` must be set to `False` (browser CORS standard).

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Regulation Assistant API")

# Enable CORS for local web clients (MUST be added BEFORE routers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your routers AFTER middleware
# app.include_router(...)
```

---

## 3. Connecting the Frontend to Your Local API

1. Open the frontend in your browser (`http://localhost:3000`).
2. Click **Settings** in the top navigation bar.
3. You have two connection options:
   - **Option A (Zero-CORS Vite Proxy - Recommended)**: Click the **`/api` (Vite Proxy - No CORS)** button. This routes all API calls through the local Vite development server, completely bypassing browser preflight checks.
   - **Option B (Direct Connection)**: Enter `http://127.0.0.1:8000` or `http://localhost:8000`.
4. Click **Test Connection**.
   - If connected, you will see a green checkmark showing server response latency (e.g., `FastAPI online (12ms latency)`).
   - If `OPTIONS /llm/ask 405 Method Not Allowed` occurs, use **Option A** (`/api`) or verify the middleware order in `main.py`.
5. Click **Save Preferences**. All queries and searches will now hit your live local backend!

### Search Modes in the UI

In the **Search & Document Explorer** tab, you can toggle between two complementary search engines:
- **Semantic Vector Search (`GET /search`)**: Leverages dense embeddings (FAISS) to match broader concepts, questions, and descriptive language.
- **Keyword & Acronym Search (`GET /search/keyword`)**: Uses SQLite FTS5 with BM25 ranking and Porter stemming. Best for short queries, exact acronyms (e.g., `ATSEP`, `AMC-20`, `FTL`), part numbers, and clause references (`CAT.OP.MPA`).
  - **LLM Expansion Toggle**: In the **Settings Modal**, you can toggle **LLM Keyword Expansion** (`use_llm`). When enabled, your local LLM in LM Studio suggests synonyms and domain terms before querying the FTS5 index.

### Interactive Document Section Viewer & Client-Side Similarity Highlighting

When viewing documents in the **Document Viewer Modal** (from `/search/docs`), the viewer automatically parses section boundaries and provides an in-browser similarity search engine:
- **Client-Side Text Similarity Search**:
  - Instant text similarity search evaluated entirely on the client side using a multi-factor BM25/TF-IDF scoring algorithm with exact-phrase bonuses and title weighting.
  - **Dynamic Score Badges**: Displays match relevance (e.g., `85% Match`, `42% Match`) directly on each section card.
  - **Luminous Highlighting**:
    - High-relevance sections (>= 60% match) illuminate with amber borders (`border-amber-500`) and a glowing ring.
    - Moderate matches (25% - 59%) display sky-blue borders (`border-sky-500`).
    - Non-matching sections are dimmed to make matching sections stand out.
  - **In-Text Highlight**: Matched terms inside each section's Markdown body (and in Continuous View) are highlighted with amber `<mark>` tags.
  - **Match Stepper (`Prev` / `Next`)**: Smoothly scrolls and centers the viewport on matching sections one by one.
  - **Sort by Relevance**: One-click toggle to sort matching sections to the top by similarity score instead of document sequence.
  - **Sensitivity Threshold**: Quick filter chips (`10%`, `25%`, `50%`) to control minimum matching threshold.
  - **Auto-Expand Matches**: Automatically expands cards that match the similarity query.
- **Sections View (Default)**:
  - Collapsible cards for individual Subparts, Certification Specifications (CS), and Acceptable Means of Compliance (AMC).
  - Type badges (`CS`, `AMC`, `Subpart`, `Annex`).
  - Category filter chips (`All`, `CS`, `AMC`, `Heading`, etc.).
  - **Original Query Chunk Indicator**: Highlights the exact section card that produced your initial search result.
  - Per-section actions: Copy section Markdown or Ask LLM about that specific section.
  - One-click **Expand All** / **Collapse All**.
- **Continuous View**:
  - Switch anytime to traditional continuous single-document Markdown viewing with query terms highlighted throughout.

---

## 4. Available Scripts

| Command | Description |
|---|---|
| `npm run dev` | Starts Vite development server on port 3000 |
| `npm run build` | Compiles TypeScript and creates optimized production bundle in `dist/` |
| `npm run preview` | Locally serves the production build for testing |
| `npm run lint` | Runs TypeScript compiler verification (`tsc --noEmit`) |

---

## 5. Troubleshooting & Tips

- **Cannot reach endpoint / NetworkError**:
  - Confirm FastAPI is running via `curl http://localhost:8000/search?query=test&top_k=1`.
  - Check whether your firewall or antivirus is blocking port `8000`.
- **CORS Issues**:
  - Ensure `allow_origins=["*"]` is present in FastAPI before route definitions.
- **Offline / Demo Mode**:
  - If your local server is offline, toggle **Offline Fallback / Demo Mode** in Settings to test all UI components with built-in authentic EU aviation regulatory data.
