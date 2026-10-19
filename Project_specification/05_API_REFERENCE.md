# 05. FastAPI Backend API Reference

## 1. Service Details
- **Base URL**: `http://localhost:8000`
- **Documentation**: Swagger UI at `/docs`, ReDoc at `/redoc`
- **Prefixes**:
  - `/search`: Core retrieval operations
  - `/regulations`: Catalog, multi-select, qualifiers, and workspace FTS
  - `/llm`: Local LLM operations
  - `/research`: Autonomous deep regulatory research

---

## 2. Endpoints Reference

### 2.1. `GET /search`
Executes dense vector semantic search across the 47,849 statutory chunks with hierarchical Act prior boosting and stakeholder domain prioritization.

#### Parameters:
- `query` (string, required): Search query or regulatory question.
- `top_k` (integer, default: 5): Maximum candidate chunks to return.
- `origin` (string, default: `all`): Filter by `all`, `eu`, or `easa`.
- `use_hyde` (boolean, default: `false`): Enable Hypothetical Document Embeddings via local LLM.
- `stakeholder` (string, optional): Prioritize or filter by domain (`airline`, `ansp`, `airport`, `economics`, `maintenance`, `flight_crew`).

#### Response:
```json
[
  {
    "chunk_id": "L_202500024EN.000101.fmx:Article 1:14",
    "score": 0.7425,
    "raw_vector_score": 0.634,
    "act_prior_score": 0.582,
    "source": "EU",
    "document_id": "L_202500024EN.000101.fmx",
    "path": ["Title", "Article 1"],
    "text": "This Regulation lays down detailed rules...",
    "primary_stakeholder": "airline",
    "stakeholder_scores": {
      "airline": 0.634,
      "ansp": 0.614,
      "airport": 0.511,
      "economics": 0.631,
      "maintenance": 0.591,
      "flight_crew": 0.501
    },
    "metadata": { ... }
  }
]
```

---

### 2.2. `GET /search/docs`
Executes Reciprocal Rank Fusion (RRF) hybrid search (Vector + BM25 FTS5) and returns enriched chunks along with the full markdown document text for direct app rendering.

#### Parameters:
Same parameters as `GET /search`.

#### Response:
Array of `SearchDocResponse` objects containing `markdown_doc: string`.

---

### 2.3. `GET /regulations/catalog`
Returns the comprehensive catalog of European aviation regulations with title search, origin filtering, stakeholder domain filtering, and pagination.

#### Parameters:
- `query` (string, optional): Title or document number search filter.
- `origin` (string, default: `all`): Filter by `all`, `eu`, `easa`.
- `stakeholder` (string, optional): Filter by stakeholder domain (`airline`, `ansp`, `airport`, `economics`, `maintenance`, `flight_crew`).
- `sort_by` (string, default: `chunks`): Sort by `chunks`, `title`, or `date`.
- `sort_order` (string, default: `desc`): `asc` or `desc`.
- `limit` (integer, default: 500): Page size.
- `offset` (integer, default: 0): Pagination offset.

#### Response:
```json
{
  "total": 357,
  "filtered_count": 50,
  "regulations": [
    {
      "document_id": "L_202500024EN.000101.fmx",
      "title": "Commission Implementing Regulation (EU) 2025/24...",
      "origin": "eu",
      "chunk_count": 82,
      "qualifier_count": 1,
      "primary_stakeholder": "airline",
      "metadata": { ... }
    }
  ]
}
```

---

### 2.4. `GET /regulations/{document_id}/qualifiers`
Returns supporting administrative qualifiers (Commission Decisions, Corrigenda, Implementing acts) that follow from the specified regulation.

#### Response:
```json
{
  "document_id": "32004R0549",
  "count": 38,
  "qualifiers": [
    {
      "qualifier_id": "L_202501064EN.000101.fmx",
      "parent_regulation_id": "32004R0549",
      "target_regulation_ref": "Regulation (EC) No 549/2004",
      "qualifier_type": "DECISION",
      "celex": "32025D1064",
      "title": "Commission Decision (EU) 2025/1064 on consistency of performance targets...",
      "date": "20250519",
      "content_preview": "THE EUROPEAN COMMISSION, Having regard to..."
    }
  ]
}
```

---

### 2.5. `POST /regulations/batch`
Fetches full markdown documents and metadata for multiple selected regulation IDs for offline caching in the client application.

