import sys
import json
import re
import sqlite3
import textwrap
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import requests
from ingestion.core.config import settings
from ingestion.retrieval.skybrary_weighting import calculate_skybrary_weight

def ensure_fts_index(conn: sqlite3.Connection):
    """
    Ensures the SQLite FTS5 virtual table exists for chunks.
    Uses external content table linking to `chunks` rowid to minimize disk usage.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts';")
    if not cursor.fetchone():
        print("[KeywordSearch] Initializing FTS5 index on chunks...")
        cursor.execute("""
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                source_text,
                section_path,
                document_id,
                content='chunks',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );
        """)
        cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');")
        conn.commit()
        print("[KeywordSearch] FTS5 index built successfully.")

def expand_query_with_llm(query: str, timeout: int = 5) -> List[str]:
    """
    Asks the local LLM in LM Studio to suggest relevant keywords,
    synonyms, and aviation regulatory acronyms for query expansion.
    Falls back gracefully if the LLM is not loaded.
    """
    prompt = (
        f"You are an expert search assistant for aviation regulations (EASA and EU).\n"
        f"Given the user query: \"{query}\", generate 3 to 6 closely related keywords, "
        f"aviation acronyms, or standard regulatory phrases for full-text search.\n"
        f"Return ONLY a valid JSON list of strings (e.g. [\"term1\", \"term2\"]). Do not include explanations."
    )
    
    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You output only valid JSON arrays."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 350
    }
    
    try:
        response = requests.post(
            f"{settings.LM_STUDIO_BASE_URL}/chat/completions",
            json=payload,
            timeout=timeout
        )
        if response.status_code == 200:
            data = response.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            content = (msg.get("content") or "").strip()
            if not content and msg.get("reasoning_content"):
                content = (msg.get("reasoning_content") or "").strip()
            # Strip think tags if any
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            # Clean up potential markdown formatting like ```json ... ```
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
            
            # Find JSON array
            array_match = re.search(r"\[[\s\S]*?\]", content)
            if array_match:
                keywords = json.loads(array_match.group(0))
                if isinstance(keywords, list):
                    return [str(k).strip() for k in keywords if str(k).strip()]
    except Exception:
        # LLM not running, model not loaded, or timeout
        pass
    
    return []

STOPWORDS = {
    'what', 'are', 'the', 'for', 'and', 'in', 'used', 'is', 'to', 'of', 'on',
    'with', 'from', 'by', 'as', 'at', 'an', 'a', 'or', 'do', 'does', 'how',
    'can', 'could', 'should', 'would', 'which', 'who', 'whom', 'this', 'that',
    'these', 'those', 'there', 'their', 'be', 'been', 'being', 'have', 'has', 'had',
    'shall', 'may', 'must', 'into', 'under', 'about', 'between', 'out', 'all', 'any'
}

def build_fts_query(raw_query: str, expanded_keywords: Optional[List[str]] = None) -> str:
    """
    Builds a robust FTS5 match query prioritizing exact phrases, domain acronyms,
    and salient content terms, while filtering conversational stopwords.
    Ensures safe quoting for tokens containing '-' or '/' to prevent FTS5 syntax errors.
    """
    if not raw_query or not raw_query.strip():
        return ""

    # 1. Extract explicitly quoted phrases
    quoted_phrases = re.findall(r'"([^"]+)"', raw_query)
    
    # 2. Process unquoted text: strip punctuation except hyphens, slashes, and periods in terms
    unquoted_text = re.sub(r'"[^"]+"', ' ', raw_query)
    clean = re.sub(r'[^\w\s\-/.]', ' ', unquoted_text).strip()
    
    raw_tokens = clean.split()
    salient_tokens = []
    
    for token in raw_tokens:
        clean_tok = token.strip(".-/")
        if not clean_tok:
            continue
        # Filter conversational stopwords unless token has hyphens/slashes
        if clean_tok.lower() in STOPWORDS and not ('-' in clean_tok or '/' in clean_tok):
            continue
        # Quote tokens with hyphens or slashes to avoid FTS5 operator collisions
        if '-' in clean_tok or '/' in clean_tok or '.' in clean_tok:
            salient_tokens.append(f'"{clean_tok}"')
        else:
            salient_tokens.append(clean_tok)
            
    clauses = []
    
    # Add quoted phrases
    for qp in quoted_phrases:
        clean_qp = qp.strip()
        if clean_qp:
            clauses.append(f'"{clean_qp}"')
            
    # Add exact phrase candidate for multiple salient words
    unquoted_salient = [t.strip('"') for t in salient_tokens]
    if len(unquoted_salient) >= 2 and len(unquoted_salient) <= 5:
        phrase_candidate = " ".join(unquoted_salient)
        clauses.append(f'"{phrase_candidate}"')
        
    # Main search terms joined with OR (enables BM25 scoring across matching keywords)
    if salient_tokens:
        clauses.append(f"({' OR '.join(salient_tokens)})")
        # Boost chunks that contain all salient terms if 2-4 key terms exist
        if len(salient_tokens) >= 2 and len(salient_tokens) <= 4:
            clauses.append(f"({' AND '.join(salient_tokens)})")

    # 3. Incorporate expanded keywords from LLM (if any)
    if expanded_keywords:
        exp_clauses = []
        for kw in expanded_keywords:
            clean_kw = re.sub(r'[^\w\s\-/.]', ' ', kw).strip()
            if not clean_kw:
                continue
            if " " in clean_kw or "-" in clean_kw or "/" in clean_kw or "." in clean_kw:
                exp_clauses.append(f'"{clean_kw}"')
            else:
                exp_clauses.append(clean_kw)
        if exp_clauses:
            clauses.append(f"({' OR '.join(exp_clauses)})")

    if not clauses:
        # Fallback to simple token search if everything was filtered
        fallback = [w for w in clean.split() if w]
        if fallback:
            return " OR ".join([f'"{w}"' if ('-' in w or '/' in w) else w for w in fallback])
        return ""
            
    return " OR ".join(clauses)

def chunk_matches_origin(origin_filter: Any, is_easa: bool, is_faa: bool, is_manual: bool, is_skybrary: bool, is_note: bool, is_user: bool = False, is_icao: bool = False) -> bool:
    if not origin_filter:
        return True
    if isinstance(origin_filter, (list, tuple, set)):
        allowed = {str(o).lower().strip() for o in origin_filter if str(o).strip()}
    else:
        allowed = {str(o).lower().strip() for o in str(origin_filter).split(",") if str(o).strip()}
    if not allowed or "all" in allowed:
        return True
    chunk_origin = "icao" if is_icao else ("user" if is_user else ("note" if is_note else ("skybrary" if is_skybrary else ("manual" if is_manual else ("faa" if is_faa else ("easa" if is_easa else "eu"))))))
    aliases = {"bookshelf": "skybrary", "notes": "note", "eurlex": "eu", "user_docs": "user", "user_supplied": "user", "icao_docs": "icao"}
    canonical_allowed = {aliases.get(a, a) for a in allowed}
    return chunk_origin in canonical_allowed


def get_origin_sql_clause(origin: Any) -> str:
    if not origin or origin == "all":
        return ""
    if isinstance(origin, (list, tuple, set)):
        allowed = {str(o).lower().strip() for o in origin if str(o).strip()}
    else:
        allowed = {str(o).lower().strip() for o in str(origin).split(",") if str(o).strip()}
    if not allowed or "all" in allowed:
        return ""
    
    aliases = {"bookshelf": "skybrary", "notes": "note", "eurlex": "eu", "user_docs": "user", "user_supplied": "user", "icao_docs": "icao"}
    canonical = {aliases.get(a, a) for a in allowed}

    clauses = []
    if "icao" in canonical:
        clauses.append("(d.source = 'ICAO PDF' OR d.document_id LIKE 'ICAO%')")
    if "faa" in canonical:
        clauses.append("(d.source = 'FAA XML' OR d.document_id LIKE 'FAA%')")
    if "skybrary" in canonical:
        clauses.append("(d.source = 'SKYBRARY' OR d.document_id LIKE 'SKYBRARY%')")
    if "manual" in canonical:
        clauses.append("(d.source = 'Manual' OR d.document_id LIKE 'MANUAL%')")
    if "note" in canonical:
        clauses.append("(d.metadata_json LIKE '%\"origin\": \"note\"%' OR d.document_id LIKE 'NOTE%')")
    if "user" in canonical:
        clauses.append("(d.source = 'USER' OR d.metadata_json LIKE '%\"origin\": \"user\"%' OR d.document_id LIKE 'USER%')")
    if "easa" in canonical:
        clauses.append("(d.source = 'EASA XML' OR d.metadata_json LIKE '%\"source\": \"EASA XML\"%')")
    if "eu" in canonical:
        clauses.append("(d.source NOT IN ('EASA XML', 'FAA XML', 'SKYBRARY', 'Manual', 'USER', 'ICAO PDF') AND d.document_id NOT LIKE 'ICAO%' AND d.document_id NOT LIKE 'FAA%' AND d.document_id NOT LIKE 'SKYBRARY%' AND d.document_id NOT LIKE 'MANUAL%' AND d.document_id NOT LIKE 'USER%' AND d.document_id NOT LIKE 'NOTE%')")

    if not clauses:
        return ""
    return " AND (" + " OR ".join(clauses) + ")"


def search_keywords(
    query: str,
    top_k: int = 5,
    origin: Any = "all",
    use_llm_expansion: bool = True,
    document_id: Optional[str] = None,
    deep_research: bool = False,
    keyword_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Performs full-text keyword search in SQLite with BM25 ranking.
    Optionally filters by document_id, origin(s), and strict keyword_filter.
    """
    db_path = settings.SQLITE_PATH
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    expanded_terms = []
    if use_llm_expansion:
        expanded_terms = expand_query_with_llm(query)
        
    fts_query = build_fts_query(query, expanded_terms)
    
    results = []
    with sqlite3.connect(db_path) as conn:
        ensure_fts_index(conn)
        cursor = conn.cursor()
        
        # Column weights for BM25:
        # source_text: 1.0, section_path: 3.0, document_id: 2.0
        # In FTS5 bm25(table, weight1, weight2, ...)
        where_extra = " AND c.document_id = ?" if document_id else ""
        where_origin = get_origin_sql_clause(origin) if not document_id else ""
        sql = f"""
            SELECT 
                c.chunk_id,
                c.document_id,
                c.section_path,
                c.source_text,
                d.metadata_json,
                d.title,
                bm25(chunks_fts, 1.0, 3.0, 2.0) AS bm25_score,
                COALESCE(c.is_active, 1) AS chunk_active,
                COALESCE(d.is_active, 1) AS doc_active,
                d.superseded_by,
                d.deactivation_reason
            FROM chunks_fts f
            JOIN chunks c ON f.rowid = c.rowid
            JOIN documents d ON c.document_id = d.document_id
            WHERE chunks_fts MATCH ?{where_extra}{where_origin}
            ORDER BY 
                CASE 
                    WHEN COALESCE(c.is_active, 1) = 0 OR COALESCE(d.is_active, 1) = 0 OR (d.superseded_by IS NOT NULL AND d.superseded_by != '')
                    THEN bm25(chunks_fts, 1.0, 3.0, 2.0) * 0.1
                    ELSE bm25(chunks_fts, 1.0, 3.0, 2.0)
                END ASC
            LIMIT ?;
        """
        
        fetch_limit = max(top_k * 4, 25) if (origin != "all" or document_id or keyword_filter) else top_k
        sql_params = [fts_query]
        if document_id:
            sql_params.append(document_id)
        sql_params.append(fetch_limit)

        try:
            cursor.execute(sql, sql_params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            # Fallback for simple literal search if complex query fails
            clean_words = re.sub(r'[^\w\s\-/]', ' ', query).split()
            safe_terms = [f'"{w}"' if ("-" in w or "/" in w) else w for w in clean_words if w]
            simple_q = " OR ".join(safe_terms)
            if not simple_q:
                return []
            try:
                fallback_params = [simple_q]
                if document_id:
                    fallback_params.append(document_id)
                fallback_params.append(fetch_limit)
                cursor.execute(sql, fallback_params)
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                return []
            
        count = 0
        for row in rows:
            if count >= fetch_limit:
                break
            chunk_id, doc_id, section_path, source_text, meta_json, doc_title, score, chunk_active, doc_active, superseded_by, deactivation_reason = row
            
            is_easa = ('"source": "EASA XML"' in meta_json) if meta_json else False
            is_faa = ('"source": "FAA XML"' in meta_json) if meta_json else (doc_id.startswith("FAA_"))
            is_manual = ('"source": "Manual"' in meta_json) if meta_json else (doc_id.startswith("MANUAL_"))
            is_skybrary = ('"source": "SKYBRARY"' in meta_json) if meta_json else (doc_id.startswith("SKYBRARY_"))
            is_note = ('"origin": "note"' in meta_json) if meta_json else (doc_id.startswith("NOTE_"))
            is_user = ('"source": "USER"' in meta_json) or ('"origin": "user"' in meta_json) or doc_id.startswith("USER_")
            is_icao = ('"source": "ICAO PDF"' in meta_json) or ('"origin": "icao"' in meta_json) or doc_id.startswith("ICAO_")
            if not document_id:
                if not chunk_matches_origin(origin, is_easa, is_faa, is_manual, is_skybrary, is_note, is_user, is_icao):
                    continue

            # Check keyword filter if specified
            if keyword_filter and keyword_filter.strip():
                kf_terms = [t.lower() for t in re.findall(r'\b\w+\b', keyword_filter) if len(t) > 1]
                if kf_terms:
                    combined_check = f"{str(doc_id).lower()} {str(section_path).lower()} {str(source_text).lower()}"
                    if not all(term in combined_check for term in kf_terms):
                        continue
                
            count += 1
            
            # Fetch parent title if this is an ANNEX or lacks a good title
            if not doc_title or str(doc_title).upper().startswith("ANNEX") or str(doc_title).upper().startswith("APPENDIX"):
                prefix = doc_id.split(".")[0] + "%"
                cursor.execute("""
                    SELECT title FROM documents 
                    WHERE document_id <= ? AND document_id LIKE ? 
                      AND title NOT LIKE 'ANNEX%' 
                      AND title NOT LIKE 'APPENDIX%'
                    ORDER BY document_id DESC LIMIT 1
                """, (doc_id, prefix))
                p_row = cursor.fetchone()
                if p_row and p_row[0]:
                    doc_title = p_row[0]

            try:
                path_list = json.loads(section_path)
            except Exception:
                path_list = []
                
            meta_dict = json.loads(meta_json) if meta_json else {}
            if doc_title:
                meta_dict["document_title"] = doc_title
            meta_dict["origin"] = "icao" if is_icao else ("user" if is_user else ("note" if is_note else ("skybrary" if is_skybrary else ("manual" if is_manual else ("faa" if is_faa else ("easa" if is_easa else "eu"))))))

            is_suppressed = bool(chunk_active == 0 or doc_active == 0 or superseded_by)
            custom_score = float(score)
            if deep_research and is_note:
                # FTS5 bm25 returns negative numbers. More negative is better.
                custom_score *= 2.5

            # Apply Skybrary recency downweighting (75% if undated, 5%/year up to 60% if dated; reports/investigations exempt)
            sky_weight = 1.0
            sky_expl = None
            if is_skybrary:
                sky_weight, sky_expl = calculate_skybrary_weight(meta_dict, doc_title, doc_id)
                # BM25 scores are negative, multiplying by sky_weight (0.25 to 1.0) brings score closer to 0 (weaker)
                custom_score *= sky_weight

            if is_suppressed:
                # Downweight by 0.1 (multiplying negative number by 0.1 brings it closer to 0, making it weaker)
                custom_score *= 0.1

            results.append({
                "rank": count,
                "score": custom_score,
                "raw_bm25_score": float(score),
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "path": path_list,
                "section_path": path_list,
                "text": source_text,
                "source_text": source_text,
                "source": "NOTE" if is_note else ("MANUAL" if is_manual else ("SKYBRARY" if is_skybrary else ("FAA" if is_faa else ("EASA" if is_easa else "EU")))),
                "metadata": meta_dict,
                "expanded_terms": expanded_terms,
                "is_active": bool(chunk_active and doc_active),
                "is_suppressed": is_suppressed,
                "superseded_by": superseded_by,
                "deactivation_reason": deactivation_reason,
                "skybrary_weight": sky_weight if is_skybrary else None,
                "skybrary_explanation": sky_expl if is_skybrary else None
            })
            
    # Re-sort results by custom_score ASC (more negative is better)
    results.sort(key=lambda x: x["score"], reverse=False)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    # Apply top_k cut here because we fetched up to fetch_limit valid items
    results = results[:top_k]

    return results

def main():
    parser = argparse.ArgumentParser(description="SQLite Keyword Search for Aviation Regulations (FTS5 + BM25 + LLM Expansion)")
    parser.add_argument("query", type=str, help="Search terms or keywords")
    parser.add_argument("--top_k", "-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--origin", choices=["all", "eu", "easa", "faa"], default="all", help="Filter by regulation source")
    parser.add_argument("--no_llm", action="store_true", help="Disable LLM keyword expansion")
    args = parser.parse_args()

    print("=" * 80)
    print(f"QUERY: \"{args.query}\"")
    print("=" * 80)

    use_llm = not args.no_llm
    if use_llm:
        print("[1/2] Checking for LLM keyword expansion...")
    else:
        print("[1/2] Skipping LLM keyword expansion (--no_llm set).")

    results = search_keywords(
        args.query,
        top_k=args.top_k,
        origin=args.origin,
        use_llm_expansion=use_llm
    )

    if not results:
        print(f"\nNo keyword matches found for query: '{args.query}'")
        return

    first_item = results[0]
    if first_item.get("expanded_terms"):
        print(f"-> LLM Expanded Keywords: {', '.join(first_item['expanded_terms'])}\n")
    else:
        print("-> Using direct keyword matching with Porter stemming and prefix expansion.\n")

    print(f"[2/2] Retrieved {len(results)} ranked matches from SQLite FTS5:\n")
    for r in results:
        print("=" * 80)
        print(f"RANK {r['rank']} | BM25 Score: {r['score']:.4f} | Source: {r['source']} | Chunk ID: {r['chunk_id']}")
        print(f"Document: {r['document_id']}")
        if r['section_path']:
            print(f"Section:  {' > '.join(r['section_path'])}")
        print("-" * 80)
        print(textwrap.fill(r['source_text'][:600] + ("..." if len(r['source_text']) > 600 else ""), width=80))
        print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
