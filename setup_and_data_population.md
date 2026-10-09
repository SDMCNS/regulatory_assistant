# AeroLex: Setup and Data Population Workflows

This document outlines the end-to-end process for setting up the AeroLex environment and populating the database with various regulatory documents including EU Formex Acts, EASA Easy Access Rules, FAA Title 14 CFR, SKYbrary, and custom user-authored notes.

## 1. System Requirements & Initial Setup

- **Python**: 3.10+
- **Node.js**: 18+ and `npm`
- **LM Studio** (for local offline LLM) or a **Google Gemini API Key** (for cloud-based AI processing)

### Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/SDMCNS/regulatory_assistant.git
cd regulatory_assistant
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux / macOS
pip install -r requirements.txt
```

### Configuration
Create a `user.settings.conf` file in the root folder. You can override settings here:
```ini
DATA_DIR=./ingestion/data

LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL_NAME=qwen2.5-7b-instruct
EMBEDDING_MODEL_NAME=text-embedding-nomic-embed-text-v1.5
EMBEDDING_DIMENSIONS=768

GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

---

## 2. Universal Ingestion Command (EASA & EU Formex)

The most straightforward way to ingest standard EU Formex XML documents and EASA Easy Access Rules is via the central ingestion orchestrator (`start.py`).

```bash
# General ingestion (assuming Formex files exist in ingestion/data/formex)
python start.py ingest

# Download and ingest EASA rules from the official RSS feed:
python start.py ingest --download_easa

# Ingest with a limit (useful for testing):
python start.py ingest --download_easa --limit 20
```

### Pipeline Steps Executed:
1. **Formex Ingestion**: Reads XML from `ingestion/data/formex`, chunks it, and saves to the database.
2. **EASA XML Downloader**: Downloads the latest rules if `--download_easa` is provided.
3. **EASA XML to JSON Conversion**: Parses the EASA XML files into an intermediate JSON format.
4. **EASA Chunker Pipeline**: Breaks down EASA JSON into searchable semantic chunks.
5. **Embedding Generation**: Automatically connects to your local (LM Studio) or cloud embedding model and generates vector embeddings for new chunks.
6. **FTS Rebuild**: Rebuilds the SQLite Full-Text Search (BM25) index to ensure keyword searches reflect the new data.

---

## 3. FAA (Title 14 CFR) Data Population

The FAA parsing relies on standard XML files obtained from the CFR repository. Since CFR files are typically massive, they use a dedicated parser and chunker pipeline.

```bash
# 1. Parse FAA Title 14 CFR XML to extract Part-level documents
python -m ingestion.parsers.faa_parser ingestion/data/regulations_xml/CFR-2025-title14-vol1.xml

# 2. Chunk the extracted parts and insert them into the DB
python -m ingestion.parsers.faa_chunker

# 3. Generate Vector Embeddings for the new FAA chunks
python -m ingestion.retrieval.embed_chunks

# 4. Rebuild the FTS Index
python -m ingestion.retrieval.rebuild_fts
```

---

## 4. User-Generated Data & Custom Manuals

AeroLex allows users to create their own custom documentation, notes, and operating manuals that are indexed just like official regulations.

### Authoring Manuals
Users can write standard operating procedures (SOPs) or flight operations manuals using the `DocumentBuilder.tsx` interface in the frontend. When published, the backend automatically handles chunking, FAISS embeddings, and FTS updates.
- **API Endpoint**: `POST /regulations/manual-document`

### Creating Notes
Users can also create personal/team notes (e.g., minutes of meetings, daily journals, project playbooks).
- **Frontend**: Accessible via the "Notes" tab in the application.
- **Workflow**: Notes are grouped by structural sections, saved in the database, and immediately queued for embedding generation.
- **Integration**: Notes are searchable alongside official regulations. In future updates, notes can serve as the primary source of truth in a dedicated "Deep Research" mode.

---

## 5. SKYbrary Publications

SKYbrary data (such as accident investigations and safety reports) typically uses the same pipeline as custom manuals or specialized parsers. Follow the general embedding and FTS rebuild process whenever new SKYbrary archives are added.

---

## 6. Verifying Data Population

You can verify that data is successfully populated using the provided CLI diagnostic scripts:

```bash
# Test Semantic Vector Search
python ingestion/retrieval/search_chunks.py "pilot rest periods and flight duty limitations" -k 5

# Test Keyword/FTS Search
python ingestion/retrieval/keyword_search.py "ATSEP" --top_k 5
```

---

## 7. LoRa Fine-Tuning Dataset Generation

If you wish to fine-tune your own local Large Language Model (e.g., using LoRa) to "speak" accurately in the context of aviation regulations, you can generate a synthetic instruction-tuning dataset based directly on the ingested chunks.

AeroLex includes a script that uses your local LM Studio instance to dynamically read regulatory chunks and generate human-like Q&A pairs.

### Prerequisites
1. Ensure your `chunks.db` database is populated with regulations (see steps 2 and 3 above).
2. Ensure **LM Studio** is running on your machine (default port 1234).
3. Load an instruction-tuned model in LM Studio (e.g., `qwen2.5-7b-instruct` or `qwen3-coder-30b-a3b-instruct`) with an appropriate context window.

### Generating the Dataset
Run the synthetic QA generator script:
```bash
cd LoRa
python generate_qa_synthetic.py --limit 1000
```

### Script Arguments:
- `--limit`: The number of chunks to randomly sample and process (default: 1000).
- `--min-chars` / `--max-chars`: Filters chunks by character length to ensure they are substantive (default: 200 to 1500 chars).
- `--out`: The output path for the JSONL file (default: `synthetic_train.jsonl`).

The script will query the local LLM and append the resulting Q&A pairs (in a standard ChatML/OpenAI schema with `system`, `user`, and `assistant` roles) to the output file, creating a massive, high-quality instruction dataset tailored specifically to aviation compliance.
