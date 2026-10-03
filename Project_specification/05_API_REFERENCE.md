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
