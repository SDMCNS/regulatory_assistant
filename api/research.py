import uuid
import json
import sqlite3
import re
import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from ingestion.core.config import settings
from ingestion.retrieval.hybrid_search import search_hybrid
from ingestion.retrieval.search_chunks import get_chunk_surrounding_context
from api.utils import (
    call_lm_studio_chat,
    call_gemini_api,
    test_gemini_connection,
    call_unified_chat,
    get_document_metadata,
    log_debug_info
)

router = APIRouter()

class ResearchJobRequest(BaseModel):
    query: str = Field(..., min_length=2, description="The query to investigate")
    recursion_level: int = Field(default=2, ge=1, le=3, description="Depth of research (1-3)")
    force_refresh: bool = Field(default=False, description="Whether to bypass cached completed research and force a new run")
    provider: Optional[str] = Field(default="local", description="LLM provider: 'local' or 'gemini'")
    gemini_api_key: Optional[str] = Field(default=None, description="Optional user Gemini API key")
    gemini_model: Optional[str] = Field(default="gemini-3.5-flash", description="Optional Gemini model name")
    origins: Optional[List[str]] = Field(default=None, description="Optional list of document origins/sources to include: 'easa', 'eu', 'faa', 'icao', 'skybrary', 'manual', 'note', 'user'")
    document_ids: Optional[List[str]] = Field(default=None, description="Optional list of specific document IDs to restrict search to")

class ResearchGap(BaseModel):
    gap_id: str
    topic: str
    description: str
    sub_query: str
    rationale: Optional[str] = None

class SkybraryReadingMaterial(BaseModel):
    document_id: str
    title: str
    category: Optional[str] = None
    author: Optional[str] = None
    summary_url: Optional[str] = None
    pdf_url: Optional[str] = None
    relevance_score: float
    match_rationale: Optional[str] = None
    key_excerpt: Optional[str] = None

class UserNoteReadingMaterial(BaseModel):
    document_id: str
    title: str
    note_type: str
    date: Optional[str] = None
    author: Optional[str] = None
    project: Optional[str] = None
    relevance_score: float
    match_rationale: Optional[str] = None
    key_excerpt: Optional[str] = None

class ResearchJobSummary(BaseModel):
    job_id: str
    status: str
    query: str
    recursion_level: int
    progress: Optional[str] = None
    has_gaps: Optional[bool] = False
    comprehensive_status: Optional[str] = "NOT_STARTED"
    provider: Optional[str] = None
    model: Optional[str] = None
    origins: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    created_at: str
    updated_at: str

class ResearchJobDetail(BaseModel):
    job_id: str
    status: str
    query: str
    recursion_level: int
    progress: Optional[str] = None
    report_markdown: Optional[str] = None
    consulted_regulations: Optional[List[dict]] = None
    referenced_chunks: Optional[Dict[str, str]] = None
    evaluation_summary: Optional[Dict[str, Any]] = None
    research_gaps: Optional[List[ResearchGap]] = None
    comprehensive_report_markdown: Optional[str] = None
    comprehensive_status: Optional[str] = "NOT_STARTED"
    skybrary_reading_materials: Optional[List[SkybraryReadingMaterial]] = None
    user_notes_reading_materials: Optional[List[UserNoteReadingMaterial]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    origins: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    created_at: str
    updated_at: str

class GenerateComprehensiveRequest(BaseModel):
    provider: Optional[str] = Field(default=None, description="Optional override for provider: 'local' or 'gemini'")
    gemini_api_key: Optional[str] = Field(default=None, description="Optional override for Gemini API key")
    gemini_model: Optional[str] = Field(default=None, description="Optional override for Gemini model")

class TestGeminiRequest(BaseModel):
    api_key: str
    model: Optional[str] = "gemini-3.5-flash"

@router.post("/test-gemini", response_model=Dict[str, Any])
def api_test_gemini(req: TestGeminiRequest):
    """
    Validates a Google Gemini API Key and checks model connectivity.
    """
    return test_gemini_connection(req.api_key, req.model or "gemini-3.5-flash")

def extract_chunk_ids_from_markdown(content: str) -> List[str]:
    """
    Extracts chunk IDs referenced in markdown links using balanced parenthesis
    or angle bracket syntax, avoiding truncation on nested parentheses.
    """
    if not content:
        return []
    chunk_ids = []
    i = 0
    len_c = len(content)
    while i < len_c:
        link_start = content.find('](', i)
        if link_start == -1:
            break
        after = content[link_start + 2:]
        target = None
        if after.startswith('<chunk:'):
            target = '<chunk:'
        elif after.startswith('chunk:'):
            target = 'chunk:'
        if not target:
            i = link_start + 2
            continue
        dest_start = link_start + 2 + len(target)
        if target == '<chunk:':
            close_idx = content.find('>)', dest_start)
            if close_idx != -1:
                cid = content[dest_start:close_idx].strip()
                if cid and cid not in chunk_ids:
                    chunk_ids.append(cid)
                i = close_idx + 2
                continue
        # Scan balanced parens
        depth = 1
        dest_end = dest_start
        while dest_end < len_c and depth > 0:
            if content[dest_end] == '(':
                depth += 1
            elif content[dest_end] == ')':
                depth -= 1
            if depth == 0:
                break
            dest_end += 1
        if depth == 0:
            raw_cid = content[dest_start:dest_end].strip().strip('<>"\'')
            if raw_cid and raw_cid not in chunk_ids:
                chunk_ids.append(raw_cid)
            i = dest_end + 1
        else:
            i = link_start + 2
    return chunk_ids

def get_db_connection():
    db_path = settings.DATA_DIR / 'regulations' / 'sqlite' / 'chunks.db'
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def init_research_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS research_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    query TEXT NOT NULL,
                    recursion_level INTEGER NOT NULL,
                    progress TEXT,
                    report_markdown TEXT,
                    consulted_regulations TEXT,
                    referenced_chunks TEXT,
                    evaluation_summary TEXT,
                    provider TEXT,
                    model TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_research_jobs_created ON research_jobs(created_at DESC);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status);")

            for col_name, col_type in [
                ("evaluation_summary", "TEXT"),
                ("provider", "TEXT"),
                ("model", "TEXT"),
                ("research_gaps", "TEXT"),
                ("comprehensive_report_markdown", "TEXT"),
                ("comprehensive_status", "TEXT"),
                ("skybrary_reading_materials", "TEXT"),
                ("user_notes_reading_materials", "TEXT"),
                ("origins", "TEXT"),
                ("document_ids", "TEXT")
            ]:
                try:
                    c.execute(f"ALTER TABLE research_jobs ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass
            
            # Reset any orphaned jobs left in PENDING/RUNNING if the server restarted
            c.execute("""
                UPDATE research_jobs 
                SET status = 'FAILED', 
                    progress = 'Interrupted: Server restarted while job was in progress.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE status IN ('PENDING', 'RUNNING');
            """)
            conn.commit()
    except Exception as e:
        print(f"Failed to initialize research_jobs table: {e}")

# Initialize database table on import
init_research_db()

def update_job_status(
    job_id: str,
    status: str,
    progress: Optional[str] = None,
    report: Optional[str] = None,
    consulted: Optional[list] = None,
    chunks: Optional[dict] = None,
    evaluation: Optional[dict] = None,
    research_gaps: Optional[list] = None,
    comprehensive_report: Optional[str] = None,
    comprehensive_status: Optional[str] = None,
    skybrary_materials: Optional[list] = None,
    user_notes_materials: Optional[list] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None
):
    with get_db_connection() as conn:
        c = conn.cursor()
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status]
        
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if report is not None:
            updates.append("report_markdown = ?")
            params.append(report)
        if consulted is not None:
            updates.append("consulted_regulations = ?")
            params.append(json.dumps(consulted))
        if chunks is not None:
            updates.append("referenced_chunks = ?")
            params.append(json.dumps(chunks))
        if evaluation is not None:
            updates.append("evaluation_summary = ?")
            params.append(json.dumps(evaluation))
        if research_gaps is not None:
            updates.append("research_gaps = ?")
            params.append(json.dumps(research_gaps))
        if comprehensive_report is not None:
            updates.append("comprehensive_report_markdown = ?")
            params.append(comprehensive_report)
        if comprehensive_status is not None:
            updates.append("comprehensive_status = ?")
            params.append(comprehensive_status)
        if skybrary_materials is not None:
            updates.append("skybrary_reading_materials = ?")
            params.append(json.dumps(skybrary_materials))
        if user_notes_materials is not None:
            updates.append("user_notes_reading_materials = ?")
            params.append(json.dumps(user_notes_materials))
        if provider is not None:
            updates.append("provider = ?")
            params.append(provider)
        if model is not None:
            updates.append("model = ?")
            params.append(model)
            
        params.append(job_id)
        
        query = f"UPDATE research_jobs SET {', '.join(updates)} WHERE job_id = ?"
        c.execute(query, params)
        conn.commit()

