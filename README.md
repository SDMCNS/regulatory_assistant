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

### 2. FastAPI Server

To run the API server:

```bash
python start.py api
```

This starts a uvicorn server on `http://0.0.0.0:8000` with hot-reload enabled.

**Available Endpoints:**
- `GET /search`: Search the document chunks.
- `GET /search/docs`: Search and retrieve the full markdown representation of the documents.
- `POST /llm/ask`: Ask a question. It automatically retrieves relevant contexts from the index and queries the local LLM.
- `POST /llm/extract`: Extract structured information from text adhering to a provided JSON schema.

## Project Structure

```
.
├── api/             # FastAPI backend source code
├── ingestion/       # Ingestion pipeline scripts, parsers, chunkers, and embedding generation
├── start.py         # Root command line tool for running the API and Ingestion
└── README.md        # This file
```
