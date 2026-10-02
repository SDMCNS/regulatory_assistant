# AeroLex EU — Aviation Regulatory Assistant & Research Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=flat&logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg?style=flat&logo=vite)](https://vitejs.dev)
[![SQLite FTS5](https://img.shields.io/badge/SQLite-FTS5%20BM25-003B57.svg?style=flat&logo=sqlite)](https://www.sqlite.org/fts5.html)
[![FAISS](https://img.shields.io/badge/FAISS-Dense%20Retrieval-0467DF.svg?style=flat)](https://github.com/facebookresearch/faiss)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, offline-first hybrid RAG (Retrieval-Augmented Generation) and regulatory intelligence workstation purpose-built for European aviation regulations, including **EASA Easy Access Rules** and **EU Formex Aviation Acts**.

AeroLex EU enables aerospace engineers, flight operations compliance auditors, safety managers, and air traffic system regulators to search, cross-reference, question, compare, and synthesize thousands of regulatory provisions with sub-millisecond retrieval and citation traceability.

---

## Key Capabilities

### 1. Hybrid Multi-Stage Retrieval Engine
- **Dense Vector Semantic Search (FAISS)**: Uses state-of-the-art embedding models to capture regulatory intent and natural language questions. Enhanced with **HyDE (Hypothetical Document Embeddings)** for query expansion.
- **SQLite FTS5 Full-Text Keyword Search (BM25)**: Sub-millisecond keyword retrieval with Porter stemming, optimized for aviation acronyms (`ATSEP`, `AMC-20`, `CPDLC`, `ADS-B`, `FTL`, `SMS`) and clause numbering (`CAT.OP.MPA`, `CS-ACNS`, `Part-FCL`).
- **Reciprocal Rank Fusion (RRF)**: Merges dense vector and BM25 ranked outputs into a unified score distribution to balance semantic comprehension with exact legal terminology.

### 2. Autonomous Deep Regulatory Research Engine
- **Scientific Multi-Perspective Synthesis**: Unlike naive RAG pipelines that blindly accept retrieved chunks, the research agent tests, validates, and actively attempts to negate candidate clauses to filter out false positives and ensure citations directly answer the query.
- **Recursive Multi-Turn Inquiry**: Iteratively identifies knowledge gaps, generates follow-up queries, and drills into specific Subparts and Acceptable Means of Compliance (AMC/GM) across depth levels 1 to 3.
- **Dual-Engine LLM Support**:
  - **Local Offline Inference**: Integrates directly with [LM Studio](https://lmstudio.ai/) (OpenAI-compatible `/v1/chat/completions`) for air-gapped, zero-data-leakage compliance auditing.
  - **Google Gemini Cloud**: Native REST client supporting `gemini-3.5-flash`, `gemini-3.5-flash-lite`, and `gemini-3.8-flash` with automated exponential backoff on transient spikes (503/429) and smart model fallback.
- **Structured Report Viewer with Interactive Citations**: Parses complex research outputs into navigable sections with interactive citation tooltips (`[Citation](chunk:ID)`). Hovering over any citation reveals the exact regulatory text, document title, and section path.
- **Direct Workspace Integration**: Easily transition from a research report directly into the dedicated workspace by clicking **"Open All in Workspace"** to load all consulted regulatory sources into a cross-document overlap analysis.

### 3. Dedicated Multi-Regulation Workspace & Cross-Document Overlap
- **Title-Level Catalog & Multi-Select**: Browse and search over 1,400+ EU aviation acts and comprehensive EASA Easy Access Rules with instant origin filtering (`easa` vs `eu`) and sorting.
- **In-App Local Caching**: Download and persist multiple regulations into client-side browser storage via **IndexedDB** (`idb-keyval`) for offline viewing, or export full JSON bundles.
- **Cross-Regulation Overlap Analysis (SQLite FTS5)**: Execute high-speed search across selected documents to visualize how safety concepts and technical specifications overlap across European regulations.
- **Multi-Column Comparison Matrix**: Inspect matching sections across 20+ regulations simultaneously in a side-by-side grid or grouped list view with overlap rate calculations and distribution bars.

### 4. High-Value Client-Side Regulatory Tools
- **"Requirement Lens"**: Real-time normative modal verb analyzer that parses and highlights legal obligations:
  - 🟢 **Mandates (`SHALL` / `MUST` / `IS REQUIRED TO`)**
  - 🔴 **Prohibitions (`SHALL NOT` / `MUST NOT` / `PROHIBITED`)**
  - 🟡 **Recommendations (`SHOULD` / `RECOMMENDED`)**
  - 🔵 **Guidance (`MAY` / `CAN` / `GM`)**
- **Zero-Latency In-Memory Filter**: Live filter across all loaded clauses without re-querying the database or backend.
- **Shared Concept Matrix**: Automatically identifies multi-word technical terms co-occurring across different regulations to highlight harmonization or regulatory divergence.
- **Word-by-Word Diff Drawer**: Side-by-side dual chunk comparison featuring a word-level diff algorithm and percentage similarity metric.
- **Compliance Working Dossier**: Pin critical regulatory clauses, annotate them with reviewer compliance rationales and audit notes, export formatted Markdown tables, or send all pinned clauses directly to the AI Assistant for synthesis.

### 5. Document Viewer & Cache Explorer
- **Interactive Document Viewer**: Inspect complete regulations with collapsible sections (Subparts, CS, AMC/GM, Annexes, Articles), in-browser text search, match jumping, and citation links.
- **Cache Explorer**: Audit locally cached documents, inspect storage footprint, and view cached texts offline.

---

## Architecture Overview

```
                      ┌───────────────────────────────────────┐
                      │        React + Vite Frontend          │
                      │  (TailwindCSS, Lucide, idb-keyval)    │
                      └──────────────────┬────────────────────┘
                                         │ REST API
                                         ▼
                      ┌───────────────────────────────────────┐
                      │            FastAPI Backend            │
                      │  (/search, /research, /regulations)   │
                      └────────┬───────────────────┬──────────┘
                               │                   │
                ┌──────────────▼──────────┐   ┌────▼─────────────────┐
                │ SQLite Chunks & FTS5    │   │ Local LLM (LM Studio)│
                │ (WAL Mode, BM25 Index)  │   │ or Google Gemini API │
                └──────────────┬──────────┘   └──────────────────────┘
                               │
                ┌──────────────▼──────────┐
                │ FAISS Dense Vector DB   │
                │ (Semantic Embeddings)   │
                └─────────────────────────┘
```

---

## Quick Start

### Prerequisites
- **Python**: 3.10+
- **Node.js**: 18+ and `npm`
- **LM Studio** (for local offline LLM) or a **Google Gemini API Key** (for cloud research)

### 1. Backend Installation

Clone the repository and install the Python dependencies:

```bash
git clone https://github.com/SDMCNS/regulatory_assistant.git
cd regulatory_assistant

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux / macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration (`user.settings.conf`)

Create a `user.settings.conf` file in the root directory to customize model and storage paths:

```ini
# Data directories
DATA_DIR=./ingestion/data

# Local LLM & Embedding Settings (LM Studio)
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL_NAME=qwen2.5-7b-instruct
EMBEDDING_MODEL_NAME=text-embedding-nomic-embed-text-v1.5
EMBEDDING_DIMENSIONS=768

# Optional: Google Gemini Cloud API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

### 3. Ingesting Regulations

To populate the local SQLite FTS5 database and FAISS index:

```bash
# Ingest EASA XML regulations directly from RSS feed:
python start.py ingest --download_easa

# Ingest with document limit for testing:
python start.py ingest --download_easa --limit 20
```

> **Note**: For EU Formex XML documents, extract your Formex dump into the `ingestion/data/regulations_xml` folder and run `python start.py ingest`.

### 4. Running the Platform

#### Start the FastAPI Backend:
```bash
python start.py api
```
*API will run on `http://localhost:8000`. Interactive docs are available at `http://localhost:8000/docs`.*

#### Start the React Frontend:
```bash
cd frontend
npm install
npm run dev
```
*Web client will run on `http://localhost:3000`.*

---

## API Reference

### `REGULATIONS` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/regulations/catalog` | List, search, and filter the regulation catalog at the title level. |
| `POST` | `/regulations/batch-download` | Fetch full markdown representations of multiple documents for local caching. |
| `POST` | `/regulations/workspace-fts` | Execute SQLite FTS5 search across active workspace regulations with overlap metrics. |

### `RESEARCH` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/research/jobs` | Queue an autonomous deep research job (supports local LLM and Gemini Cloud). |
| `GET` | `/research/jobs` | List recent and active research jobs. |
| `GET` | `/research/jobs/{job_id}` | Retrieve report markdown, consulted regulations, and referenced chunk texts. |
| `DELETE`| `/research/jobs/{job_id}` | Delete a research job from the persistent queue. |
| `POST` | `/research/validate-gemini` | Test Google Gemini API credentials and model availability. |

### `SEARCH` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/search` | Dense vector semantic search using FAISS and query embeddings. |
| `GET` | `/search/keyword` | Fast keyword & acronym search using SQLite FTS5 BM25 with Porter stemming. |
| `GET` | `/search/hybrid` | Blended semantic + keyword search using Reciprocal Rank Fusion (RRF). |
| `GET` | `/search/docs/{doc_id}` | Retrieve complete markdown of a regulation with embedded section breaks. |
| `GET` | `/search/docs/{doc_id}/sections`| Retrieve structured regulatory sections (Subparts, CS, AMCs, Annexes). |

### `LLM` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/llm/ask` | Context-aware regulatory Q&A with targeted chunks or auto-retrieval. |
| `POST` | `/llm/extract` | Structured JSON information extraction conforming to a provided schema. |

---

## CLI Diagnostic & Search Tools

Test retrieval capabilities directly from the command line:

```bash
# 1. Semantic Vector Search
python ingestion/retrieval/search_chunks.py "pilot rest periods and flight duty limitations" -k 5

# 2. SQLite FTS5 Acronym & Clause Search
python ingestion/retrieval/keyword_search.py "ATSEP" --top_k 5
python ingestion/retrieval/keyword_search.py "CAT.OP.MPA.100" --top_k 3 --no_llm

# 3. Hybrid RRF Search
python ingestion/retrieval/hybrid_search.py "ADS-B surveillance avionics" --top_k 5
```

---

## Project Structure

```
.
├── api/                             # FastAPI application & endpoints
│   ├── main.py                      # Application entrypoint & route registration
│   ├── regulations.py               # Regulations catalog & workspace FTS endpoints
│   ├── research.py                  # Deep research engine & queue management
│   └── utils.py                     # LLM call wrappers (LM Studio & Gemini) & database pool
├── frontend/                        # React 18 + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── AskAssistant.tsx     # Context-aware regulatory chat
│   │   │   ├── RegulationsWorkspace.tsx # Multi-regulation workspace & overlap analyzer
│   │   │   ├── ResearchTab.tsx      # Autonomous deep research UI & citation viewer
│   │   │   ├── SearchExplorer.tsx   # Hybrid semantic/keyword search
│   │   │   ├── DocViewerModal.tsx   # Structured section document viewer
│   │   │   ├── CacheExplorer.tsx    # IndexedDB offline storage explorer
│   │   │   ├── ErrorBoundary.tsx    # Crash protection & recovery boundary
│   │   │   └── SettingsModal.tsx    # Local & Gemini LLM settings
│   │   ├── services/apiClient.ts    # Typed API client & IndexedDB cache manager
│   │   ├── types.ts                 # TypeScript type definitions
│   │   └── App.tsx                  # Root navigation & state orchestration
├── ingestion/                       # Ingestion pipeline & retrieval engines
│   ├── parsers/                     # EASA XML & EU Formex XML parsers
│   ├── chunkers/                    # Semantic & section-based legal chunkers
│   ├── retrieval/                   # FAISS, SQLite FTS5, and Hybrid RRF algorithms
│   └── core/config.py               # Pydantic settings & path management
├── api_schema.json                  # OpenAPI 3.1 schema specification
├── api_description.md               # API integration workflows & developer guide
├── start.py                         # Unified orchestration CLI for ingestion and API
└── README.md                        # Project documentation
```

---

## License

This project is licensed under the [MIT License](LICENSE).
