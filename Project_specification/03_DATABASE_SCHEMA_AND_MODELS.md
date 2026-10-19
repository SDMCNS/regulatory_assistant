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

---

## 3. Kùzu Embedded Property Graph Schema (`kuzu_db`)

The graph engine is built using **Kùzu** (`ingestion/data/kuzu_db`), a lightweight, embedded property graph database optimized for sub-millisecond multi-hop Cypher queries and low-memory graph traversals.

### 3.1. Node Tables

| Node Table | Primary Key | Key Properties | Description |
| :--- | :--- | :--- | :--- |
| `RegulationDocument` | `id: STRING` | `title: STRING`, `source: STRING`, `total_topics: INT64`, `code: STRING` | High-level regulatory acts and standard suites across 5 jurisdictions (EASA, FAA, EU, EUROCAE, SKYbrary; total 536 documents). |
| `Annex` | `id: STRING` | `code: STRING`, `title: STRING`, `source_doc_id: STRING` | Technical annexes, parts, or appendices (e.g. Part-CAT, Part-ORO, Part-MED). |
| `Provision` | `id: STRING` | `code: STRING`, `title: STRING`, `content_type: STRING`, `legal_force: STRING`, `text: STRING`, `subject: STRING` | Granular statutory clauses, certification specifications (CS), acceptable means of compliance (AMC), guidance material (GM), and federal regulations (FAR). |
| `Concept` | `id: STRING` | `name: STRING`, `category: STRING`, `description: STRING` | Standardized and custom aviation domain concepts (e.g. Safety Management System, Fuel Planning, EDTO/ETOPS, Part-IS). |
| `Organization` | `id: STRING` | `name: STRING`, `type: STRING`, `country: STRING` | Governing agencies (EASA, FAA, ICAO), national aviation authorities, or industry standard bodies. |

### 3.2. Relational Edge Tables

| Edge Type | From Node $\to$ To Node | Properties | Semantics |
| :--- | :--- | :--- | :--- |
| `CONTAINS_ANNEX` | `RegulationDocument` $\to$ `Annex` | None | Structural hierarchy linking acts to sub-annexes. |
| `BELONGS_TO_ANNEX` | `Provision` $\to$ `Annex` | None | Maps provisions to their parent technical annex. |
| `GOVERNS_CONCEPT` | `Provision` $\to$ `Concept` | `relevance_score: INT64`, `source: STRING` | Semantic association where a provision establishes requirements for an aviation concept. |
| `BRIDGES_TO` | `Concept` $\to$ `RegulationDocument` | `shared_rules: INT64`, `rule_count: INT64` | Cross-regulatory bridge connecting a concept to external governing regulations. |
| `COVERS_CONCEPT` | `RegulationDocument` $\to$ `Concept` | `rule_count: INT64` | Direct regulatory mandate over a concept domain. |
| `SATISFIES` | `Provision` $\to$ `Provision` | `weight: DOUBLE` | Soft Law (AMC/GM) satisfying Hard Law (Implementing Rule). |
| `CROSS_REFERENCES` | `Provision` $\to$ `Provision` | `citation_text: STRING` | Explicit statutory citations and inter-clause references. |
| `SIMILAR_TO` | `Provision` $\to$ `Provision` | `similarity_score: DOUBLE` | Semantic vector cosine similarity between provisions ($\ge 0.82$). |
| `AMENDS` | `RegulationDocument` $\to$ `RegulationDocument` | `date: STRING` | Legal amendment tracking between historical and amending acts. |

### 3.3. Core Aviation Concepts Taxonomy (`CONCEPT_TAXONOMY`)

The system ships with 17 canonical aviation concepts compiled into high-precision regex patterns for automated rule scoring and classification:
1. `CONCEPT_SAFETY_MANAGEMENT_SYSTEM__SMS` (Governance & Compliance)
2. `CONCEPT_FUEL_PLANNING___ENERGY_SCHEMES` (Flight Operations)
3. `CONCEPT_EXTENDED_DIVERSION_TIME_OPERATIONS__EDTO_ETOPS` (Operational Authorizations)
4. `CONCEPT_FLIGHT_TIME_LIMITATIONS___FATIGUE__FTL` (Crew Licensing & Rest)
5. `CONCEPT_ALL_WEATHER___LOW_VISIBILITY_OPERATIONS__LVO_AWO` (All-Weather Operations)
6. `CONCEPT_STERILE_FLIGHT_DECK_PROCEDURE` (Cockpit Procedures)
7. `CONCEPT_DANGEROUS_GOODS__DG` (Cargo & Special Loads)
8. `CONCEPT_ALTIMETER_SETTING___RVSM` (Navigation & Separation)
9. `CONCEPT_RAMP_INSPECTIONS__SAFA_SACA` (Safety Oversight)
10. `CONCEPT_MASS_AND_BALANCE__W_B` (Aircraft Performance)
11. `CONCEPT_CONTINUING_AIRWORTHINESS___MAINTENANCE` (Airworthiness)
12. `CONCEPT_AERODROME_DESIGN___RUNWAY_SAFETY` (Aerodromes & Ground)
13. `CONCEPT_PILOT___CREW_LICENSING__PART_FCL___MED` (Personnel Licensing)
14. `CONCEPT_AIR_TRAFFIC_MANAGEMENT___AIRSPACE__ATM_ANS_SERA` (Air Traffic & Airspace)
15. `CONCEPT_UNMANNED_AIRCRAFT_SYSTEMS___U_SPACE` (UAS & Drones)
16. `CONCEPT_INFORMATION_SECURITY___CYBERSECURITY__PART_IS` (Cybersecurity & Security)
17. `CONCEPT_OCCURRENCE_REPORTING___JUST_CULTURE` (Safety Intelligence)

