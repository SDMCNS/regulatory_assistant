"""Integration tests for FastAPI REST API endpoints."""

from fastapi.testclient import TestClient
from icao_rag.api import app, get_pipeline


def test_api_health():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_api_stats():
    client = TestClient(app)
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_chunks" in data
    assert "total_documents" in data


def test_api_search():
    client = TestClient(app)
    payload = {
        "query": "airport charges",
        "top_k": 3,
        "dense_weight": 0.7,
        "bm25_weight": 0.3
    }
    response = client.post("/api/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "airport charges"
    assert "results" in data
    assert len(data["results"]) <= 3


def test_api_root_html():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "ICAO" in response.text
