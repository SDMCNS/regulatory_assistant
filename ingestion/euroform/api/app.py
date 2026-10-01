"""FastAPI application for Formex 4 XML to JSON/text conversion."""
from __future__ import annotations

import io
import time
import xml.etree.ElementTree as ET
from typing import Any, Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from ..models import BatchConversionResponse, BatchItemResult, ErrorResponse, XmlPayloadRequest
from ..parser import parse_formex
from ..render import render_text
from ..schema import build_schema

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EuroForm &mdash; Formex 4 XML to JSON Converter</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(18, 24, 38, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #6366f1;
      --primary-glow: rgba(99, 102, 241, 0.25);
      --primary-hover: #4f46e5;
      --accent: #06b6d4;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --error: #ef4444;
      --code-bg: #05070d;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.08) 0px, transparent 50%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    header {
      border-bottom: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      background: rgba(9, 13, 22, 0.8);
      padding: 1.25rem 2rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 50;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      text-decoration: none;
      color: var(--text);
    }

    .brand-icon {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, var(--primary), var(--accent));
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 1.1rem;
      box-shadow: 0 0 16px var(--primary-glow);
    }

    .brand-title {
      font-weight: 700;
      font-size: 1.25rem;
      letter-spacing: -0.025em;
    }

    .brand-badge {
      font-size: 0.75rem;
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid rgba(99, 102, 241, 0.3);
      color: #a5b4fc;
      padding: 0.2rem 0.5rem;
      border-radius: 9999px;
      margin-left: 0.5rem;
    }

    .nav-links {
      display: flex;
      gap: 1.25rem;
    }

    .nav-links a {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.875rem;
      font-weight: 500;
      transition: color 0.2s;
    }

    .nav-links a:hover {
      color: var(--text);
    }

    main {
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
      padding: 2.5rem 2rem;
      display: grid;
      grid-template-columns: 460px 1fr;
      gap: 2rem;
    }

    @media (max-width: 992px) {
      main { grid-template-columns: 1fr; }
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      backdrop-filter: blur(16px);
      padding: 1.75rem;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
      display: flex;
      flex-direction: column;
    }

    .card-title {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .tabs {
      display: flex;
      background: rgba(0, 0, 0, 0.25);
      border-radius: 8px;
      padding: 4px;
      margin-bottom: 1.25rem;
      border: 1px solid var(--card-border);
    }

    .tab-btn {
      flex: 1;
      padding: 0.5rem 0.75rem;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 0.85rem;
      font-weight: 500;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .tab-btn.active {
      background: var(--primary);
      color: white;
      box-shadow: 0 2px 8px var(--primary-glow);
    }

    .dropzone {
      border: 2px dashed rgba(99, 102, 241, 0.35);
      border-radius: 12px;
      padding: 2.25rem 1.5rem;
      text-align: center;
      cursor: pointer;
      transition: all 0.25s ease;
      background: rgba(99, 102, 241, 0.03);
      position: relative;
    }

    .dropzone:hover, .dropzone.dragover {
      border-color: var(--primary);
      background: rgba(99, 102, 241, 0.08);
      transform: translateY(-1px);
    }

    .dropzone input {
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      opacity: 0; cursor: pointer;
    }

    .dropzone-icon {
      font-size: 2.2rem;
      margin-bottom: 0.75rem;
    }

    .dropzone-text {
      font-weight: 500;
      font-size: 0.95rem;
      margin-bottom: 0.25rem;
    }

    .dropzone-subtext {
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    .file-pill {
      display: none;
      margin-top: 1rem;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 0.6rem 0.8rem;
      font-size: 0.85rem;
      align-items: center;
      justify-content: space-between;
    }

    .xml-textarea {
      width: 100%;
      height: 180px;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      padding: 0.75rem;
      resize: vertical;
      display: none;
    }

    .xml-textarea:focus {
      outline: none;
      border-color: var(--primary);
    }

    .options-group {
      margin: 1.5rem 0;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .option-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 0.875rem;
    }

    .option-label {
      color: var(--text);
      display: flex;
      flex-direction: column;
    }

    .option-desc {
      font-size: 0.75rem;
      color: var(--text-muted);
    }

    .switch {
      position: relative;
      width: 40px;
      height: 22px;
    }

    .switch input { opacity: 0; width: 0; height: 0; }

    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: rgba(255, 255, 255, 0.15);
      transition: .3s;
      border-radius: 22px;
    }

    .slider:before {
      position: absolute;
      content: "";
      height: 16px;
      width: 16px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: .3s;
      border-radius: 50%;
    }

    input:checked + .slider {
      background-color: var(--primary);
    }

    input:checked + .slider:before {
      transform: translateX(18px);
    }

    .btn-convert {
      width: 100%;
      padding: 0.85rem;
      background: linear-gradient(135deg, var(--primary), #4f46e5);
      border: none;
      border-radius: 10px;
      color: white;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 4px 16px var(--primary-glow);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
    }

    .btn-convert:hover {
      opacity: 0.95;
      transform: translateY(-1px);
    }

    .btn-convert:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }

    .output-card {
      min-height: 540px;
      position: relative;
    }

    .output-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1rem;
    }

    .output-stats {
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    .output-actions {
      display: flex;
      gap: 0.5rem;
    }

    .btn-action {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 0.4rem 0.75rem;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }

    .btn-action:hover {
      background: rgba(255, 255, 255, 0.15);
    }

    .viewer {
      flex: 1;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 1.25rem;
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      overflow: auto;
      max-height: 650px;
      white-space: pre-wrap;
      word-break: break-word;
      color: #e2e8f0;
      line-height: 1.5;
    }

    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      min-height: 380px;
      color: var(--text-muted);
      text-align: center;
    }

    .empty-state-icon {
      font-size: 3rem;
      margin-bottom: 1rem;
      opacity: 0.5;
    }

    .spinner {
      display: none;
      width: 18px;
      height: 18px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-top-color: white;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .toast {
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      background: rgba(16, 185, 129, 0.95);
      color: white;
      padding: 0.75rem 1.25rem;
      border-radius: 8px;
      font-size: 0.875rem;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
      display: none;
      z-index: 100;
    }
  </style>
</head>
<body>
  <header>
    <a href="/" class="brand">
      <div class="brand-icon">EF</div>
      <div class="brand-title">EuroForm</div>
      <span class="brand-badge">FastAPI Formex 4</span>
    </a>
    <nav class="nav-links">
      <a href="/docs" target="_blank">Swagger API</a>
      <a href="/redoc" target="_blank">ReDoc</a>
      <a href="/schema" target="_blank">JSON Schema</a>
      <a href="/health" target="_blank">Health</a>
    </nav>
  </header>

  <main>
    <section class="card">
      <h2 class="card-title">Document Input</h2>
      <div class="tabs">
        <button class="tab-btn active" id="tab-file" onclick="setMode('file')">Upload File</button>
        <button class="tab-btn" id="tab-raw" onclick="setMode('raw')">Paste XML</button>
      </div>

      <div id="file-container">
        <div class="dropzone" id="dropzone">
          <input type="file" id="file-input" accept=".xml,.fmx,.fmx4">
          <div class="dropzone-icon">&#128196;</div>
          <div class="dropzone-text">Drop your Formex XML file here</div>
          <div class="dropzone-subtext">Supports .xml, .fmx.xml files</div>
        </div>
        <div class="file-pill" id="file-pill">
          <span id="file-name" style="font-weight: 500;"></span>
          <span id="file-size" style="color: var(--text-muted); font-size: 0.75rem;"></span>
        </div>
      </div>

      <textarea class="xml-textarea" id="xml-input" placeholder="<ACT>&#10;  <TITLE>...</TITLE>&#10;  ...&#10;</ACT>"></textarea>

      <div class="options-group">
        <div class="option-item">
          <div class="option-label">
            <span>Nest Point Hierarchy</span>
            <span class="option-desc">Nest sub-points (a), (i) and lists under their points</span>
          </div>
          <label class="switch">
            <input type="checkbox" id="opt-nest" checked>
            <span class="slider"></span>
          </label>
        </div>

        <div class="option-item">
          <div class="option-label">
            <span>Extract Metadata</span>
            <span class="option-desc">Include languages, OJ dates, document identifiers</span>
          </div>
          <label class="switch">
            <input type="checkbox" id="opt-metadata" checked>
            <span class="slider"></span>
          </label>
        </div>

        <div class="option-item">
          <div class="option-label">
            <span>Keep Table of Contents</span>
            <span class="option-desc">Preserve TOC elements that duplicate body content</span>
          </div>
          <label class="switch">
            <input type="checkbox" id="opt-toc">
            <span class="slider"></span>
          </label>
        </div>

        <div class="option-item">
          <div class="option-label">
            <span>Plain Text Output</span>
            <span class="option-desc">Render human-readable text instead of JSON</span>
          </div>
          <label class="switch">
            <input type="checkbox" id="opt-text">
            <span class="slider"></span>
          </label>
        </div>
      </div>

      <button class="btn-convert" id="btn-convert" onclick="convertDocument()">
        <span class="spinner" id="spinner"></span>
        <span id="btn-text">Convert Formex XML</span>
      </button>
    </section>

    <section class="card output-card">
      <div class="output-header">
        <div>
          <h2 class="card-title" style="margin-bottom: 0.25rem;">Result</h2>
          <div class="output-stats" id="output-stats">Ready for conversion</div>
        </div>
        <div class="output-actions">
          <button class="btn-action" id="btn-copy" onclick="copyResult()">Copy</button>
          <button class="btn-action" id="btn-download" onclick="downloadResult()">Download</button>
        </div>
      </div>

      <div class="viewer" id="viewer">
        <div class="empty-state">
          <div class="empty-state-icon">&#9881;</div>
          <p>Upload a Formex XML document or paste XML code on the left to see the converted output.</p>
        </div>
      </div>
    </section>
  </main>

  <div class="toast" id="toast">Copied to clipboard!</div>

  <script>
    let mode = 'file';
    let currentResult = '';
    let selectedFile = null;

    const fileInput = document.getElementById('file-input');
    const filePill = document.getElementById('file-pill');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const dropzone = document.getElementById('dropzone');

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) {
        selectedFile = e.target.files[0];
        fileName.textContent = selectedFile.name;
        fileSize.textContent = (selectedFile.size / 1024).toFixed(1) + ' KB';
        filePill.style.display = 'flex';
      }
    });

    ['dragover', 'dragenter'].forEach(e => {
      dropzone.addEventListener(e, (ev) => {
        ev.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(e => {
      dropzone.addEventListener(e, (ev) => {
        ev.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', (ev) => {
      if (ev.dataTransfer.files.length) {
        fileInput.files = ev.dataTransfer.files;
        selectedFile = ev.dataTransfer.files[0];
        fileName.textContent = selectedFile.name;
        fileSize.textContent = (selectedFile.size / 1024).toFixed(1) + ' KB';
        filePill.style.display = 'flex';
      }
    });

    function setMode(m) {
      mode = m;
      document.getElementById('tab-file').classList.toggle('active', m === 'file');
      document.getElementById('tab-raw').classList.toggle('active', m === 'raw');
      document.getElementById('file-container').style.display = m === 'file' ? 'block' : 'none';
      document.getElementById('xml-input').style.display = m === 'raw' ? 'block' : 'none';
    }

    async function convertDocument() {
      const btn = document.getElementById('btn-convert');
      const spinner = document.getElementById('spinner');
      const btnText = document.getElementById('btn-text');
      const stats = document.getElementById('output-stats');
      const viewer = document.getElementById('viewer');

      const isText = document.getElementById('opt-text').checked;
      const nest = document.getElementById('opt-nest').checked;
      const metadata = document.getElementById('opt-metadata').checked;
      const toc = document.getElementById('opt-toc').checked;
      const format = isText ? 'text' : 'json';

      btn.disabled = true;
      spinner.style.display = 'inline-block';
      btnText.textContent = 'Converting...';

      const t0 = performance.now();
      try {
        let response;
        if (mode === 'file') {
          if (!selectedFile) {
            alert('Please select or drop an XML file first.');
            return;
          }
          const formData = new FormData();
          formData.append('file', selectedFile);
          const params = new URLSearchParams({
            nest_points: nest,
            include_metadata: metadata,
            keep_toc: toc,
            output_format: format
          });
          response = await fetch(`/convert?${params.toString()}`, {
            method: 'POST',
            body: formData
          });
        } else {
          const xml = document.getElementById('xml-input').value.trim();
          if (!xml) {
            alert('Please enter or paste XML content.');
            return;
          }
          const params = new URLSearchParams({
            nest_points: nest,
            include_metadata: metadata,
            keep_toc: toc,
            output_format: format
          });
          response = await fetch(`/convert/raw?${params.toString()}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/xml' },
            body: xml
          });
        }

        const t1 = performance.now();
        const duration = (t1 - t0).toFixed(1);

        if (!response.ok) {
          const err = await response.json();
          viewer.innerHTML = `<span style="color: var(--error);">Error (${response.status}): ${err.detail || 'Parsing failed'}</span>`;
          stats.textContent = `Failed in ${duration}ms`;
          currentResult = '';
          return;
        }

        if (isText) {
          const text = await response.text();
          currentResult = text;
          viewer.textContent = text;
        } else {
          const data = await response.json();
          currentResult = JSON.stringify(data, null, 2);
          viewer.textContent = currentResult;
        }
        stats.textContent = `Completed in ${duration}ms (${(currentResult.length / 1024).toFixed(1)} KB)`;
      } catch (e) {
        viewer.innerHTML = `<span style="color: var(--error);">Network or server error: ${e.message}</span>`;
        stats.textContent = 'Conversion failed';
      } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
        btnText.textContent = 'Convert Formex XML';
      }
    }

    function copyResult() {
      if (!currentResult) return;
      navigator.clipboard.writeText(currentResult);
      showToast('Copied to clipboard!');
    }

    function downloadResult() {
      if (!currentResult) return;
      const isText = document.getElementById('opt-text').checked;
      const ext = isText ? '.txt' : '.json';
      const type = isText ? 'text/plain' : 'application/json';
      const blob = new Blob([currentResult], { type });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `formex_converted${ext}`;
      a.click();
    }

    function showToast(msg) {
      const toast = document.getElementById('toast');
      toast.textContent = msg;
      toast.style.display = 'block';
      setTimeout(() => { toast.style.display = 'none'; }, 2200);
    }
  </script>
</body>
</html>
"""


def _execute_parse(
    xml_data: str | bytes | io.IOBase,
    *,
    keep_toc: bool,
    include_metadata: bool,
    nest_points: bool,
    output_format: str,
) -> Response:
    """Internal helper to parse XML and return appropriate JSON or PlainText response."""
    try:
        doc = parse_formex(
            xml_data,
            keep_toc=keep_toc,
            include_metadata=include_metadata,
            nest_points=nest_points,
        )
    except ET.ParseError as pe:
        msg = str(pe)
        line, column = None, None
        if pe.position:
            line, column = pe.position
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                detail=f"Invalid XML syntax: {msg}",
                error_type="XMLParseError",
                line=line,
                column=column,
            ).model_dump(),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                detail=f"Formex parsing error: {exc}",
                error_type="ConversionError",
            ).model_dump(),
        )

    if output_format == "text":
        rendered = render_text(doc)
        return PlainTextResponse(content=rendered, media_type="text/plain; charset=utf-8")

    return JSONResponse(content=doc, media_type="application/json")


def create_app() -> FastAPI:
    """Application factory for EuroForm FastAPI app."""
    app_instance = FastAPI(
        title="EuroForm API",
        description="High-performance Formex 4 XML to structured JSON / readable text converter.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app_instance.get("/", summary="Web UI and API Information", response_class=Response)
    async def index(request: Request) -> Response:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return HTMLResponse(content=HTML_UI)
        return JSONResponse(
            content={
                "name": "EuroForm API",
                "version": "0.1.0",
                "description": "Convert Formex 4 XML files to structured JSON or clean text.",
                "endpoints": {
                    "ui": "/",
                    "convert": "POST /convert",
                    "convert_file": "POST /convert/file",
                    "convert_raw": "POST /convert/raw",
                    "convert_json": "POST /convert/json",
                    "convert_batch": "POST /convert/batch",
                    "schema": "GET /schema",
                    "health": "GET /health",
                    "docs": "/docs",
                    "redoc": "/redoc",
                },
            }
        )

    @app_instance.get("/health", summary="Health Check")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "euroform", "version": "0.1.0"}

    @app_instance.get("/schema", summary="Get Output JSON Schema")
    async def get_schema() -> dict[str, Any]:
        """Return the JSON Schema (Draft 2020-12) describing the parsed Formex output structure."""
        return build_schema()

    @app_instance.post(
        "/convert",
        summary="Convert Formex XML (File, Raw XML or JSON payload)",
        description="Unified endpoint supporting multipart file uploads, raw XML body, or JSON payloads.",
        responses={
            200: {"description": "Successfully parsed Formex document"},
            400: {"model": ErrorResponse, "description": "Invalid XML or processing error"},
        },
    )
    async def convert(
        request: Request,
        keep_toc: bool = Query(False, description="Whether to retain table of contents (TOC)"),
        include_metadata: bool = Query(True, description="Whether to extract metadata block"),
        nest_points: bool = Query(True, description="Whether to nest points and lists"),
        output_format: Literal["json", "text"] = Query("json", description="Output format ('json' or 'text')"),
    ) -> Response:
        content_type = request.headers.get("content-type", "")

        # 1. Handle multipart form file upload
        if "multipart/form-data" in content_type:
            form = await request.form()
            file_obj = form.get("file")
            if not file_obj or not hasattr(file_obj, "read"):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        detail="No file uploaded under form key 'file'",
                        error_type="MissingFileError",
                    ).model_dump(),
                )
            content = await file_obj.read()  # type: ignore[union-attr]
            if not content:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        detail="Uploaded file is empty",
                        error_type="EmptyInputError",
                    ).model_dump(),
                )
            return _execute_parse(
                content,
                keep_toc=keep_toc,
                include_metadata=include_metadata,
                nest_points=nest_points,
                output_format=output_format,
            )

        # 2. Handle JSON payload { "xml": "..." }
        if "application/json" in content_type:
            try:
                body_json = await request.json()
                req_model = XmlPayloadRequest(**body_json)
            except Exception as e:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        detail=f"Invalid JSON request payload: {e}",
                        error_type="InvalidPayloadError",
                    ).model_dump(),
                )
            if not req_model.xml.strip():
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        detail="XML string in payload is empty",
                        error_type="EmptyInputError",
                    ).model_dump(),
                )
            return _execute_parse(
                req_model.xml,
                keep_toc=req_model.keep_toc or keep_toc,
                include_metadata=req_model.include_metadata if not include_metadata else req_model.include_metadata,
                nest_points=req_model.nest_points if not nest_points else req_model.nest_points,
                output_format=req_model.output_format or output_format,
            )

        # 3. Handle raw XML body (application/xml, text/xml, etc.)
        body_bytes = await request.body()
        if not body_bytes.strip():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    detail="Request body is empty. Please provide Formex XML via file or body.",
                    error_type="EmptyInputError",
                ).model_dump(),
            )

        return _execute_parse(
            body_bytes,
            keep_toc=keep_toc,
            include_metadata=include_metadata,
            nest_points=nest_points,
            output_format=output_format,
        )

    @app_instance.post(
        "/convert/file",
        summary="Convert Formex XML File Upload",
        description="Upload a single .xml or .fmx.xml file as multipart/form-data.",
        responses={
            200: {"description": "Parsed Formex document"},
            400: {"model": ErrorResponse, "description": "Invalid XML or file upload error"},
        },
    )
    async def convert_file(
        file: UploadFile = File(..., description="Formex XML file to parse"),
        keep_toc: bool = Form(False, description="Whether to retain table of contents"),
        include_metadata: bool = Form(True, description="Whether to extract metadata block"),
        nest_points: bool = Form(True, description="Whether to nest points and lists"),
        output_format: Literal["json", "text"] = Form("json", description="Output format"),
    ) -> Response:
        content = await file.read()
        if not content:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(detail="Uploaded file is empty", error_type="EmptyInputError").model_dump(),
            )
        return _execute_parse(
            content,
            keep_toc=keep_toc,
            include_metadata=include_metadata,
            nest_points=nest_points,
            output_format=output_format,
        )

    @app_instance.post(
        "/convert/raw",
        summary="Convert Raw Formex XML Body",
        description="Submit raw XML text/bytes directly in the HTTP request body.",
        responses={
            200: {"description": "Parsed Formex document"},
            400: {"model": ErrorResponse, "description": "Invalid XML error"},
        },
    )
    async def convert_raw(
        request: Request,
        keep_toc: bool = Query(False),
        include_metadata: bool = Query(True),
        nest_points: bool = Query(True),
        output_format: Literal["json", "text"] = Query("json"),
    ) -> Response:
        body = await request.body()
        if not body.strip():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(detail="Request body is empty", error_type="EmptyInputError").model_dump(),
            )
        return _execute_parse(
            body,
            keep_toc=keep_toc,
            include_metadata=include_metadata,
            nest_points=nest_points,
            output_format=output_format,
        )

    @app_instance.post(
        "/convert/json",
        summary="Convert Formex XML in JSON Payload",
        description="Send JSON with `xml` field and conversion options.",
    )
    async def convert_json(payload: XmlPayloadRequest) -> Response:
        if not payload.xml.strip():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(detail="XML payload cannot be empty", error_type="EmptyInputError").model_dump(),
            )
        return _execute_parse(
            payload.xml,
            keep_toc=payload.keep_toc,
            include_metadata=payload.include_metadata,
            nest_points=payload.nest_points,
            output_format=payload.output_format,
        )

    @app_instance.post(
        "/convert/batch",
        summary="Batch Convert Multiple Formex XML Files",
        description="Upload multiple Formex XML files in a single request.",
        response_model=BatchConversionResponse,
    )
    async def convert_batch(
        files: list[UploadFile] = File(..., description="Multiple Formex XML files"),
        keep_toc: bool = Form(False),
        include_metadata: bool = Form(True),
        nest_points: bool = Form(True),
        output_format: Literal["json", "text"] = Form("json"),
    ) -> BatchConversionResponse:
        results: list[BatchItemResult] = []
        successful = 0
        failed = 0

        for f in files:
            name = f.filename or "unknown.xml"
            try:
                content = await f.read()
                if not content:
                    results.append(BatchItemResult(filename=name, success=False, error="File is empty"))
                    failed += 1
                    continue

                doc = parse_formex(
                    content,
                    keep_toc=keep_toc,
                    include_metadata=include_metadata,
                    nest_points=nest_points,
                )
                if output_format == "text":
                    results.append(
                        BatchItemResult(
                            filename=name,
                            success=True,
                            text=render_text(doc),
                        )
                    )
                else:
                    results.append(
                        BatchItemResult(
                            filename=name,
                            success=True,
                            document=doc,
                        )
                    )
                successful += 1
            except Exception as exc:
                results.append(BatchItemResult(filename=name, success=False, error=str(exc)))
                failed += 1

        return BatchConversionResponse(
            total=len(files),
            successful=successful,
            failed=failed,
            results=results,
        )

    return app_instance


app = create_app()


def run_cli() -> None:
    """Convenience launcher for the API server CLI."""
    import uvicorn
    uvicorn.run("euroform.api.app:app", host="127.0.0.1", port=8000, reload=True)