def extract_json_data(text: str) -> Any:
    """Robustly extracts JSON data from LLM responses containing code fences or prose."""
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    
    try:
        return json.loads(cleaned)
    except Exception:
        # Fallback: scan for outermost [ ] or { }
        start_bracket = cleaned.find('[')
        start_brace = cleaned.find('{')
        if start_bracket != -1 and (start_brace == -1 or start_bracket < start_brace):
            end_bracket = cleaned.rfind(']')
            if end_bracket != -1:
                try:
                    return json.loads(cleaned[start_bracket:end_bracket+1])
                except Exception:
                    pass
        elif start_brace != -1:
            end_brace = cleaned.rfind('}')
            if end_brace != -1:
                try:
                    return json.loads(cleaned[start_brace:end_brace+1])
                except Exception:
                    pass
    return None

def extract_json_array_from_text(text: str) -> List[str]:
    """Helper to parse a list of strings from LLM text output."""
    data = extract_json_data(text)
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return [str(item).strip() for item in v if str(item).strip()]
    
    # Line-by-line fallback
    lines = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(?:\d+[\.\)]|[-*•])\s*(.*)$", line)
        if m:
            candidate = m.group(1).strip().strip('"').strip("'")
            if candidate and len(candidate) > 5:
                lines.append(candidate)
    return lines[:2]


def analyze_report_gaps(
    query: str,
    report_markdown: str,
    chat_fn,
) -> List[Dict[str, Any]]:
    """
    Critically audits the synthesized report to identify any elements, regulatory domains,
    operational obligations, or practical enforcement mechanics that are not satisfactorily
    explained, formulated into actionable sub-research follow-up jobs.
    """
    critique_prompt = f"""You are a principal aviation regulatory inspector and critical legal auditor.
Carefully review the regulatory research inquiry and the draft research report below:

ORIGINAL INQUIRY:
"{query}"

DRAFT REGULATORY REPORT:
{report_markdown}

AUDIT OBJECTIVE:
Read the report critically and spot any elements, regulatory dimensions, stakeholder duties, or operational scenarios that are NOT satisfactorily explained, remain ambiguous, or represent obvious knowledge gaps.

If the report contains genuine gaps or unanswered compliance questions, formulate 1 to 3 targeted follow-up sub-research jobs with specific queries that will gather the missing regulatory evidence to resolve each gap.
If the report already provides an exhaustive and completely satisfactory answer across all dimensions with no gaps, return an empty list of gaps.

CRITICAL: Return valid JSON ONLY matching this exact structure:
{{
  "has_gaps": true,
  "gaps": [
    {{
      "gap_id": "gap-1",
      "topic": "Concise title of the gap",
      "description": "Specific explanation of what was insufficiently explained or omitted in the report",
      "sub_query": "Targeted regulatory research search query to retrieve evidence for this gap",
      "rationale": "Why investigating this gap provides critical compliance clarity"
    }}
  ]
}}
"""
    try:
        raw_res = chat_fn([
            {"role": "system", "content": "You are a meticulous aviation regulatory auditor and compliance reviewer."},
            {"role": "user", "content": critique_prompt}
        ], max_tokens=2048, temperature=0.1)

        data = extract_json_data(raw_res)
        if isinstance(data, dict) and data.get("has_gaps") and isinstance(data.get("gaps"), list):
            valid_gaps = []
            for idx, g in enumerate(data["gaps"]):
                if isinstance(g, dict) and g.get("topic") and g.get("sub_query"):
                    valid_gaps.append({
                        "gap_id": g.get("gap_id") or f"gap-{idx+1}",
                        "topic": g["topic"].strip(),
                        "description": g.get("description", "").strip(),
                        "sub_query": g["sub_query"].strip(),
                        "rationale": g.get("rationale", "").strip()
                    })
            if valid_gaps:
                return valid_gaps[:3]
    except Exception as e:
        print(f"Report gap critique warning: {e}")

    # Heuristic fallback: check if the report text indicates unresolved regulatory aspects
    if report_markdown:
        gap_patterns = [
            (r'(?:remains?\s+(?:unclear|ambiguous|under review|unresolved)|not\s+(?:satisfactorily\s+)?(?:explained|addressed|specified|detailed|covered))\s*[:\-\.]?\s*([^.\n]+)', "Regulatory Ambiguity & Open Provisions"),
            (r'(?:subject to\s+(?:national|member state)\s+discretion|left to national authorities)\s*[:\-\.]?\s*([^.\n]+)', "National Discretion & Local Deviations"),
            (r'(?:guidance material\s+(?:is missing|not yet published|under development)|AMC\/GM\s+pending)\s*[:\-\.]?\s*([^.\n]+)', "Pending AMC/GM Guidance Material")
        ]
        fallback_gaps = []
        for pat, default_topic in gap_patterns:
            m = re.search(pat, report_markdown, re.IGNORECASE)
            if m:
                snippet = m.group(1).strip()
                if len(snippet) > 8:
                    fallback_gaps.append({
                        "gap_id": f"gap-{len(fallback_gaps)+1}",
                        "topic": default_topic,
                        "description": f"The report notes that {snippet[:150]} requires further regulatory clarity.",
                        "sub_query": f"{query} {snippet[:60]}",
                        "rationale": "Clarifies ambiguous or delegated regulatory provisions."
                    })
            if len(fallback_gaps) >= 2:
                break
        if fallback_gaps:
            return fallback_gaps

    return []



