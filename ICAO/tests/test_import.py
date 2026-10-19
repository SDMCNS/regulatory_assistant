"""Unit tests for import directory tracking, change detection, and reparsing."""

import shutil
import time
from pathlib import Path
import fitz
import pytest

from icao_rag.config import PipelineConfig
from icao_rag.pipeline import ICAOPipeline


@pytest.fixture
def temp_import_env(tmp_path):
    """Create a temporary test environment with data and import directories."""
    data_dir = tmp_path / "data"
    import_dir = tmp_path / "import_pdfs"
    storage_dir = tmp_path / "storage"

    data_dir.mkdir()
    import_dir.mkdir()
    storage_dir.mkdir()

    # Create a tiny 1-page valid PDF in data_dir
    pdf1 = data_dir / "test_doc1.pdf"
    doc1 = fitz.open()
    page1 = doc1.new_page()
    page1.insert_text((50, 72), "Chapter 1. Initial airport economic regulations and landing fees.")
    doc1.save(str(pdf1))
    doc1.close()

    config = PipelineConfig(
        data_dir=data_dir,
        import_dir=import_dir,
        storage_dir=storage_dir
    )
    # Use lightweight embedder for fast tests
    config.embedder.backend = "tfidf"
    config.filter.exclude_cover_pages = False

    pipe = ICAOPipeline(config)
    pipe.index_document(pdf1)

    return pipe, data_dir, import_dir, pdf1


def test_import_status_up_to_date(temp_import_env):
    pipe, data_dir, import_dir, pdf1 = temp_import_env
    status = pipe.check_import_status()

    assert not status.has_pending_changes
    assert status.total_pending == 0
    assert len(status.new_files) == 0
    assert len(status.updated_files) == 0
    assert len(status.up_to_date_files) == 1
    assert status.up_to_date_files[0].filename == "test_doc1.pdf"


def test_detect_new_file_in_import_dir(temp_import_env):
    pipe, data_dir, import_dir, pdf1 = temp_import_env

    # Create a new PDF directly in import_dir
    new_pdf = import_dir / "test_doc2.pdf"
    doc2 = fitz.open()
    page = doc2.new_page()
    page.insert_text((50, 72), "Global Air Navigation satellite systems and CNS/ATM architecture.")
    doc2.save(str(new_pdf))
    doc2.close()

    status = pipe.check_import_status()
    assert status.has_pending_changes
    assert status.total_pending == 1
    assert len(status.new_files) == 1
    assert status.new_files[0].filename == "test_doc2.pdf"
    assert status.new_files[0].status == "new"

    # Sync and verify status updates to up_to_date
    sync_res = pipe.sync_imports()
    assert sync_res.synced_count == 1

    status_after = pipe.check_import_status()
    assert not status_after.has_pending_changes
    assert len(status_after.up_to_date_files) == 2


def test_detect_updated_version(temp_import_env):
    pipe, data_dir, import_dir, pdf1 = temp_import_env

    time.sleep(1.1)  # Ensure mtime diff > 1.0 second

    # Copy updated version of test_doc1 into import_dir with more content
    doc_updated = fitz.open()
    p = doc_updated.new_page()
    p.insert_text((50, 72), "Chapter 1. Revision 2 with updated passenger charges and concession rates.")
    doc_updated.save(str(import_dir / "test_doc1.pdf"))
    doc_updated.close()

    status = pipe.check_import_status()
    assert status.has_pending_changes
    assert len(status.updated_files) == 1
    assert status.updated_files[0].filename == "test_doc1.pdf"
    assert status.updated_files[0].status == "updated"

    # Sync the update
    sync_res = pipe.sync_imports()
    assert sync_res.synced_count == 1

    status_after = pipe.check_import_status()
    assert not status_after.has_pending_changes
    assert len(status_after.updated_files) == 0
