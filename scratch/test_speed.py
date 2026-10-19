import time
from sentence_transformers import CrossEncoder

print("Loading model...")
t0 = time.time()
model = CrossEncoder("BAAI/bge-reranker-v2-m3")
print(f"Loaded in {time.time() - t0:.2f}s")

query = "what provisions are applicable to the inplementation and operation of CAT III operations from both the ground and airbourne perspectives?"
docs = ["Sample doc text about all weather operations CAT III low visibility " * 10] * 20

pairs = [[query, d] for d in docs]

t1 = time.time()
scores = model.predict(pairs)
print(f"Scored {len(pairs)} pairs in {time.time() - t1:.3f}s ({(time.time() - t1)/len(pairs)*1000:.1f}ms per pair)")
