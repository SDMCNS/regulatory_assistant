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
2. **Client-Side Text Similarity Search**: Real-time substring and fuzzy search across document sections with word frequency counters and match stepping.
3. **Supporting Regulations & Decisions Banner**:
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
