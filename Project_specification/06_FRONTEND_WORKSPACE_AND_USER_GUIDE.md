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
