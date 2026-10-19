"""FastAPI REST API for ICAO Document Search and Retrieval."""

import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import PipelineConfig
from .models import (
    Chunk,
    DocumentMetadata,
    ImportStatusResponse,
    IndexingStats,
    SearchFilter,
    SearchRequest,
    SearchResponse,
    SyncImportResponse,
)
from .pipeline import ICAOPipeline

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up pipeline on server startup."""
    try:
        get_pipeline()
    except Exception as e:
        print(f"Startup pipeline initialization notice: {e}")
    yield


# Initialize FastAPI application
app = FastAPI(
    title="ICAO Document Intelligence & Search API",
    description="REST API to parse, filter, chunk, embed, and search ICAO technical documents with hybrid retrieval (Dense + BM25).",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pipeline singleton
pipeline: Optional[ICAOPipeline] = None


def get_pipeline() -> ICAOPipeline:
    """Lazy initialize master pipeline."""
    global pipeline
    if pipeline is None:
        config = PipelineConfig()
        pipeline = ICAOPipeline(config)
        # Auto-index PDFs if not yet indexed
        if pipeline.vector_store.total_chunks == 0:
            pipeline.index_directory()
    return pipeline


# Mount static directory for frontend assets
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    pipe = get_pipeline()
    return {
        "status": "healthy",
        "service": "ICAO Document Intelligence API",
        "version": "1.0.0",
        "indexed_chunks": pipe.vector_store.total_chunks,
        "indexed_documents": len(pipe.vector_store.documents),
        "embedder": pipe.config.embedder.backend
    }


@app.get("/api/stats", response_model=IndexingStats)
def get_stats():
    """Get indexing and corpus statistics."""
    pipe = get_pipeline()
    return pipe.get_stats()


@app.get("/api/documents")
def list_documents():
    """List all indexed documents with page count and metadata."""
    pipe = get_pipeline()
    return {"documents": pipe.vector_store.documents}


@app.get("/api/import/status", response_model=ImportStatusResponse)
def get_import_status():
    """Check for new or modified PDF documents available for parsing in import_pdfs/."""
    pipe = get_pipeline()
    return pipe.check_import_status()


@app.post("/api/import/sync", response_model=SyncImportResponse)
def sync_imported_documents(force: bool = Query(False, description="Force re-indexing of all documents")):
    """Reparse and index any new or updated PDF documents."""
    pipe = get_pipeline()
    return pipe.sync_imports(force=force)


@app.post("/api/import/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a new or updated ICAO PDF document directly into import_pdfs/."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pipe = get_pipeline()
    import_dir = Path(pipe.config.import_dir)
    import_dir.mkdir(parents=True, exist_ok=True)

    dest_path = import_dir / file.filename
    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    status = pipe.check_import_status()
    return {
        "filename": file.filename,
        "saved_to": str(dest_path),
        "status": status
    }


@app.post("/api/index", response_model=IndexingStats)
def trigger_indexing(force: bool = Query(False, description="Force re-indexing from scratch")):
    """Trigger document parsing, filtering, chunking, and embedding."""
    pipe = get_pipeline()
    stats = pipe.index_directory(force_reindex=force)
    return stats


@app.post("/api/search", response_model=SearchResponse)
def search_documents(request: SearchRequest):
    """Perform hybrid search (Dense semantic + BM25 keyword) across ICAO documents."""
    pipe = get_pipeline()
    if pipe.vector_store.total_chunks == 0:
        raise HTTPException(
            status_code=400,
            detail="No documents have been indexed yet. Please run /api/index first."
        )

    response = pipe.search_engine.search(request)
    return response


@app.get("/api/chunk/{chunk_id}")
def get_chunk(chunk_id: str):
    """Retrieve full chunk content, context prefix, and metadata."""
    pipe = get_pipeline()
    chunk = pipe.get_chunk(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail=f"Chunk '{chunk_id}' not found.")
    return chunk


@app.get("/", response_class=HTMLResponse)
def index_page():
    """Serve the interactive web UI."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return HTMLResponse("<h2>ICAO Search API is running. Explore interactive docs at <a href='/docs'>/docs</a>.</h2>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("icao_rag.api:app", host="127.0.0.1", port=8000, reload=True)
