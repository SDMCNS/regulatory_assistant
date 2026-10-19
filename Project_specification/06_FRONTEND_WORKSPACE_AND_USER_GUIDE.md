# 06. Frontend Workspace & User Guide

## 1. Frontend Technology Stack
- **Framework**: React 18 + TypeScript + Vite
- **Styling**: Vanilla TailwindCSS with dynamic dark mode
- **Icons**: Lucide React
- **Local Persistence**: IndexedDB via `idb-keyval` (offline regulation storage) + `localStorage` (dossier and preferences)
- **Markdown & Syntax**: Marked with custom HTML sanitizer and highlight injector

---

## 2. Workspace Features

### 2.1. Regulations Catalog & Stakeholder Domain Filter
Located under the **Catalog & Download** tab:
1. **Full Regulation Catalog**: Displays all authoritative primary regulations.
2. **Stakeholder Domain Pills**: Instant filtering by domain:
   - `All Domains`
   - `Airlines / Operators`
   - `ANSP / ATM`
   - `Airports`
   - `Economics / Charges`
   - `Maintenance`
   - `Flight Crew`
3. **Badges**:
   - `EASA Easy Access` vs `EU Regulation`
   - `Cached Offline` indicator (IndexedDB)
   - Stakeholder Domain (`AIRLINE`, `ANSP`, etc.)
   - `⚡ {n} Supporting Acts` (indicates attached decisions & corrigenda)
4. **Multi-Selection & Batch Download**: Users can select multiple regulations and click **Download Selected for In-App Viewing** to cache full text offline into IndexedDB.

---

### 2.2. Interactive Document Viewer & Supporting Acts Drawer
Clicking **View in App** opens the `DocViewerModal`:
1. **Interactive Sections Breakdown vs. Continuous Reading**: Toggle between collapsible statutory sections and traditional document view.
2. **Sequential Provision Stepper & Match Navigation**:
   - Automatically detects all matching clauses when opened from Search Explorer or Assistant citations without filtering out non-matching sections, preserving preceding/succeeding statutory context.
   - **Exact Referenced Match vs. Incidental Matches**: Clearly separates the exact clause clicked or cited from incidental search matches across the document.
     - **Exact Referenced Match**: Receives an emerald border and glowing ring (`ring-2 ring-emerald-400`), a bold `🎯 REFERENCED MATCH` badge on the section header, and a dedicated **`[🎯 Referenced Match]`** button in the header toolbar to immediately return to the focal clause at any time.
     - **Incidental Matches**: Highlighted with amber borders (`border-amber-500/40`), glowing amber rings when active, and an `INCIDENTAL MATCH #X` badge.
   - **Navigation Controls**: Use `Prev` / `Next` stepper buttons, keyboard shortcuts (<kbd>↓</kbd>/<kbd>j</kbd>/<kbd>n</kbd> for Next, <kbd>↑</kbd>/<kbd>k</kbd>/<kbd>p</kbd> for Prev, <kbd>r</kbd> for Referenced Match), or the quick-jump selector dropdown to navigate through all matches.
3. **Client-Side Text Similarity Search**: Real-time substring and fuzzy search across document sections with word frequency counters and match stepping.
4. **Supporting Regulations & Decisions Banner**:
   - If the regulation has supporting acts, an interactive banner appears:
     > 🔗 **This regulation has {n} supporting acts (Decisions, Corrigenda, Implementing acts) that follow from it. Would you like to explore these too?**
   - Clicking **Explore Supporting Acts** expands a curated card grid displaying the title, date, CELEX reference, type badge (`DECISION`, `CORRIGENDUM`), and content snippet of each supporting act.

---

### 2.3. Dedicated Workspace & Cross-Document Overlap
Once regulations are pinned into the Dedicated Workspace:
1. **SQLite FTS5 Querying**: Sub-millisecond keyword and phrase queries run across only the pinned documents.
2. **Overlap Metrics**: Visualizes overlap percentage across documents and displays shared search terms.
3. **Multi-Column Side-by-Side Matrix**: Compares clauses from multiple regulations side-by-side in real-time.
4. **Requirement Lens**: Highlights and counts normative legal verbs:
   - **Mandates**: `shall`, `must`, `is required to` (Red/Amber highlight)
   - **Prohibitions**: `shall not`, `must not`, `may not`, `prohibited` (Rose highlight)
   - **Recommendations**: `should`, `is recommended to` (Blue highlight)
   - **Guidance**: `may`, `can`, `acceptable means` (Emerald highlight)
5. **Dual-Chunk Word Diff Comparator**: Select any two clauses to view word-by-word insertions, deletions, and phrasing differences.
6. **Compliance Working Dossier**: Pin specific clauses, write auditor compliance notes, and export a ready-to-share Markdown audit report.
7. **Surrounding Provision Sequence ("Get Context")**: On any matched clause, click **Get Context** to inspect preceding and subsequent provisions and synthesize practical operational implications using the LLM.

---

