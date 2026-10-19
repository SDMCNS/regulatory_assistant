"""
diagram_extractor.py - Visual Graphic & Diagram Detection and Gemini HyDE Summarizer.

Detects diagrams, schematics, flowcharts, vector drawings, and images within PDF documents,
renders high-resolution visual clips, and uses Google Gemini to generate dense HyDE
(Hypothetical Document Embeddings) technical summaries.

All generated summaries are tagged with 'Summary of Graphical Elements' for chunking,
indexing, semantic vector search, and deep regulatory research.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

import requests
from ingestion.core.config import settings


# Regex to detect figure captions and labels near graphics
RE_CAPTION = re.compile(
    r"\b(figure|fig\.?|diagram|chart|illustration|schematic|flowchart|table|exhibit|plate)\s*([0-9A-Za-z.\-_:]*)",
    re.IGNORECASE
)

# Candidate Gemini models for vision tasks (ordered by preference and availability)
GEMINI_VISION_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]


def detect_page_graphics(
    page: "fitz.Page",
    page_num: int,
    min_width: float = 80.0,
    min_height: float = 60.0,
    min_area: float = 8000.0,
    dpi: int = 150
) -> List[Dict[str, Any]]:
    """
    Scans a PDF page for significant raster images and vector diagrams.
    Returns a list of detected graphic dictionaries with image bytes, dimensions,
    bounding rectangles, and nearby contextual caption text.
    """
    if fitz is None:
        return []

    page_rect = page.rect
    detected: List[Dict[str, Any]] = []
    seen_rects: List["fitz.Rect"] = []

    # Get page text blocks for nearby caption correlation
    text_blocks = page.get_text("blocks")  # (x0, y0, x1, y1, "text", block_no, block_type)

    def find_nearby_caption(target_rect: "fitz.Rect") -> str:
        """Finds captions or text lines immediately above or below the graphic."""
        captions: List[str] = []
        for b in text_blocks:
            b_rect = fitz.Rect(b[0], b[1], b[2], b[3])
            b_text = (b[4] or "").strip()
            if not b_text:
                continue

            # Vertical proximity: within 60 points above or below
            is_above = (0 <= target_rect.y0 - b_rect.y1 <= 60)
            is_below = (0 <= b_rect.y0 - target_rect.y1 <= 60)
            overlaps_x = not (b_rect.x1 < target_rect.x0 - 40 or b_rect.x0 > target_rect.x1 + 40)

            if (is_above or is_below) and overlaps_x:
                # Prioritize lines matching figure or diagram pattern
                for line in b_text.splitlines():
                    clean_line = line.strip()
                    if RE_CAPTION.search(clean_line):
                        captions.append(clean_line)
                    elif len(captions) == 0 and len(clean_line) < 160:
                        captions.append(clean_line)

        return " | ".join(captions[:2]) if captions else ""

    # 1. Raster Images Detection
    images = page.get_images()
    for img in images:
        xref = img[0]
        rects = page.get_image_rects(xref)
        if not rects:
            continue

        rect = rects[0]
        area = rect.width * rect.height

        # Filter out tiny bullets, icons, logos, or thin horizontal dividers
        if rect.width < min_width or rect.height < min_height or area < min_area:
            continue

        # Avoid exact duplicate overlapping boxes
        is_dup = any(abs(r.x0 - rect.x0) < 5 and abs(r.y0 - rect.y0) < 5 for r in seen_rects)
        if is_dup:
            continue

        seen_rects.append(rect)

        # Expand clipping box slightly to encompass border lines or adjacent labels
        clip_rect = fitz.Rect(
            max(0, rect.x0 - 4),
            max(0, rect.y0 - 4),
            min(page_rect.width, rect.x1 + 4),
            min(page_rect.height, rect.y1 + 4)
        )

        try:
            pix = page.get_pixmap(clip=clip_rect, dpi=dpi)
            img_bytes = pix.tobytes("png")
            nearby_cap = find_nearby_caption(rect)

            detected.append({
                "page": page_num,
                "figure_id": f"p{page_num}_img_{xref}",
                "graphic_type": "raster_image",
                "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                "width": pix.width,
                "height": pix.height,
                "image_bytes": img_bytes,
                "nearby_caption": nearby_cap
            })
        except Exception:
            continue

    # 2. Vector Diagrams & Drawing Clusters
    drawings = page.get_drawings()
    if len(drawings) >= 10:
        # Filter out whole-page borders/margins (> 85% width AND > 85% height)
        diagram_drawings = []
        for d in drawings:
            dr = d["rect"]
            if dr.width >= page_rect.width * 0.88 and dr.height >= page_rect.height * 0.88:
                continue
            diagram_drawings.append(d)

        if len(diagram_drawings) >= 8:
            xs = [d["rect"].x0 for d in diagram_drawings] + [d["rect"].x1 for d in diagram_drawings]
            ys = [d["rect"].y0 for d in diagram_drawings] + [d["rect"].y1 for d in diagram_drawings]
            v_rect = fitz.Rect(min(xs), min(ys), max(xs), max(ys))

            # Ensure the vector region is a substantial diagram block
            if v_rect.width >= 120 and v_rect.height >= 80:
                # Check if this vector region overlaps an already captured raster image
                overlaps_raster = any(
                    abs(v_rect.x0 - r.x0) < 30 and abs(v_rect.y0 - r.y0) < 30 for r in seen_rects
                )
                if not overlaps_raster:
                    seen_rects.append(v_rect)
                    clip_rect = fitz.Rect(
                        max(0, v_rect.x0 - 6),
                        max(0, v_rect.y0 - 6),
                        min(page_rect.width, v_rect.x1 + 6),
                        min(page_rect.height, v_rect.y1 + 6)
                    )
                    try:
                        pix = page.get_pixmap(clip=clip_rect, dpi=dpi)
                        img_bytes = pix.tobytes("png")
                        nearby_cap = find_nearby_caption(v_rect)

                        detected.append({
                            "page": page_num,
                            "figure_id": f"p{page_num}_vector_diag",
                            "graphic_type": "vector_diagram",
                            "rect": (v_rect.x0, v_rect.y0, v_rect.x1, v_rect.y1),
                            "width": pix.width,
                            "height": pix.height,
                            "image_bytes": img_bytes,
                            "nearby_caption": nearby_cap
                        })
                    except Exception:
                        pass

    return detected


def generate_diagram_hyde_summary(
    graphic_info: Dict[str, Any],
    doc_title: str,
    api_key: Optional[str] = None,
    preferred_model: Optional[str] = None
) -> str:
    """
    Generates a HyDE-style technical summary of the visual diagram using Google Gemini Vision.
    Converts diagram structures, labels, arrows, and limits into dense technical text for chunking.
    Guarantees robust fallback to heuristic tagging if Gemini is offline or unconfigured.
    """
    page_num = graphic_info.get("page", 1)
    fig_id = graphic_info.get("figure_id", "figure")
    caption = graphic_info.get("nearby_caption", "")
    width = graphic_info.get("width", 0)
    height = graphic_info.get("height", 0)
    img_bytes = graphic_info.get("image_bytes")

    active_key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()

    # Heuristic fallback template when offline or without Gemini API key
    fallback_summary = (
        f"[Summary of Graphical Elements: Figure on Page {page_num}]\n"
        f"- **Element Type**: Visual Diagram / Technical Illustration ({width}x{height} px)\n"
        f"- **Caption / Nearby Context**: {caption or 'Aviation operational/technical graphic'}\n"
        f"- **HyDE Synthetic Scope**: Contains visual operational representations, schematics, or workflow steps "
        f"supporting {doc_title}. Tagged as summary of graphical elements for regulatory reference."
    )

    if not active_key or not img_bytes:
        return fallback_summary

    prompt = (
        f"You are an expert aviation regulatory and technical documentation analyst.\n"
        f"Analyze the attached diagram, flowchart, schematic, chart, or technical graphic extracted from an aviation document.\n\n"
        f"Document Context:\n"
        f"- Document Title: {doc_title}\n"
        f"- Page: {page_num}\n"
        f"- Nearby Caption/Context: {caption or 'None provided'}\n\n"
        f"Task:\n"
        f"Perform a HyDE (Hypothetical Document Embeddings) visual information extraction. "
        f"Convert ALL visual information, labels, process flows, and structural relationships into rich, "
        f"dense technical text suitable for semantic vector retrieval and regulatory search.\n\n"
        f"Strict Requirements:\n"
        f"1. Your response MUST begin with the exact header:\n"
        f"   [Summary of Graphical Elements: Figure on Page {page_num}]\n"
        f"2. Clearly identify the **Diagram Type** (e.g. Architecture Diagram, Operational Flowchart, Electrical/Mechanical Schematic, Performance Envelope, Decision Tree, Layout).\n"
        f"3. Transcribe and describe all **Visual Components & Workflow** (sequence of nodes, arrows, decision branches, inputs, outputs, subsystems).\n"
        f"4. List and expand all visible **Labels, Acronyms, Limits & Numerical Values**.\n"
        f"5. Provide a dense **HyDE Technical Scope**: write a comprehensive technical explanation answering hypothetical engineering, compliance, or operational questions that this diagram addresses.\n\n"
        f"Keep the output dense, precise, and authoritative. Do NOT include conversational filler."
    )

    # 1. Try google.genai SDK
    try:
        from google import genai
        from google.genai import types

        candidate_models = [preferred_model] if preferred_model else []
        for m in GEMINI_VISION_MODELS:
            if m not in candidate_models:
                candidate_models.append(m)

        client = genai.Client(api_key=active_key)
        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        prompt
                    ]
                )
                text = (response.text or "").strip()
                if text:
                    if not text.startswith("[Summary of Graphical Elements:"):
                        text = f"[Summary of Graphical Elements: Figure on Page {page_num}]\n\n{text}"
                    return text
            except Exception:
                continue

    except Exception:
        pass

    # 2. Direct REST API Fallback
    try:
        b64_image = base64.b64encode(img_bytes).decode("utf-8")
        candidate_models = [preferred_model] if preferred_model else []
        for m in GEMINI_VISION_MODELS:
            if m not in candidate_models:
                candidate_models.append(m)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": b64_image
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048
            }
        }

        headers = {"Content-Type": "application/json"}
        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={active_key}"
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=45)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text_parts = [p.get("text", "") for p in parts if p.get("text")]
                        text = "".join(text_parts).strip()
                        if text:
                            if not text.startswith("[Summary of Graphical Elements:"):
                                text = f"[Summary of Graphical Elements: Figure on Page {page_num}]\n\n{text}"
                            return text
            except Exception:
                continue

    except Exception:
        pass

    return fallback_summary
