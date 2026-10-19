"""
hyde.py - Hypothetical Document Embeddings (HyDE) Search Engine for EASA Regulatory Graph.

Provides semantic query-to-node discovery by:
1. Taking user's natural language question, operational scenario, or regulatory intent.
2. Generating a concise hypothetical EASA regulatory excerpt (Implementing Rule / AMC).
3. Encoding the hypothetical text into the dense embedding space (all-MiniLM-L6-v2).
4. Ranking the 19,616 codified provisions by cosine similarity to identify candidate entry nodes.
5. Serving as a primary entry point alongside exact provision code matching.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import kuzu
import numpy as np
from ingestion.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hyde")

DB_PATH = settings.KUZU_DB_PATH
CACHE_DIR = settings.GRAPH_CACHE_DIR
EMBEDDINGS_FILE = CACHE_DIR / "provision_embeddings.npy"
METADATA_FILE = CACHE_DIR / "provision_metadata.json"

LM_STUDIO_URL = f"{settings.LM_STUDIO_BASE_URL}/chat/completions"
LM_STUDIO_MODELS_URL = f"{settings.LM_STUDIO_BASE_URL}/models"


class HydeEngine:
    """HyDE Search Engine for identifying regulatory candidate nodes in Kùzu."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.model = None
        self.embeddings: Optional[np.ndarray] = None
        self.metadata: Optional[List[Dict[str, Any]]] = None
        self.active_llm_model: Optional[str] = None
        self._init_engine()

    def _init_engine(self) -> None:
        """Loads embedding model and cached embeddings."""
        from sentence_transformers import SentenceTransformer
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading SentenceTransformer ('all-MiniLM-L6-v2') on {device}...")
        self.model = SentenceTransformer("all-MiniLM-L6-v2", device=device)

        if EMBEDDINGS_FILE.exists() and METADATA_FILE.exists():
            self._load_cache()
        else:
            self._build_cache()

    def _load_cache(self) -> None:
        """Loads precomputed embeddings and metadata from disk in milliseconds."""
        t0 = time.time()
        logger.info(f"Loading cached provision embeddings from {EMBEDDINGS_FILE}...")
        self.embeddings = np.load(str(EMBEDDINGS_FILE))
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)
        logger.info(f"Loaded {len(self.metadata)} provisions (shape: {self.embeddings.shape}) in {time.time() - t0:.3f}s.")

    def _build_cache(self) -> None:
        """Builds provision embeddings cache from Kùzu database."""
        logger.info("Building provision embeddings cache from Kùzu...")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        db = kuzu.Database(str(self.db_path))
        conn = kuzu.Connection(db)

        q = """
        MATCH (p:Provision)-[:BELONGS_TO_ANNEX]->(a:Annex)
        RETURN p.id, p.code, p.base_code, p.title, p.content_type, p.legal_force, p.subject, p.text, p.word_count, a.code, a.name
        """
        res = conn.execute(q)

        metadata = []
        texts_to_encode = []

        while res.has_next():
            row = res.get_next()
            p_id, code, base_code, title, c_type, legal_force, subject, text, word_count, a_code, a_name = row

            clean_text = (text or "").replace("\xa0", " ").strip()
            snippet = clean_text[:280] + "..." if len(clean_text) > 280 else clean_text

            item = {
                "id": p_id,
                "code": code or "",
                "base_code": base_code or "",
                "title": title or "",
                "content_type": c_type or "OTHER",
                "legal_force": legal_force or "Implementing Rule",
                "subject": subject or "",
                "annex_code": a_code or "EASA",
                "annex_name": a_name or "",
                "word_count": word_count or 0,
                "snippet": snippet
            }
            metadata.append(item)

            words = clean_text.split()[:100]
            rep = f"{code} {title}. {subject}. {' '.join(words)}"
            texts_to_encode.append(rep)

        logger.info(f"Encoding {len(texts_to_encode)} provisions on GPU with batch_size=256...")
        t0 = time.time()
        embeddings = self.model.encode(texts_to_encode, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
        logger.info(f"Encoding completed in {time.time() - t0:.2f}s.")

        np.save(str(EMBEDDINGS_FILE), embeddings)
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False)

        self.embeddings = embeddings
        self.metadata = metadata
        logger.info(f"Successfully cached {len(metadata)} provisions.")

    def _get_active_llm(self) -> str:
        """Finds an available LLM model in LM Studio."""
        if self.active_llm_model:
            return self.active_llm_model

        try:
            req = urllib.request.Request(LM_STUDIO_MODELS_URL)
            res = urllib.request.urlopen(req, timeout=1.5)
            data = json.loads(res.read().decode())
            models = [m["id"] for m in data.get("data", [])]
            for preferred in ["qwen/qwen2.5-coder-14b", "qwen3-coder-30b-a3b-instruct", "google/gemma-4-e4b"]:
                if preferred in models:
                    self.active_llm_model = preferred
                    return preferred
            llms = [m for m in models if "embedding" not in m]
            if llms:
                self.active_llm_model = llms[0]
                return llms[0]
        except Exception:
            pass

        return "qwen/qwen2.5-coder-14b"

    def generate_hypothetical_document(self, query: str) -> Tuple[str, str]:
        """
        Generates a hypothetical EASA regulatory text excerpt for the query.
        Returns (hypothetical_text, generation_method).
        """
        clean_q = query.strip()
        model_name = self._get_active_llm()

        system_prompt = (
            "You are an expert EASA aviation regulatory drafting specialist. "
            "Draft a concise, realistic hypothetical excerpt of an EASA Implementing Rule (IR) "
            "or Acceptable Means of Compliance (AMC) that directly addresses the given aviation scenario or question. "
            "Use formal European aviation regulatory terminology (e.g. 'The operator shall ensure...', "
            "'acceptable means of compliance', 'safety management', 'operational procedures')."
        )
        user_prompt = f"Draft a concise hypothetical EASA regulatory provision addressing this topic:\nTopic/Question: {clean_q}\nHypothetical Provision:"

        try:
            body = json.dumps({
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 140,
                "temperature": 0.2
            }).encode("utf-8")

            req = urllib.request.Request(
                LM_STUDIO_URL,
                data=body,
                headers={"Content-Type": "application/json"}
            )
            res = urllib.request.urlopen(req, timeout=6.0)
            data = json.loads(res.read().decode())
            content = data["choices"][0]["message"]["content"].strip()
            if content and len(content) > 30:
                return content, f"LM Studio ({model_name})"
        except Exception as e:
            logger.warning(f"LM Studio HyDE generation unavailable or timed out: {e}")

        fallback_text = (
            f"EASA Commission Regulation (EU) No 965/2012 / Easy Access Rules for Air Operations. "
            f"The operator shall establish, implement and maintain operational procedures and technical compliance specifications "
            f"governing {clean_q}. The management system shall specify designated responsibilities, hazard identification, "
            f"risk mitigation, operational limitations, personnel competence, and compliance monitoring associated with {clean_q}."
        )
        return fallback_text, "AeroLex Expert Regulatory Template"

    def search_candidates(
        self,
        query: str,
        top_k: int = 12,
        active_sources: Set[str] = None,
        skybrary_topics: Set[str] = None
    ) -> Dict[str, Any]:
        """
        Executes HyDE search:
        1. Generates hypothetical regulatory document.
        2. Embeds hypothetical document.
        3. Computes dot product across all 19,616 provision vectors (if EASA active).
        4. Blends in secondary source candidates (FAA, EU, Skybrary, EUROCAE) if active.
        5. Returns top candidate nodes.
        """
        t0 = time.time()
        top_k = int(top_k) if top_k else 12
        hypo_doc, method = self.generate_hypothetical_document(query)
        active_sources = active_sources or {"EASA", "EU", "FAA", "SKYBRARY", "EUROCAE"}

        candidate_nodes = []
        hypo_vector = None

        # 1. EASA Vector Search (if active)
        if "EASA" in active_sources:
            hypo_vector = self.model.encode([hypo_doc], normalize_embeddings=True)[0]
            sim_scores = np.dot(self.embeddings, hypo_vector)
            top_indices = np.argsort(sim_scores)[::-1][:top_k]

            for idx in top_indices:
                score = float(sim_scores[idx])
                meta = self.metadata[idx]

                candidate_nodes.append({
                    "id": meta["id"],
                    "code": meta["code"],
                    "base_code": meta["base_code"],
                    "title": meta["title"],
                    "content_type": meta["content_type"],
                    "source": "EASA",
                    "legal_force": meta["legal_force"],
                    "annex": meta["annex_code"],
                    "annex_name": meta["annex_name"],
                    "score": round(score, 4),
                    "score_pct": int(round(score * 100)),
                    "snippet": meta["snippet"]
                })

        # 2. Multi-Source Matches from secondary sources (FAA, EU, Skybrary, EUROCAE)
        sec_sources = set(active_sources) - {"EASA"}
        if sec_sources:
            from ingestion.graph.sources import get_source_manager
            sm = get_source_manager()
            sec_matches = sm.search_sources(
                query,
                active_sources=sec_sources,
                skybrary_topics=skybrary_topics,
                limit_per_source=5
            )
            if sec_matches:
                if hypo_vector is None:
                    hypo_vector = self.model.encode([hypo_doc], normalize_embeddings=True)[0]
                sec_texts = [f"{m['code']} {m['title']} {m.get('text', '')[:200]}" for m in sec_matches]
                sec_embs = self.model.encode(sec_texts, normalize_embeddings=True)
                sec_scores = np.dot(sec_embs, hypo_vector)
                for score, m in zip(sec_scores, sec_matches):
                    candidate_nodes.append({
                        "id": m["id"],
                        "code": m["code"],
                        "base_code": m["code"],
                        "title": m["title"],
                        "content_type": m["type"],
                        "source": m["source"],
                        "legal_force": m.get("legal_force", m.get("subject", "")),
                        "annex": m["source"],
                        "annex_name": m.get("subject", ""),
                        "score": round(float(score), 4),
                        "score_pct": int(round(float(score) * 100)),
                        "snippet": m.get("text", "")[:280]
                    })

        candidate_nodes.sort(key=lambda x: x["score"], reverse=True)
        candidate_nodes = candidate_nodes[:top_k]

        duration = round(time.time() - t0, 3)
        return {
            "query": query,
            "hypothetical_document": hypo_doc,
            "generation_method": method,
            "duration_seconds": duration,
            "active_sources": list(active_sources),
            "candidate_count": len(candidate_nodes),
            "candidate_nodes": candidate_nodes,
            "candidates": candidate_nodes
        }


# Singleton engine instance
_hyde_engine: Optional[HydeEngine] = None


def get_hyde_engine() -> HydeEngine:
    global _hyde_engine
    if _hyde_engine is None:
        _hyde_engine = HydeEngine()
    return _hyde_engine