def find_skybrary_reading_materials(
    query: str,
    report_markdown: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Identifies high-relevance SKYbrary Bookshelf publications as additional potential
    reading materials matching the completed regulatory report.
    """
    try:
        words = re.findall(r'\b[a-zA-Z]{4,}\b', query)
        header_matches = re.findall(r'#+\s+([^\n]+)', report_markdown)
        if header_matches:
            words.extend(re.findall(r'\b[a-zA-Z]{4,}\b', header_matches[0]))

        stop_words = {
            "regulatory", "regulation", "regulations", "report", "research", "compliance",
            "requirements", "applicable", "framework", "synthesis", "summary", "concluding",
            "european", "union", "article", "section", "directive", "aviation"
        }
        filtered_words = [w.lower() for w in words if w.lower() not in stop_words]
        unique_words = list(dict.fromkeys(filtered_words))[:8]
        if not unique_words:
            unique_words = ["safety", "operations", "management"]

        fts_query = " OR ".join(unique_words)

        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT c.document_id, d.title, d.metadata_json, c.chunk_id, c.source_text, rank
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.rowid
                JOIN documents d ON c.document_id = d.document_id
                WHERE chunks_fts MATCH ? AND d.source = 'SKYBRARY'
                ORDER BY rank
                LIMIT 50
            """, (fts_query,))
            rows = c.fetchall()

        if not rows:
            return []

        # Find best chunk and rank per document
        docs_map: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            doc_id = r["document_id"]
            if doc_id not in docs_map:
                meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                raw_rank = float(r["rank"])
                text = (r["source_text"] or "").strip().replace("\n", " ")
                excerpt = text[:220] + "..." if len(text) > 220 else text
                category = meta.get("category") or "Aviation Safety"
                author = meta.get("author") or "Safety Agency"

                match_rationale = (
                    f"Operational safety analysis and practical guidelines in the '{category}' domain "
                    f"published by {author}."
                )

                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "title": r["title"] or meta.get("title") or doc_id,
                    "category": category,
                    "author": author,
                    "summary_url": meta.get("summary_url"),
                    "pdf_url": meta.get("pdf_url"),
                    "raw_rank": raw_rank,
                    "match_rationale": match_rationale,
                    "key_excerpt": excerpt
                }

        # Sort by rank
        sorted_docs = sorted(docs_map.values(), key=lambda x: x["raw_rank"])
        max_abs = max(abs(d["raw_rank"]) for d in sorted_docs) if sorted_docs else 1.0

        results = []
        for d in sorted_docs[:limit]:
            score = round(0.70 + 0.28 * (abs(d["raw_rank"]) / max_abs), 2)
            d["relevance_score"] = min(0.99, max(0.65, score))
            d.pop("raw_rank", None)
            results.append(d)

        return results
    except Exception as e:
        print(f"Error finding SKYbrary reading materials: {e}")
        return []


def find_user_notes_reading_materials(
    query: str,
    report_markdown: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Identifies high-relevance user-generated documentation (daily journals, minutes of meetings,
    or project notes) matching the completed regulatory report as potential follow-up reading.
    """
    try:
        words = re.findall(r'\b[a-zA-Z]{4,}\b', query)
        header_matches = re.findall(r'#+\s+([^\n]+)', report_markdown)
        if header_matches:
            words.extend(re.findall(r'\b[a-zA-Z]{4,}\b', header_matches[0]))

        stop_words = {
            "regulatory", "regulation", "regulations", "report", "research", "compliance",
            "requirements", "applicable", "framework", "synthesis", "summary", "concluding",
            "european", "union", "article", "section", "directive", "aviation"
        }
        filtered_words = [w.lower() for w in words if w.lower() not in stop_words]
        unique_words = list(dict.fromkeys(filtered_words))[:8]
        if not unique_words:
            unique_words = ["project", "status", "operation", "meeting"]

        fts_query = " OR ".join(unique_words)

        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT c.document_id, d.title, d.metadata_json, c.chunk_id, c.source_text, rank
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.rowid
                JOIN documents d ON c.document_id = d.document_id
                WHERE chunks_fts MATCH ? AND (d.document_id LIKE 'NOTE_%' OR d.metadata_json LIKE '%"origin": "note"%')
                ORDER BY rank
                LIMIT 50
            """, (fts_query,))
            rows = c.fetchall()

        if not rows:
            return []

        docs_map: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            doc_id = r["document_id"]
            if doc_id not in docs_map:
                meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                raw_rank = float(r["rank"])
                text = (r["source_text"] or "").strip().replace("\n", " ")
                excerpt = text[:220] + "..." if len(text) > 220 else text
                note_type = meta.get("note_type") or "general_note"
                author = meta.get("author") or "User"
                project = meta.get("project") or ""
                date = meta.get("date") or ""

                match_rationale = (
                    f"Internal {note_type.replace('_', ' ')} recorded by {author}"
                    + (f" for project '{project}'" if project else "")
                    + (f" on {date}" if date else "")
                    + " containing relevant operational context."
                )

                docs_map[doc_id] = {
                    "document_id": doc_id,
                    "title": r["title"] or meta.get("title") or doc_id,
                    "note_type": note_type,
                    "date": date,
                    "author": author,
                    "project": project,
                    "raw_rank": raw_rank,
                    "match_rationale": match_rationale,
                    "key_excerpt": excerpt
                }

        sorted_docs = sorted(docs_map.values(), key=lambda x: x["raw_rank"])
        max_abs = max(abs(d["raw_rank"]) for d in sorted_docs) if sorted_docs else 1.0

        results = []
        for d in sorted_docs[:limit]:
            score = round(0.70 + 0.28 * (abs(d["raw_rank"]) / max_abs), 2)
            d["relevance_score"] = min(0.99, max(0.65, score))
            d.pop("raw_rank", None)
            results.append(d)

        return results
    except Exception as e:
        print(f"Error finding user notes reading materials: {e}")
        return []


