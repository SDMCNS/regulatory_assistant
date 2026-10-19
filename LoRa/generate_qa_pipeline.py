#!/usr/bin/env python3
"""
Aviation Regulations & Operations LoRA Q&A Generation Pipeline
==============================================================
Generates synthetic Question & Answer pairs from chunked aviation regulation 
documents (JSON format) using LM Studio and google/gemma-4-e4b.

Features:
- Incremental & Resumeable: Uses SQLite checkpointing so newly added chunk files
  are seamlessly discovered and processed without duplicate generations.
- Continuous Watch Mode: Can monitor the chunks/ folder for incoming files.
- Multithreaded: Configurable worker threads for high throughput with LM Studio.
- Context-Aware: Supplies document title, category, and section path to the prompt.
- SFT/LoRA Ready: Outputs formatted JSONL lines ready for HuggingFace SFTTrainer.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# CONFIGURATION & DEFAULTS
# ==============================================================================

DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-4-e4b"
DEFAULT_CHUNKS_DIR = "chunks"
DEFAULT_OUTPUT_FILE = "aviation_qa_lora.jsonl"
DEFAULT_DB_FILE = "qa_generation_state.db"

SYSTEM_PROMPT = """You are an expert aviation regulatory and operations specialist.
Your task is to generate realistic, accurate, and professional Question and Answer pairs based strictly on the provided aviation document excerpt.

CRITICAL RULES ON PEOPLE, ROLES, AND TIMELESS KNOWLEDGE:
These aviation documents span 2-3 decades and will remain authoritative for many years to come. Regulatory rules, engineering physics, operational procedures, and investigation findings endure, whereas individual personnel change:
1. NEVER generate questions or answers concerning ephemeral points of contact, office liaisons, inquiry contacts, email addresses, phone numbers, or transient administrative post-holders (e.g. do NOT ask "Who can be contacted for...", "To whom should inquiries be directed...", or mention specific names as contact points).
2. DISTINGUISH CONTACTS FROM SCHOLARLY AUTHORS / EXPERTS: You MAY reference individuals who are authors of research papers, lead accident investigators, developers of recognized safety frameworks, or pioneering subject matter experts (e.g., James Reason, Rasmussen, academic researchers, study authors). Cite their conceptual findings, safety models, or empirical conclusions—NOT their contact details.
3. FOCUS ON LASTING SUBSTANCE:
   - Regulatory mandates, prohibitions, rights, and exemptions (e.g., EASA, FAA, ICAO).
   - Operational procedures, emergency responses, contingency actions.
   - Investigation conclusions, causal factors, system failures, and safety recommendations.
   - Technical standards, aeronautical definitions, and safety management concepts.
4. Formulate 2 distinct Q&A pairs:
   - Pair 1: Operational or situational question (e.g., procedures, decision-making, emergency handling).
   - Pair 2: Regulatory requirement, technical standard, investigation finding, or expert concept.
5. Answer directly, authoritatively, and professionally without referencing phrases like "the excerpt states" or "according to the text".
6. Output MUST be ONLY a valid JSON array of objects with keys "q" and "a". No markdown or preamble.

