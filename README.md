# Regulation Assistant

This repository provides a unified pipeline for ingesting, parsing, chunking, and querying regulatory documents (such as EU Formex and EASA Easy Access Rules) using a local LLM setup via LM Studio. 

It contains two main components:
1. **Ingestion Pipeline** (`ingestion/`): Handles downloading, parsing, chunking, and embedding generation for regulatory documents (saved locally via FAISS index and SQLite metadata).
2. **FastAPI Server** (`api/`): Provides REST endpoints to search the document index and interact with the text using a local LLM.

## Setup

1. **Install dependencies**: Make sure you have installed all required packages (such as `fastapi`, `uvicorn`, `requests`, `pydantic-settings`, etc.).
2. **Local LLM setup**: The API relies on a locally hosted LLM and Embedding Model via [LM Studio](https://lmstudio.ai/). By default, the app expects LM Studio's local server running at `http://localhost:1234/v1`. 
3. **Data preparation**: The EU Formex XML files need to be manually downloaded from the EU at [https://datadump.publications.europa.eu/dashboard](https://datadump.publications.europa.eu/dashboard) and extracted into the relevant `data\regulations_xml` folder. 

## Usage

### Configuration

You can override default settings (like data paths, LLM, or embedding models) by creating a `user.settings.conf` file at the root of the project. The `start.py` script automatically loads this file.

**Example `user.settings.conf`:**
```ini
# Folder locations
DATA_DIR=./my_custom_data_dir

# LLM / Embeddings settings
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL_NAME=my-custom-model
EMBEDDING_MODEL_NAME=my-embedding-model
EMBEDDING_DIMENSIONS=1024
```

A unified startup script `start.py` is provided at the root of the project to run both components.

### 1. Ingestion Pipeline

To run the data ingestion and generate the embeddings index:

```bash
python start.py ingest [OPTIONS]
```

**Common Options:**
- `--download_easa`: Download fresh EASA XML files from the EASA RSS feed.
- `--reset`: Reset the environment before running (clears old data).
- `--limit N`: Limit the number of documents to process for testing purposes.

Example:
```bash
python start.py ingest --download_easa --limit 10
```

### 2. Search & Retrieval CLI Tools

You can test searches directly from the command line:

```bash
# 1. Semantic Vector Search (FAISS)
python ingestion/retrieval/search_chunks.py "pilot duty limitations" -k 5

# 2. SQLite FTS5 Keyword & Acronym Search (BM25 + Porter Stemming)
python ingestion/retrieval/keyword_search.py "ATSEP" --top_k 5
python ingestion/retrieval/keyword_search.py "pilot rest" --top_k 3 --no_llm
```

### 3. FastAPI Server

To run the API server:

```bash
python start.py api
```

This starts a uvicorn server on `http://0.0.0.0:8000` with hot-reload enabled. Interactive API documentation is available at `http://localhost:8000/docs`.

**Available Endpoints:**

#### `SEARCH` Operations
- `GET /search`: Search document chunks using semantic dense vectors (FAISS).
- `GET /search/keyword`: High-speed keyword & acronym search powered by SQLite FTS5 (BM25) with Porter stemming. Ideal for short queries, acronyms (`ATSEP`, `AMC-20`, `FTL`), and clause codes (`CAT.OP.MPA`). Includes `use_llm` flag (default: `true`) to toggle local LLM query expansion.
- `GET /search/docs`: Search and retrieve the full markdown representation of the matching documents.

#### `LLM` Operations
- `POST /llm/ask`: Ask a regulatory question. It automatically retrieves relevant document contexts from the index and queries the local LLM.
- `POST /llm/extract`: Extract structured information from text adhering to a provided JSON schema.

## Project Structure

```
.
├── api/             # FastAPI backend source code
├── frontend/        # React + Vite web user interface
├── ingestion/       # Ingestion pipeline scripts, parsers, chunkers, and embedding generation
├── start.py         # Root command line tool for running the API and Ingestion
├── api_schema.json  # Exported OpenAPI 3.1 schema
├── api_description.md # API server description and workflows
└── README.md        # This file
```

