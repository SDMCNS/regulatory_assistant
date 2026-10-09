import sqlite3
import requests
import json
import random
import time
from pathlib import Path
import argparse

# LM Studio default endpoints
LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"

SYSTEM_PROMPT = """You are an expert aviation regulatory assistant. Your task is to generate realistic, professional Question and Answer pairs based ONLY on the provided regulatory text. 
The questions should represent what a pilot, engineer, or compliance manager might actually ask.
The answers should be conversational, accurate, and speak directly to the user (e.g. "Under this regulation, you must...").

You MUST return the result EXACTLY as a valid JSON array of objects with 'q' and 'a' keys, like this:
[
  {
    "q": "What is the maximum flight duty period?",
    "a": "According to the regulation, the maximum flight duty period is..."
  }
]
Do not include any markdown blocks, introductory text, or concluding text. Just the JSON array.
"""

def generate_qa_for_chunk(chunk_text: str, max_retries=2):
    user_prompt = f"Generate 2 distinct Q&A pairs for the following regulatory provision:\n\n{chunk_text}"
    
    payload = {
        "model": "google/gemma-4-e4b", # Uses whatever is loaded in LM Studio if model name doesn't perfectly match
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
        "stream": False
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(LM_STUDIO_URL, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            
            # Clean up potential markdown code blocks around JSON
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            qa_pairs = json.loads(content.strip())
            
            # Validate format
            if isinstance(qa_pairs, list) and all("q" in item and "a" in item for item in qa_pairs):
                return qa_pairs
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
            
    return []

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic QA pairs for LoRa training.")
    parser.add_argument("--db", type=str, default="../ingestion/data/regulations/sqlite/chunks.db", help="Path to chunks.db")
    parser.add_argument("--out", type=str, default="synthetic_train.jsonl", help="Output JSONL file")
    parser.add_argument("--limit", type=int, default=1000, help="Number of chunks to process")
    parser.add_argument("--min-chars", type=int, default=200, help="Minimum chunk length")
    parser.add_argument("--max-chars", type=int, default=1500, help="Maximum chunk length")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return

    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get a random sample of chunks that are long enough to have meaningful content
    cursor.execute('''
        SELECT chunk_id, document_id, source_text 
        FROM chunks 
        WHERE source_text IS NOT NULL 
          AND length(trim(source_text)) >= ? 
          AND length(trim(source_text)) <= ?
        ORDER BY RANDOM()
        LIMIT ?
    ''', (args.min_chars, args.max_chars, args.limit))
    
    rows = cursor.fetchall()
    print(f"Loaded {len(rows)} chunks for processing.")
    
    output_path = Path(args.out)
    processed = 0
    generated = 0
    
    with open(output_path, "a", encoding="utf-8") as f_out:
        for row in rows:
            processed += 1
            chunk_id = row["chunk_id"]
            doc_id = row["document_id"]
            source_text = row["source_text"].strip()
            
            print(f"[{processed}/{len(rows)}] Generating QA for {chunk_id}...")
            
            qa_pairs = generate_qa_for_chunk(source_text)
            
            for qa in qa_pairs:
                # Format exactly like test_1.py for seamless integration
                lora_example = {
                    "task": "synthetic_qa",
                    "chunk_id": chunk_id,
                    "document_id": doc_id,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a regulatory analysis assistant. Answer using only the regulatory information supplied in the prompt."
                        },
                        {
                            "role": "user",
                            "content": f"Context: {source_text}\n\nQuestion: {qa['q']}"
                        },
                        {
                            "role": "assistant",
                            "content": qa['a']
                        }
                    ]
                }
                
                f_out.write(json.dumps(lora_example, ensure_ascii=False) + "\n")
                generated += 1
                
    print(f"\nDone! Generated {generated} synthetic Q&A pairs from {processed} chunks.")
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    main()