Example output:
[
  {
    "q": "What separation minima must be applied when primary radar data is lost?",
    "a": "When primary radar data is lost, air traffic controllers must revert to procedural separation minima, verify positions via voice reports or available SSR, and coordinate with adjacent sectors."
  },
  {
    "q": "What are the primary organisational factors contributing to latent errors in safety management?",
    "a": "According to systemic accident models, latent errors arise from strategic management decisions, resource allocation constraints, and organizational culture that remain dormant until triggered by active operational conditions."
  }
]"""

# ==============================================================================
# LOGGING SETUP
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LoRA-QAGen")

# ==============================================================================
# STATE & DATABASE (RESUME / DEDUPLICATION)
# ==============================================================================

class StateManager:
    """Manages SQLite checkpoint state to track processed chunks and files."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT,
                    file_path TEXT,
                    qa_count INTEGER,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_path TEXT PRIMARY KEY,
                    mtime REAL,
                    file_size INTEGER,
                    chunk_count INTEGER,
                    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_chunk_processed(self, chunk_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_chunks WHERE chunk_id = ?", (chunk_id,))
            return cursor.fetchone() is not None

    def get_processed_chunk_ids(self) -> set[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chunk_id FROM processed_chunks")
            return {row[0] for row in cursor.fetchall()}

    def record_processed_chunk(self, chunk_id: str, document_id: str, file_path: str, qa_count: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO processed_chunks (chunk_id, document_id, file_path, qa_count)
                VALUES (?, ?, ?, ?)
            """, (chunk_id, document_id, file_path, qa_count))
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*), coalesce(sum(qa_count), 0) FROM processed_chunks")
            row = cursor.fetchone()
            return {
                "chunks_processed": row[0] if row else 0,
                "qa_pairs_generated": row[1] if row else 0
            }

# ==============================================================================
# LLM CLIENT (LM STUDIO / GEMMA)
# ==============================================================================

class LMStudioClient:
    """Client for generating completions via LM Studio."""

    def __init__(self, api_url: str = DEFAULT_LM_STUDIO_URL, model: str = DEFAULT_MODEL, timeout: int = 90):
        self.api_url = api_url
        self.model = model
        self.timeout = timeout

    def check_connection(self) -> bool:
        """Verify LM Studio server connectivity."""
        try:
            base_url = self.api_url.rsplit("/chat/completions", 1)[0] + "/models"
            req = urllib.request.Request(base_url, headers={"User-Agent": "LoRA-Generator"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Connection check to LM Studio failed: {e}")
            return False

    def generate_qa(self, context_header: str, chunk_text: str, max_retries: int = 2) -> List[Dict[str, str]]:
        """Call LM Studio to generate Q&A pairs for a given chunk."""
        user_message = (
            f"Aviation Reference:\n{context_header}\n\n"
            f"Document Excerpt:\n{chunk_text}\n\n"
            f"Generate 2 high-quality Q&A pairs in JSON format:"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.25,
            "max_tokens": 1200,
            "stream": False
        }

        data = json.dumps(payload).encode("utf-8")

        for attempt in range(max_retries + 1):
            try:
                req = urllib.request.Request(
                    self.api_url,
                    headers={"Content-Type": "application/json"},
                    data=data
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    raw_content = res_body["choices"][0]["message"]["content"].strip()
                    parsed = self._extract_json(raw_content)
                    if parsed:
                        return parsed
                    logger.warning(f"Failed to parse JSON from model. Raw content preview: {raw_content[:200]}")
            except urllib.error.URLError as e:
                logger.warning(f"Network error on attempt {attempt+1}: {e}")
            except Exception as e:
                logger.warning(f"Exception on attempt {attempt+1}: {e}")

            time.sleep(1.0 * (attempt + 1))

        return []

    def _extract_json(self, text: str) -> Optional[List[Dict[str, str]]]:
        """Safely extract and validate JSON list from model response."""
        cleaned = text.strip()

        # Handle markdown blocks ```json ... ```
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        # Regex search for JSON array if surrounded by other characters
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                data = json.loads(candidate)
                if isinstance(data, list):
                    valid_pairs = []
                    for item in data:
                        if isinstance(item, dict) and "q" in item and "a" in item:
                            q_text = str(item["q"]).strip()
                            a_text = str(item["a"]).strip()
                            if len(q_text) > 10 and len(a_text) > 15:
                                valid_pairs.append({"q": q_text, "a": a_text})
                    if valid_pairs:
                        return valid_pairs
            except json.JSONDecodeError:
                pass

    def _is_ephemeral_contact(self, q: str, a: str) -> bool:
        """
        Detects if a Q&A pair is asking for or providing ephemeral contact details
        (e.g., person phone, email, point of contact), while preserving scholarly
        authorship or expert citations.
        """
        text = (q + " " + a).lower()

        # Phrases indicating ephemeral administrative/contact info
        contact_markers = [
            r"\bcontact\s+(person|point|officer|details|number|information|email)\b",
            r"\bpoint\s+of\s+contact\b",
            r"\bdirected\s+to\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b",
            r"\binquiries\s+(can|should|may)\s+be\s+directed\b",
            r"\breach\s+out\s+to\b",
            r"\bcall\s+(or\s+email\s+)?(\+?\d[\d\s-]{6,}|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)",
            r"\bemail\s+(address\s+)?is\b",
            r"\bphone\s+number\s+is\b",
            r"\bfocal\s+point\b",
            r"\bwhom\s+should\s+(a\s+)?(pilot|operator|member|user)\s+(contact|direct)\b"
        ]

        for pat in contact_markers:
            if re.search(pat, text):
                logger.info(f"Filtered out ephemeral contact pair: '{q[:60]}...'")
                return True

        return False

    def _extract_json(self, text: str) -> Optional[List[Dict[str, str]]]:
        """Safely extract and validate JSON list from model response."""
        cleaned = text.strip()

        # Handle markdown blocks ```json ... ```
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        def parse_and_validate(raw_str: str) -> Optional[List[Dict[str, str]]]:
            try:
                data = json.loads(raw_str)
                if isinstance(data, list):
                    valid_pairs = []
                    for item in data:
                        if isinstance(item, dict) and "q" in item and "a" in item:
                            q_text = str(item["q"]).strip()
                            a_text = str(item["a"]).strip()
                            if len(q_text) > 10 and len(a_text) > 15:
                                # Reject if it contains transient contact personnel info
                                if not self._is_ephemeral_contact(q_text, a_text):
                                    valid_pairs.append({"q": q_text, "a": a_text})
                    if valid_pairs:
                        return valid_pairs
            except json.JSONDecodeError:
                pass
            return None

        # Try regex search for candidate JSON array
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if match:
            res = parse_and_validate(match.group(0))
            if res:
                return res

        # Attempt recovery if unclosed array or trailing commas
        if "[" in cleaned and not cleaned.rstrip().endswith("]"):
            candidate = cleaned.rstrip()
            if candidate.endswith("}"):
                candidate += "]"
            elif candidate.endswith("},"):
                candidate = candidate[:-1] + "]"
            res = parse_and_validate(candidate)
            if res:
                return res

        return parse_and_validate(cleaned)

# ==============================================================================
# CHUNK PARSING & FILTERING
# ==============================================================================

@dataclass
class EligibleChunk:
    chunk_id: str
    document_id: str
    title: str
    category: str
    author: str
    section_path: str
    text: str
    file_path: str

def is_informative_chunk(text: str, min_chars: int = 200, max_chars: int = 3500) -> bool:
    """Filter out non-informative or boilerplate chunks."""
    s = text.strip()
    if len(s) < min_chars or len(s) > max_chars:
        return False

    words = s.split()
    if len(words) < 35:
        return False

    # Check for pure copyright/distribution footers
    lower = s.lower()
    if lower.startswith("©") and len(s) < 350:
        return False
    if "all rights reserved" in lower and len(s) < 300:
        return False
    if "this document is published by eurocontrol for information purposes" in lower and len(s) < 400:
        return False
    if "table of contents" in lower and s.count(".") > 15:
        return False

    # Check for document header / cover page patterns (e.g. ATSB Occurrence Investigation ... Final)
    if "final report" in lower and "transport safety report" in lower and len(words) < 70:
        return False

    # Must contain some alphabetical text and sentences
    alpha_count = sum(c.isalpha() for c in s)
    if alpha_count / max(1, len(s)) < 0.55:
        return False

    return True

def extract_chunks_from_file(file_path: Path, min_chars: int = 200, max_chars: int = 3500) -> List[EligibleChunk]:
    """Parse a single .chunks.json file into eligible chunks."""
    eligible: List[EligibleChunk] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc_meta = data.get("document", {})
        doc_id = doc_meta.get("document_id") or file_path.stem
        title = doc_meta.get("title") or ""
        category = doc_meta.get("category") or ""
        author = doc_meta.get("author") or ""

        chunks_list = data.get("chunks", [])
        for ch in chunks_list:
            chunk_id = ch.get("chunk_id")
            if not chunk_id:
                continue

            # Skip cover page if word count is small
            meta = ch.get("metadata", {})
            if meta.get("page_start") == 1 and meta.get("word_count", 0) < 60:
                continue

            source_text = ch.get("source_text") or ch.get("embedding_text") or ""
            source_text = source_text.strip()

            if not is_informative_chunk(source_text, min_chars=min_chars, max_chars=max_chars):
                continue

            section_path_list = ch.get("section_path") or []
            section_path_str = " > ".join(str(p) for p in section_path_list)

            eligible.append(EligibleChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                title=title,
                category=category,
                author=author,
                section_path=section_path_str,
                text=source_text,
                file_path=str(file_path)
            ))
    except Exception as e:
        logger.debug(f"Failed to parse {file_path.name}: {e}")

    return eligible

# ==============================================================================
# MAIN PROCESSING PIPELINE
# ==============================================================================

def process_single_chunk(
    chunk: EligibleChunk,
    client: LMStudioClient,
    state_mgr: StateManager,
    output_file: Path
) -> int:
    """Worker function to process one chunk and append results."""
    # Build concise context header
    header_parts = []
    if chunk.title:
        header_parts.append(f"Title: {chunk.title}")
    if chunk.category:
        header_parts.append(f"Category: {chunk.category}")
    if chunk.author:
        header_parts.append(f"Authority: {chunk.author}")
    if chunk.section_path:
        header_parts.append(f"Section: {chunk.section_path}")
    context_header = " | ".join(header_parts)

    qa_pairs = client.generate_qa(context_header, chunk.text)
    if not qa_pairs:
        # Still record with 0 QA to avoid infinite retry loops on unparsable text
        state_mgr.record_processed_chunk(chunk.chunk_id, chunk.document_id, chunk.file_path, 0)
        return 0

    lines_to_write = []
    for qa in qa_pairs:
        record = {
            "task": "aviation_qa",
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "category": chunk.category,
            "author": chunk.author,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert aviation regulatory and operations assistant. Provide accurate, professional, and authoritative guidance grounded in established aviation standards and procedures."
                },
                {
                    "role": "user",
                    "content": qa["q"]
                },
                {
                    "role": "assistant",
                    "content": qa["a"]
                }
            ]
        }
        lines_to_write.append(json.dumps(record, ensure_ascii=False))

    # Append safely
    with open(output_file, "a", encoding="utf-8") as f_out:
        for line in lines_to_write:
            f_out.write(line + "\n")

    state_mgr.record_processed_chunk(chunk.chunk_id, chunk.document_id, chunk.file_path, len(qa_pairs))
    return len(qa_pairs)


def run_pipeline(
    chunks_dir: Path,
    output_file: Path,
    db_file: Path,
    limit: Optional[int],
    workers: int,
    watch: bool,
    sleep_interval: int,
    min_chars: int,
    max_chars: int,
    model_name: str,
    max_hours: Optional[float] = None,
    golden_file: Optional[Path] = None
):
    """Executes the Q&A generation pipeline across chunk files or distilled golden corpus."""
    session_start_time = time.time()
    state_mgr = StateManager(db_file)
    client = LMStudioClient(model=model_name)

    logger.info("=" * 70)
    logger.info("AVIATION LoRA Q&A GENERATION PIPELINE")
    logger.info("=" * 70)
    if golden_file:
        logger.info(f"Target Golden Corpus:    {golden_file}")
    else:
        logger.info(f"Target Chunks Directory: {chunks_dir}")
    logger.info(f"Output Dataset:          {output_file}")
    logger.info(f"State Database:          {db_file}")
    logger.info(f"Worker Threads:          {workers}")
    logger.info(f"Model ID:                {model_name}")
    if max_hours:
        logger.info(f"Time Budget:             {max_hours:.2f} hours (auto-stops after duration)")

    if not client.check_connection():
        logger.warning("Could not reach LM Studio models API at http://127.0.0.1:1234/v1/models.")
        logger.warning("Make sure LM Studio local server is started and the model is loaded.")

    initial_stats = state_mgr.get_stats()
    logger.info(f"Current State: {initial_stats['chunks_processed']} chunks previously processed "
                f"({initial_stats['qa_pairs_generated']} Q&A pairs generated).")

    processed_ids = state_mgr.get_processed_chunk_ids()
    total_generated_session = 0
    total_chunks_session = 0

    while True:
        from collections import defaultdict
        import random

        chunks_by_category = defaultdict(list)

        if golden_file and golden_file.exists():
            logger.info(f"Loading distilled chunks from {golden_file.name}...")
            with open(golden_file, "r", encoding="utf-8") as f_gold:
                for line in f_gold:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    cid = item.get("chunk_id")
                    if cid in processed_ids:
                        continue
                    cat = item.get("category") or "Uncategorized"
                    chunks_by_category[cat].append(EligibleChunk(
                        chunk_id=cid,
                        document_id=item.get("document_id", ""),
                        title=item.get("title", ""),
                        category=cat,
                        author=item.get("author", ""),
                        section_path=item.get("section_path", ""),
                        text=item.get("text", ""),
                        file_path=item.get("file_path", "")
                    ))
            logger.info(f"Loaded {sum(len(v) for v in chunks_by_category.values())} pending golden chunks across {len(chunks_by_category)} categories.")
        else:
            # Discover all .chunks.json files currently in directory
            chunk_files = list(chunks_dir.rglob("*.chunks.json"))
            logger.info(f"Discovered {len(chunk_files)} .chunks.json files in {chunks_dir.name}...")

            files_by_category = defaultdict(list)
            for cf in chunk_files:
                cat_name = cf.parent.name
                files_by_category[cat_name].append(cf)

            for cat in files_by_category:
                random.seed(42)
                random.shuffle(files_by_category[cat])

            logger.info(f"Discovered {len(files_by_category)} distinct aviation categories.")

            for cat_name, cat_files in files_by_category.items():
                for cf in cat_files:
                    file_chunks = extract_chunks_from_file(cf, min_chars=min_chars, max_chars=max_chars)
                    unprocessed = [ch for ch in file_chunks if ch.chunk_id not in processed_ids]
                    chunks_by_category[cat_name].extend(unprocessed)
                    if len(chunks_by_category[cat_name]) >= 150:
                        break

        # Interleave round-robin across all categories to guarantee balanced diversity
        queue: List[EligibleChunk] = []
        cat_lists = [chunks_by_category[c] for c in sorted(chunks_by_category.keys()) if chunks_by_category[c]]
        max_depth = max((len(l) for l in cat_lists), default=0)

        for depth in range(max_depth):
            for c_list in cat_lists:
                if depth < len(c_list):
                    queue.append(c_list[depth])
                    if limit and len(queue) >= limit:
                        break
            if limit and len(queue) >= limit:
                break

        logger.info(f"Queued {len(queue)} pending chunks across {len(cat_lists)} active categories (balanced round-robin).")

        if queue:
            logger.info(f"Starting Q&A generation with {workers} parallel worker(s)...")
            start_time = time.time()
            time_limit_reached = False

            with ThreadPoolExecutor(max_workers=workers) as executor:
                # Submit only while within time limit
                future_to_chunk = {}
                for ch in queue:
                    if max_hours and ((time.time() - session_start_time) >= max_hours * 3600):
                        logger.info(f"Target duration of {max_hours:.2f} hours reached. Stopping submissions.")
                        time_limit_reached = True
                        break
                    future_to_chunk[executor.submit(process_single_chunk, ch, client, state_mgr, output_file)] = ch

                completed_count = 0
                for future in as_completed(future_to_chunk):
                    ch = future_to_chunk[future]
                    completed_count += 1
                    total_chunks_session += 1
                    processed_ids.add(ch.chunk_id)

                    try:
                        n_qa = future.result()
                        total_generated_session += n_qa
                        if completed_count % 10 == 0 or completed_count == len(future_to_chunk):
                            elapsed = time.time() - start_time
                            session_elapsed = time.time() - session_start_time
                            rate = completed_count / max(1.0, elapsed)
                            rem_hours = max(0.0, max_hours - (session_elapsed / 3600.0)) if max_hours else 0.0
                            logger.info(
                                f"Progress: [{completed_count}/{len(future_to_chunk)}] chunks "
                                f"({total_generated_session} Q&As) | "
                                f"{rate:.2f} chunks/sec | Elapsed: {session_elapsed/3600:.2f}h"
                                f"{f' | Remaining: {rem_hours:.2f}h' if max_hours else ''} | "
                                f"Doc: {ch.document_id[:35]}"
                            )
                    except Exception as exc:
                        logger.error(f"Error processing chunk {ch.chunk_id}: {exc}")

                    if max_hours and ((time.time() - session_start_time) >= max_hours * 3600):
                        logger.info(f"Time budget of {max_hours:.2f} hours reached during batch processing.")
                        time_limit_reached = True

            logger.info(f"Finished processing batch of {len(future_to_chunk)} chunks.")

            if time_limit_reached:
                logger.info("Time limit reached. Exiting pipeline loop gracefully.")
                break

        if not watch:
            break

        if max_hours and ((time.time() - session_start_time) >= max_hours * 3600):
            logger.info(f"Time limit of {max_hours:.2f} hours reached. Exiting watch loop.")
            break

        logger.info(f"Watch mode active. Sleeping for {sleep_interval}s before checking for new files...")
        time.sleep(sleep_interval)

    final_stats = state_mgr.get_stats()
    total_session_elapsed = time.time() - session_start_time
    logger.info("=" * 70)
    logger.info("PIPELINE EXECUTION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total Chunks in DB:     {final_stats['chunks_processed']}")
    logger.info(f"Total Q&As in DB:       {final_stats['qa_pairs_generated']}")
    logger.info(f"Session Chunks:         {total_chunks_session}")
    logger.info(f"Session Q&As Generated: {total_generated_session}")
    logger.info(f"Output saved to:        {output_file.resolve()}")
    logger.info("Done.")

# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Aviation Regulations & Operations LoRA Q&A Generation Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--chunks-dir", type=str, default=DEFAULT_CHUNKS_DIR,
                        help="Root folder containing chunked .json files")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_FILE,
                        help="Target JSONL file for training pairs")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_FILE,
                        help="SQLite state database for deduplication and resume")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help="Model name loaded in LM Studio")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of chunks to process in this run (None for all)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent requests to LM Studio (keep 1 for default desktop LM Studio)")
    parser.add_argument("--watch", action="store_true",
                        help="Run continuously in watch mode, polling for newly added files")
    parser.add_argument("--interval", type=int, default=30,
                        help="Interval in seconds between scans in watch mode")
    parser.add_argument("--min-chars", type=int, default=160,
                        help="Minimum character count for a chunk to be processed")
    parser.add_argument("--max-chars", type=int, default=3500,
                        help="Maximum character count for a chunk to be processed")
    parser.add_argument("--golden-chunks", type=str, default=None,
                        help="Path to pre-distilled golden chunks JSONL file (skips scanning chunks dir)")
    parser.add_argument("--max-hours", type=float, default=None,
                        help="Maximum execution time budget in hours (e.g. 10.0)")

    args = parser.parse_args()

    chunks_path = Path(args.chunks_dir).resolve()
    golden_path = Path(args.golden_chunks).resolve() if args.golden_chunks else None
    if not golden_path and not chunks_path.exists():
        logger.error(f"Chunks directory does not exist: {chunks_path}")
        sys.exit(1)

    output_path = Path(args.output).resolve()
    db_path = Path(args.db).resolve()

    run_pipeline(
        chunks_dir=chunks_path,
        output_file=output_path,
        db_file=db_path,
        limit=args.limit,
        workers=args.workers,
        watch=args.watch,
        sleep_interval=args.interval,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        model_name=args.model,
        max_hours=args.max_hours,
        golden_file=golden_path
    )

if __name__ == "__main__":
    main()
