import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_api():
    print("=== 1. Testing Catalog FAA Origin Filter ===")
    res = client.get("/regulations/catalog?origin=faa&limit=10")
    assert res.status_code == 200, f"Catalog failed: {res.text}"
    data = res.json()
    print(f"Total FAA regulations in catalog: {data['total']}, filtered: {data['filtered_count']}")
    assert data["filtered_count"] > 0, "No FAA regulations returned for origin=faa!"
    first_faa = data["regulations"][0]
    print(f"First FAA doc: {first_faa['document_id']} - {first_faa['title']} (Origin: {first_faa['origin']}, Chunks: {first_faa['chunk_count']})")
    assert first_faa["origin"] == "faa"

    print("\n=== 2. Testing Manual Document Creation Endpoint ===")
    doc_payload = {
        "title": "Corporate Standard Operating Procedures - Flight Dispatch",
        "document_id": "MANUAL_SOP_DISPATCH_TEST",
        "source": "AeroLex Flight Operations",
        "date": "2026-03-01",
        "language": "eng",
        "stakeholder": "airline",
        "description": "Standard operating procedures for flight dispatchers and dispatch release requirements.",
        "sections": [
            {
                "section_number": "1.1",
                "title": "Operational Dispatch Release",
                "subpart": "Subpart A - General Dispatch",
                "subject_group": "FLIGHT RELEASE",
                "text": "The aircraft dispatcher shall issue an operational dispatch release for each scheduled flight.\n\n(a) The PIC and dispatcher shall mutually agree on weather minima and route contingency.\n(b) The release shall specify fuel requirements and alternate airports."
            },
            {
                "section_number": "1.2",
                "title": "En-route Weather Monitoring",
                "subpart": "Subpart A - General Dispatch",
                "subject_group": "IN-FLIGHT COMMUNICATIONS",
                "text": "During flight time, the dispatcher shall continuously monitor en-route weather and SIGMET reports.\n\n(c) Any hazardous weather divergence must be communicated to the flight crew immediately."
            }
        ]
    }
    create_res = client.post("/regulations/manual-document", json=doc_payload)
    assert create_res.status_code == 200, f"Creation failed: {create_res.text}"
    created_data = create_res.json()
    print(f"Manual Document Result: {created_data}")
    assert created_data["success"] is True
    assert created_data["chunk_count"] == 2
    assert created_data["document_id"] == "MANUAL_SOP_DISPATCH_TEST"

    print("\n=== 3. Testing Catalog Manual Origin Filter ===")
    cat_manual = client.get("/regulations/catalog?origin=manual")
    assert cat_manual.status_code == 200
    manual_data = cat_manual.json()
    print(f"Manual docs in catalog: {manual_data['filtered_count']}")
    assert any(d["document_id"] == "MANUAL_SOP_DISPATCH_TEST" for d in manual_data["regulations"])

    print("\n=== 4. Testing Dedicated Workspace FTS with Manual & FAA Docs ===")
    fts_req = {
        "query": "dispatcher release",
        "document_ids": ["MANUAL_SOP_DISPATCH_TEST"],
        "top_k_per_doc": 5,
        "total_top_k": 10
    }
    fts_res = client.post("/regulations/workspace-fts", json=fts_req)
    assert fts_res.status_code == 200, f"FTS query failed: {fts_res.text}"
    fts_data = fts_res.json()
    print(f"Workspace FTS Total Matches: {fts_data['total_matches']}")
    assert fts_data["total_matches"] > 0
    first_match = fts_data["all_results"][0]
    print(f"Match Section: {first_match['section_title']}")
    print(f"Previous chunk ID: {first_match['previous_chunk_id']}, Next chunk ID: {first_match['next_chunk_id']}")
    assert "MANUAL_SOP_DISPATCH_TEST" in first_match["chunk_id"]

    print("\n=== 5. Testing Surrounding Provisions Retrieval ===")
    context_res = client.get(f"/search/chunks/{first_match['chunk_id']}/context?window=2")
    assert context_res.status_code == 200, f"Context endpoint failed: {context_res.text}"
    ctx_data = context_res.json()
    print(f"Surrounding chunks for {first_match['chunk_id']}: {ctx_data['total_chunks']} chunks returned")
    assert ctx_data["total_chunks"] >= 1
    target_found = any(c["is_target"] for c in ctx_data["chunks"])
    assert target_found, "Target chunk not flagged as is_target!"

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_api()
