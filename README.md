# AeroLex — Aviation Regulatory Assistant & Research Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=flat&logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg?style=flat&logo=vite)](https://vitejs.dev)
[![SQLite FTS5](https://img.shields.io/badge/SQLite-FTS5%20BM25-003B57.svg?style=flat&logo=sqlite)](https://www.sqlite.org/fts5.html)
[![FAISS](https://img.shields.io/badge/FAISS-Dense%20Retrieval-0467DF.svg?style=flat)](https://github.com/facebookresearch/faiss)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, offline-first hybrid RAG (Retrieval-Augmented Generation) and regulatory intelligence workstation purpose-built for global civil aviation frameworks: **EASA Easy Access Rules**, **EU Formex Aviation Acts**, **FAA Title 14 CFR Regulations**, and **Custom User-Authored Operating Manuals**.

AeroLex enables aerospace engineers, flight operations compliance auditors, safety managers, and air traffic system regulators to search, cross-reference, question, compare, and synthesize thousands of regulatory provisions with sub-millisecond retrieval and citation traceability.

---

## Key Capabilities

### 1. Hybrid Multi-Stage Retrieval Engine
- **Dense Vector Semantic Search (FAISS)**: Uses state-of-the-art embedding models to capture regulatory intent and natural language questions. Enhanced with **HyDE (Hypothetical Document Embeddings)** for query expansion with configurable timeout and safe cold-start fallback.
- **SQLite FTS5 Full-Text Keyword Search (BM25)**: Sub-millisecond keyword retrieval with Porter stemming, optimized for aviation acronyms (`ATSEP`, `AMC-20`, `CPDLC`, `ADS-B`, `FTL`, `SMS`, `FAR`, `CFR`) and clause numbering (`CAT.OP.MPA`, `CS-ACNS`, `Part-FCL`, `§ 25.1309`, `§ 121.311`).
- **Comprehensive Origin Filtering**: Dynamically filter queries across `ALL`, `EASA` (Easy Access Rules), `EU` (EUR-Lex Formex Acts), `FAA` (US Federal Aviation Regulations Title 14 CFR), and `MANUAL` (custom company SOPs).
- **Reciprocal Rank Fusion (RRF)**: Merges dense vector and BM25 ranked outputs into a unified score distribution to balance semantic comprehension with exact legal terminology.
- **Context Expansion & Practical Implications ("Get Context")**: On any retrieved chunk, fetch surrounding provisions from the same regulation with sequential forward/backward linking and generate an AI synthesis of the legal context and practical operational implications.
- **Document-Scoped Search ("Focus Document")**: Instantly isolate and re-query a single regulation from any search result to discover all related requirements within that specific act.

### 2. Autonomous Deep Regulatory Research Engine
- **Scientific Multi-Perspective Synthesis**: Unlike naive RAG pipelines that blindly accept retrieved chunks, the research agent tests, validates, and actively attempts to negate candidate clauses to filter out false positives and ensure citations directly answer the query.
- **Surrounding Provision Sequence Expansion**: Validated candidate chunks that pass the adversarial gate are expanded with preceding and subsequent provisions (window ±1). Surrounding provisions are fed into fact extraction so the LLM accounts for parent definitions, operational conditions, and exceptions before formulating conclusions.
- **Full Citation Traceability & Hydration**: All surrounding provisions discovered during research are hydrated into the persistent job reference database, ensuring interactive citations and tooltips (`[Citation](chunk:ID)`) resolve seamlessly without broken references.
- **Dual-Tab Chunk Inspector Modal**: In-depth inspection modal allowing users to toggle between the **Focal Provision Text** and the **Surrounding Sequence & LLM Context**, complete with AI-generated operational implications and full chronological sequence navigation.
- **Scientific Evidence & Negation Ledger**: Transparent audit ledger displaying all validated and rejected clauses with falsification rationales, an active indicator for surrounding context expansion, and direct one-click buttons to inspect surrounding provision sequences.
- **Recursive Multi-Turn Inquiry**: Iteratively identifies knowledge gaps, generates follow-up queries, and drills into specific Subparts and Acceptable Means of Compliance (AMC/GM) across depth levels 1 to 3.
- **Dual-Engine LLM Support**:
  - **Local Offline Inference**: Integrates directly with [LM Studio](https://lmstudio.ai/) (OpenAI-compatible `/v1/chat/completions`) for air-gapped, zero-data-leakage compliance auditing with configurable timeout resilience.
  - **Google Gemini Cloud**: Native REST client supporting `gemini-3.5-flash`, `gemini-3.5-flash-lite`, and `gemini-3.8-flash` with automated exponential backoff on transient spikes (503/429) and smart model fallback.
- **Direct Workspace Integration**: Easily transition from a research report directly into the dedicated workspace by clicking **"Open All in Workspace"** to load all consulted regulatory sources into a cross-document overlap analysis.

### 3. Dedicated Multi-Regulation Workspace & Cross-Document Overlap
- **Title-Level Catalog & Multi-Select**: Browse and search over 1,400+ EU aviation acts, comprehensive EASA Easy Access Rules, and FAA 14 CFR regulations with instant origin filtering (`all`, `eu`, `easa`, `faa`, `manual`) and sorting.
- **FAA Regulations Ingestion (Title 14 CFR)**: Streaming XML parser for US Federal Aviation Administration regulations, splitting multi-part CFR volumes into discrete part-level documents (e.g. Part 21, Part 25, Part 91, Part 121, Part 135, Part 145) with structured subparts, section-level chunking (`§ XX.YY`), definitions, and GPOTABLE conversion.
- **Corrected Regulatory Viewer Mapping**: High-fidelity document viewer renders authentic FAA Part structures, EASA Easy Access Rules, and EU acts without cross-origin collisions.
- **Surrounding Chunks & Impact Analysis ("Get Context")**: On any matched provision in the dedicated workspace, inspect immediate surrounding provisions in regulatory sequence and synthesize the regulatory context and practical operational implications with local or Gemini LLMs.
- **Supporting Regulations & Qualifiers**: Tracks hierarchical relationships between primary acts and supporting decisions, corrigenda, and amendments, with dedicated qualifier exploration drawers.
- **In-App Local Caching**: Download and persist multiple regulations into client-side browser storage via **IndexedDB** (`idb-keyval`) for offline viewing, or export full JSON bundles.
- **Cross-Regulation Overlap Analysis (SQLite FTS5)**: Execute high-speed search across selected documents to visualize how safety concepts and technical specifications overlap across regulations.
- **Multi-Column Comparison Matrix**: Inspect matching sections across 20+ regulations simultaneously in a side-by-side grid or grouped list view with overlap rate calculations and distribution bars.

### 4. Manual Regulatory Document Builder & Schema Publisher
- **Author & Publish Custom Manuals**: Dedicated frontend studio (`DocumentBuilder.tsx`) for authoring company standard operating procedures (SOPs), flight operations manuals (OM Part A/B/C/D), or SMS policies.
- **Enforced Regulatory Hierarchy & Chunking**: Automatically enforces the exact same schema as official EASA and FAA regulations (`chunk_id`, `section_path`, `embedding_text`, `previous_chunk_id`, `next_chunk_id`).
- **Live Chunking & Hierarchy Simulation**: Real-time simulation of how provisions will be chunked, linked, and indexed into dense vector and SQLite FTS5 representations before publishing.
- **Instant FTS5 Indexing**: Automatically commits documents to SQLite, rebuilds the BM25 full-text index, flushes the catalog cache, and generates JSON representations for seamless viewing.

### 5. High-Value Client-Side Regulatory Tools
- **"Requirement Lens"**: Real-time normative modal verb analyzer that parses and highlights legal obligations:
  - 🟢 **Mandates (`SHALL` / `MUST` / `IS REQUIRED TO`)**
  - 🔴 **Prohibitions (`SHALL NOT` / `MUST NOT` / `PROHIBITED`)**
  - 🟡 **Recommendations (`SHOULD` / `RECOMMENDED`)**
  - 🔵 **Guidance (`MAY` / `CAN` / `GM`)**
- **Zero-Latency In-Memory Filter**: Live filter across all loaded clauses without re-querying the database or backend.
- **Shared Concept Matrix**: Automatically identifies multi-word technical terms co-occurring across different regulations to highlight harmonization or regulatory divergence.
- **Word-by-Word Diff Drawer**: Side-by-side dual chunk comparison featuring a word-level diff algorithm and percentage similarity metric.
- **Compliance Working Dossier**: Pin critical regulatory clauses, annotate them with reviewer compliance rationales and audit notes, export formatted Markdown tables, or send all pinned clauses directly to the AI Assistant for synthesis.

### 6. Document Viewer & Cache Explorer
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
| `GET` | `/regulations/catalog` | List, search, and filter the regulation catalog at the title level (origins: `all`, `eu`, `easa`, `faa`, `manual`). |
| `POST` | `/regulations/manual-document` | Author and ingest custom manuals/SOPs with automated chunking and instant FTS5 indexing. |
| `POST` | `/regulations/batch-download` | Fetch full markdown representations of multiple documents for local caching. |
| `POST` | `/regulations/workspace-fts` | Execute SQLite FTS5 search across active workspace regulations with overlap metrics. |

### `CHUNKS & CONTEXT` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/chunks/{chunk_id}/context` | Fetch preceding and subsequent provisions (window ±N) and generate AI synthesis of regulatory context and operational implications. |

### `RESEARCH` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/research/jobs` | Queue an autonomous deep research job with adversarial negation, surrounding sequence fact extraction, and multi-turn inquiry. |
| `GET` | `/research/jobs` | List recent and active research jobs. |
| `GET` | `/research/jobs/{job_id}` | Retrieve report markdown, consulted regulations, surrounding provisions, and referenced chunk texts. |
| `DELETE`| `/research/jobs/{job_id}` | Delete a research job from the persistent queue. |
| `POST` | `/research/validate-gemini` | Test Google Gemini API credentials and model availability. |

### `SEARCH` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/search` | Dense vector semantic search using FAISS and query embeddings (origins: `all`, `eu`, `easa`, `faa`, `manual`). |
| `GET` | `/search/keyword` | Fast keyword & acronym search using SQLite FTS5 BM25 with Porter stemming. |
| `GET` | `/search/hybrid` | Blended semantic + keyword search using Reciprocal Rank Fusion (RRF). |
| `GET` | `/search/origin-options`| List all supported origin filter types. |
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

# 2. SQLite FTS5 Acronym & Clause Search (supports FAA & EASA)
python ingestion/retrieval/keyword_search.py "ATSEP" --top_k 5
python ingestion/retrieval/keyword_search.py "121.311" --top_k 3 --no_llm

# 3. Hybrid RRF Search
python ingestion/retrieval/hybrid_search.py "ADS-B surveillance avionics" --top_k 5

# 4. Ingest and Chunk FAA Title 14 CFR Regulations
python -m ingestion.parsers.faa_parser ingestion/data/regulations_xml/CFR-2025-title14-vol1.xml
python -m ingestion.parsers.faa_chunker

# 5. Generate Vector Embeddings for Chunks (Supports Local LM Studio & OpenAI)
python -m ingestion.retrieval.embed_chunks
```

---

## Project Structure

```
.
├── api/                             # FastAPI application & endpoints
│   ├── main.py                      # Application entrypoint & route registration
│   ├── regulations.py               # Regulations catalog, manual builder & workspace FTS endpoints
│   ├── research.py                  # Deep research engine with surrounding context sequence expansion
│   └── utils.py                     # LLM call wrappers (LM Studio & Gemini) & database pool
├── frontend/                        # React 18 + Vite frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── AskAssistant.tsx     # Context-aware regulatory chat
│   │   │   ├── DocumentBuilder.tsx  # Interactive manual regulatory document builder & schema publisher
│   │   │   ├── RegulationsWorkspace.tsx # Multi-regulation workspace & overlap analyzer
│   │   │   ├── ResearchTab.tsx      # Autonomous deep research UI, dual-tab inspector & audit ledger
│   │   │   ├── SearchExplorer.tsx   # Hybrid semantic/keyword search with "Get Context" and "Focus"
│   │   │   ├── DocViewerModal.tsx   # Structured section document viewer (EASA, EU, FAA, Manual)
│   │   │   ├── CacheExplorer.tsx    # IndexedDB offline storage explorer
│   │   │   ├── ErrorBoundary.tsx    # Crash protection & recovery boundary
│   │   │   └── SettingsModal.tsx    # Local & Gemini LLM settings and timeout configuration
│   │   ├── services/apiClient.ts    # Typed API client & IndexedDB cache manager
│   │   ├── types.ts                 # TypeScript type definitions
│   │   └── App.tsx                  # Root navigation & state orchestration
├── ingestion/                       # Ingestion pipeline & retrieval engines
│   ├── parsers/                     # EASA XML, EU Formex XML, and FAA 14 CFR XML parsers
│   ├── chunkers/                    # Semantic, section-based, and FAA legal chunkers
│   ├── retrieval/                   # FAISS, SQLite FTS5, surrounding context & Hybrid RRF algorithms
│   └── core/config.py               # Pydantic settings & path management
├── api_schema.json                  # OpenAPI 3.1 schema specification
├── api_description.md               # API integration workflows & developer guide
├── start.py                         # Unified orchestration CLI for ingestion and API
└── README.md                        # Project documentation
```

---

## License

This project is licensed under the [MIT License](LICENSE).
