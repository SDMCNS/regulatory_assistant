"""
similarity.py - Semantic Similarity Engine for EASA Regulatory Knowledge Graph.

Introduces high-value SIMILAR_TO edges connecting provisions where semantic similarity
is strong (but not identical) and where provisions are NOT already explicitly linked
(via SATISFIES, EXPLAINS, CROSS_REFERENCES, or shared base code).
"""

import csv
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import kuzu
from ingestion.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("similarity")

DB_PATH = settings.KUZU_DB_PATH
SIMILARITY_CSV_PATH = settings.GRAPH_DIR / "rel_similar_to.csv"


def clean_text_for_embedding(text: str, max_words: int = 150) -> str:
    """Cleans legal text and extracts first N words for semantic embedding."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = clean.replace("\xa0", " ").replace("&amp;", "&").replace("&quot;", '"')
    clean = re.sub(r"\s+", " ", clean).strip()
    words = clean.split()
    return " ".join(words[:max_words])


def load_provisions_and_exclusions(conn: kuzu.Connection) -> Tuple[List[Dict[str, Any]], Set[Tuple[str, str]]]:
    """
    Loads all provisions along with their annex and document metadata,
    and constructs the exclusion set of already-explicitly-linked provisions.
    """
    logger.info("Loading provisions and existing structural edges from Kùzu...")

    q_prov = """
    MATCH (p:Provision)-[:BELONGS_TO_ANNEX]->(a:Annex)
    RETURN p.id, p.code, p.base_code, p.title, p.content_type, p.subject, p.text, p.word_count, a.id, a.code
    """
    res = conn.execute(q_prov)
    provisions = []
    while res.has_next():
        row = res.get_next()
        p_id, code, base_code, title, content_type, subject, text, word_count, annex_id, annex_code = row
        provisions.append({
            "id": p_id,
            "code": code,
            "base_code": base_code,
            "title": title or "",
            "content_type": content_type,
            "subject": subject,
            "text": text or "",
            "word_count": word_count or 0,
            "annex_id": annex_id,
            "annex_code": annex_code,
        })

    forbidden_pairs: Set[Tuple[str, str]] = set()

    for rel_name in ["SATISFIES", "EXPLAINS", "CROSS_REFERENCES"]:
        try:
            res_rel = conn.execute(f"MATCH (a:Provision)-[r:{rel_name}]->(b:Provision) RETURN a.id, b.id")
            while res_rel.has_next():
                u, v = res_rel.get_next()
                forbidden_pairs.add((u, v))
                forbidden_pairs.add((v, u))
        except Exception:
            pass

    return provisions, forbidden_pairs


def compute_similarities_dense(
    provisions: List[Dict[str, Any]],
    forbidden_pairs: Set[Tuple[str, str]],
    threshold: float = 0.72,
    top_k: int = 5,
    batch_size: int = 256,
) -> List[Dict[str, Any]]:
    """
    Computes high-value SIMILAR_TO edges using all-MiniLM-L6-v2 embeddings.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading SentenceTransformer ('all-MiniLM-L6-v2') on device: {device}")
    model = SentenceTransformer("all-MiniLM-L6-v2", device=device)

    texts = [f"{p['code']} {p['title']}. {clean_text_for_embedding(p['text'])}" for p in provisions]
    logger.info(f"Encoding {len(texts)} provisions into dense vectors...")
    t0 = time.time()
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=True, normalize_embeddings=True)
    logger.info(f"Encoding complete in {time.time() - t0:.2f}s. Shape: {embeddings.shape}")

    similar_edges = []
    num_nodes = len(provisions)

    logger.info(f"Scanning for cross-provision semantic similarity (threshold >= {threshold})...")
    chunk_size = 500
    for start_idx in range(0, num_nodes, chunk_size):
        end_idx = min(start_idx + chunk_size, num_nodes)
        sub_emb = embeddings[start_idx:end_idx]
        sim_matrix = np.dot(sub_emb, embeddings.T)

        for i_rel, i_global in enumerate(range(start_idx, end_idx)):
            scores = sim_matrix[i_rel]
            scores[i_global] = -1.0

            top_indices = np.argsort(scores)[::-1][: top_k * 4]
            added = 0
            p_source = provisions[i_global]

            for j in top_indices:
                score = float(scores[j])
                if score < threshold or score >= 0.999:
                    break

                p_target = provisions[j]

                if (p_source["id"], p_target["id"]) in forbidden_pairs:
                    continue
                if p_source["base_code"] == p_target["base_code"] and p_source["base_code"] != "GENERAL":
                    continue

                diff_annex = p_source["annex_id"] != p_target["annex_id"]
                score_pct = int(round(score * 100))
                scope_str = "Cross-Annex Harmonization" if diff_annex else "Intra-Domain Parallel"
                reason = f"{score_pct}% Semantic Match ({scope_str}): {p_source['title']} ↔ {p_target['title']}"

                similar_edges.append({
                    "from": p_source["id"],
                    "to": p_target["id"],
                    "score": round(score, 4),
                    "method": "all-MiniLM-L6-v2-dense",
                    "reason": reason,
                })
                added += 1
                if added >= top_k:
                    break

    logger.info(f"Generated {len(similar_edges)} high-value SIMILAR_TO edges.")
    return similar_edges


def export_similar_to_csv(similar_edges: List[Dict[str, Any]], output_path: Path) -> None:
    """Writes SIMILAR_TO edges to CSV formatted for Kùzu COPY."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["from", "to", "score", "method", "reason"])
        for e in similar_edges:
            writer.writerow([e["from"], e["to"], e["score"], e["method"], e["reason"]])
    logger.info(f"Exported {len(similar_edges)} SIMILAR_TO edges to {output_path}")


def load_similarities_to_kuzu(conn: kuzu.Connection = None, csv_path: Path = None, db_path: Path = None) -> int:
    """Loads SIMILAR_TO edges into Kùzu database."""
    csv_path = Path(csv_path or SIMILARITY_CSV_PATH)
    if not csv_path.exists():
        logger.warning(f"Similarity CSV not found at {csv_path}")
        return 0

    if conn is None:
        db_path = Path(db_path or DB_PATH)
        db = kuzu.Database(str(db_path))
        conn = kuzu.Connection(db)

    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS SIMILAR_TO (
            FROM Provision TO Provision,
            score DOUBLE,
            method STRING,
            reason STRING
        );
    """)

    csv_str = str(csv_path).replace("\\", "/")
    logger.info(f"Copying SIMILAR_TO from {csv_str}...")
    conn.execute(f"COPY SIMILAR_TO FROM '{csv_str}' (HEADER=TRUE);")

    res = conn.execute("MATCH ()-[r:SIMILAR_TO]->() RETURN count(r)").get_next()
    count = res[0]
    logger.info(f"Successfully loaded {count} SIMILAR_TO edges into Kùzu.")
    return count


def compute_and_save_similarities(db_path: Path = None, csv_path: Path = None) -> int:
    """Full execution function to compute and save similarities."""
    db_path = Path(db_path or DB_PATH)
    csv_path = Path(csv_path or SIMILARITY_CSV_PATH)

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)

    provisions, forbidden = load_provisions_and_exclusions(conn)
    edges = compute_similarities_dense(provisions, forbidden, threshold=0.72, top_k=5)
    export_similar_to_csv(edges, csv_path)
    return load_similarities_to_kuzu(conn, csv_path)


if __name__ == "__main__":
    compute_and_save_similarities()
