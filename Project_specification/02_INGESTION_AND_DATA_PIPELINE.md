# 02. Ingestion & Data Pipeline Specification

## 1. Overview

The ingestion pipeline transforms raw European Union Formex XML archives (and EASA Easy Access XML documents) into clean, structured legal knowledge models. The pipeline is located in `ingestion/pipelines/ingest_formex.py` and supported by `ingestion/core/formex_package.py`.

---

## 2. Ingestion Stages

### Stage 1: Streaming Package Discovery (`iter_formex_packages`)
The pipeline processes directory trees of uncompressed XML files or ZIP publication archives. It groups sibling files by publication package:
- **Primary Acts**: Files ending in `.000101.xml` or containing `<ACT>`.
- **Annexes**: Sibling files containing `<ANNEX>` or numerical publication extensions (e.g., `.01004501.xml`).
- **Administrative Qualifiers**: Commission Decisions (`<DECISION>`), Implementing Decisions, and Corrigenda (`<CORRIGENDUM>`).
- **Master Wrappers**: Master documents with suffix `.doc.xml` or `.toc.xml` that contain no unique substantive legal clauses.

### Stage 2: Aviation Domain Relevance Filtering
Before parsing, each package undergoes multi-pass domain relevance detection:
1. **Title and Header Inspection**: Checks for core European aviation keywords (e.g., `aviation`, `air traffic`, `air operator`, `aerodrome`, `EASA`, `Single European Sky`, `airworthiness`, `Eurocontrol`, `ATM/ANS`, `CPDLC`).
2. **Citation & Legal Basis**: Checks for references to foundational aviation regulations (e.g., Regulation (EU) 2018/1139, Regulation (EC) No 549/2004, Regulation (EU) No 965/2012).
3. Non-aviation packages (e.g. agriculture, maritime fisheries) are filtered out, preserving index purity.

### Stage 3: Annex Consolidation
When a package contains multiple technical annexes:
1. The parser renders each annex into a clean JSON structure:
   ```json
   {
     "tag": "ANNEX",
     "heading": "ANNEX I — Operational Requirements",
     "body": [ ... ]
   }
   ```
2. The annexes are appended directly into the primary regulation's `annexes` list.
3. The chunking pipeline processes the primary act and its attached annexes under a single, authoritative `document_id`.

### Stage 4: Supporting Qualifier Segregation
Decisions and Corrigenda are not stored as standalone primary regulations. Instead:
1. They are parsed into a lightweight representation (Title, CELEX, Date, Summary/Preview).
2. The target regulation reference is extracted via regex (e.g., `pursuant to Regulation (EC) No 549/2004`).
3. The record is inserted into the `qualifiers` table:
   - `qualifier_id`
   - `parent_regulation_id` (CELEX or target document ID)
   - `target_regulation_ref` (e.g. `Regulation 549/2004`)
   - `qualifier_type` (`DECISION`, `CORRIGENDUM`, `NOTE`)
   - `content_text`

### Stage 5: Semantic Chunking
The chunking engine (`ingestion/pipelines/chunking_pipeline.py`) segments the document along statutory boundaries:
- **Preambles & Recitals**: Grouped by recital number `(1)`, `(2)`, etc.
- **Articles & Paragraphs**: Preserves statutory hierarchy `Article 1 > (1) > (a) > (i)`.
- **Annex Sections**: Chunks annex tables, specifications, and appendices with section path tracking.
- Every chunk includes:
  - `source_text`: Raw verbatim text.
  - `embedding_text`: Context-enriched text formatted with title, section hierarchy, and breadcrumbs.

### Stage 6: Vector & FTS5 Indexing
1. **SQLite FTS5 Rebuild**: Automatically rebuilds the `chunks_fts` virtual table using SQLite FTS5 for sub-millisecond BM25 keyword matching.
2. **Dense Vector Generation**: Checks `http://localhost:1234/v1`. If LM Studio is available, generates vectors for new chunks into `chunk.index`, document scopes into `act.index`, and calculates stakeholder domain profiles.

---

## 3. FAA Title 14 CFR Ingestion Pipeline

The FAA ingestion pipeline (`ingestion/parsers/faa_parser.py` and `ingestion/parsers/faa_chunker.py`) processes US Federal Aviation Regulations published as Government Publishing Office (GPO) Title 14 CFR XML volumes:

1. **Volume Decomposition**: FAA XML files bundle dozens of distinct regulations into massive multi-megabyte volumes (e.g. `CFR-2025-title14-vol1.xml`). The parser splits these into individual Part-level documents (`PART 21`, `PART 25`, `PART 91`, `PART 121`, `PART 135`, `PART 145`), each with its own authoritative `document_id`.
2. **Hierarchical Extraction**:
   - Subparts (`SUBPART A`, `SUBPART B`), Subject Groups, and Sections (`SECTION`, `<SECTNO>§ 121.311</SECTNO>`).
   - GPOTABLE conversion: Converts XML tabular data into structured, readable ASCII/Markdown tables.
   - Authority and Source citations parsed and mapped to document metadata.
3. **Aligned Chunking Strategy**: The FAA chunker mirrors the EASA chunking model:
   - Chunk IDs: `FAA:14CFR_PART_{PART}:{SECTION}` (e.g., `FAA:14CFR_PART_121:121.311`).
   - Breadcrumb navigation: `Title 14 CFR > Chapter I > Subchapter G > Part 121 > Subpart K > § 121.311`.
   - Sequential linking: Each chunk records its `previous_chunk_id` and `next_chunk_id` to enable surrounding context navigation.
   - Automatic insertion into SQLite `documents`, `chunks`, and `chunks_fts`.

---

## 4. Manual Regulatory Document Publishing Pipeline

The manual document ingestion pipeline (`api/regulations.py` via `POST /regulations/manual-document`):
1. **Schema Validation**: Validates client-provided `ManualDocumentRequest` containing document metadata and ordered `ManualSectionInput` sections.
2. **Hierarchical Normalization**: Derives document IDs (`MANUAL_{HASH}` or slug) and section chunk identifiers (`MANUAL_{DOC_ID}_S{IDX}`).
3. **Sequential Provision Chaining**: Assigns `previous_chunk_id` and `next_chunk_id` across sections to maintain provision adjacency.
4. **Instant Database Commit**: Writes to SQLite `documents` and `chunks`, triggers FTS5 index update, invalidates the catalog cache, and generates full markdown views for the document viewer.

---

## 5. Pipeline Execution Commands

### Full Ingestion with Auto-Reset:
```powershell
python -m ingestion.pipelines.ingest_formex "ingestion/data/regulation_xml" --reset --defrag
```

### Ingest with a Maximum Package Limit (for Testing):
```powershell
python -m ingestion.pipelines.ingest_formex "ingestion/data/regulation_xml" --limit 50
```

### Ingest and Chunk FAA 14 CFR XML Volume:
```powershell
python -m ingestion.parsers.faa_parser ingestion/data/regulations_xml/CFR-2025-title14-vol1.xml
python -m ingestion.parsers.faa_chunker
```

### Standalone Embedding Generation & Stakeholder Scoring:
```powershell
python -m ingestion.retrieval.embed_chunks
```

### Standalone SQLite FTS5 Full-Text Index Rebuild:
```powershell
python -m ingestion.retrieval.rebuild_fts
```
