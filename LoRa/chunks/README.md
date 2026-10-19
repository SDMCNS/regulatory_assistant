# Aviation Chunks Data Directory Guide

This directory (`chunks/`) is intended to store pre-processed, chunked aviation operations and regulatory source documents in JSON format.

> [!NOTE]
> The full raw dataset contains over **6,700 chunk files** (~330,000 individual paragraphs and sections) and is excluded from git tracking to prevent repository bloat. To inspect the expected file schema, refer to [`../chunks_sample/sample.chunks.json`](../chunks_sample/sample.chunks.json) or [`../chunks_sample/sample_chunks.jsonl`](../chunks_sample/sample_chunks.jsonl).

---

## 1. Directory Structure Convention

Each chunk file is placed within a subfolder corresponding to its aviation domain or operational category:

```text
chunks/
├── Accident Investigation/
│   └── Flight Data Recorder Handbook.chunks.json
├── Accident Reports/
│   └── Accident Report_ 2007-01-25 - B735.chunks.json
├── Air Ground Communication/
│   └── Voice Communication Procedures.chunks.json
├── Airspace Infringement/
│   └── European Action Plan Airspace Infringement.chunks.json
├── Airworthiness/
│   └── Maintenance Oversight Directive.chunks.json
├── Human Factors/
│   └── CRM Implementation Guidelines.chunks.json
└── ... (86 active categories)
```

---

## 2. File Format & Schema Specification

Each `*.chunks.json` file has the following JSON structure:

```json
{
  "document": {
    "document_id": "SKYBRARY_2667",
    "title": "Advisory to Operators of Civil Unmanned Aircraft Systems",
    "author": "NTSB",
    "category": "Accident Investigation",
    "publication_date": "29.Jul.2016",
    "total_pages": 4,
    "total_chunks": 12
  },
  "chunks": [
    {
      "chunk_id": "SKYBRARY_2667:P2:3",
      "document_id": "SKYBRARY_2667",
      "chunk_type": "paragraph",
      "section_path": ["Requirements", "Notification Standards"],
      "source_text": "A civil UAS operator must immediately and by the most expeditious means, notify the NTSB of an accident or incident...",
      "metadata": {
        "page_start": 2,
        "page_end": 2,
        "word_count": 215,
        "char_count": 1420
      }
    }
  ]
}
```

### Key Field Descriptions:
- **`chunk_id`** *(string, unique)*: Globally unique identifier for the chunk (e.g. `DOC_ID:PAGE:INDEX`).
- **`document_id`** *(string)*: Identifier of the parent publication.
- **`section_path`** *(array of strings)*: Breadcrumb path of document chapters and subheadings.
- **`source_text`** *(string)*: The authoritative raw text content of the chunk.
- **`metadata`** *(object)*: Contains `page_start`, `page_end`, and text metrics (`word_count`, `char_count`).

---

## 3. How Chunks are Consumed in the LoRA Pipeline

1. **Non-LLM Distillation (`distill_corpus.py`):**
   Scans all `.chunks.json` files in this directory and extracts high-salience chunks into `golden_chunks.jsonl` by filtering out boilerplate and ranking regulatory/operational directive density.
2. **Q&A Generation (`generate_qa_pipeline.py`):**
   Reads chunks and queries local LLM endpoints (LM Studio with `google/gemma-4-e4b`) to produce structured Q&A pairs for fine-tuning.
