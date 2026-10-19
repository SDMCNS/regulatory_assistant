import sys
from sentence_transformers import CrossEncoder

print("Loading CrossEncoder('BAAI/bge-reranker-v2-m3')...")
try:
    model = CrossEncoder("BAAI/bge-reranker-v2-m3")
    query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
    docs = [
        "Annex IV (Part-ADR.OPS) to Regulation (EU) No 139/2014 lays down the requirements for the operation of aerodromes. That Annex should be amended to address all-weather operations, aerodrome low visibility procedures (LVP), and ground facilities for Category III (CAT III) operations.",
        "GM1 SPA.LVO.120(a) Flight crew competence for Low-Visibility Operations (LVOs) and operations with operational credits. Cat II/III approach and landing operations, airborne equipment requirements.",
        "CAT operations with aeroplanes and helicopters shall be subject to the requirements of Subpart FTL of Annex III.",
        "Push-back, power-back or taxi interference by vehicle, equipment or person at the aerodrome apron."
    ]
    pairs = [[query, d] for d in docs]
    scores = model.predict(pairs)
    print("\n=== RESULTS ===")
    for score, doc in sorted(zip(scores, docs), key=lambda x: x[0], reverse=True):
        print(f"Score: {score:+.4f} | {doc[:100]}...")
except Exception as e:
    print("Error:", e)
