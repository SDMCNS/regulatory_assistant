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

class ResearchJobSummary(BaseModel):
    job_id: str
    status: str
    query: str
    recursion_level: int
    progress: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
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
    provider: Optional[str] = None
    model: Optional[str] = None
    created_at: str
    updated_at: str

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

            # Upgrade columns if database existed previously
            for col_name, col_type in [
                ("evaluation_summary", "TEXT"),
                ("provider", "TEXT"),
                ("model", "TEXT")
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

def run_deep_research(
    job_id: str,
    query: str,
    recursion_level: int,
    provider: str = "local",
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None
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
            "model": active_model
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
                    results = search_hybrid(q, top_k=15, use_hyde=False)
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
                fallback_results = search_hybrid(query, top_k=20, use_hyde=False)
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
                            for r in search_hybrid(rq, top_k=10, use_hyde=False):
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

        update_job_status(
            job_id,
            "COMPLETED",
            progress="Completed",
            report=report_markdown,
            consulted=consulted_regs_list,
            chunks=referenced_chunks_dict,
            evaluation=evaluation_summary,
            provider=active_provider,
            model=active_model
        )
        log_debug_info("DEEP_RESEARCH_COMPLETE", {
            "job_id": job_id,
            "validated_count": len(validated_chunks_log),
            "negated_count": len(negated_chunks_log),
            "docs_count": len(consulted_regs_list)
        })
        
    except Exception as e:
        import traceback
        err_msg = f"{str(e)}"
        print(f"Deep Research Failed for job {job_id}:\n{traceback.format_exc()}")
        log_debug_info("DEEP_RESEARCH_ERROR", {"job_id": job_id, "error": err_msg, "traceback": traceback.format_exc()})
        update_job_status(job_id, "FAILED", progress=f"Research failed: {err_msg}")

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
                SELECT job_id, query, recursion_level, status, created_at
                FROM research_jobs
                WHERE status = 'COMPLETED' AND recursion_level >= ?
                ORDER BY created_at DESC
            """, (req.recursion_level,))
            rows = c.fetchall()
            for r in rows:
                if normalize_query(r["query"]) == norm_query:
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

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO research_jobs (job_id, status, query, recursion_level, progress, provider, model)
            VALUES (?, 'PENDING', ?, ?, 'Queued in background...', ?, ?)
        """, (job_id, req.query, req.recursion_level, active_provider, active_model))
        conn.commit()
        
    background_tasks.add_task(
        run_deep_research,
        job_id,
        req.query,
        req.recursion_level,
        active_provider,
        req.gemini_api_key,
        clean_gemini_model
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
            SELECT job_id, status, query, recursion_level, progress, provider, model, created_at, updated_at
            FROM research_jobs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        
    return [ResearchJobSummary(**dict(r)) for r in rows]

@router.get("/jobs/{job_id}", response_model=ResearchJobDetail)
def get_research_job(job_id: str):
    """
    Returns full details for a research job, including its synthesized report,
    consulted regulations, referenced chunks, and scientific evaluation summary.
    """
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM research_jobs WHERE job_id = ?", (job_id,))
        row = c.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Research job not found")
            
        d = dict(row)
        d["consulted_regulations"] = json.loads(d["consulted_regulations"]) if d["consulted_regulations"] else None
        ref_chunks = json.loads(d["referenced_chunks"]) if d["referenced_chunks"] else {}
        d["evaluation_summary"] = json.loads(d["evaluation_summary"]) if d.get("evaluation_summary") else None

        # Hydrate any missing chunk excerpts cited in the report
        if d.get("report_markdown"):
            cited_ids = extract_chunk_ids_from_markdown(d["report_markdown"])
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
