import urllib.request
import json

query = """recorded by the air traffic services unit serving the FIR within which the aircraft is flying in such a manner that it is available for reference and in case it is requested for search and rescue action"""

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/search',
    data=json.dumps({
        'query': query,
        'top_k': 5,
        'filter': {
            'doc_id': 'doc_4444'
        }
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))

print("Total results:", data.get("total_results"))
print(f"Time taken: {data.get('time_taken_ms')} ms")
for idx, r in enumerate(data.get("results", []), start=1):
    print(f"\n[{idx}] Score: {r.get('score'):.4f} (Dense: {r.get('dense_score')}, BM25: {r.get('bm25_score')})")
    print(f"    Source:  {r.get('doc_title')} ({r.get('filename')}) - Page {r.get('page_number')}")
    print(f"    Chapter: {r.get('chapter')}")
    print(f"    Full Text:\n{r.get('text')}\n")
