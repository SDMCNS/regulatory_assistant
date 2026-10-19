# Regulation Assistant API - Server Description

This API provides a semantic search and LLM (Large Language Model) querying interface over a curated database of regulatory documents, including **EASA Easy Access Rules**, **EU Formex Aviation Acts**, **FAA Title 14 CFR Regulations**, and **Custom User-Authored Operating Manuals**. It is designed to be the backend for applications (such as AI Studio agents, Single Page Apps, or compliance auditing workflows) to retrieve regulatory guidelines, inspect sequential legal provisions, and ask context-aware questions.

## Core Workflows for Client Applications

### SEARCH Operations
1. **Semantic Search (`GET /search`)**
   Provides lightning-fast semantic vector search over the regulatory database using dense embeddings. The client sends a `query` string, and the server returns the top `top_k` matching chunks of text from the regulations. You can filter by `origin` (`all`, `eu`, `easa`, `faa`, `manual`, `skybrary`, `note`).

2. **Keyword & Acronym Search (`GET /search/keyword`)**
   Performs high-speed BM25 full-text search powered by SQLite FTS5 with Porter stemming. This is ideal for short queries, exact aviation acronyms (e.g., `ATSEP`, `AMC-20`, `FTL`, `SMS`, `FAR`), part numbers, and clause codes (`CAT.OP.MPA`, `§ 25.1309`, `§ 121.311`).
   - `query`: The search phrase, acronym, or keywords.
   - `top_k`: Number of results to return (default: `5`).
   - `origin`: Filter by `all`, `eu`, `easa`, `faa`, or `manual` (default: `all`).
   - `use_llm`: Boolean flag (`true` by default) to enable LLM query expansion. When enabled, the local LLM generates synonyms and domain acronyms to broaden the search; if set to `false` or if the LLM is unavailable, it runs direct Porter-stemmed keyword matching.

3. **Origin Filter Options (`GET /search/origin-options`)**
   Returns the complete list of supported origin filters for dropdowns and filtering chips (`all`, `eu`, `easa`, `faa`, `manual`, `skybrary`, `note`).

4. **Contextual Document Search (`GET /search/docs/{document_id}`)**
   Retrieves the **full markdown representation** of an entire document by its ID, with embedded section break comments (`<!-- SECTION_BREAK ... -->`). This is used by the frontend modal to render interactive, collapsible sections without bloating the search payloads.

5. **Document Sections (`GET /search/docs/{document_id}/sections`)**
   Retrieves structured regulatory sections (Subparts, CS specifications, AMCs, Annexes, CFR Parts) for a specific document ID. Each section includes metadata (`id`, `title`, `type`) and isolated markdown text.

### CHUNKS & CONTEXT Operations
6. **Surrounding Provision Context & Implications (`GET /chunks/{chunk_id}/context`)**
   Retrieves the sequential regulatory flow around a given chunk (window ±N provisions from the same document) and generates an AI synthesis of the broader context and operational implications relative to a query:
   - `chunk_id`: The focal chunk identifier.
   - `query`: The active operational or compliance question.
   - `window`: Number of preceding and subsequent provisions to fetch (default: `2`).
   Returns `surrounding_chunks` (with sequence position `before`, `target`, `after`) and the LLM `summary`.

### LLM Operations
7. **Ask a Question & Conversational Assistant (`POST /llm/ask`)**
   Submit a natural language `prompt` to the local or cloud LLM with full context awareness and citation traceability. 
   - **Multi-Turn Chat History:** Pass an array of previous `messages` (`role: user | assistant`, `content`) to maintain conversational state across multi-turn compliance consultations.
   - **Origin Filtering:** Restrict regulatory context via `origin` (`all`, `eu`, `easa`, `faa`, `manual`, `skybrary`, `note`).
   - **Targeted:** Provide a specific list of `chunk_ids` (obtained from `/search` or `/search/keyword`) to constrain the LLM to inspect only those specific provisions.
   - **Section Context:** Provide `context_sections` (custom sections of text selected by the user) to supply direct context to the LLM and bypass backend retrieval.
   - **Hybrid Auto-Retrieval:** If no `chunk_ids` or `context_sections` are provided, the API automatically performs a hybrid semantic + BM25 keyword search behind the scenes, retrieves the most relevant provisions, and synthesizes answers based on that context.
   - **Title Generation:** Set `generate_title: true` on initial conversation turns to have the model generate a succinct 3-5 word discussion title.
   - **Structured Citations & References:** Returns `answer`, `referenced_chunks` (complete with `chunk_id`, `document_id`, `document_title`, `source`, and snippet text), and contextual follow-up inquiries.