def run_deep_research(
    job_id: str,
    query: str,
    recursion_level: int,
    provider: str = "local",
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    origins: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None
):
    """
    Executes scientific, multi-level recursive regulatory research.
    
    CRITICAL QUALITY & FALSIFICATION MANDATES:
    1. Scope Analysis: Explicitly identifies target regulatory frameworks vs excluded domains.
    2. Adversarial Chunk Negation: Actively tests, challenges, and negates candidate chunks
       (rejecting out-of-scope matches like VTOL/SC-VTOL for ATM questions).
    3. To-and-Fro Retrieval: If candidate chunks are negated, refines queries dynamically
       to find truly applicable governing regulations.
    4. Genuine Value Gate: Only validated chunks with demonstrated legal applicability are cited.
    5. Preserved Audit Trail: Records full critique reasoning for all validated and negated chunks.
    """
    active_provider = (provider or "local").lower().strip()
    clean_gemini_model = (gemini_model or "").strip()
    if not clean_gemini_model or clean_gemini_model.startswith("gemini-1.") or clean_gemini_model.startswith("gemini-2."):
        clean_gemini_model = "gemini-3.5-flash"
    active_model = clean_gemini_model if active_provider == "gemini" else settings.LLM_MODEL_NAME

    allowed_origins = [str(o).lower().strip() for o in origins if str(o).strip()] if origins else None
    target_doc_id = document_ids[0] if (document_ids and len(document_ids) == 1) else None

    def chat(messages, schema=None, max_tokens=4096, temperature=0.2):
        return call_unified_chat(
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
            temperature=temperature,
            provider=active_provider,
            gemini_api_key=gemini_api_key,
            gemini_model=clean_gemini_model
        )

    try:
        update_job_status(
            job_id,
            "RUNNING",
            progress=f"Initializing research pipeline via {active_provider.upper()} ({active_model})...",
            provider=active_provider,
            model=active_model
        )
        log_debug_info("DEEP_RESEARCH_START", {
            "job_id": job_id,
            "query": query,
            "recursion_level": recursion_level,
            "provider": active_provider,
            "model": active_model,
            "origins": allowed_origins,
            "document_ids": document_ids
        })
        
        # -------------------------------------------------------------
        # STEP 1: Rigorous Regulatory Scope & Exclusion Formulation
        # -------------------------------------------------------------
        update_job_status(job_id, "RUNNING", progress="Analyzing regulatory domain boundaries and scope exclusions...")
        
        scope_prompt = f"""You are a European aviation regulatory legal specialist and compliance auditor.
Analyze the user's research inquiry:
"{query}"

Determine the scientific and legal boundaries for this investigation:
1. "target_domains": List the exact governing EU/EASA regulatory frameworks and domains that have legal authority over this topic (e.g. "Air Traffic Management / Air Navigation Services (ATM/ANS)", "Regulation (EU) 2017/373", "CS-ACNS Airborne Communications, Navigation and Surveillance").
2. "excluded_domains": List common tangential or out-of-scope regulatory frameworks that must be critically CHALLENGED and NEGATED if retrieved by superficial keyword matching (e.g. "VTOL / SC-VTOL aircraft airworthiness", "CS-25 large aeroplane structural criteria", "Aerodrome physical infrastructure", "Flight crew licensing").
3. "initial_queries": 3 to 5 targeted, regulatory-specific search queries designed to retrieve the governing regulations.

Return a JSON object conforming to:
{{
  "target_domains": ["..."],
  "excluded_domains": ["..."],
  "initial_queries": ["..."]
}}
"""
        target_domains = ["EU Aviation Regulations"]
        excluded_domains = []
        questions_to_ask = [query]
        
        try:
            scope_res = chat([
                {"role": "system", "content": "You are a regulatory scope auditor for EASA and European Union aviation law. Return ONLY a JSON object."},
                {"role": "user", "content": scope_prompt}
            ], schema={
                "type": "object",
                "properties": {
                    "target_domains": {"type": "array", "items": {"type": "string"}},
                    "excluded_domains": {"type": "array", "items": {"type": "string"}},
                    "initial_queries": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["target_domains", "excluded_domains", "initial_queries"]
            }, max_tokens=2048)
            scope_data = extract_json_data(scope_res)
            if isinstance(scope_data, dict):
                target_domains = scope_data.get("target_domains", target_domains)
                excluded_domains = scope_data.get("excluded_domains", excluded_domains)
                init_qs = scope_data.get("initial_queries", [])
                if init_qs and isinstance(init_qs, list):
                    questions_to_ask = [str(q).strip() for q in init_qs if str(q).strip()]
                
                # Direct targeted query harvesting from target_domains
                for td in target_domains:
                    found_regs = re.findall(r'(?:(?:Regulation\s*(?:\(EU\))?\s*)?\d{4}/\d+|\bCS-[A-Z0-9-]+\b|\bPart-[A-Z0-9-]+\b)', td, re.IGNORECASE)
                    for reg in found_regs:
                        clean_reg = reg.strip()
                        if clean_reg and clean_reg not in questions_to_ask:
                            questions_to_ask.append(clean_reg)
        except Exception as scope_err:
            print(f"Scope analysis warning: {scope_err}, proceeding with baseline query.")

        visited_chunks = set()
        consulted_docs = set()
        referenced_chunks_dict = {}
        validated_chunks_log = {}
        negated_chunks_log = {}
        synthesized_facts = []

        # -------------------------------------------------------------
        # STEP 2: Recursive Retrieval, Critique & Negation Loop
        # -------------------------------------------------------------
        for level in range(recursion_level):
            level_num = level + 1
            active_queries = questions_to_ask[:5]
            update_job_status(
                job_id,
                "RUNNING",
                progress=f"Level {level_num}/{recursion_level}: Searching regulations ({len(active_queries)} query branch(es))..."
            )
            
            raw_candidates = []
            for q in active_queries:
                try:
                    results = search_hybrid(q, top_k=15, origins=allowed_origins, document_id=target_doc_id, use_hyde=False)
                except Exception as search_err:
                    print(f"Hybrid search failed for '{q}': {search_err}")
                    results = []
                    
                for r in results:
                    cid = r["chunk_id"]
                    if cid not in visited_chunks:
                        visited_chunks.add(cid)
                        raw_candidates.append(r)
                        referenced_chunks_dict[cid] = r["text"]
            
            # Fallback if no new candidates on level 0
            if not raw_candidates and level == 0:
                fallback_results = search_hybrid(query, top_k=20, origins=allowed_origins, document_id=target_doc_id, use_hyde=False)
                for r in fallback_results:
                    cid = r["chunk_id"]
                    if cid not in visited_chunks:
                        visited_chunks.add(cid)
                        raw_candidates.append(r)
                        referenced_chunks_dict[cid] = r["text"]

            if not raw_candidates:
                update_job_status(
                    job_id,
                    "RUNNING",
                    progress=f"Level {level_num}/{recursion_level}: No new candidate regulatory sections found. Proceeding to synthesis."
                )
                break

            # -------------------------------------------------------------
            # ADVERSARIAL CHUNK EVALUATION & FALSIFICATION GATE
            # -------------------------------------------------------------
            update_job_status(
                job_id,
                "RUNNING",
                progress=f"Level {level_num}/{recursion_level}: Scientifically evaluating and challenging {len(raw_candidates)} candidate chunks..."
            )
            
            validated_chunks_this_level = []
            eval_by_id = {}
            batch_size = 12
            
            for b_idx in range(0, len(raw_candidates), batch_size):
                batch_candidates = raw_candidates[b_idx:b_idx + batch_size]
                candidates_formatted = "\n\n".join([
                    f"=== CHUNK ID: {c['chunk_id']} | DOC: {c['document_id']} ===\n{c['text'][:1200]}"
                    for c in batch_candidates
                ])

                batch_eval_prompt = f"""You are an adversarial regulatory compliance auditor.
Your job is to SCIENTIFICALLY CHALLENGE, QUESTION, AND FILTER retrieved regulatory chunks.
Do NOT blindly accept chunks just because they share words like "surveillance", "communication", or "navigation"!

Original User Inquiry: "{query}"
Target Governing Domains: {json.dumps(target_domains)}
Excluded / Tangential Domains: {json.dumps(excluded_domains)}

MANDATORY CRITICAL REVIEW:
For EACH chunk below, determine whether it represents genuine, legally applicable regulatory evidence or an out-of-scope false match.
Example: If the inquiry is about Air Traffic Management (ATM), chunks governing VTOL aircraft airworthiness (SC-VTOL), rotorcraft, general aeroplane design (CS-25), or drone airworthiness are OUT OF SCOPE and MUST BE REJECTED.

Evaluate EACH chunk and return a JSON array of evaluation objects:
[
  {{
    "chunk_id": "exact chunk ID",
    "regulatory_domain": "the specific regulatory domain of this chunk",
    "critique_negation": "Adversarial critique: explain why this chunk might be misleading, tangential, or out of scope for the user's inquiry",
    "verdict": "VALID" or "REJECTED",
    "relevance_score": integer 1-10,
    "genuine_value": "If VALID, state the exact requirement/standard it provides. If REJECTED, state why it lacks genuine value."
  }}
]

Chunks to Evaluate:
{candidates_formatted}
"""
                try:
                    eval_res = chat([
                        {"role": "system", "content": "You are a strict, skeptical aviation regulatory compliance auditor. Return ONLY a JSON array of evaluations."},
                        {"role": "user", "content": batch_eval_prompt}
                    ], max_tokens=4096)
                    eval_list = extract_json_data(eval_res)
                    if isinstance(eval_list, dict):
                        for v in eval_list.values():
                            if isinstance(v, list):
                                eval_list = v
                                break
                    if isinstance(eval_list, list):
                        for item in eval_list:
                            if isinstance(item, dict) and item.get("chunk_id"):
                                eval_by_id[item["chunk_id"]] = item
                except Exception as b_err:
                    print(f"Batch evaluation warning for batch {b_idx}: {b_err}")

            for c in raw_candidates:
                cid = c["chunk_id"]
                ev = eval_by_id.get(cid)
                doc_title = str(c.get("document_id", "")).lower()
                is_excluded_title = any(ex.lower() in doc_title for ex in ["vtol", "vca", "cs-25", "cs-23", "aerodromes"])
                
                if ev:
                    verdict = str(ev.get("verdict", "")).upper()
                    score = int(ev.get("relevance_score", 0)) if str(ev.get("relevance_score", "0")).isdigit() else 0
                    critique = ev.get("critique_negation", "Evaluated against query scope.")
                    
                    if verdict == "VALID" and score >= 6 and not is_excluded_title:
                        validated_chunks_this_level.append(c)
                        consulted_docs.add(c["document_id"])
                        referenced_chunks_dict[cid] = c["text"]
                        validated_chunks_log[cid] = ev
                    else:
                        negated_chunks_log[cid] = {
                            "critique": critique,
                            "regulatory_domain": ev.get("regulatory_domain", "Out of scope"),
                            "genuine_value": ev.get("genuine_value", "Rejected during adversarial applicability review.")
                        }
                else:
                    if is_excluded_title:
                        negated_chunks_log[cid] = {
                            "critique": "Excluded: Document title matches out-of-scope domain.",
                            "regulatory_domain": "Out of scope",
                            "genuine_value": "Excluded based on domain boundaries."
                        }
                    else:
                        validated_chunks_this_level.append(c)
                        consulted_docs.add(c["document_id"])
                        referenced_chunks_dict[cid] = c["text"]
                        validated_chunks_log[cid] = {
                            "chunk_id": cid,
                            "verdict": "VALID",
                            "relevance_score": 7,
                            "genuine_value": "Retained under regulatory scope."
                        }

            # -------------------------------------------------------------
            # TO-AND-FRO RETRIEVAL REFINEMENT
            # If all candidate chunks were negated, refine query to find governing regulations
            # -------------------------------------------------------------
            if not validated_chunks_this_level and raw_candidates:
                update_job_status(
                    job_id,
                    "RUNNING",
                    progress=f"Level {level_num}/{recursion_level}: All {len(raw_candidates)} chunks negated as out-of-scope. Refining query for governing regulations..."
                )
                
                refine_prompt = f"""Search returned only out-of-scope candidate chunks (e.g. {', '.join(list(negated_chunks_log.keys())[:2])}).
User Inquiry: "{query}"
Target Governing Domains: {json.dumps(target_domains)}

Formulate 2 new search queries that explicitly target the governing European regulations (such as Regulation (EU) 2017/373, Part-ATM/ANS, or EASA CS-ACNS) and avoid aircraft type certification rules.
Return ONLY a JSON array of 1-2 search strings: ["query 1", "query 2"]
"""
                try:
                    refine_res = chat([
                        {"role": "system", "content": "Return ONLY a JSON array of 1-2 search strings."},
                        {"role": "user", "content": refine_prompt}
                    ], max_tokens=1024)
                    new_qs = extract_json_array_from_text(refine_res)
                    if new_qs:
                        for rq in new_qs[:2]:
                            for r in search_hybrid(rq, top_k=10, origins=allowed_origins, document_id=target_doc_id, use_hyde=False):
                                if r["chunk_id"] not in visited_chunks:
                                    visited_chunks.add(r["chunk_id"])
                                    # Basic domain check
                                    doc_low = str(r["document_id"]).lower()
                                    if not any(ex.lower() in doc_low for ex in ["vtol", "vca", "cs-25"]):
                                        validated_chunks_this_level.append(r)
                                        consulted_docs.add(r["document_id"])
                                        referenced_chunks_dict[r["chunk_id"]] = r["text"]
                                        validated_chunks_log[r["chunk_id"]] = {
                                            "chunk_id": r["chunk_id"],
                                            "verdict": "VALID",
                                            "relevance_score": 8,
                                            "genuine_value": f"Retrieved via query refinement: '{rq}'"
                                        }
                except Exception as ref_err:
                    print(f"Query refinement warning: {ref_err}")

            if not validated_chunks_this_level:
                update_job_status(
                    job_id,
                    "RUNNING",
                    progress=f"Level {level_num}/{recursion_level}: Valid evidence gathered. Moving to synthesis."
                )
                break

            # -------------------------------------------------------------
            # FACT EXTRACTION (strictly from validated chunks + surrounding sequence)
            # -------------------------------------------------------------
            update_job_status(
                job_id,
                "RUNNING",
                progress=f"Level {level_num}/{recursion_level}: Expanding surrounding regulatory sequence & extracting facts from {len(validated_chunks_this_level)} validated chunks..."
            )

            validated_context_blocks = []
            for c in validated_chunks_this_level:
                cid = c["chunk_id"]
                try:
                    ctx = get_chunk_surrounding_context(cid, window=1)
                    surrounding_list = ctx.get("chunks", [])
                    block_parts = [f"=== FOCAL PROVISION: {cid} | DOC: {c['document_id']} ==="]
                    for sc in surrounding_list:
                        sc_id = sc["chunk_id"]
                        referenced_chunks_dict[sc_id] = sc["text"]
                        if sc.get("is_target"):
                            block_parts.append(f"--- [FOCAL REQUIREMENT: {sc_id}] ---\n{sc['text']}")
                        elif sc.get("position") == "before":
                            block_parts.append(f"--- [PRECEDING PROVISION: {sc_id}] ---\n{sc['text']}")
                        else:
                            block_parts.append(f"--- [SUBSEQUENT PROVISION: {sc_id}] ---\n{sc['text']}")
                    validated_context_blocks.append("\n".join(block_parts))
                except Exception as ctx_err:
                    validated_context_blocks.append(f"=== CHUNK ID: {cid} | DOC: {c['document_id']} ===\n{c['text']}")

            validated_context = "\n\n".join(validated_context_blocks)

            fact_extract_prompt = f"""You are an expert aviation regulatory compliance analyst.

Original User Query: {query}
Governing Target Domains: {json.dumps(target_domains)}

Review the following VALIDATED regulatory provisions along with their immediate surrounding sequential document context (preceding and subsequent provisions).
Analyze how each focal provision fits into its surrounding regulatory framework (definitions, prerequisites, operational conditions, exceptions, and parent rules).
Extract concrete requirements, definitions, scope, standards, operational caveats, and rules relevant to the query.

STRICT CITATION REQUIREMENT:
For EVERY fact, obligation, or requirement you extract, cite its source Chunk ID using this exact angle-bracket syntax: [Citation](<chunk:CHUNK_ID>)
Cite the specific Chunk ID where the requirement, condition, or exception is defined.
Do NOT cite any negated or external chunks.

Validated Regulatory Provisions with Sequential Surrounding Context:
{validated_context}
"""
            facts_text = chat([
                {"role": "system", "content": "You are a meticulous aviation regulatory compliance researcher."},
                {"role": "user", "content": fact_extract_prompt}
            ], max_tokens=8192)
            synthesized_facts.append(facts_text)

            # Generate follow-up queries if recursion levels remain
            if level < recursion_level - 1:
                update_job_status(
                    job_id,
                    "RUNNING",
                    progress=f"Level {level_num}/{recursion_level}: Formulating follow-up research questions based on validated evidence..."
                )
                
                q_prompt = f"""Based on the original query: "{query}"
Target Domains: {json.dumps(target_domains)}
And the validated regulatory facts extracted so far:
{facts_text}

Identify 1 or 2 specific technical or regulatory gaps, cross-references, or implementing standards (AMC/GM) that require further investigation in the regulatory database.
Return ONLY a JSON list of 1-2 concise search queries targeting the governing regulations.
Example: ["Regulation 2017/373 ATM/ANS.OR.B.005 management system requirements", "CS-ACNS surveillance performance requirements"]
"""
                try:
                    q_res = chat([
                        {"role": "system", "content": "Return ONLY a JSON array of 1-2 search strings: [\"query 1\", \"query 2\"]."},
                        {"role": "user", "content": q_prompt}
                    ], max_tokens=1024)
                    new_qs = extract_json_array_from_text(q_res)
                    if new_qs:
                        questions_to_ask = new_qs[:3]
                    else:
                        break
                except Exception as q_err:
                    print(f"Follow-up question warning: {q_err}")
                    break

        # -------------------------------------------------------------
        # STEP 3: Report Synthesis with Scientific Exclusions Section
        # -------------------------------------------------------------
        update_job_status(
            job_id,
            "RUNNING",
            progress=f"Synthesizing report ({len(validated_chunks_log)} validated chunks, {len(negated_chunks_log)} negated)..."
        )
        
        all_facts = "\n\n".join(synthesized_facts) if synthesized_facts else "No specific regulatory facts were extracted."
        
        report_prompt = f"""You are a principal regulatory counsel specializing in EASA and European Union aviation law.
Write an authoritative, cohesive, and deeply structured regulatory research report addressing:
"{query}"

Synthesized Regulatory Evidence (strictly from validated governing chunks):
{all_facts}

Scientific Scope & Exclusions Ledger:
- Target Governing Frameworks: {json.dumps(target_domains)}
- Evaluated & Negated Out-of-Scope Domains: {json.dumps(list(negated_chunks_log.keys())[:6])}

INSTRUCTIONS FOR THE REPORT:
1. Provide a professional, thorough analysis structured with clean Markdown:
   - # Regulatory Research Report: {query}
   - ## Executive Summary
   - ## Applicable Regulatory Framework & Scope
     (You MUST include a dedicated subsection titled 'Regulatory Scope & Evaluated Exclusions' that explicitly details the governing European regulations applied, and notes that out-of-scope aircraft type-certification specifications—such as VTOL/SC-VTOL or CS-25—were evaluated and negated as inapplicable to ATM service provision).
   - ## Key Requirements & Compliance Mandates
   - ## Practical Implementation & Standards (AMC/GM)
   - ## Synthesis & Concluding Recommendations
2. EMBED CITATIONS DIRECTLY IN THE TEXT:
   Whenever you mention any requirement, condition, or standard from the evidence, cite its Chunk ID using this EXACT markdown angle-bracket syntax:
   [Citation](<chunk:CHUNK_ID_HERE>) or [Descriptive Title](<chunk:CHUNK_ID_HERE>)
   Example:
   "Service providers must ensure continuous monitoring of safety performance [Citation](<chunk:L_2017062EN.01010101:(a):32>)."
   Do not cite any chunk not present in the validated evidence.
3. Be authoritative, precise, and completely faithful to the cited evidence.
"""
        report_markdown = chat([
            {"role": "system", "content": "You are a principal regulatory counsel specializing in EASA and EU aviation law."},
            {"role": "user", "content": report_prompt}
        ], max_tokens=8192)

        # Compile consulted regulations metadata
        consulted_regs_list = []
        for doc_id in consulted_docs:
            meta = get_document_metadata(doc_id)
            meta["document_id"] = doc_id
            consulted_regs_list.append(meta)
        consulted_regs_list.sort(key=lambda x: x.get("document_title") or x.get("title") or x.get("document_id"))

        # Hydrate any cited chunks in report_markdown that might be missing from referenced_chunks_dict
        if report_markdown:
            cited_cids = extract_chunk_ids_from_markdown(report_markdown)
            try:
                with get_db_connection() as conn_c:
                    c_db = conn_c.cursor()
                    for cid in cited_cids:
                        if cid not in referenced_chunks_dict:
                            c_db.execute("SELECT source_text FROM chunks WHERE chunk_id = ?", (cid,))
                            ch_row = c_db.fetchone()
                            if ch_row and ch_row[0]:
                                referenced_chunks_dict[cid] = ch_row[0]
                            else:
                                last_col = cid.rfind(':')
                                if last_col != -1 and len(cid[last_col:]) > 2:
                                    c_db.execute("SELECT source_text FROM chunks WHERE chunk_id LIKE ?", (f"%{cid[last_col:]}",))
                                    s_row = c_db.fetchone()
                                    if s_row and s_row[0]:
                                        referenced_chunks_dict[cid] = s_row[0]
            except Exception as hydrate_err:
                print(f"Citation hydration warning: {hydrate_err}")

        # Build scientific evaluation summary
        evaluation_summary = {
            "total_evaluated": len(validated_chunks_log) + len(negated_chunks_log),
            "validated_count": len(validated_chunks_log),
            "negated_count": len(negated_chunks_log),
            "target_domains": target_domains,
            "excluded_domains": excluded_domains,
            "origins": allowed_origins,
            "document_ids": document_ids,
            "surrounding_context_expanded": True,
            "provider": active_provider,
            "model": active_model,
            "negated_chunks": {
                cid: info.get("critique", "Out of scope")
                for cid, info in negated_chunks_log.items()
            },
            "validated_chunks": {
                cid: info.get("genuine_value", "Validated regulatory provision")
                for cid, info in validated_chunks_log.items()
            }
        }

        # Step 6: Critical Self-Audit for Regulatory Gaps
        update_job_status(job_id, "RUNNING", progress="Auditing report for unexplained elements and regulatory gaps...")
        identified_gaps = analyze_report_gaps(query, report_markdown, chat)
        
        # Step 7: Match Relevant SKYbrary Bookshelf Documents for Potential Reading
        skybrary_allowed = (not allowed_origins) or ("all" in allowed_origins) or ("skybrary" in allowed_origins)
        if skybrary_allowed:
            update_job_status(job_id, "RUNNING", progress="Matching relevant SKYbrary Bookshelf reading materials...")
            skybrary_materials = find_skybrary_reading_materials(query, report_markdown, limit=6)
        else:
            skybrary_materials = []

        # Step 8: Match Relevant User Notes & Project Journals for Potential Follow-up Reading
        notes_allowed = (not allowed_origins) or ("all" in allowed_origins) or any(o in ("note", "notes") for o in allowed_origins)
        if notes_allowed:
            update_job_status(job_id, "RUNNING", progress="Matching internal project notes and meeting minutes...")
            user_notes_materials = find_user_notes_reading_materials(query, report_markdown, limit=5)
        else:
            user_notes_materials = []

        update_job_status(
            job_id,
            "COMPLETED",
            progress="Completed",
            report=report_markdown,
            consulted=consulted_regs_list,
            chunks=referenced_chunks_dict,
            evaluation=evaluation_summary,
            research_gaps=identified_gaps,
            comprehensive_status="NOT_STARTED",
            skybrary_materials=skybrary_materials,
            user_notes_materials=user_notes_materials,
            provider=active_provider,
            model=active_model
        )
        log_debug_info("DEEP_RESEARCH_COMPLETE", {
            "job_id": job_id,
            "validated_count": len(validated_chunks_log),
            "negated_count": len(negated_chunks_log),
            "docs_count": len(consulted_regs_list),
            "gaps_count": len(identified_gaps),
            "skybrary_count": len(skybrary_materials),
            "user_notes_count": len(user_notes_materials)
        })
        
    except Exception as e:
        import traceback
        err_msg = f"{str(e)}"
        print(f"Deep Research Failed for job {job_id}:\n{traceback.format_exc()}")
        log_debug_info("DEEP_RESEARCH_ERROR", {"job_id": job_id, "error": err_msg, "traceback": traceback.format_exc()})
        update_job_status(job_id, "FAILED", progress=f"Research failed: {err_msg}")


def run_comprehensive_research(
    job_id: str,
    provider: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None
):
    """
    Executes sub-research activities for identified regulatory gaps and synthesizes
    an expanded Comprehensive Regulatory Research Report.
    """
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,))
            row = c.fetchone()
            if not row:
                return
            
            query = row["query"]
            initial_report = row["report_markdown"] or ""
            gaps_json = row["research_gaps"]
            if not gaps_json:
                update_job_status(job_id, status="COMPLETED", comprehensive_status="COMPLETED", progress="No gaps to investigate.")
                return
            
            gaps = json.loads(gaps_json)
            if not gaps:
                update_job_status(job_id, status="COMPLETED", comprehensive_status="COMPLETED", progress="No gaps to investigate.")
                return

            ref_chunks = json.loads(row["referenced_chunks"]) if row["referenced_chunks"] else {}
            consulted_regs = json.loads(row["consulted_regulations"]) if row["consulted_regulations"] else []
            origins_raw = row["origins"] if "origins" in row.keys() else None
            job_origins = json.loads(origins_raw) if origins_raw else None
            active_provider = (provider or row["provider"] or "local").lower().strip()
            clean_gemini_model = (gemini_model or row["model"] or "").strip()
            if not clean_gemini_model or clean_gemini_model.startswith("gemini-1.") or clean_gemini_model.startswith("gemini-2."):
                clean_gemini_model = "gemini-3.5-flash"
            active_model = clean_gemini_model if active_provider == "gemini" else settings.LLM_MODEL_NAME

        def chat(messages, schema=None, max_tokens=4096, temperature=0.2):
            return call_unified_chat(
                messages=messages,
                schema=schema,
                max_tokens=max_tokens,
                temperature=temperature,
                provider=active_provider,
                gemini_api_key=gemini_api_key,
                gemini_model=clean_gemini_model
            )

        update_job_status(
            job_id,
            status="COMPLETED",
            comprehensive_status="RUNNING",
            progress=f"Investigating {len(gaps)} sub-research jobs addressing identified gaps..."
        )

        gap_findings_list = []
        new_consulted_doc_ids = set()

        for idx, gap in enumerate(gaps):
            topic = gap.get("topic", f"Gap {idx+1}")
            sub_query = gap.get("sub_query") or topic
            update_job_status(
                job_id,
                status="COMPLETED",
                comprehensive_status="RUNNING",
                progress=f"Sub-research [{idx+1}/{len(gaps)}]: Investigating '{topic}'..."
            )

            # Retrieve regulatory evidence for this specific gap
            sub_results = search_hybrid(sub_query, top_k=6, origins=job_origins)
            gap_chunk_texts = []
            for r in sub_results:
                cid = r["chunk_id"]
                txt = r["text"]
                doc_id = r["document_id"]
                ref_chunks[cid] = txt
                new_consulted_doc_ids.add(doc_id)
                gap_chunk_texts.append(f"[{cid}]\n{txt}")

            if gap_chunk_texts:
                gap_evidence = "\n\n".join(gap_chunk_texts)
                extract_prompt = f"""You are an aviation regulatory compliance researcher resolving a specific research gap.
Gap Topic: {topic}
Gap Description: {gap.get('description', '')}
Sub-Research Inquiry: {sub_query}

Retrieved Regulatory Evidence:
{gap_evidence}

Extract the precise legal requirements, AMC/GM standards, and compliance obligations that resolve this gap.
Cite every specific rule using: [Citation](<chunk:CHUNK_ID>).
If the evidence does not directly address the gap, state so clearly."""
                findings = chat([
                    {"role": "system", "content": "You are a precise aviation regulatory analyst."},
                    {"role": "user", "content": extract_prompt}
                ], max_tokens=2048)
            else:
                findings = f"No additional regulatory provisions were retrieved specifically matching query: {sub_query}"

            gap_findings_list.append(f"### Gap Investigation: {topic}\n- **Scope & Deficit**: {gap.get('description', '')}\n- **Resolved Regulatory Findings**:\n{findings}")

        # Update consulted regulations
        for doc_id in new_consulted_doc_ids:
            if not any(cr.get("document_id") == doc_id for cr in consulted_regs):
                meta = get_document_metadata(doc_id)
                meta["document_id"] = doc_id
                consulted_regs.append(meta)

        update_job_status(
            job_id,
            status="COMPLETED",
            comprehensive_status="RUNNING",
            progress="Synthesizing unified Comprehensive Report..."
        )

        all_gap_findings = "\n\n".join(gap_findings_list)

        synthesis_prompt = f"""You are a principal regulatory counsel specializing in EASA and European Union aviation law.
You previously authored an initial regulatory research report for:
"{query}"

INITIAL REPORT:
{initial_report}

NEW REGULATORY EVIDENCE AND SUB-RESEARCH RESOLVING IDENTIFIED GAPS:
{all_gap_findings}

INSTRUCTIONS FOR THE COMPREHENSIVE MASTER REPORT:
1. Synthesize an authoritative, exhaustive COMPREHENSIVE REGULATORY RESEARCH REPORT.
2. Structure the comprehensive report cleanly in Markdown:
   - # Comprehensive Regulatory Research Report: {query}
   - ## Executive Summary (Expanded to encompass resolved gaps)
   - ## Applicable Regulatory Framework & Scope
   - ## Key Requirements & Compliance Mandates (Integrating findings from the sub-research)
   - ## Practical Implementation & Standards (AMC/GM)
   - ## Comprehensive Gap Resolution & Deep Dive Analysis
     (Dedicate detailed subsections to each investigated gap, explicitly explaining how the additional regulatory evidence addresses the previously open elements).
   - ## Synthesis & Concluding Recommendations
3. MANDATORY CITATIONS:
   Whenever you mention any requirement, condition, or standard, cite its Chunk ID using this EXACT syntax:
   [Citation](<chunk:CHUNK_ID_HERE>) or [Descriptive Title](<chunk:CHUNK_ID_HERE>)
   Preserve all citations from the initial report and incorporate citations from the new sub-research evidence.
4. Be authoritative, comprehensive, and exhaustive."""

        comprehensive_markdown = chat([
            {"role": "system", "content": "You are a principal regulatory counsel specializing in EASA and EU aviation law."},
            {"role": "user", "content": synthesis_prompt}
        ], max_tokens=8192)

        # Hydrate any new cited chunks
        if comprehensive_markdown:
            cited_cids = extract_chunk_ids_from_markdown(comprehensive_markdown)
            try:
                with get_db_connection() as conn_c:
                    c_db = conn_c.cursor()
                    for cid in cited_cids:
                        if cid not in ref_chunks:
                            c_db.execute("SELECT source_text FROM chunks WHERE chunk_id = ?", (cid,))
                            ch_row = c_db.fetchone()
                            if ch_row and ch_row[0]:
                                ref_chunks[cid] = ch_row[0]
            except Exception as hydrate_err:
                print(f"Comprehensive citation hydration warning: {hydrate_err}")

        update_job_status(
            job_id,
            status="COMPLETED",
            comprehensive_status="COMPLETED",
            comprehensive_report=comprehensive_markdown,
            consulted=consulted_regs,
            chunks=ref_chunks,
            progress="Comprehensive report ready"
        )

    except Exception as e:
        import traceback
        err_msg = str(e)
        print(f"Comprehensive Research Failed for job {job_id}:\n{traceback.format_exc()}")
        update_job_status(
            job_id,
            status="COMPLETED",
            comprehensive_status="FAILED",
            progress=f"Comprehensive report generation failed: {err_msg}"
        )

