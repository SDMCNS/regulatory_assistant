# 01. System Architecture Specification

## 1. Executive Overview

The **Regulation Assistant (AeroLex EU)** is an enterprise-grade regulatory intelligence platform designed specifically for European Union (EU) and European Union Aviation Safety Agency (EASA) aviation law. It ingests thousands of complex legal publication packages, unifies fragmented technical annexes, segregates non-regulatory administrative qualifiers (Decisions and Corrigenda), and powers high-precision hybrid retrieval (Dense Vector + BM25 Full-Text Search).

The system integrates local open-weights AI inference via **LM Studio** (`text-embedding-kalm-embedding-gemma3-12b-2511` producing 3,840-dimensional vectors) with SQLite FTS5, providing completely private, local, and auditable search and synthesis without requiring external cloud API dependencies.

---

## 2. High-Level Component Architecture

```mermaid
graph TD
    subgraph DataSources["Data Sources (EU & EASA)"]
        FMX["Formex XML / ZIP Archives<br/>(30,000+ packages)"]
        EASA["EASA Easy Access Rules<br/>(XML / AMC / GM)"]
    end

    subgraph IngestionPipeline["Ingestion & Consolidation Pipeline"]
        PKG["Package Classifier & Streamer<br/>(iter_formex_packages)"]
        PARSER["Euroform & Formex Parsers<br/>(XML to Canonical JSON)"]
        MERGER["Annex Consolidator<br/>(Groups 1,200+ annexes into parents)"]
        ROUTER["Qualifier Router<br/>(Segregates Decisions & Corrigenda)"]
        CHUNKER["Legal Hierarchy Chunker<br/>(Articles, Recitals, Annexes)"]
    end

    subgraph DualStorage["Dual-Layer Storage Architecture"]
        SQLITE[("SQLite Database (chunks.db)<br/>- documents (357 acts)<br/>- chunks (47,849 clauses)<br/>- qualifiers (343 acts)<br/>- chunks_fts (BM25 FTS5)<br/>- stakeholder_scores")]
        FAISS[("FAISS Vector Index (LocalVectorIndex)<br/>- chunk.index (3840D)<br/>- act.index (3840D)<br/>- 6x Concept Anchor Vectors")]
    end

    subgraph Inference["Local AI Inference (LM Studio)"]
        EMBED["text-embedding-kalm-embedding-gemma3-12b<br/>(3840-dimensional embeddings)"]
        LLM["google/gemma-4-e4b<br/>(Hypothetical Docs & Q&A)"]
    end

    subgraph BackendAPI["FastAPI Backend Service (:8000)"]
        SEARCH_API["/search & /search/docs<br/>(Hierarchical 2-Stage & Hybrid RRF)"]
        REGS_API["/regulations/catalog & /batch<br/>(Multi-select & Offline Cache)"]
        QUAL_API["/regulations/{id}/qualifiers<br/>(Supporting Decisions & Corrigenda)"]
        FTS_API["/regulations/workspace-fts<br/>(Cross-regulation Overlap Analysis)"]
    end

    subgraph FrontendApp["React + Vite Single Page Application (:5173)"]
        CATALOG_UI["Catalog & Domain Filter<br/>(Airlines, ANSP, Airports, Economics)"]
        VIEWER_UI["Doc Viewer & Supporting Acts Banner<br/>(Continuous & Section-based)"]
        WORKSPACE_UI["Dedicated Overlap Workspace<br/>(Multi-column comparison & Word Diff)"]
        LENS_UI["Requirement Lens & Working Dossier<br/>(SHALL/SHOULD modal verb analyzer)"]
    end

    FMX --> PKG
    EASA --> PKG
    PKG --> PARSER
    PARSER --> MERGER
    PARSER --> ROUTER
    MERGER --> CHUNKER
    ROUTER --> SQLITE
    CHUNKER --> SQLITE
    SQLITE --> EMBED
    EMBED --> FAISS

    DualStorage --> BackendAPI
    Inference --> BackendAPI
    BackendAPI --> FrontendApp
```

---

## 3. Core Architectural Tenets

### 3.1. Package-Level Ingestion vs. File-Level Clutter
Earlier ingestion pipelines processed every XML file in isolation, generating over 1,400 fragmented document records. Under that paradigm, technical annexes containing critical operational specifications (e.g. Part-CAT, Part-ORO) were stored as orphaned documents without titles, leaving user searches disconnected from parent acts.

The current architecture operates at the **Publication Package** level:
1. Identifies the primary regulation act (`.000101.xml` or `<ACT>`).
2. Gathers attached annexes (`.01004501.xml`, `<ANNEX>`) and nests them directly inside the parent regulation JSON.
3. Segregates administrative qualifiers (Commission Decisions and Corrigenda) into a dedicated relational table linked back to the target regulation.
4. Drops phantom master wrappers (`.doc.xml`, `.toc.xml`).

### 3.2. Dual-Layer Storage
- **Relational & Keyword Layer (SQLite)**: Stores clean legal document metadata, full markdown text, individual chunks, cross-document relations, and SQLite FTS5 indices for BM25 keyword matching.
- **Dense Vector Layer (FAISS `IndexFlatIP`)**: Stores normalized 3,840-dimensional vector embeddings for cosine similarity search. Partitioned into `CHUNK` (fine-grained clauses) and `ACT` (document-level scope).

### 3.3. Hierarchical Retrieval & Domain Anchors
Instead of flat chunk similarity, retrieval uses a 2-stage hierarchical score:
1. **Act-Level Prior**: The user query is matched against the 357 primary regulation scopes (`act.index`).
2. **Chunk-Level Search**: Chunks belonging to top-ranking regulations receive an Act Prior bonus:
   $$\text{Score} = (0.75 \times \text{ChunkScore}) + (0.25 \times \text{ParentActScore}) + \text{StakeholderBonus}$$
3. **Concept Anchor Domain Scoring**: All chunks and regulations are pre-scored against 6 stakeholder reference vectors (Airlines, ANSP, Airports, Economics, Maintenance, Flight Crew) using matrix multiplication in NumPy, enabling instant domain filtering and user persona boosting.

### 3.4. Offline-First Client Architecture
The frontend leverages browser **IndexedDB** (`idb-keyval`) to locally cache full regulation markdown documents. Once cached, users can run client-side text similarity, view word-by-word diffs, and inspect clauses without consuming backend bandwidth.
