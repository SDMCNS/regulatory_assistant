# Regulation Assistant API - Server Description

This API provides a semantic search and LLM (Large Language Model) querying interface over a curated database of regulatory documents, primarily EU Formex and EASA Easy Access Rules. It is designed to be the backend for applications (such as AI Studio agents or single-page web apps) to retrieve regulatory guidelines and ask context-aware questions.

## Core Workflows for Client Applications

### SEARCH Operations
1. **Semantic Search (`GET /search`)**
   Provides lightning-fast semantic vector search over the regulatory database using dense embeddings. The client sends a `query` string, and the server returns the top `top_k` matching chunks of text from the regulations. You can filter by `origin` (e.g., `eu` or `easa`).

2. **Keyword & Acronym Search (`GET /search/keyword`)**
   Performs high-speed BM25 full-text search powered by SQLite FTS5 with Porter stemming. This is ideal for short queries, exact aviation acronyms (e.g., `ATSEP`, `AMC-20`, `FTL`), part numbers, and clause codes (`CAT.OP.MPA`).
   - `query`: The search phrase, acronym, or keywords.
   - `top_k`: Number of results to return (default: `5`).
   - `origin`: Filter by `all`, `eu`, or `easa` (default: `all`).
   - `use_llm`: Boolean flag (`true` by default) to enable LLM query expansion. When enabled, the local LLM generates synonyms and domain acronyms to broaden the search; if set to `false` or if the LLM is unavailable, it runs direct Porter-stemmed keyword matching.

3. **Contextual Search (`GET /search/docs/{document_id}`)**
   Retrieves the **full markdown representation** of an entire document by its ID, with embedded section break comments (`<!-- SECTION_BREAK ... -->`). This is used by the frontend modal to render interactive, collapsible sections without bloating the search payloads.

4. **Document Sections (`GET /search/docs/{document_id}/sections`)**
   Retrieves structured regulatory sections (Subparts, CS specifications, AMCs, Annexes) for a specific document ID. Each section includes metadata (`id`, `title`, `type`) and isolated markdown text.

### LLM Operations
4. **Ask a Question (`POST /llm/ask`)**
   Submit a natural language `prompt` to the local LLM. 
   - **Targeted:** You can provide a specific list of `chunk_ids` (obtained from `/search` or `/search/keyword`) to force the LLM to only read those specific documents.
   - **Section Context:** You can provide `context_sections` (custom sections of text selected by the user) to provide direct context to the LLM and bypass the backend retrieval entirely.
   - **Auto-Search:** If no `chunk_ids` or `context_sections` are provided, the API automatically performs a semantic search behind the scenes, retrieves the relevant documents, and asks the LLM to answer the question based on that context.

5. **Structured Extraction (`POST /llm/extract`)**
   Send an unstructured `text` string and a `json_schema` definition. The API prompts the LLM to extract information from the text and guarantees the response is formatted as a valid JSON object matching the provided schema.

## Integration Note
An OpenAPI 3.1 schema is provided alongside this document (`api_schema.json`), which can be directly imported into Google AI Studio, Postman, or used to automatically generate client-side TypeScript/JavaScript SDKs for your Single Page App.