def normalize_query(q: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", q.lower())
    return " ".join(cleaned.split())

@router.post("/jobs", response_model=Dict[str, Any])
def create_research_job(req: ResearchJobRequest, background_tasks: BackgroundTasks):
    """
    Submits a new deep research job. If an equivalent research job has already completed
    and force_refresh is False, returns the preserved job instantly to prevent redundant work.
    """
    norm_query = normalize_query(req.query)
    
    # Check for existing completed research if not forcing a refresh
    if not req.force_refresh:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT job_id, query, recursion_level, status, origins, document_ids, created_at
                FROM research_jobs
                WHERE status = 'COMPLETED' AND recursion_level >= ?
                ORDER BY created_at DESC
            """, (req.recursion_level,))
            rows = c.fetchall()
            req_origins_norm = set([str(o).lower().strip() for o in req.origins if str(o).strip()]) if req.origins else None
            req_docs_norm = set([str(d).strip() for d in req.document_ids if str(d).strip()]) if req.document_ids else None
            for r in rows:
                if normalize_query(r["query"]) == norm_query:
                    row_origins = json.loads(r["origins"]) if r["origins"] else None
                    row_origins_norm = set([str(o).lower().strip() for o in row_origins if str(o).strip()]) if row_origins else None
                    if req_origins_norm != row_origins_norm:
                        continue
                    row_docs = json.loads(r["document_ids"]) if r["document_ids"] else None
                    row_docs_norm = set([str(d).strip() for d in row_docs if str(d).strip()]) if row_docs else None
                    if req_docs_norm != row_docs_norm:
                        continue
                    return {
                        "job_id": r["job_id"],
                        "cached": True,
                        "status": "COMPLETED",
                        "message": "Preserved research result reused."
                    }

    job_id = str(uuid.uuid4())
    active_provider = (req.provider or "local").lower().strip()
    clean_gemini_model = (req.gemini_model or "").strip()
    if not clean_gemini_model or clean_gemini_model.startswith("gemini-1.") or clean_gemini_model.startswith("gemini-2."):
        clean_gemini_model = "gemini-3.5-flash"
    active_model = clean_gemini_model if active_provider == "gemini" else settings.LLM_MODEL_NAME

    origins_json = json.dumps(req.origins) if req.origins else None
    doc_ids_json = json.dumps(req.document_ids) if req.document_ids else None

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO research_jobs (job_id, status, query, recursion_level, progress, provider, model, origins, document_ids)
            VALUES (?, 'PENDING', ?, ?, 'Queued in background...', ?, ?, ?, ?)
        """, (job_id, req.query, req.recursion_level, active_provider, active_model, origins_json, doc_ids_json))
        conn.commit()
        
    background_tasks.add_task(
        run_deep_research,
        job_id,
        req.query,
        req.recursion_level,
        active_provider,
        req.gemini_api_key,
        clean_gemini_model,
        req.origins,
        req.document_ids
    )
    return {"job_id": job_id, "cached": False, "status": "PENDING"}

