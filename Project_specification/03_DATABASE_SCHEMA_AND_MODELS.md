# 03. Database Schema & Data Models

## 1. SQLite Relational Schema (`chunks.db`)

The database is located at `ingestion/data/regulations/sqlite/chunks.db`. It consists of five relational tables and one SQLite FTS5 full-text virtual table.

---

### 1.1. `documents` Table
Stores authoritative, consolidated regulation metadata.

| Column | Type | Description |
| :--- | :--- | :--- |
| `document_id` | `TEXT PRIMARY KEY` | Canonical unique document identifier (e.g. `L_202500024EN.000101.fmx` or `32018R1139`) |
| `title` | `TEXT` | Official title of the regulation |
| `language` | `TEXT` | Document language code (`EN`) |
| `date` | `TEXT` | Publication or adoption date (`YYYYMMDD`) |
| `source` | `TEXT` | Data source (`FORMEX XML` or `EASA XML`) |
| `metadata_json` | `TEXT` | JSON object containing CELEX, OJ collection, doc number, annex counts, amendments, and keywords |

---

### 1.2. `chunks` Table
Stores granular statutory text fragments (recitals, articles, annex paragraphs).

| Column | Type | Description |
| :--- | :--- | :--- |
| `chunk_id` | `TEXT PRIMARY KEY` | Unique chunk identifier (e.g. `L_202500024EN.000101.fmx:Article 2:15`) |
| `document_id` | `TEXT` | Foreign key referencing `documents(document_id)` |
| `chunk_type` | `TEXT` | Hierarchy type (`PREAMBLE_RECITAL`, `ARTICLE`, `ANNEX`, `FINAL_PROVISION`) |
| `section_path` | `TEXT` | JSON list of statutory headings (e.g. `["Title", "Chapter I", "Article 2"]`) |
| `section_numbers` | `TEXT` | Numeric identifier of the section (e.g. `Article 2(1)`) |
| `source_text` | `TEXT` | Raw verbatim legal text of the provision |
| `embedding_text` | `TEXT` | Enriched context string prepared for vectorization |
| `parent_chunk_id` | `TEXT` | ID of parent statutory container |
| `previous_chunk_id` | `TEXT` | ID of preceding sequential chunk |
| `next_chunk_id` | `TEXT` | ID of succeeding sequential chunk |
| `structure_json` | `TEXT` | JSON metadata of section structure |
| `references_json` | `TEXT` | Internal and external citations detected in text |
| `metadata_json` | `TEXT` | Additional chunk properties (word count, modality) |

---

### 1.3. `qualifiers` Table
Stores administrative supporting documents (Decisions, Corrigenda, Notes) segregated from primary regulations.

| Column | Type | Description |
| :--- | :--- | :--- |
| `qualifier_id` | `TEXT PRIMARY KEY` | Unique identifier (e.g. `L_202501064EN.000101.fmx`) |
| `parent_regulation_id` | `TEXT` | Target CELEX or document ID of the regulation this qualifier supports |
| `target_regulation_ref` | `TEXT` | Verbatim text reference (e.g. `Regulation (EC) No 549/2004`) |
| `qualifier_type` | `TEXT` | Classification: `DECISION`, `CORRIGENDUM`, `NOTE`, `IMPLEMENTING_ACT` |
| `celex` | `TEXT` | CELEX number of the qualifier |
| `title` | `TEXT` | Title of the decision or corrigendum |
| `date` | `TEXT` | Publication date |
| `source_file` | `TEXT` | Originating file path |
| `content_text` | `TEXT` | Full text or executive summary of the qualifier |
| `metadata_json` | `TEXT` | Structured qualifier properties |

---

### 1.4. `chunks_fts` (SQLite FTS5 Virtual Table)
Powers millisecond-latency BM25 full-text keyword search across all chunks.

```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    source_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

---

### 1.5. `chunk_stakeholder_scores` Table
Stores Concept Anchor cosine similarity projections across all 6 stakeholder domains.

| Column | Type | Description |
| :--- | :--- | :--- |
| `chunk_id` | `TEXT PRIMARY KEY` | References `chunks(chunk_id)` |
| `score_airline` | `REAL` | Applicability score to Airlines / Air Operators (0.0 to 1.0) |
| `score_ansp` | `REAL` | Applicability score to Air Navigation Service Providers / ATM |
| `score_airport` | `REAL` | Applicability score to Aerodromes / Ground Handling |
| `score_economics` | `REAL` | Applicability score to Economic Regulation & Route Charges |
| `score_maintenance` | `REAL` | Applicability score to Part-M, Part-145, Continuing Airworthiness |
| `score_flight_crew` | `REAL` | Applicability score to Part-FCL Flight Crew Licensing |
| `primary_stakeholder` | `TEXT` | Top-scoring stakeholder domain for this chunk |

---

### 1.6. `document_stakeholder_scores` Table
Aggregated document-level stakeholder profile.

| Column | Type | Description |
| :--- | :--- | :--- |
| `document_id` | `TEXT PRIMARY KEY` | References `documents(document_id)` |
| `score_airline` | `REAL` | Mean airline score across all document chunks |
| `score_ansp` | `REAL` | Mean ANSP score across all document chunks |
| `score_airport` | `REAL` | Mean airport score across all document chunks |
| `score_economics` | `REAL` | Mean economics score across all document chunks |
| `score_maintenance` | `REAL` | Mean maintenance score across all document chunks |
| `score_flight_crew` | `REAL` | Mean flight crew score across all document chunks |
| `primary_stakeholder` | `TEXT` | Primary stakeholder domain for this regulation |

---

## 2. Pydantic Core Models (`ingestion/core/models.py`)

- `LegalFragment`: Canonical representation of any statutory unit.
- `EmbeddingRecord`: Standard container for FAISS storage:
  - `embedding_id`: string
  - `fragment_id`: string
  - `embedding_type`: `EmbeddingType` (`CHUNK`, `ACT`, `ARTICLE`, `REQUIREMENT`)
  - `model`: string (`text-embedding-kalm-embedding-gemma3-12b-2511`)
  - `dimensions`: integer (`3840`)
  - `vector`: `List[float]`
  - `text_hash`: SHA-256 hash of text