#### Request Body:
```json
{
  "document_ids": [
    "L_202500024EN.000101.fmx",
    "L_202401110EN.000101.fmx"
  ]
}
```

---

### 2.6. `POST /regulations/workspace-fts`
High-speed cross-document SQLite FTS5 search restricted specifically to the user's active workspace regulations. Computes cross-document overlap metrics.

#### Request Body:
```json
{
  "query": "fatigue management rest periods",
  "document_ids": ["L_202500024EN.000101.fmx", "Easy Access Rules for Air Operations"],
  "top_k_per_doc": 8,
  "total_top_k": 50
}
```

---

### 2.7. `GET /chunks/{chunk_id}/context`
Fetches the sequential regulatory flow around a specific chunk (window ±N provisions from the same document) and returns an AI synthesis of the legal context and practical operational implications relative to a query.

#### Parameters:
- `chunk_id` (string, path parameter): The identifier of the focal chunk.
- `query` (string, query parameter, required): The user's inquiry or operational question.
- `window` (integer, query parameter, default: 2): Number of preceding and subsequent provisions to retrieve.

#### Response:
```json
{
  "chunk_id": "FAA:14CFR_PART_121:121.311",
  "document_id": "FAA_14CFR_PART_121",
  "document_title": "PART 121—OPERATING REQUIREMENTS: DOMESTIC, FLAG, AND SUPPLEMENTAL OPERATIONS",
  "query": "child restraint systems and seat belt requirements",
  "surrounding_chunks": [
    {
      "chunk_id": "FAA:14CFR_PART_121:121.310",
      "section_path": ["Part 121", "Subpart K", "§ 121.310 Additional emergency equipment."],
      "text": "...",
      "is_target": false,
      "position": "before"
    },
    {
      "chunk_id": "FAA:14CFR_PART_121:121.311",
      "section_path": ["Part 121", "Subpart K", "§ 121.311 Seats, safety belts, and shoulder harnesses."],
      "text": "...",
      "is_target": true,
      "position": "target"
    }
  ],
  "summary": "This section operates within the cabin emergency safety framework..."
}
```

---

### 2.8. `POST /regulations/manual-document`
Authors, chunks, and ingests a custom regulation, standard operating procedure (SOP), or flight manual into the system with full SQLite FTS5 full-text indexing.

#### Request Body:
```json
{
  "title": "Flight Operations Manual Part A - General Policy",
  "source": "AeroLex Internal Manuals",
  "date": "2026-10-01",
  "sections": [
    {
      "section_number": "OM-A 1.1",
      "title": "Corporate Safety Management System",
      "subpart": "Subpart A - General",
      "text": "All flight crew members shall comply with company SMS reporting guidelines..."
    }
  ]
}
```

---

### 2.9. `GET /search/origin-options`
Returns the list of supported regulatory origins (`all`, `eu`, `easa`, `faa`, `manual`).

---

## 3. Regulatory Knowledge Graph & GraphRAG Endpoints (`/graph/*`)

The Knowledge Graph API provides interactive access to the Kùzu property graph engine (`api/graph.py`), supporting D3 force-directed visual subgraphs, blast radius impact tracing, concept ontology navigation, and federated multi-source search.

---

### 3.1. `GET /graph/stats`
Returns global topology metrics for the Kùzu graph database.

#### Response:
```json
{
  "total_provisions": 48215,
  "total_documents": 536,
  "total_annexes": 1284,
  "total_concepts": 17,
  "sources_breakdown": {
    "EASA": 42,
    "FAA": 82,
    "EU": 316,
    "EUROCAE": 12,
    "SKYBRARY": 84
  }
}
```

---

### 3.2. `GET /graph/regulations`
Returns the catalog of all primary regulation documents and technical frameworks in the graph.

#### Response:
```json
[
  {
    "id": "DOC_02_AIR_OPERATIONS",
    "name": "Air Operations (Reg 965/2012)",
    "code": "AIR-OPS (965/2012)",
    "title": "Easy Access Rules for Air Operations (Regulation (EU) No 965/2012)",
    "source": "EASA",
    "total_topics": 412,
    "annex_count": 8
  },
  {
    "id": "DOC_FAA_PART_121",
    "name": "14 CFR Part 121: Operating Requirements: Domestic, Flag, And Supplemental Operations",
    "code": "FAR Part 121",
    "title": "Title 14 CFR Part 121",
    "source": "FAA",
    "total_topics": 284,
    "annex_count": 1
  }
]
```