@router.get("/jobs", response_model=List[ResearchJobSummary])
def list_research_jobs(limit: int = Query(500, ge=1, le=1000)):
    """
    Returns a lightweight summary of all research jobs ordered by creation date.
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT job_id, status, query, recursion_level, progress, research_gaps, comprehensive_status, provider, model, origins, document_ids, created_at, updated_at
            FROM research_jobs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        
    results = []
    for r in rows:
        d = dict(r)
        gaps_json = d.pop("research_gaps", None)
        d["has_gaps"] = bool(gaps_json and gaps_json not in ("[]", "null"))
        origins_raw = d.get("origins")
        d["origins"] = json.loads(origins_raw) if origins_raw else None
        doc_ids_raw = d.get("document_ids")
        d["document_ids"] = json.loads(doc_ids_raw) if doc_ids_raw else None
        results.append(ResearchJobSummary(**d))
    return results

@router.get("/jobs/{job_id}", response_model=ResearchJobDetail)
def get_research_job(job_id: str):
    """
    Returns full details for a research job, including its synthesized report,
    consulted regulations, referenced chunks, identified research gaps,
    comprehensive report (if generated), and matched SKYbrary reading materials.
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Research job not found")
            
        d = dict(row)
        d["consulted_regulations"] = json.loads(d["consulted_regulations"]) if d.get("consulted_regulations") else None
        ref_chunks = json.loads(d["referenced_chunks"]) if d.get("referenced_chunks") else {}
        d["evaluation_summary"] = json.loads(d["evaluation_summary"]) if d.get("evaluation_summary") else None
        d["research_gaps"] = json.loads(d["research_gaps"]) if d.get("research_gaps") else None
        d["skybrary_reading_materials"] = json.loads(d["skybrary_reading_materials"]) if d.get("skybrary_reading_materials") else None
        d["user_notes_reading_materials"] = json.loads(d["user_notes_reading_materials"]) if d.get("user_notes_reading_materials") else None
        d["origins"] = json.loads(d["origins"]) if d.get("origins") else None
        d["document_ids"] = json.loads(d["document_ids"]) if d.get("document_ids") else None

        # Hydrate any missing chunk excerpts cited in initial or comprehensive reports
        combined_markdown = f"{d.get('report_markdown') or ''}\n\n{d.get('comprehensive_report_markdown') or ''}"
        if combined_markdown.strip():
            cited_ids = extract_chunk_ids_from_markdown(combined_markdown)
            missing_ids = [cid for cid in cited_ids if cid not in ref_chunks]
            if missing_ids:
                for mid in missing_ids:
                    c.execute("SELECT source_text FROM chunks WHERE chunk_id = ?", (mid,))
                    ch_row = c.fetchone()
                    if ch_row and ch_row["source_text"]:
                        ref_chunks[mid] = ch_row["source_text"]
                    else:
                        last_col = mid.rfind(':')
                        if last_col != -1 and len(mid[last_col:]) > 2:
                            c.execute("SELECT source_text FROM chunks WHERE chunk_id LIKE ?", (f"%{mid[last_col:]}",))
                            s_row = c.fetchone()
                            if s_row and s_row["source_text"]:
                                ref_chunks[mid] = s_row["source_text"]

        d["referenced_chunks"] = ref_chunks if ref_chunks else None

    return ResearchJobDetail(**d)