### 2.4. Manual Regulatory Document Builder
Located under the **Document Builder** tab (`DocumentBuilder.tsx`):
1. **Custom Manual Authoring**: Author internal flight operations manuals (OM Part A/B/C/D), company SOPs, or compliance procedures.
2. **Structural Hierarchy Enforcement**: Enforces regulatory metadata (Title, Document ID, Source, Date) and ordered sections with Subpart and Subject Group categorization.
3. **Live Chunking Simulation**: Real-time interactive preview simulating how the backend will segment the text into chunks with breadcrumb paths and sequence identifiers.
4. **Instant Ingestion & Indexing**: One-click publishing creates the document, assigns `previous_chunk_id`/`next_chunk_id` linkages, updates SQLite FTS5, flushes the catalog cache, and makes the manual immediately searchable and accessible across the workspace.

---

### 2.5. Autonomous Deep Research Studio & Dual-Tab Inspector
Located under the **Deep Research** tab (`ResearchTab.tsx`):
1. **Multi-Turn Recursive Investigation**: Explores complex compliance questions across depth levels 1 to 3 with automated query generation and gap analysis.
2. **Scientific Adversarial Falsification Gate**: Evaluates candidate chunks against query boundaries, explicitly rejecting out-of-scope provisions (e.g. VTOL/rotorcraft rules for fixed-wing inquiries).
3. **Surrounding Provision Sequence Expansion**: Validated chunks are automatically paired with preceding and subsequent provisions (`window=1`) during fact extraction so definitions, prerequisites, and operational exceptions are integrated into findings.
4. **Dual-Tab Chunk Inspector Modal**:
   - **Focal Provision**: Full text of the cited provision with copy capabilities.
   - **Surrounding Sequence & LLM Context**: AI synthesis of operational implications alongside the chronological sequence of preceding, focal, and subsequent provisions.
5. **Evidence & Negation Audit Ledger**: Transparent accounting of validated vs. negated provisions with one-click access to surrounding provision sequences.
6. **Interactive HTML Report Export**: One-click export generates a self-contained, beautifully styled HTML compliance report featuring collapsible report sections, collapsible appendices/tables, and interactive mouseover tooltips displaying full cited clause texts and operational context.

---

### 2.6. Ask Assistant & Regulatory Chat
Located under the **Ask Assistant** tab (`AskAssistant.tsx`):
1. **Context-Aware Dialogue**: Chat with local or Gemini LLMs with hybrid retrieval across EASA, EU, FAA, Skybrary, Notes, and custom manuals.
2. **Conversation Management**: Create multiple chat threads, auto-title new discussions, and inline-rename conversations directly in the history sidebar.
3. **Referenced Regulatory Standards**: Displays user-friendly, descriptive regulation titles (rather than cryptic database IDs) with direct access to open the full document and jump straight to the cited clause.
4. **HTML Chat Report Export**: Export the conversation thread into a standalone interactive HTML report with expandable sections, mouseover citation cards, and referenced regulatory standards summaries.

---

### 2.7. Knowledge Graph Explorer & Regulation Concepts Workspace
Located under the **Knowledge Graph** tab (`KnowledgeGraphExplorer.tsx`):
1. **Multi-Mode Topology Exploration**:
   - **Compliance Chain (`chain`)**: Trace statutory authority from parent annex down through Implementing Rules (Hard Law) and satisfying AMC/GM clauses (Soft Law).
   - **Blast Radius (`blast`)**: Assess downstream regulatory impact for any proposed clause revision across dependent rules and stakeholder domains.
   - **Concept View (`concept`)**: Map out provisions and governing bodies for any of the 17 core or custom aviation concepts.
   - **Regulation Concepts View (`reg_concept`)**: Select any regulation framework to see its applicable concepts and discover cross-regulatory bridges to other jurisdictions.
2. **Target Framework Selector & Source Filtering**:
   - Filter 536 regulations using categorized source tabs: **`ALL (536)`**, **`EASA (42)`**, **`FAA (82)`**, **`EU (316)`**, **`EUROCAE (12)`**, and **`SKYBRARY (84)`**.
   - Instant search filter by framework name, statutory code, or document title.
   - Clear topic and annex count badges for each regulation.
3. **Interactive D3 Force Simulation Engine**:
   - Dynamically scaled link distances based on node density to eliminate overlapping clusters.
   - Color-coded edge links by semantic relationship (`COVERS_CONCEPT`, `BRIDGES_TO`, `SATISFIES`, `CROSS_REFERENCES`, `SIMILAR_TO`).
   - Drag, zoom, pan, and one-click auto-fit controls.
4. **Interactive Edge Clicking & Rule Parity Drawer**:
   - Clicking any edge line opens a dedicated slide-out drawer detailing the regulatory relationship between the connected nodes.
   - **Exact Count Parity**: The rule count rendered directly on the edge label (e.g. `Bridges (20 rules)`) strictly matches the count of associated rules displayed in the drawer.
   - Each rule item includes statutory code, title, legal force badge (`HARD_LAW`, `SOFT_LAW`), annex, and expandable text snippet.
5. **AI Concept Narratives & Custom Ontology Generation**:
   - **Executive Concept Narrative**: One-click synthesis of regulatory interactions across EU, EASA, and FAA frameworks powered by local or cloud LLMs.
   - **Custom Concept Builder**: Propose and extract custom domain ontologies with automated provision extraction and persistent storage in the knowledge graph.