### RESEARCH Operations
8. **Autonomous Deep Research (`POST /research/jobs`, `GET /research/jobs`, `GET /research/jobs/{job_id}`)**
   Empowers clients to conduct non-blocking, recursive exploration across the entire regulatory database:
   - `POST /research/jobs`: Queues an asynchronous deep research job with `query`, `recursion_level` (1-3), and optional cloud LLM parameters (`gemini_api_key`, `gemini_model`). Supports scientific multi-perspective synthesis:
     - **Adversarial Falsification Gate**: Validates or actively negates candidate chunks to purge out-of-scope provisions (e.g., rotorcraft/VTOL clauses for fixed-wing queries).
     - **Surrounding Provision Sequence Expansion**: Validated candidate chunks automatically pull preceding and subsequent provisions (window ±1) into the fact extraction prompt, capturing definitions, parent conditions, and exceptions.
     - **Self-Critique & Gap Spotting**: After synthesizing the initial report, the engine critically audits its own report for aspects that are not satisfactorily explained, formulating structured sub-research tasks (`research_gaps` with `gap_id`, `topic`, `sub_query`, and `rationale`). This self-audit never blocks initial report delivery.
     - **SKYbrary Bookshelf Matching**: Matches finished reports against official SKYbrary aviation safety documents and guidance papers (`skybrary_reading_materials`), presenting them as additional recommended reading materials with relevance percentages (0–100%), match rationales, excerpts, and direct links to official PDFs and portal articles.
   - `POST /research/jobs/{job_id}/generate-comprehensive`: Triggers background comprehensive report synthesis. Executes targeted hybrid retrieval across identified regulatory gaps, extracts supplemental facts with citations, and generates a unified comprehensive report resolving each gap while retaining the initial report.
   - `GET /research/jobs`: Returns a lightweight list of historical and active research jobs (including `has_gaps` and `comprehensive_status`).
   - `GET /research/jobs/{job_id}`: Returns the full report in markdown, list of consulted regulations, evaluation summary (`surrounding_context_expanded: true`), dictionary of referenced chunk texts supporting interactive tooltips and citation traceability (`[Citation](chunk:CHUNK_ID)`), identified `research_gaps`, `comprehensive_report_markdown`, and curated `skybrary_reading_materials`.
   - `DELETE /research/jobs/{job_id}`: Removes a research job from the persistent SQLite queue.
   - `POST /research/validate-gemini`: Validates connectivity and API key verification for Google Gemini Cloud models.

### REGULATIONS Operations
9. **Regulations Catalog & Dedicated Workspace (`/regulations/...`)**
   - `GET /regulations/catalog`: Browse, filter by origin (`eu`, `easa`, `faa`, `manual`, `skybrary`), and search the complete regulation catalog at the title level.
   - `POST /regulations/manual-document`: Ingest custom company manuals, SOPs, or flight operations manuals. The backend enforces structural regulatory hierarchy (`chunk_id`, sequential linking `previous_chunk_id`/`next_chunk_id`, `embedding_text`), saves to SQLite, rebuilds the BM25 full-text index, and makes the manual immediately searchable across all tools.
   - `GET /regulations/notes`: Retrieve a list of user-authored notes.
   - `POST /regulations/notes`: Create a new user-authored note, chunk it, and save it to the database.
   - `GET /regulations/notes/{id}`: Retrieve a single user-authored note and its structural sections.
   - `POST /regulations/notes/{id}/embed`: Generate FAISS vector embeddings for the chunks of a specific note.
   - `POST /regulations/batch-download`: Fetch full markdown representations of multiple selected regulations for in-app offline caching via IndexedDB or external export.
   - `POST /regulations/workspace-fts`: High-speed SQLite FTS5 search restricted specifically to selected active workspace regulations, computing cross-document overlap metrics, shared terms, and matching clauses.
   - `GET /regulations/skybrary/categories`: Retrieve all 70+ Bookshelf publication categories with publication and chunk counts.

### SKYBRARY BOOKSHELF Operations
10. **Dedicated Bookshelf Search (`GET /search/skybrary` or `GET /regulations/skybrary/search`)**
   - High-speed FTS BM25 search across 228,000+ chunks with multi-criteria filtering:
     - `query`: Free-text query, phrases, or aviation acronyms.
     - `category`: Filter by safety category (e.g., `Accident Investigation`, `Human Factors`, `Runway Incursion`, `Airworthiness`, `Single European Sky`).
     - `author`: Filter by publishing authority (e.g., `EASA`, `FAA`, `NTSB`, `UK AAIB`, `EUROCONTROL`, `ICAO`).
     - `top_k`: Number of results (default `10`).
     - `sort_by`: `relevance` or `date`.
   - Returns enriched items with source text, page numbers, direct PDF download links (`pdf_url`), and online article links (`summary_url`).