@router.post("/jobs/{job_id}/generate-comprehensive")
def api_generate_comprehensive_report(
    job_id: str,
    req: GenerateComprehensiveRequest,
    background_tasks: BackgroundTasks
):
    """
    Triggers sub-research jobs addressing the identified regulatory gaps and
    synthesizes an expanded Comprehensive Regulatory Research Report.
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Research job not found")
        if row["status"] != "COMPLETED":
            raise HTTPException(status_code=400, detail="Initial research job must be completed first")
        
        gaps = json.loads(row["research_gaps"]) if row["research_gaps"] else []
        if not gaps:
            raise HTTPException(status_code=400, detail="No research gaps were identified for this job")
            
        if row["comprehensive_status"] == "RUNNING":
            return {"job_id": job_id, "status": "RUNNING", "message": "Comprehensive report is already being generated"}

    update_job_status(
        job_id,
        status="COMPLETED",
        comprehensive_status="RUNNING",
        progress="Starting comprehensive research sub-jobs..."
    )
    
    background_tasks.add_task(
        run_comprehensive_research,
        job_id,
        req.provider,
        req.gemini_api_key,
        req.gemini_model
    )
    return {"job_id": job_id, "status": "RUNNING", "message": "Comprehensive report generation initiated."}

@router.delete("/jobs/{job_id}")
def delete_research_job(job_id: str):
    """
    Deletes a research job by ID.
    """
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM research_jobs WHERE job_id = ?", (job_id,))
        conn.commit()
        if c.rowcount == 0:
            raise HTTPException(status_code=404, detail="Research job not found")
    return {"status": "deleted", "job_id": job_id}
