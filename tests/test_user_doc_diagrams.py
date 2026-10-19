import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import fitz
import pytest
from ingestion.user_docs.diagram_extractor import detect_page_graphics, generate_diagram_hyde_summary
from ingestion.user_docs.extractor import extract_user_document
from ingestion.skybrary_bookshelf.lib.chunker import SkybraryChunker


def create_test_pdf_with_diagram(file_path: Path) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Insert text heading
    page.insert_text(fitz.Point(50, 50), "FLIGHT SAFETY BULLETIN: LATERAL SEPARATION CRITERIA", fontsize=14)
    page.insert_text(fitz.Point(50, 80), "This advisory circular outlines emergency procedures for wake turbulence avoidance.", fontsize=10)

    # Draw boxes
    drawings = [
        (50, 120, 250, 160),
        (300, 120, 500, 160),
        (175, 200, 375, 240),
        (50, 280, 250, 320),
        (300, 280, 500, 320)
    ]
    for x0, y0, x1, y1 in drawings:
        rect = fitz.Rect(x0, y0, x1, y1)
        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(color=(0.1, 0.3, 0.7), fill=(0.9, 0.95, 1.0), width=1.5)
        shape.commit()

    # Draw connecting lines and arrows
    for p1, p2 in [((250, 140), (300, 140)), ((150, 160), (275, 200)), ((375, 200), (400, 280)), ((275, 240), (150, 280)), ((250, 300), (300, 300))]:
        shape = page.new_shape()
        shape.draw_line(fitz.Point(*p1), fitz.Point(*p2))
        shape.finish(color=(0.2, 0.2, 0.2), width=2.0)
        shape.commit()

    # Insert labels inside diagram
    page.insert_text(fitz.Point(60, 145), "Detection of Wake Vortex", fontsize=9)
    page.insert_text(fitz.Point(310, 145), "Evaluate Lateral Distance (>5 NM)", fontsize=9)
    page.insert_text(fitz.Point(185, 225), "Decision: Climb or Turn 30 deg", fontsize=9)
    page.insert_text(fitz.Point(60, 305), "Execute Vector Heading 270", fontsize=9)
    page.insert_text(fitz.Point(310, 305), "Maintain Separation Minimums", fontsize=9)

    # Caption
    page.insert_text(fitz.Point(50, 345), "Figure 1: Aircraft Separation Decision Matrix & Flowchart", fontsize=10)
    page.insert_text(fitz.Point(50, 370), "Operational flight crews must adhere to the lateral spacing minimums depicted above.", fontsize=9)

    doc.save(str(file_path))
    doc.close()
    return file_path


def test_detect_page_graphics(tmp_path):
    pdf_path = create_test_pdf_with_diagram(tmp_path / "test.pdf")
    doc = fitz.open(str(pdf_path))
    page = doc[0]

    graphics = detect_page_graphics(page, page_num=1)
    assert len(graphics) >= 1
    g = graphics[0]
    assert g["page"] == 1
    assert g["graphic_type"] in ("vector_diagram", "raster_image")
    assert g["image_bytes"] is not None
    assert len(g["image_bytes"]) > 0
    assert "Figure 1: Aircraft Separation" in g.get("nearby_caption", "") or len(g.get("nearby_caption", "")) > 0
    doc.close()


def test_generate_diagram_hyde_summary_fallback(tmp_path):
    pdf_path = create_test_pdf_with_diagram(tmp_path / "test.pdf")
    doc = fitz.open(str(pdf_path))
    graphics = detect_page_graphics(doc[0], page_num=1)
    doc.close()

    # When no API key is provided, verify graceful heuristic fallback with correct prefix
    summary = generate_diagram_hyde_summary(graphics[0], doc_title="Separation Criteria", api_key=None)
    assert summary.startswith("[Summary of Graphical Elements: Figure on Page 1]")
    assert "Separation Criteria" in summary


def test_extract_user_document_with_diagrams(tmp_path):
    pdf_path = create_test_pdf_with_diagram(tmp_path / "test.pdf")
    doc_dict = extract_user_document(
        pdf_path,
        "test.pdf",
        extract_diagrams=True,
        gemini_api_key=None
    )

    assert doc_dict["diagrams_detected"] >= 1
    text = doc_dict["raw_text"]
    assert "Summary of Graphical Elements" in text
    assert "LATERAL SEPARATION CRITERIA" in text


def test_chunker_graphic_summary_tagging():
    chunker = SkybraryChunker(target_words=100, max_words=200)
    pub_info = {
        "id": "HYDRAULIC_SOP",
        "title": "Hydraulic System SOP",
        "category": "User Supplied",
        "author": "User Upload",
        "publication_date": "2026-03-01",
        "sha256": "dummy_sha",
        "filename": "hydraulic_sop.pdf",
        "origin": "user"
    }
    raw_text = (
        "--- PAGE 1 ---\n"
        "Section 1: General Requirements.\n"
        "The system pressure shall remain within nominal parameters across all operations.\n\n"
        "[Summary of Graphical Elements: Figure on Page 1] Flowchart showing Hydraulic Flow, Reservoir A connected to Auxiliary Pump and Bypass Valve.\n\n"
        "Section 2: Maintenance Inspections.\n"
        "Perform routine visual inspections every 100 flight hours."
    )

    doc_meta, chunks = chunker.chunk_document(pub_info=pub_info, raw_text=raw_text, doc_id_prefix="USER")
    graphic_chunks = [c for c in chunks if c.chunk_type == "graphic_summary" or c.metadata.get("is_graphic_summary")]

    assert len(graphic_chunks) == 1
    gc = graphic_chunks[0]
    assert gc.chunk_type == "graphic_summary"
    assert gc.metadata.get("is_graphic_summary") is True
    assert gc.metadata.get("graphic_tag") == "Summary of Graphical Elements"
    assert "Summary of Graphical Elements" in gc.section_path[-1]
    assert gc.metadata.get("origin") == "user"