---

### 3.3. `GET /graph/regulation/concepts`
Retrieves the applicable concepts in a target regulation and computes cross-regulatory bridges to other jurisdictions.

#### Parameters:
- `name` (string, default: `Air Operations`): Regulation title, code, or alias.

#### Response:
```json
{
  "regulation": { "id": "DOC_02_AIR_OPERATIONS", "code": "AIR-OPS (965/2012)", "title": "..." },
  "nodes": [
    { "id": "DOC_02_AIR_OPERATIONS", "label": "AIR-OPS (965/2012)", "type": "REGULATION", "is_anchor": true },
    { "id": "CONCEPT_SAFETY_MANAGEMENT_SYSTEM__SMS", "label": "Safety Management System (SMS)", "type": "CONCEPT", "rule_count": 25 },
    { "id": "CROSS_REG_DOC_08_CONTINUING_AIRWORTHINESS", "label": "AIRWORTHINESS (1321/2014)", "type": "CROSS_REGULATION", "shared_rules": 20 }
  ],
  "links": [
    {
      "source": "DOC_02_AIR_OPERATIONS",
      "target": "CONCEPT_SAFETY_MANAGEMENT_SYSTEM__SMS",
      "type": "COVERS_CONCEPT",
      "label": "Governs (25 rules)",
      "rule_count": 25,
      "rules": [ ... ]
    },
    {
      "source": "CONCEPT_SAFETY_MANAGEMENT_SYSTEM__SMS",
      "target": "CROSS_REG_DOC_08_CONTINUING_AIRWORTHINESS",
      "type": "BRIDGES_TO",
      "label": "Bridges (20 rules)",
      "shared_rules": 20,
      "rule_count": 20,
      "rules": [ ... ]
    }
  ],
  "total_concepts": 14
}
```

---

### 3.4. `GET /graph/concepts`
Returns the list of all available aviation concepts (17 core concepts + custom user concepts).

---

### 3.5. `GET /graph/concept`
Generates a D3 force-directed subgraph for a specific concept showing its governing regulations and key provisions across frameworks.

#### Parameters:
- `name` (string, required): Canonical concept name (e.g. `Fuel Planning & Energy Schemes`, `Safety Management System (SMS)`).

---

### 3.6. `POST /graph/concept/generate`
Dynamically proposes, extracts provisions for, and persists a new custom aviation concept mesh.

#### Request Body:
```json
{
  "name": "Cabin Lithium Battery Thermal Runaway Mitigation",
  "category": "Cabin Safety & Fire Protection",
  "description": "Procedures, containment bags, and firefighting protocols for personal electronic device battery fires."
}
```

---

### 3.7. `POST /graph/concept/narrative`
Generates an executive regulatory narrative synthesizing how a concept is governed across EU, EASA, and FAA frameworks.

#### Request Body:
```json
{
  "concept_name": "Safety Management System (SMS)",
  "provider": "gemini",
  "force_refresh": false
}
```

---

### 3.8. `GET /graph/chain`
Retrieves the interactive Compliance Chain for any provision code: maps parent annex, governing Implementing Rule (Hard Law), satisfying AMCs/GMs (Soft Law), and cross-referenced requirements.

#### Parameters:
- `code` (string, required): Statutory provision code (e.g. `ORO.GEN.200`, `CAT.OP.MPA.175`).

---

### 3.9. `GET /graph/blast`
Performs Blast Radius impact analysis for a changed or proposed clause: traces dependent AMCs, similar provisions across other domains, and affected stakeholder groups.

#### Parameters:
- `code` (string, required): Statutory provision code.

---

### 3.10. `GET /graph/node`
Fetches a complete 360° Inspection Dossier for any node ID or statutory code in the graph.

---

### 3.11. `GET /graph/hyde`
Executes multi-source Hypothetical Document Embeddings (HyDE) discovery across federated knowledge bases.

#### Parameters:
- `q` (string, required): Operational intent or regulatory question.
- `sources` (string, default: `EASA,EU,FAA,SKYBRARY,EUROCAE`): Comma-separated active sources.
- `skybrary_topics` (string, optional): Specific SKYbrary sub-categories.
- `top_k` (integer, default: 12): Maximum candidate provisions to return.

---

### 3.12. `GET /graph/search`
Direct keyword and code search across Kùzu graph and secondary sources.

