# AeroLex EU — Aviation Regulatory Assistant & Research Platform
*SESAR Deployment Manager Modernization & Compliance Intelligence*

[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=flat&logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg?style=flat&logo=vite)](https://vitejs.dev)
[![Kùzu Graph DB](https://img.shields.io/badge/Kùzu-Embedded%20Graph%20DB-8A2BE2.svg?style=flat)](https://kuzudb.com)
[![D3.js](https://img.shields.io/badge/D3.js-Force--Directed%20Graphs-F9A03C.svg?style=flat&logo=d3.js)](https://d3js.org)
[![SQLite FTS5](https://img.shields.io/badge/SQLite-FTS5%20BM25-003B57.svg?style=flat&logo=sqlite)](https://www.sqlite.org/fts5.html)
[![FAISS](https://img.shields.io/badge/FAISS-Dense%20Retrieval-0467DF.svg?style=flat)](https://github.com/facebookresearch/faiss)
[![SESAR DM](https://img.shields.io/badge/SESAR-Deployment%20Manager-008080.svg?style=flat)](https://www.sesardeploymentmanager.eu)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, offline-first hybrid RAG (Retrieval-Augmented Generation), public consultation analysis, and regulatory intelligence workstation purpose-built for the **SESAR Deployment Manager (SDM)**, Air Navigation Service Providers (ANSPs), National Aviation Authorities (NAAs), airlines, and aerospace manufacturers.

AeroLex EU unifies global civil aviation legal frameworks: **EASA Easy Access Rules**, **EU Formex Aviation Acts**, **FAA Title 14 CFR Regulations**, **EUROCAE Technical Standards**, **SKYbrary Air Safety Knowledge**, **User-Authored Notes**, and **Custom Operating Manuals**.

---

## What AeroLex EU Does

1. **Aviation Regulatory Search & Cross-Referencing**: Sub-millisecond keyword retrieval and semantic search over tens of thousands of provisions, certification specifications (CS), acceptable means of compliance (AMC), guidance material (GM), and federal regulations.
2. **Regulatory Knowledge Graph Explorer & GraphRAG**: High-performance embedded graph database (Kùzu) mapping Hard Law Implementing Rules, Soft Law AMCs/GMs, certification specifications, stakeholders, and aviation concepts. Features dual-entry discovery (exact code autocomplete & HyDE vector search), D3 force-directed subgraphs (Compliance Chains, Blast Radius, Concept Ontologies), and complete 360° Node Inspection dossiers.
3. **Autonomous Adversarial Deep Research**: Multi-pass research agent that formulates hypotheses, extracts clauses, systematically challenges citations through an adversarial falsification gate, and synthesizes traceable compliance reports.
4. **Public Consultation & Stakeholder Intelligence**: Ingestion and automated analysis of regulatory consultation documents (Word/PDF) and stakeholder feedback comments (CSV/Excel). Maps consensus, detects dissent, traces organizational alignment ("Direction of Travel"), diagnoses regulatory tensions, and performs silence accounting.
5. **Multi-Regulation Workspace & Requirement Lens**: Side-by-side cross-document overlap matrix with real-time modal verb analysis (Mandates, Prohibitions, Recommendations, Guidance) and compliance dossier curation.
6. **User Document Intelligence & Multimodal Diagram Extraction**: Automated document ingestion supporting PDF diagram/table detection, Gemini Vision HyDE graphical summarization, and executive comparison for duplicate and superseded document management.
7. **Knowledge Governance & Corpus Hygiene**: Real-time auditing of corpus health, obsolescence tracking against recent amendments, topic deactivation/activation, and duplicate detection.
8. **Sovereign & Air-Gapped AI**: 100% offline-capable via local LLMs (LM Studio, Ollama, vLLM) with zero telemetry or data leakage, alongside cloud options (Google Gemini, OpenAI).
---

## How It Works

```
                                ┌────────────────────────────────────────────────────────┐
                                │          AeroLex EU Modern Frontend (React 18)         │
                                │  • Theme Switcher (Dark / Light) • Custom Tab Manager  │
                                │  • SESAR DM About Modal • D3 Force-Directed Graph UI   │
                                └───────────────────────────┬────────────────────────────┘
                                                            │ REST / JSON API
                                                            ▼
                                ┌────────────────────────────────────────────────────────┐
                                │             FastAPI Regulatory Engine                  │
                                │  (/graph, /search, /research, /consultation, /upload)  │
                                └─────────────┬───────────────────────────┬──────────────┘
                                              │                           │
                    ┌─────────────────────────▼──────────────┐   ┌────────▼──────────────┐
                    │      Multi-Stage Retrieval & Graph     │   │   Inference Engine    │
                    │  • Kùzu Embedded Graph Engine          │   │ • Local LM Studio /   │
                    │  • SQLite FTS5 (BM25 + Porter Stem)   │   │   Ollama (Offline)    │
                    │  • FAISS Vector Store (Nomic Embed)    │   │ • Google Gemini Cloud │
                    │  • HyDE Vector Anchor Synthesis        │   │   (3.5/3.8 Flash,     │
                    │  • Reciprocal Rank Fusion (RRF)        │   │    Gemini Vision)     │
                    └─────────────────────────┬──────────────┘   └───────────────────────┘
                                              │
                    ┌─────────────────────────▼──────────────┐
                    │      Specialized Workspaces & Logic    │
                    │  • Knowledge Graph Explorer & GraphRAG │
                    │  • Consultation Synthesis & Radar      │
                    │  • Deep Adversarial Research Agent     │
                    │  • Requirement Lens & Dossier          │
                    │  • User Document & Diagram Ingestion   │
                    │  • Knowledge Governance & Forgetting   │
                    └────────────────────────────────────────┘
```

### 1. Regulatory Knowledge Graph & Multi-Source Federation (Kùzu DB)
- **Embedded Property Graph**: Powered by Kùzu, structuring EASA regulations into explicit typed nodes (`Document`, `Annex`, `Provision`, `Concept`, `Stakeholder`) and legal relationships (`SATISFIES`, `EXPLAINS`, `CROSS_REFERENCES`, `GOVERNS_CONCEPT`, `APPLIES_TO`, `SIMILAR_TO`).
- **Dual-Entry Discovery**: Instant provision code autocomplete with fast selection and **HyDE (Hypothetical Document Embeddings)** vector discovery that translates operational scenarios into synthesized regulatory anchors.
- **Interactive D3 Visualizations**: Force-directed subgraphs for compliance chains, blast radius dependency analysis, and cross-annex concept ontologies.
- **Multi-Source Catalog Federation**: Unifies EASA Easy Access Rules, EU Formex Acts, FAA Title 14 CFR, EUROCAE technical standards, and SKYbrary air safety publications (with 70+ categories & sub-topics filtering).

### 2. Ingestion, Structured Chunking & Multimodal Extraction
- **EASA XML Parser**: Ingests Easy Access Rules directly, preserving the rich hierarchy of Cover Regulations, Annexes, Subparts, CS, AMC, and GM.
- **EU Formex XML Parser**: Ingests Official Journal legal acts from EUR-Lex with full metadata, preamble recitals, articles, and corrigenda.
- **FAA Title 14 CFR Parser**: Streaming XML parser segmenting multi-part CFR volumes into individual Parts (e.g., Part 21, 25, 91, 121, 135) with structured subparts and section-level chunking (`§ XX.YY`).
- **User Document & Diagram Extraction**: Automated PDF/Office document analysis with page-level diagram/table detection, Gemini Vision HyDE graphical summarization, and executive comparison for duplicate and superseded document management.
- **Sequential Linking**: Every chunk records `previous_chunk_id` and `next_chunk_id` pointers, enabling instant retrieval of surrounding provisions.

### 3. Multi-Stage Hybrid Retrieval (BM25 + FAISS + RRF)
- **FTS5 BM25 Engine**: Optimized for exact aviation acronyms (`ATSEP`, `CPDLC`, `ADS-B`, `FTL`, `SMS`, `ACNS`) and specific clause codes (`CAT.OP.MPA.110`).
- **Dense Vector Embeddings**: Uses high-dimensional embeddings (e.g., Nomic Embed v1.5) via FAISS for conceptual semantics and natural language regulatory intent.
- **HyDE & Local LLM Expansion**: Generation of hypothetical regulatory clauses or synonym expansions to bridge vocabulary gaps.
- **Reciprocal Rank Fusion**: Re-ranks and merges keyword and dense semantic results into a unified score distribution.

### 4. Consultation Intelligence Suite
- **Document & Feedback CSV Ingestion**: Automatically inspects stakeholder comment matrices (CSV/Excel) and extracts consultation document drafts (DOCX/PDF).
- **Automated Column Mapping**: Heuristically detects Organization, Comment Text, Clause/Paragraph Reference, Proposed Amendment, and Sentiment columns.
- **Direction of Travel & Spider/Radar Taxonomy**: Categorizes stakeholder feedback across canonical regulatory vectors (e.g., *Mandate Acceleration*, *Economic Proportionality*, *Harmonization*, *Interoperability*, *Safety Buffer*).
- **Tension Diagnostics**: Identifies structural conflicts between stakeholder groups (e.g., Airlines vs. ANSPs vs. OEMs).
- **Silence Accounting**: Automatically uncovers critical draft articles that received zero stakeholder comments, identifying potential blind spots before regulatory adoption.

### 5. Autonomous Deep Research Engine
- **Hypothesis & Query Generation**: Deconstructs complex aerospace compliance queries into multi-turn research vectors.
- **Adversarial Falsification Gate**: Systematically analyzes retrieved candidates to eliminate false citations, ensuring that every quoted clause directly supports the legal reasoning.
- **Surrounding Provision Expansion**: Automatically brings preceding and following clauses into the synthesis context to guarantee that parent definitions, operational conditions, and derogations are accounted for.
- **Audit Ledger & Traceable Citations**: Produces fully interactive reports with mouseover previews, clickable references, and complete provenance records.

### 6. Knowledge Governance & Corpus Hygiene
- **Health & Consistency Auditing**: Tracks active vs. deactivated regulations, orphaned chunks, and index synchronization.
- **Obsolescence Detection**: Identifies provisions potentially superseded by newer regulatory packages or corrigenda.
- **Selective Deactivation**: Enables regulatory compliance officers to temporarily or permanently deactivate outdated regulations without database rebuilds.

### 7. Modern User Experience & Customization
- **Theme Switcher**: Instant one-click toggle between Dark Mode and Light Mode with persistent local storage.
- **Customizable Workspace Tabs**: Toggle visibility of advanced tabs (Knowledge Graph, Knowledge Governance, Document Builder, Query Memory, Schema Extractor, and Local Cache) via simple checkboxes in Settings.
- **Interactive About Modal**: Comprehensive project briefing modal displaying the SESAR Deployment Manager badge, platform mission, and technological architecture.
- **Interactive Document Viewer & Stepper**: Sequential document navigation with emerald highlighting for exact referenced matches and amber highlighting for incidental matches.
---

## Detailed Capabilities

### 1. Hybrid Multi-Stage Retrieval Engine
- **Dense Vector Semantic Search (FAISS)**: Uses state-of-the-art embedding models to capture regulatory intent and natural language questions. Enhanced with **HyDE (Hypothetical Document Embeddings)** for query expansion with configurable timeout and safe cold-start fallback.
- **SQLite FTS5 Full-Text Keyword Search (BM25)**: Sub-millisecond keyword retrieval with Porter stemming, optimized for aviation acronyms (`ATSEP`, `AMC-20`, `CPDLC`, `ADS-B`, `FTL`, `SMS`, `FAR`, `CFR`) and clause numbering (`CAT.OP.MPA`, `CS-ACNS`, `Part-FCL`, `§ 25.1309`, `§ 121.311`).
- **Comprehensive Origin Filtering**: Dynamically filter queries across `ALL`, `EASA` (Easy Access Rules), `EU` (EUR-Lex Formex Acts), `FAA` (US Federal Aviation Regulations Title 14 CFR), `SKYBRARY`, `NOTES` (User-Authored Notes), and `MANUAL` (custom company SOPs).
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
- **Interactive HTML Report Export**: Download complete research reports as standalone, beautifully styled HTML documents featuring collapsible report sections, collapsible appendices/tables, and interactive mouseover tooltips displaying full cited provision texts and legal context.
- **Direct Workspace Integration**: Easily transition from a research report directly into the dedicated workspace by clicking **"Open All in Workspace"** to load all consulted regulatory sources into a cross-document overlap analysis.

### 3. Public Consultation & Stakeholder Intelligence Suite
- **End-to-End Session Lifecycle**: Upload consultation draft documents (.docx, .doc, .pdf, .xml) and stakeholder comment spreadsheets (.csv, .xlsx).
- **Intelligent Column Inspection**: Real-time header detection with interactive overrides for Organization, Comment, Clause, Proposed Change, and Category columns.
- **Direction of Travel (Radar / Spider Mapping)**: Maps stakeholder sentiments across aviation governance dimensions:
  - *Technical Rigor vs. Simplification*
  - *Operational Burden vs. Safety Enhancement*
  - *Timetable Feasibility vs. Acceleration*
  - *Harmonization vs. Subsidiarity*
- **Tension Diagnostics**: Pinpoints contentious clauses where stakeholders hold polarized opinions, displaying side-by-side opposing quotes.
- **Silence Accounting**: Scans consultation document sections against stakeholder feedback to reveal provisions that received zero review comments.
- **Reviewer Triage & Disposition Matrix**: Tag, prioritize, and record official dispositions (Accepted, Rejected, Partially Accepted, Clarification Provided) with full export capabilities.

### 4. Dedicated Multi-Regulation Workspace & Cross-Document Overlap
- **Title-Level Catalog & Multi-Select**: Browse and search over 1,400+ EU aviation acts, comprehensive EASA Easy Access Rules, and FAA 14 CFR regulations with instant origin filtering (`all`, `eu`, `easa`, `faa`, `manual`) and sorting.
- **FAA Regulations Ingestion (Title 14 CFR)**: Streaming XML parser for US Federal Aviation Administration regulations, splitting multi-part CFR volumes into discrete part-level documents (e.g. Part 21, Part 25, Part 91, Part 121, Part 135, Part 145) with structured subparts, section-level chunking (`§ XX.YY`), definitions, and GPOTABLE conversion.
- **Corrected Regulatory Viewer Mapping**: High-fidelity document viewer renders authentic FAA Part structures, EASA Easy Access Rules, and EU acts without cross-origin collisions.
- **Surrounding Chunks & Impact Analysis ("Get Context")**: On any matched provision in the dedicated workspace, inspect immediate surrounding provisions in regulatory sequence and synthesize the regulatory context and practical operational implications with local or Gemini LLMs.
- **Supporting Regulations & Qualifiers**: Tracks hierarchical relationships between primary acts and supporting decisions, corrigenda, and amendments, with dedicated qualifier exploration drawers.
- **In-App Local Caching**: Download and persist multiple regulations into client-side browser storage via **IndexedDB** (`idb-keyval`) for offline viewing, or export full JSON bundles.
- **Cross-Regulation Overlap Analysis (SQLite FTS5)**: Execute high-speed search across selected documents to visualize how safety concepts and technical specifications overlap across regulations.
- **Multi-Column Comparison Matrix**: Inspect matching sections across 20+ regulations simultaneously in a side-by-side grid or grouped list view with overlap rate calculations and distribution bars.

### 5. Manuals & User-Authored Notes
- **Author & Publish Custom Manuals**: Dedicated frontend studio (`DocumentBuilder.tsx`) for authoring company standard operating procedures (SOPs), flight operations manuals (OM Part A/B/C/D), or SMS policies.
- **User-Authored Notes**: Create structural meeting notes, daily journals, or project playbooks via the `NotesTab`. Notes are stored and chunked just like standard regulations and can be surfaced during semantic searches alongside official acts.
- **Enforced Regulatory Hierarchy & Chunking**: Automatically enforces the exact same schema as official EASA and FAA regulations (`chunk_id`, `section_path`, `embedding_text`, `previous_chunk_id`, `next_chunk_id`).
- **Live Chunking & Hierarchy Simulation**: Real-time simulation of how provisions will be chunked, linked, and indexed into dense vector and SQLite FTS5 representations before publishing.
- **Instant FTS5 Indexing**: Automatically commits documents to SQLite, rebuilds the BM25 full-text index, flushes the catalog cache, and generates JSON representations for seamless viewing.

### 6. High-Value Client-Side Regulatory Tools
- **"Requirement Lens"**: Real-time normative modal verb analyzer that parses and highlights legal obligations:
  - 🟢 **Mandates (`SHALL` / `MUST` / `IS REQUIRED TO`)**
  - 🔴 **Prohibitions (`SHALL NOT` / `MUST NOT` / `PROHIBITED`)**
  - 🟡 **Recommendations (`SHOULD` / `RECOMMENDED`)**
  - 🔵 **Guidance (`MAY` / `CAN` / `GM`)**
- **Zero-Latency In-Memory Filter**: Live filter across all loaded clauses without re-querying the database or backend.
- **Shared Concept Matrix**: Automatically identifies multi-word technical terms co-occurring across different regulations to highlight harmonization or regulatory divergence.
- **Word-by-Word Diff Drawer**: Side-by-side dual chunk comparison featuring a word-level diff algorithm and percentage similarity metric.
- **Compliance Working Dossier**: Pin critical regulatory clauses, annotate them with reviewer compliance rationales and audit notes, export formatted Markdown tables, or send all pinned clauses directly to the AI Assistant for synthesis.

### 7. Interactive Document Viewer & Sequential Match Stepper
- **Full Regulatory Context Preservation**: Inspect complete multi-hundred or thousand-page regulations in full sequential order without filtering out non-matching sections, allowing auditors to read surrounding articles for context.
- **Exact Referenced Match vs. Incidental Matches**:
  - **Exact Referenced Match**: The specific clause clicked or cited is given a glowing emerald highlight (`ring-2 ring-emerald-400`), a bold `🎯 REFERENCED MATCH` header badge, and a dedicated **`[🎯 Referenced Match]`** toolbar button (shortcut: <kbd>r</kbd>) to instantly return to it at any time.
  - **Incidental Matches**: Other provisions matching the search query or citations across the document are highlighted with amber borders, glowing rings when active, and `INCIDENTAL MATCH #X` badges.
- **Match Stepper & Navigation**: Step through matches via `Prev` / `Next` buttons, keyboard shortcuts (<kbd>↓</kbd>/<kbd>j</kbd>/<kbd>n</kbd> and <kbd>↑</kbd>/<kbd>k</kbd>/<kbd>p</kbd>), or jump directly using the provision dropdown.
- **In-Browser Text Similarity**: Live client-side fuzzy search with keyword hit counters and real-time highlighted in-text snippets.

### 8. Conversational Regulatory Assistant & Chat Reports
- **Context-Aware Dialogue**: Multi-turn chat with hybrid retrieval across EASA, EU, FAA, Skybrary, Notes, and company manuals.
- **Conversation Renaming & Organization**: Rename active and past chat threads directly in the sidebar for clean audit organization.
- **Legible Regulatory Standards Citations**: Displays human-readable document titles and descriptions in citation headers instead of raw database IDs.
- **HTML Chat Report Export**: Export chat sessions as standalone interactive HTML reports with expandable messages, mouseover citation previews, and referenced regulatory standards summaries.

### 9. Knowledge Governance & Cache Explorer
- **Corpus Auditing & Deactivation**: Monitor active vs. deactivated documents across all origins, review recent governance actions, and deactivate obsolete acts without losing historical reference records.
- **Cache Explorer**: Audit locally cached documents, inspect storage footprint, and view cached texts offline.

### 10. Regulatory Knowledge Graph Explorer & GraphRAG (Kùzu + D3.js)
- **Embedded Property Graph Engine**: Powered by [Kùzu](https://kuzudb.com/), structuring European and international aviation rules into typed nodes (`Document`, `Annex`, `Provision`, `Concept`, `Stakeholder`) and legal relationships (`CONTAINS_ANNEX`, `BELONGS_TO_ANNEX`, `SATISFIES`, `EXPLAINS`, `CROSS_REFERENCES`, `GOVERNS_CONCEPT`, `APPLIES_TO`, `SIMILAR_TO`).
- **Dual-Entry Graph Discovery**:
  - **Exact Provision Code Autocomplete**: Instant search with type-ahead provision matching and interactive dropdown navigation. Selecting any provision immediately renders its full visual graph.
  - **HyDE Vector Anchor Search**: Converts complex natural language operational scenarios (e.g. *"minimum fuel reserves and point of safe return for isolated aerodrome operations"*) into synthesized legal anchors via local or cloud LLMs, embeds them, and discovers nearest regulatory nodes across all sources.
- **Interactive D3 Force-Directed Subgraphs**:
  - **Compliance Chain Graph**: Renders the complete vertical hierarchy for any focal provision — connecting the root Implementing Rule (Hard Law) to its parent Annex, downstream Acceptable Means of Compliance (AMCs), Guidance Material (GMs), governed Concepts, and responsible Stakeholders.
  - **Blast Radius Graph**: Regulatory impact and dependency analysis visualizing all provisions citing the focal rule (upstream dependent rules) and all target rules cited by it (downstream dependencies).
  - **Concept Ontology Subgraph**: Cross-Annex thematic topology connecting high-level concepts (e.g., Fuel Planning, SMS, FTL, Airworthiness) to governing provisions across diverse European rulebooks.
- **Multi-Source Knowledge Federation**:
  - **EASA Easy Access Rules**: 42 comprehensive aviation rulebooks (Air Operations, Aircrew, Aerodromes, ATM/ANS, Airworthiness, Drones/UAS).
  - **EU Formex Aviation Acts**: Primary and secondary EU aviation legislation with EUR-Lex metadata.
  - **FAA Title 14 CFR**: Federal Aviation Regulations with Parts 21, 25, 91, 121, 135, and 145.
  - **SKYbrary Air Safety Knowledge**: Air safety publications with filtering across 70+ categories and sub-topics.
  - **EUROCAE Standards**: Technical specifications and guidance documents (ED-12C, ED-78A, ED-102B, etc.) with automatic acronym interpretation.
- **360° Node Inspector Modal & GraphRAG Dossier**:
  - **Verbatim Text**: Full unabridged clause text with clean formatting.
  - **Legal Hierarchy**: Upstream hard law provisions and parent annexes.
  - **Downstream Soft Law**: Interactive lists of associated AMCs and GMs.
  - **Dependencies & Citations**: Direct links to cited and citing provisions.
  - **Semantic Parallels (`SIMILAR_TO`)**: Cosine similarity matches surfacing parallel requirements across other regulatory domains.
  - **GraphRAG Markdown Context**: Automatically generated synthesis package ready to copy or inject directly into LLM prompts for grounded compliance reasoning.
- **Compliance Path Finding**: Computes and renders the shortest citation path between any two regulatory provisions in the graph.

### 11. User Document Intelligence & Multimodal Diagram Extraction
- **Multi-Format Upload Analysis**: Ingests user PDFs, Word documents, text files, and XML packages with content hashing (SHA-256) and automated format classification.
- **Page-Level Diagram & Table Detection**: Scans uploaded PDFs (`ingestion/user_docs/detector.py`) to detect visual elements, system architectures, wiring diagrams, flowcharts, and technical tables.
- **Gemini Vision HyDE Graphical Summaries**: Employs multimodal vision models to generate structured textual descriptions of detected diagrams, ensuring diagrams are fully indexed and retrievable via semantic vector search.
- **Executive Duplicate & Update Resolution**: Compares uploaded documents against existing corpus holdings to detect exact duplicates or newer revisions, offering one-click executive actions to **supersede** older editions, **suppress** conflicting drafts, or retain side-by-side versions.

---

## Architecture Overview

```
                      ┌───────────────────────────────────────┐
                      │        React + Vite Frontend          │
                      │  (TailwindCSS, D3.js, Lucide, idb)    │
                      └──────────────────┬────────────────────┘
                                         │ REST API
                                         ▼
                      ┌───────────────────────────────────────┐
                      │            FastAPI Backend            │
                      │  (/graph, /search, /research, /upload)│
                      └────────┬───────────────────┬──────────┘
                               │                   │
         ┌─────────────────────▼────────┐     ┌────▼─────────────────┐
         │     Multi-Stage Engines      │     │   Inference Engine   │
         │ • Kùzu Graph Engine          │     │ • Local LM Studio /  │
         │   (Nodes, Edges, HyDE)       │     │   Ollama (Offline)   │
         │ • SQLite FTS5 (BM25 Index)   │     │ • Google Gemini Cloud│
         │ • FAISS Dense Vector DB      │     │   (Flash & Vision)   │
         │ • Document & Diagram Parser  │     └──────────────────────┘
         └──────────────────────────────┘
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

> **Setup & Ingestion Guide**: For a complete overview of ingestion pipelines for FAA, Formex, EASA, and Custom Manuals, see [setup_and_data_population.md](setup_and_data_population.md).

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

### `REGULATORY KNOWLEDGE GRAPH & GRAPHRAG` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/graph/stats` | Retrieve graph statistics (total documents, annexes, provisions, concepts, stakeholders, and relationship counts). |
| `GET` | `/graph/sources` | Fetch the multi-source federated catalog (EASA, EU, FAA, SKYbrary, EUROCAE) and Skybrary sub-topic filters. |
| `GET` | `/graph/search` | Search across the EASA knowledge graph and federated sources with multi-source filtering and Skybrary topic filters. |
| `GET` | `/graph/hyde` | Hypothetical Document Embeddings (HyDE) discovery: synthesizes hypothetical legal anchors and finds nearest provisions. |
| `GET` | `/graph/chain` | Retrieve complete compliance chain subgraph for a provision in D3 force-directed format (`nodes` & `links`). |
| `GET` | `/graph/blast` | Retrieve regulatory blast radius dependency graph for a provision in D3 format (citing rules & cited targets). |
| `GET` | `/graph/concept` | Retrieve cross-annex concept ontology subgraph in D3 format for a concept name (e.g. `Fuel`, `SMS`, `FTL`). |
| `GET` | `/graph/node` | Deep 360° inspection of any provision, annex, concept, or stakeholder with full text and GraphRAG markdown context. |
| `GET` | `/graph/path` | Discover shortest citation path connecting two provisions in the knowledge graph. |

### `DOCUMENT UPLOAD & DIAGRAM EXTRACTION` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/documents/analyze` | Multi-format upload analysis (PDF, Word, XML) with diagram/table detection and duplicate comparison. |
| `POST` | `/documents/confirm-ingest` | Confirm ingestion with executive actions (`none`, `supersede`, `suppress`) and Gemini Vision diagram summarization. |

### `CONSULTATION & STAKEHOLDER INTELLIGENCE` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/consultation/sessions` | Create a new consultation session by uploading draft documents (Word/PDF) and feedback comments (CSV/Excel). |
| `GET` | `/consultation/sessions` | List all existing consultation sessions with summary metrics. |
| `GET` | `/consultation/sessions/{session_id}` | Retrieve full consultation session details, including parsed sections and enriched comments. |
| `POST` | `/consultation/sessions/inspect-csv` | Pre-inspect a feedback CSV to auto-detect columns and return sample headers. |
| `POST` | `/consultation/sessions/{session_id}/synthesize` | Trigger AI-powered consultation synthesis, thematic clustering, tension diagnostics, and Direction of Travel metrics. |
| `PUT` | `/consultation/sessions/{session_id}/comments/{comment_id}` | Update human reviewer disposition, consideration notes, and classification tags. |
| `GET` | `/consultation/sessions/{session_id}/export-matrix` | Export the complete disposition review matrix as an Excel/CSV document. |

### `KNOWLEDGE GOVERNANCE` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/regulations/governance/stats` | Retrieve global knowledge governance metrics, active vs deactivated acts, and audit logs. |
| `POST` | `/regulations/governance/{document_id}/deactivate` | Deactivate a specific regulation from active search and research indexing. |
| `POST` | `/regulations/governance/{document_id}/activate` | Re-activate a previously deactivated regulation. |
| `POST` | `/regulations/governance/batch/deactivate` | Deactivate multiple regulations in a single batch operation. |
| `POST` | `/regulations/governance/category/{category}/deactivate` | Deactivate an entire regulatory category or origin. |
| `POST` | `/regulations/governance/ai-obsolescence-scan` | Perform an AI-assisted scan of the corpus to identify potentially superseded provisions. |

### `REGULATIONS` Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/regulations/catalog` | List, search, and filter the regulation catalog at the title level (origins: `all`, `eu`, `easa`, `faa`, `manual`, `skybrary`). |
| `POST` | `/regulations/manual-document` | Author and ingest custom manuals/SOPs with automated chunking and instant FTS5 indexing. |
| `GET` | `/regulations/notes` | List user-authored notes. |
| `POST` | `/regulations/notes` | Create a new user-authored note, chunk it, and save it to the database. |
| `GET` | `/regulations/notes/{id}` | Retrieve a single user-authored note and its structural sections. |
| `POST` | `/regulations/notes/{id}/embed` | Generate FAISS vector embeddings for the chunks of a specific note. |
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
| `GET` | `/search` | Dense vector semantic search using FAISS and query embeddings (origins: `all`, `eu`, `easa`, `faa`, `manual`, `skybrary`, `note`). |
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

# 5. Build and Populate the Kùzu Regulatory Knowledge Graph
python -m ingestion.graph.builder
python -m ingestion.graph.similarity

# 6. Generate Vector Embeddings for Chunks (Supports Local LM Studio & OpenAI)
python -m ingestion.retrieval.embed_chunks
```

---

## Project Structure

```
.
├── api/                             # FastAPI application & endpoints
│   ├── main.py                      # Application entrypoint & route registration
│   ├── graph.py                     # Regulatory Knowledge Graph Explorer & GraphRAG router
│   ├── upload.py                    # Multi-format user document upload and diagram extraction
│   ├── consultation.py              # Consultation session lifecycle, spider mapping & CSV parsing
│   ├── regulations.py               # Regulations catalog, governance, manual builder & workspace FTS
│   ├── research.py                  # Deep research engine with surrounding context sequence expansion
│   └── utils.py                     # LLM call wrappers (LM Studio & Gemini) & database pool
├── frontend/                        # React 18 + Vite frontend
│   ├── public/
│   │   └── sesar_logo.png           # SESAR Deployment Manager badge asset
│   ├── src/
│   │   ├── components/
│   │   │   ├── KnowledgeGraphExplorer.tsx # Kùzu D3 force-directed graph UI & 360° Node Inspector
│   │   │   ├── AboutModal.tsx       # SESAR Deployment Manager mission & architectural briefing modal
│   │   │   ├── AskAssistant.tsx     # Context-aware regulatory chat
│   │   │   ├── ConsultationWorkspace.tsx # Stakeholder consultation synthesis & Direction of Travel
│   │   │   ├── StakeholderSpiderModal.tsx # Direction of Travel spider/radar comparison chart
│   │   │   ├── DocumentBuilder.tsx  # Interactive manual regulatory document builder & schema publisher
│   │   │   ├── KnowledgeGovernance.tsx # Corpus hygiene, obsolescence scanner & topic deactivator
│   │   │   ├── RegulationsWorkspace.tsx # Multi-regulation workspace & overlap analyzer
│   │   │   ├── ResearchTab.tsx      # Autonomous deep research UI, dual-tab inspector & audit ledger
│   │   │   ├── SearchExplorer.tsx   # Hybrid semantic/keyword search with "Get Context" and "Focus"
│   │   │   ├── DocViewerModal.tsx   # Structured section document viewer (EASA, EU, FAA, Manual)
│   │   │   ├── NotesTab.tsx         # User-authored note creator and viewer
│   │   │   ├── CacheExplorer.tsx    # IndexedDB offline storage explorer
│   │   │   ├── TopBar.tsx           # Navigation header, tab switcher, theme toggle & About trigger
│   │   │   ├── SettingsModal.tsx    # Connection settings, tab visibility toggles & theme preferences
│   │   │   └── ErrorBoundary.tsx    # Crash protection & recovery boundary
│   │   ├── services/
│   │   │   ├── apiClient.ts         # Typed API client & IndexedDB cache manager
│   │   │   └── graphService.ts      # Dedicated Knowledge Graph API service & D3 payload adapter
│   │   ├── types.ts                 # TypeScript type definitions
│   │   └── App.tsx                  # Root navigation & state orchestration
├── ingestion/                       # Ingestion pipeline & retrieval engines
│   ├── graph/                       # Regulatory Knowledge Graph pipeline (Kùzu DB)
│   │   ├── schema.py                # Graph schema (Documents, Annexes, Provisions, Concepts, Edges)
│   │   ├── builder.py               # EASA Easy Access XML graph builder & CSV bulk copier
│   │   ├── traversal.py             # Kùzu graph query engine (Chains, Blast Radius, Ontologies, Node 360°)
│   │   ├── hyde.py                  # HyDE dense vector anchor search engine
│   │   ├── sources.py               # Federated multi-source catalog manager (EU, FAA, SKYbrary, EUROCAE)
│   │   └── similarity.py            # Cosine semantic parallel (SIMILAR_TO) edge generator
│   ├── user_docs/                   # User document ingestion & diagram analysis
│   │   ├── detector.py              # PDF page-level diagram, table, and graphic detector
│   │   ├── extractor.py             # Multimodal text and Gemini Vision diagram extractor
│   │   └── ingest.py                # Staging, executive duplicate comparison & DB committer
│   ├── consultation/                # Consultation metrics, sentiment analysis & spider mapping
│   ├── parsers/                     # EASA XML, EU Formex XML, and FAA 14 CFR XML parsers
│   ├── chunkers/                    # Semantic, section-based, and FAA legal chunkers
│   ├── retrieval/                   # FAISS, SQLite FTS5, surrounding context & Hybrid RRF algorithms
│   └── core/config.py               # Pydantic settings & path management
├── api_schema.json                  # OpenAPI 3.1 schema specification
├── api_description.md               # API integration workflows & developer guide
├── start.py                         # Unified orchestration CLI for ingestion and API
└── README.md                        # Project documentation

---

## License

This project is licensed under the [MIT License](LICENSE).
