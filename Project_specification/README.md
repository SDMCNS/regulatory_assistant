# Project Specification & Technical Architecture Documentation

Welcome to the **AeroLex EU / Regulation Assistant** technical documentation directory. This folder contains the authoritative technical architecture, schema specifications, retrieval algorithms, API documentation, and operational onboarding guides for developers, systems architects, and auditors.

---

## Documentation Index

| Document | Title | Key Contents |
| :--- | :--- | :--- |
| [01. System Architecture](file:///c:/Projects/Regs/Project_specification/01_SYSTEM_ARCHITECTURE.md) | High-Level Architecture & Tenets | System topology, Mermaid architecture diagram, package grouping vs file clutter, dual-layer storage (SQLite + FAISS), and offline-first client architecture. |
| [02. Ingestion & Data Pipeline](file:///c:/Projects/Regs/Project_specification/02_INGESTION_AND_DATA_PIPELINE.md) | Ingestion & Package Consolidation | Formex/EASA XML parsing, package streaming (`iter_formex_packages`), annex consolidation (1,275 annexes merged), qualifier segregation (343 acts), and chunking. |
| [03. Database Schema & Models](file:///c:/Projects/Regs/Project_specification/03_DATABASE_SCHEMA_AND_MODELS.md) | Relational Schema & Pydantic | Complete SQLite table definitions (`documents`, `chunks`, `qualifiers`, `chunks_fts`, `chunk_stakeholder_scores`, `document_stakeholder_scores`) and Pydantic models. |
| [04. Retrieval & Semantic Search](file:///c:/Projects/Regs/Project_specification/04_RETRIEVAL_AND_SEMANTIC_SEARCH.md) | Vector Search & Domain Anchors | 3840D Gemma-3 12B embeddings, Hierarchical 2-stage retrieval (Act prior + Chunk precision), Concept Anchor stakeholder profiling (Airlines, ANSP, Airports, Economics), and Hybrid RRF. |
| [05. API Reference](file:///c:/Projects/Regs/Project_specification/05_API_REFERENCE.md) | FastAPI Endpoint Reference | Complete endpoint signatures, request/response models, query parameters, and example JSON payloads for `/search`, `/regulations/*`, `/llm/*`, and `/research/*`. |
| [06. Frontend Workspace Guide](file:///c:/Projects/Regs/Project_specification/06_FRONTEND_WORKSPACE_AND_USER_GUIDE.md) | UI Features & User Guide | Regulations Catalog, Stakeholder Domain pills, Supporting Acts exploration banner, Requirement Lens (SHALL/SHOULD normative verb analysis), and Word Diff. |
| [07. Operations & Deployment](file:///c:/Projects/Regs/Project_specification/07_OPERATIONS_AND_DEPLOYMENT.md) | Setup & Developer Onboarding | Hardware prerequisites, LM Studio setup, running via `start.py`, rebuilding data/embeddings, and project directory layout. |

---

*Generated and verified for the AeroLex EU regulatory platform on branch `feature/formex-ingestion-pipeline`.*
