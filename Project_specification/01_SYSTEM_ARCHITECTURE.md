# 01. System Architecture Specification

## 1. Executive Overview

The **Regulation Assistant (AeroLex EU)** is an enterprise-grade regulatory intelligence platform designed specifically for European Union (EU) and European Union Aviation Safety Agency (EASA) aviation law. It ingests thousands of complex legal publication packages, unifies fragmented technical annexes, segregates non-regulatory administrative qualifiers (Decisions and Corrigenda), and powers high-precision hybrid retrieval (Dense Vector + BM25 Full-Text Search).

The system integrates local open-weights AI inference via **LM Studio** (`text-embedding-kalm-embedding-gemma3-12b-2511` producing 3,840-dimensional vectors) with SQLite FTS5, providing completely private, local, and auditable search and synthesis without requiring external cloud API dependencies.

---

## 2. High-Level Component Architecture

```mermaid
graph TD
    subgraph DataSources["Multi-Jurisdiction Data Sources"]
        EASA["EASA Easy Access Rules<br/>(42 Regulations / CS / AMC / GM)"]
        FAA["FAA Title 14 CFR<br/>(82 FAR Parts & E-CFR Acts)"]
        EU["EU EUR-Lex Formex<br/>(316 Aviation Regulations & Acts)"]
        EUROCAE["EUROCAE Standards<br/>(12 Technical Publications & EDs)"]
        SKYBRARY["SKYbrary Bookshelf<br/>(84 Operational Articles & Safety Studies)"]
        USER_DOCS["User & Consultation Docs<br/>(PDFs, Word, XLSX Submissions)"]
    end

    subgraph IngestionPipeline["Ingestion, Graph & Consolidation Pipeline"]
        PKG["Package Classifier & Streamer<br/>(iter_formex_packages & parsers)"]
        MERGER["Annex Consolidator & Qualifier Router<br/>(Groups annexes & segregates decisions)"]
        CHUNKER["Legal Hierarchy Chunker<br/>(Articles, Recitals, AMC/GM Clauses)"]
        GRAPH_INGEST["Kùzu Graph Builder & Concept Mapper<br/>(17 Core Aviation Concepts Taxonomy)"]
    end

    subgraph StorageLayer["Triple-Tier Storage Architecture"]
        SQLITE[("SQLite Database (chunks.db)<br/>- documents (357 acts)<br/>- chunks (47,849 clauses)<br/>- qualifiers (343 acts)<br/>- chunks_fts (BM25 FTS5)<br/>- stakeholder_scores")]
        FAISS[("FAISS Vector Index (LocalVectorIndex)<br/>- chunk.index (3840D)<br/>- act.index (3840D)<br/>- 6x Concept Anchor Vectors")]
        KUZU[("Kùzu Embedded Graph DB (kuzu_db)<br/>- 536 Regulation Documents<br/>- 1,200+ Annexes & 48,000+ Provisions<br/>- 17 Core & Custom Concepts Mesh<br/>- 9 Edge Types (GOVERNS, BRIDGES, etc.)")]
    end

    subgraph Inference["Local & Cloud AI Inference"]
        EMBED["text-embedding-kalm-embedding-gemma3-12b<br/>(3840-dimensional embeddings)"]
        LLM["google/gemma-4-e4b & Gemini Cloud<br/>(HyDE Vectors, Synthesis, Consultation Radar)"]
    end

    subgraph BackendAPI["FastAPI Backend Service (:8000)"]
        SEARCH_API["/search & /search/docs<br/>(Hierarchical 2-Stage & Hybrid RRF)"]
        GRAPH_API["/graph/*<br/>(Compliance Chain, Blast Radius, Regulation Concepts, HyDE)"]
        REGS_API["/regulations/*<br/>(Catalog, Batch, Qualifiers, Overlap FTS)"]
        RESEARCH_API["/research/* & /consultation/*<br/>(Adversarial Deep Research & Consultation Radar)"]
    end

    subgraph FrontendApp["React + Vite Single Page Application (:5173)"]
        GRAPH_UI["Knowledge Graph Explorer<br/>(Chain, Blast, Concepts, Regulation Bridge View, Edge Inspector)"]
        CATALOG_UI["Catalog & Domain Filter<br/>(Framework Tabs: ALL, EASA, FAA, EU, EUROCAE, SKYBRARY)"]
        WORKSPACE_UI["Dedicated Overlap Workspace<br/>(Multi-column comparison & Word Diff)"]
        CONSULT_UI["Consultation Workspace & Research Studio<br/>(Consensus Mapping, Silence Accounting, Dossiers)"]
    end

    EASA --> PKG
    FAA --> PKG
    EU --> PKG
    EUROCAE --> PKG
    SKYBRARY --> PKG
    USER_DOCS --> PKG

    PKG --> MERGER
    MERGER --> CHUNKER
    CHUNKER --> SQLITE
    CHUNKER --> GRAPH_INGEST
    GRAPH_INGEST --> KUZU
    CHUNKER --> EMBED
    EMBED --> FAISS

    StorageLayer --> BackendAPI
    Inference --> BackendAPI
    BackendAPI --> FrontendApp
```