### KNOWLEDGE GRAPH & GRAPHRAG Operations
11. **Regulatory Knowledge Graph Explorer (`/graph/...`)**
    Provides high-performance graph database traversal and GraphRAG context generation powered by Kùzu:
    - `GET /graph/stats`: Returns node and edge counts across the knowledge graph (documents, annexes, provisions, concepts, stakeholders, and legal relationship types).
    - `GET /graph/sources`: Returns the multi-source federated catalog (EASA, EU, FAA, SKYbrary, EUROCAE) and the full taxonomy of Skybrary sub-topics for selective filtering.
    - `GET /graph/search`: High-speed autocomplete and keyword search across the knowledge graph and federated sources:
      - `q`: Search term, clause code, or keyword.
      - `sources`: Comma-separated list of active sources (`EASA`, `EU`, `FAA`, `SKYBRARY`, `EUROCAE`).
      - `skybrary_topics`: Comma-separated list of selected Skybrary sub-topics.
    - `GET /graph/hyde`: Hypothetical Document Embeddings (HyDE) vector discovery. Translates natural language operational queries into synthetic regulatory anchors, embeds them, and discovers nearest regulatory nodes across all federated sources:
      - `q`: Natural language scenario or regulatory query.
      - `sources`: Comma-separated list of active sources.
      - `skybrary_topics`: Comma-separated sub-topic filters.
      - `top_k`: Maximum candidate provisions to return (default: `12`).
    - `GET /graph/chain`: Generates a compliance chain subgraph in D3 force-directed format (`nodes` and `links`):
      - `code`: Provision code (e.g. `CAT.OP.MPA.180`, `ORO.GEN.200`).
      - Returns visual hierarchy connecting the anchor Implementing Rule to its parent Annex, downstream AMCs, GMs, governed Concepts, and Stakeholders.
    - `GET /graph/blast`: Generates a blast radius dependency subgraph in D3 force-directed format:
      - `code`: Target provision code.
      - Visualizes all rules citing this provision (upstream impact) and all rules cited by it (downstream dependencies).
    - `GET /graph/concept`: Generates a concept ontology subgraph in D3 force-directed format:
      - `name`: Aviation concept name or substring (e.g. `Fuel`, `SMS`, `FTL`, `Airworthiness`).
      - Connects the concept to governing provisions across all regulatory annexes.
    - `GET /graph/node`: Comprehensive 360° inspection of any provision, annex, concept, or stakeholder:
      - `id` or `code`: Node identifier or provision code.
      - Returns verbatim text, legal hierarchy, downstream soft law (AMCs/GMs), cross-references, semantic parallels (`SIMILAR_TO`), and ready-to-prompt GraphRAG markdown context.
    - `GET /graph/path`: Computes and renders the shortest compliance citation path connecting two provisions in the knowledge graph:
      - `start`: Origin provision code.
      - `end`: Destination provision code.

### USER DOCUMENT UPLOAD & DIAGRAM EXTRACTION Operations
12. **User Document Ingestion Pipeline (`/documents/...`)**
    Supports multi-format document analysis, multimodal diagram extraction, and executive lifecycle management:
    - `POST /documents/analyze`:
      - Uploads a user PDF, Word document, text file, or XML package.
      - Performs automated format detection (`EU_FORMEX_XML`, `EASA_XML`, `FAA_CFR_XML`, or `USER_SKYBRARY`).
      - Detects page-level diagrams and tables (`ingestion/user_docs/detector.py`).
      - Computes content SHA-256 hash and compares against existing corpus documents to spot duplicates or newer editions.
      - Returns analysis results, detected diagrams, matches, and suggested executive action (`none`, `supersede`, `suppress`).
    - `POST /documents/confirm-ingest`:
      - Confirms ingestion of the staged document into SQLite chunks, FAISS vector embeddings, and FTS5 index.
      - Executes executive resolution (`supersede` deactivates older editions; `suppress` marks conflicting drafts as inactive; `none` keeps both).
      - Integrates with Gemini Vision for automated HyDE graphical summarization of detected diagrams.

## Integration Note
An OpenAPI 3.1 schema is provided alongside this document (`api_schema.json`), which can be directly imported into Google AI Studio, Postman, or used to automatically generate client-side TypeScript/JavaScript SDKs for your Single Page App.

## Setup and Data Population
For a complete overview of ingestion pipelines for FAA, Formex, EASA, and Custom Manuals, see [setup_and_data_population.md](setup_and_data_population.md).


