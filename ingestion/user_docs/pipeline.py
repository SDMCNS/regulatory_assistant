"""
pipeline.py - Unified Ingestion Pipeline for User-Supplied Documents.

Coordinates format detection, extraction, chunking, database persistence,
vector embeddings generation, FTS index refresh, and executive governance actions
(superseding or suppressing predecessor documents).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from ingestion.core.config import settings
from ingestion.core.governance import deactivate_document
from ingestion.core.models import EmbeddingRecord, EmbeddingType
from ingestion.retrieval.embed_chunks import generate_embeddings, get_text_hash, is_lm_studio_available
from ingestion.retrieval.faiss_index import LocalVectorIndex
from ingestion.retrieval.rebuild_fts import rebuild_fts
from ingestion.skybrary_bookshelf.lib.chunker import SkybraryChunker
from ingestion.skybrary_bookshelf.lib.storage import save_to_sqlite

from .detector import DocFormat, detect_document_format
from .extractor import extract_user_document


def sanitize_doc_id(candidate: str, prefix: str = "USER") -> str:
    """Creates a URL-safe, clean document ID."""
    clean = re.sub(r"[^\w\-.]", "_", candidate.strip()).strip("_")
    if not clean:
        clean = f"doc_{int(time.time())}"
    if not clean.upper().startswith(prefix.upper()):
        clean = f"{prefix}_{clean}"
    return clean[:80]


def ingest_easa_xml_doc(
    file_path: Path,
    filename: str,
    custom_title: Optional[str] = None
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Ingests an EASA XML document using the EASA parser."""
    from ingestion.parsers.convert_easa_to_json import parse_easa_xml
    
    parsed_items = parse_easa_xml(str(file_path))
    if not parsed_items:
        raise ValueError("Failed to parse EASA XML structure or document is empty.")

    stem = Path(filename).stem
    doc_id = f"EASA_{sanitize_doc_id(stem, prefix='').lstrip('_')}"
    title = custom_title or stem.replace("_", " ").title()

    db_path = settings.SQLITE_PATH
    chunks: List[Dict[str, Any]] = []

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO documents (document_id, title, language, date, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            doc_id, title, "en", "", "EASA XML",
            json.dumps({"source": "EASA XML", "origin": "easa", "filename": filename})
        ))

        current_heading = None
        for idx, item in enumerate(parsed_items):
            meta = item.get("meta", {})
            text = item.get("text", "").strip()
            if not text:
                continue

            t_type = meta.get("type", "section")
            t_title = meta.get("title", "")
            t_id = meta.get("id", str(idx))

            if t_type == "heading":
                current_heading = t_title

            section_path = []
            if current_heading and t_title != current_heading:
                section_path.append(current_heading)
            if t_title:
                section_path.append(t_title)

            chunk_id = f"{doc_id}:{t_id}"
            embedding_text = f"Document: {title}\n"
            if section_path:
                embedding_text += f"Context: {' > '.join(section_path)}\n"
            embedding_text += f"\n{text}"

            chunks.append({
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "chunk_type": t_type,
                "section_path": json.dumps(section_path),
                "section_numbers": json.dumps([]),
                "source_text": text,
                "embedding_text": embedding_text,
                "parent_chunk_id": current_heading,
                "structure_json": json.dumps({"title": t_title}),
                "references_json": "[]",
                "metadata_json": json.dumps(meta)
            })

        # Insert chunks
        for i, c in enumerate(chunks):
            prev_id = chunks[i-1]["chunk_id"] if i > 0 else None
            next_id = chunks[i+1]["chunk_id"] if i < len(chunks) - 1 else None
            conn.execute("""
                INSERT OR REPLACE INTO chunks (
                    chunk_id, document_id, chunk_type, section_path, section_numbers,
                    source_text, embedding_text, parent_chunk_id, previous_chunk_id, next_chunk_id,
                    structure_json, references_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c["chunk_id"], c["document_id"], c["chunk_type"],
                c["section_path"], c["section_numbers"], c["source_text"],
                c["embedding_text"], c["parent_chunk_id"], prev_id, next_id,
                c["structure_json"], c["references_json"], c["metadata_json"]
            ))

    return doc_id, title, chunks


def ingest_faa_xml_doc(
    file_path: Path,
    filename: str,
    custom_title: Optional[str] = None
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Ingests a FAA 14 CFR XML file."""
    from ingestion.parsers.faa_cfr_parser import parse_cfr_volume

    doc_parts = parse_cfr_volume(file_path)
    if not doc_parts:
        raise ValueError("No valid 14 CFR Parts found in XML.")

    db_path = settings.SQLITE_PATH
    all_chunks: List[Dict[str, Any]] = []
    primary_doc_id = ""
    primary_title = ""

    with sqlite3.connect(db_path) as conn:
        for p_idx, part in enumerate(doc_parts):
            p_id = part["document_id"]
            p_title = custom_title if (p_idx == 0 and custom_title) else part["title"]
            if p_idx == 0:
                primary_doc_id = p_id
                primary_title = p_title

            conn.execute("""
                INSERT OR REPLACE INTO documents (document_id, title, language, date, source, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                p_id, p_title, "en", part.get("date", "2025-01-01"), "FAA XML",
                json.dumps(part.get("metadata", {}))
            ))

            part_chunks = part.get("chunks", [])
            for c in part_chunks:
                all_chunks.append(c)
                conn.execute("""
                    INSERT OR REPLACE INTO chunks (
                        chunk_id, document_id, chunk_type, section_path, section_numbers,
                        source_text, embedding_text, parent_chunk_id, previous_chunk_id, next_chunk_id,
                        structure_json, references_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["chunk_id"], c["document_id"], c["chunk_type"],
                    json.dumps(c.get("section_path", [])), json.dumps(c.get("section_numbers", [])),
                    c["source_text"], c["embedding_text"], c.get("parent_chunk_id"),
                    c.get("previous_chunk_id"), c.get("next_chunk_id"),
                    json.dumps(c.get("structure", {})), json.dumps(c.get("references", [])),
                    json.dumps(c.get("metadata", {}))
                ))

    return primary_doc_id, primary_title, all_chunks


def ingest_user_document(
    file_path: Path,
    filename: str,
    custom_title: Optional[str] = None,
    custom_date: Optional[str] = None,
    executive_action: str = "none",  # "none", "supersede", "suppress"
    target_doc_id: Optional[str] = None,
    embed_vectors: bool = True
) -> Dict[str, Any]:
    """
    Executes full ingestion workflow for user-supplied documents:
    1. Detects format (EASA XML, EU Formex XML, FAA CFR XML, or Skybrary workflow).
    2. Runs parser & chunker according to detected workflow.
    3. Saves documents and chunks into central SQLite chunks.db.
    4. Generates FAISS vector embeddings (if LM Studio / embedding endpoint is online).
    5. Rebuilds and optimizes SQLite FTS5 search index.
    6. Applies executive governance action (superseding or suppressing predecessor).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # 1. Format Detection
    format_info = detect_document_format(file_path, filename)
    doc_format = format_info["format"]
    db_path = settings.SQLITE_PATH

    new_doc_id = ""
    doc_title = ""
    created_chunks: List[Any] = []
    source = "USER"
    origin = "user"

    # 2. Ingestion Routing
    if doc_format == DocFormat.EASA_XML.value:
        source = "EASA XML"
        origin = "easa"
        new_doc_id, doc_title, created_chunks = ingest_easa_xml_doc(file_path, filename, custom_title)

    elif doc_format == DocFormat.FAA_CFR_XML.value:
        source = "FAA XML"
        origin = "faa"
        new_doc_id, doc_title, created_chunks = ingest_faa_xml_doc(file_path, filename, custom_title)

    else:
        # Standard User-Supplied Document -> Skybrary Workflow
        source = "USER"
        origin = "user"
        extracted = extract_user_document(file_path, filename)
        doc_title = custom_title or extracted["title"]
        pub_date = custom_date or extracted["date"] or ""

        # Unique document ID
        raw_slug = Path(filename).stem
        new_doc_id = sanitize_doc_id(raw_slug, prefix="USER")

        # Chunk with SkybraryChunker (target words 350, max words 600, page & structure aware)
        chunker = SkybraryChunker(target_words=350, max_words=600)
        pub_info = {
            "id": new_doc_id.replace("USER_", ""),
            "title": doc_title,
            "category": "User Supplied",
            "author": "User Upload",
            "publication_date": pub_date,
            "sha256": extracted["sha256"],
            "filename": filename,
            "origin": "user"
        }

        doc_meta, chunk_records = chunker.chunk_document(
            pub_info=pub_info,
            raw_text=extracted["raw_text"],
            doc_id_prefix="USER"
        )
        # Ensure source is USER and origin is user
        doc_meta.source = "USER"
        doc_meta.category = "User Supplied"
        doc_meta.metadata = {
            "origin": "user",
            "category": "User Supplied",
            "filename": filename,
            "sha256": extracted["sha256"],
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "page_count": extracted["page_count"],
            "word_count": extracted["word_count"],
        }

        # Save to SQLite
        save_to_sqlite(db_path=db_path, doc_meta=doc_meta, chunks=chunk_records, create_fts=False)
        created_chunks = chunk_records

    # 3. Vector Embeddings Generation (into FAISS)
    embeddings_count = 0
    if embed_vectors and is_lm_studio_available():
        try:
            vector_index = LocalVectorIndex()
            chunk_texts: List[str] = []
            chunk_ids: List[str] = []

            for c in created_chunks:
                c_id = c.chunk_id if hasattr(c, "chunk_id") else c["chunk_id"]
                emb_text = c.embedding_text if hasattr(c, "embedding_text") else c["embedding_text"]
                chunk_ids.append(c_id)
                chunk_texts.append(f"passage: {emb_text}")

            if chunk_texts:
                # Embed in batches of 16
                for b_start in range(0, len(chunk_texts), 16):
                    b_texts = chunk_texts[b_start:b_start + 16]
                    b_ids = chunk_ids[b_start:b_start + 16]
                    vecs = generate_embeddings(b_texts)

                    if vecs and len(vecs) == len(b_texts):
                        records = []
                        for cid, txt, vec in zip(b_ids, b_texts, vecs):
                            records.append(EmbeddingRecord(
                                embedding_id=cid,
                                fragment_id=cid,
                                embedding_type=EmbeddingType.CHUNK,
                                model=settings.EMBEDDING_MODEL_NAME,
                                dimensions=len(vec),
                                vector=vec,
                                text_hash=get_text_hash(txt)
                            ))
                        vector_index.add_records(records)
                        embeddings_count += len(records)

            # Also embed document prior into ACT partition
            act_text = f"passage: [{source} Document] {doc_title}. Regulatory Instrument ID: {new_doc_id}."
            act_vecs = generate_embeddings([act_text])
            if act_vecs:
                vector_index.add_records([EmbeddingRecord(
                    embedding_id=new_doc_id,
                    fragment_id=new_doc_id,
                    embedding_type=EmbeddingType.ACT,
                    model=settings.EMBEDDING_MODEL_NAME,
                    dimensions=len(act_vecs[0]),
                    vector=act_vecs[0],
                    text_hash=get_text_hash(act_text)
                )])
        except Exception as e:
            print(f"[User Ingestion Warning] Failed generating embeddings for {new_doc_id}: {e}")

    # 4. Rebuild / Optimize FTS5 Search Index
    try:
        rebuild_fts(db_path)
    except Exception as e:
        print(f"[User Ingestion Warning] Failed refreshing FTS5 index: {e}")

    # 5. Apply Executive Governance Action on Predecessor Document
    action_summary = "Kept both active (no changes to existing documents)."
    if target_doc_id:
        target_doc_id_clean = target_doc_id.strip()
        if executive_action == "supersede":
            try:
                deactivate_document(
                    document_id=target_doc_id_clean,
                    reason=f"Superseded by user-supplied document '{doc_title}' ({new_doc_id})",
                    superseded_by=new_doc_id
                )
                action_summary = f"Predecessor document '{target_doc_id_clean}' was marked as superseded by '{new_doc_id}'."
            except Exception as e:
                action_summary = f"Error superseding '{target_doc_id_clean}': {e}"

        elif executive_action == "suppress":
            try:
                deactivate_document(
                    document_id=target_doc_id_clean,
                    reason=f"Suppressed upon upload of user-supplied document '{doc_title}' ({new_doc_id})",
                    superseded_by=None
                )
                action_summary = f"Predecessor document '{target_doc_id_clean}' was suppressed/deactivated."
            except Exception as e:
                action_summary = f"Error suppressing '{target_doc_id_clean}': {e}"

    # Invalidate catalog cache in memory if imported
    try:
        from api.regulations import _CATALOG_CACHE
        _CATALOG_CACHE["timestamp"] = 0
    except Exception:
        pass

    return {
        "status": "success",
        "document_id": new_doc_id,
        "title": doc_title,
        "source": source,
        "origin": origin,
        "workflow": format_info["workflow"],
        "chunks_count": len(created_chunks),
        "embeddings_count": embeddings_count,
        "executive_action": executive_action,
        "target_doc_id": target_doc_id,
        "action_summary": action_summary
    }