---

## 3. Core Architectural Tenets

### 3.1. Package-Level Ingestion vs. File-Level Clutter
Earlier ingestion pipelines processed every XML file in isolation, generating fragmented document records without parent hierarchy. Under that paradigm, technical annexes containing critical operational specifications (e.g. Part-CAT, Part-ORO) were stored as orphaned documents without titles, leaving user searches disconnected from parent acts.

The current architecture operates at the **Publication Package** level:
1. Identifies the primary regulation act (`.000101.xml` or `<ACT>`).
2. Gathers attached annexes (`.01004501.xml`, `<ANNEX>`) and nests them directly inside the parent regulation JSON.
3. Segregates administrative qualifiers (Commission Decisions and Corrigenda) into a dedicated relational table linked back to the target regulation.
4. Drops phantom master wrappers (`.doc.xml`, `.toc.xml`).

### 3.2. Triple-Tier Storage Architecture
- **Relational & Keyword Layer (SQLite)**: Stores clean legal document metadata, full markdown text, individual chunks, cross-document relations, and SQLite FTS5 indices for BM25 keyword matching.
- **Dense Vector Layer (FAISS `IndexFlatIP`)**: Stores normalized 3,840-dimensional vector embeddings for cosine similarity search. Partitioned into `CHUNK` (fine-grained clauses) and `ACT` (document-level scope).
- **Embedded Property Graph Layer (Kùzu DB)**: Stores 536 multi-jurisdiction regulation documents, technical annexes, binding provisions/CS/AMC/GM clauses, organizations, and the aviation concept ontology mesh. High-performance native Cypher graph traversals evaluate direct mandates, blast radius propagation, and cross-regulatory bridges.

### 3.3. Hierarchical Retrieval & Domain Anchors
Instead of flat chunk similarity, retrieval uses a 2-stage hierarchical score:
1. **Act-Level Prior**: The user query is matched against primary regulation scopes (`act.index`).
2. **Chunk-Level Search**: Chunks belonging to top-ranking regulations receive an Act Prior bonus:
   $$\text{Score} = (0.75 \times \text{ChunkScore}) + (0.25 \times \text{ParentActScore}) + \text{StakeholderBonus}$$
3. **Concept Anchor Domain Scoring**: All chunks and regulations are pre-scored against 6 stakeholder reference vectors (Airlines, ANSP, Airports, Economics, Maintenance, Flight Crew) using matrix multiplication in NumPy, enabling instant domain filtering and user persona boosting.

### 3.4. Multi-Jurisdiction Knowledge Graph & Regulation Concepts Mesh
The platform maps civil aviation frameworks across 5 primary sources into a cohesive property graph:
- **EASA Easy Access Rules**: 42 consolidated rulebooks covering Air Operations, Continuing Airworthiness, Aerodromes, ATM/ANS, CS-25, etc.
- **FAA Regulations (Title 14 CFR)**: 82 Federal Aviation Regulation parts (Part 25, Part 91, Part 121, Part 135, Part 5, etc.).
- **European Union Law (EUR-Lex Formex)**: 316 binding EU regulations and directives.
- **EUROCAE Technical Standards**: 12 consensus specifications (ED-202A/203A Cybersecurity, ADS-B, etc.).
- **SKYbrary Air Safety Knowledge**: 84 curated operational safety articles and research studies.

A reasoned **17 Core Aviation Concepts Taxonomy** (covering SMS, Fuel Planning, EDTO/ETOPS, FTL, LVO/AWO, Cybersecurity Part-IS, Ramp Inspections, etc.) is overlaid across all provisions. When viewing any regulation, the graph maps applicable concepts and discovers high-confidence **Cross-Regulatory Bridges** connecting equivalent mandates across jurisdictions with precision rule ranking and exact edge-to-drawer count parity.

### 3.5. Offline-First Client Architecture
The frontend leverages browser **IndexedDB** (`idb-keyval`) to locally cache full regulation markdown documents. Once cached, users can run client-side text similarity, view word-by-word diffs, inspect clauses, and explore interactive D3 force simulations without consuming backend bandwidth.
