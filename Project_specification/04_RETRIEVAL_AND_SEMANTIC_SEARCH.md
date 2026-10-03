# 04. Retrieval & Semantic Search Engine

## 1. Dense Vector Engine

The vector store is managed by `LocalVectorIndex` (`ingestion/retrieval/faiss_index.py`), which interfaces with FAISS (`IndexFlatIP`) using L2-normalized vectors to implement exact Cosine Similarity.

### Key Specifications:
- **Embedding Model**: `text-embedding-kalm-embedding-gemma3-12b-2511`
- **Embedding Dimensions**: **3,840 dimensions** (Gemma-3 12B native hidden dimension)
- **Local Inference Server**: LM Studio on `http://localhost:1234/v1`
- **Partitions**:
  - `CHUNK`: 47,849 statutory provisions (`chunk.index`, ~735 MB)
  - `ACT`: 357 authoritative primary regulations (`act.index`, ~5.5 MB)

---

## 2. Asymmetric Instruction-Tuned Embeddings

The Kalm/Gemma-3 embedding model uses asymmetric task prefixes to distinguish passages from search queries:

- **Passage Prefix (Indexing Time)**:
  ```text
  passage: [EU Aviation Regulation {document_id}] {title}. Scope & Text: {clause_text}
  ```
- **Query Prefix (Search Time)**:
  ```text
  query: Given an EU aviation regulation search query, retrieve the authoritative articles and annexes: {user_query}
  ```

This improves legal semantic recall by differentiating between an informational statement and an exploratory statutory question.

---

## 3. Hierarchical 2-Stage Retrieval (Act Prior + Chunk Precision)

A standard bi-encoder query across 48,000 chunks often suffers from **"recital false positives"**—where an airline regulation mentions *"air traffic controller"* in a passing recital and scores higher than the actual governing ANSP regulation.

To solve this, retrieval uses a two-stage hierarchical model:
1. **Act Scoping**: The query vector is matched against all 357 regulations in `act.index`. Top matching regulations receive an Act Prior score $S_{\text{act}} \in [0, 1]$.
2. **Chunk Retrieval**: The query vector retrieves top candidate chunks from `chunk.index`.
3. **Score Combination**:
   $$\text{FinalScore} = \begin{cases} 
   0.75 \times S_{\text{chunk}} + 0.25 \times S_{\text{act}} + \text{Bonus}_{\text{stakeholder}} & \text{if } S_{\text{act}} > 0 \\
   S_{\text{chunk}} + \text{Bonus}_{\text{stakeholder}} & \text{otherwise}
   \end{cases}$$

This guarantees that provisions originating from the primary governing regulation bubble to the top.

---

## 4. Concept Anchor Stakeholder Domain Profiling

Every chunk and document is projected against 6 canonical stakeholder reference anchors:
1. **Airlines / Air Operators (`airline`)**: Part-CAT, Part-ORO, flight operations, crew duty limits, AOC.
2. **ANSP / ATM (`ansp`)**: Air navigation service providers, air traffic controllers, airspace, Single European Sky, ATM/ANS.
3. **Airports / Aerodromes (`airport`)**: Aerodrome operations, runway conditions, ground handling, ADR.
4. **Economics / Charges (`economics`)**: Route charges, airport charges, performance scheme, slot allocation.
5. **Continuing Airworthiness (`maintenance`)**: Part-M, Part-145, Part-CAMO, certifying staff.
6. **Flight Crew Licensing (`flight_crew`)**: Part-FCL, pilot ratings, flight synthetic training devices.

### Matrix Dot Product Scoring:
Because all chunks are stored in FAISS as contiguous 3840D vectors, scoring all 47,849 chunks against the 6 domain anchors is executed via a single BLAS matrix multiplication:
$$\mathbf{S} = \mathbf{V}_{\text{chunks}} \cdot \mathbf{V}_{\text{anchors}}^T \quad (47,849 \times 6)$$
This completes in **under 200 milliseconds** on CPU without requiring external LLM tokens.

---

## 5. Reciprocal Rank Fusion (RRF) Hybrid Search

For hybrid search (`/search/docs` and `hybrid_search.py`), the system merges results from **Dense Vector Search** and **SQLite FTS5 BM25 Keyword Search** using Reciprocal Rank Fusion:

$$\text{RRF Score}(d) = \sum_{m \in \{\text{vector}, \text{bm25}\}} \frac{1}{k + \text{rank}_m(d)}$$
where $k = 60$.

This combines the vocabulary precision of statutory terms (e.g. `8.33 kHz`, `CPDLC`, `AOC`) with the conceptual flexibility of dense vector embeddings.
