#!/usr/bin/env python3
"""
Aviation LoRA Interactive Inference & Evaluation Tool
======================================================
Loads a base model (e.g. google/gemma-4-E4B-it) in 4-bit and mounts the
trained LoRA adapter for interactive testing or batch evaluation on test.jsonl.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

SYSTEM_PROMPT = "You are an expert aviation regulatory and operations assistant. Provide accurate, professional, and authoritative guidance grounded in established aviation standards and procedures."

def load_lora_model(base_model_id: str, adapter_path: str):
    print(f"Loading Base Model: {base_model_id} in 4-bit...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(adapter_path if Path(adapter_path).exists() else base_model_id)
    
    model_cls = AutoModelForCausalLM
    try:
        from transformers.models.gemma4.modeling_gemma4 import Gemma4ForCausalLM
        if "gemma-4" in base_model_id.lower():
            model_cls = Gemma4ForCausalLM
    except ImportError:
        pass

    base_model = model_cls.from_pretrained(
        base_model_id,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )

    print(f"Mounting LoRA Adapter from: {adapter_path}...")
    model = PeftModel.from_pretrained(base_model, adapter_path)
    model.eval()
    return model, tokenizer

def generate_response(model, tokenizer, question: str, max_new_tokens: int = 512) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.2,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )

    response_text = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return response_text.strip()

def run_interactive(model, tokenizer):
    print("\n" + "=" * 70)
    print("Aviation Regulatory Assistant - Interactive LoRA Mode")
    print("Type your operational/regulatory question (or 'quit' / 'exit'):")
    print("=" * 70)

    while True:
        try:
            q = input("\n[Question]> ").strip()
            if not q or q.lower() in ("exit", "quit"):
                break
            start_t = time.perf_counter()
            ans = generate_response(model, tokenizer, q)
            elapsed = time.perf_counter() - start_t
            print(f"\n[Aviation Assistant ({elapsed:.2f}s)]:\n{ans}")
        except KeyboardInterrupt:
            break

def run_batch_eval(model, tokenizer, test_file: str, max_samples: int = 20):
    test_path = Path(test_file)
    if not test_path.exists():
        print(f"Evaluation file not found: {test_path}")
        return

    print(f"\nRunning batch evaluation on {test_path} (limit {max_samples})...")
    with open(test_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()][:max_samples]

    for idx, line in enumerate(lines, 1):
        item = json.loads(line)
        msgs = item.get("messages", [])
        q = next((m["content"] for m in msgs if m["role"] == "user"), "")
        expected = next((m["content"] for m in msgs if m["role"] == "assistant"), "")

        print("\n" + "=" * 70)
        print(f"TEST SAMPLE {idx}/{len(lines)} (Doc: {item.get('document_id', 'Unknown')})")
        print(f"Q: {q}")
        print("-" * 70)
        ans = generate_response(model, tokenizer, q)
        print(f"MODEL PREDICTION:\n{ans}")
        print("-" * 70)
        print(f"GROUND TRUTH REFERENCE:\n{expected}")

def main():
    parser = argparse.ArgumentParser(description="Inference & Evaluation for Aviation LoRA Adapter")
    parser.add_argument("--base-model", type=str, default="google/gemma-4-E4B-it", help="Base model ID")
    parser.add_argument("--adapter", type=str, default="models/aviation-gemma-lora", help="Path to LoRA adapter")
    parser.add_argument("--eval-file", type=str, default=None, help="Optional test.jsonl path for evaluation")
    parser.add_argument("--samples", type=int, default=15, help="Max test samples to evaluate")

    args = parser.parse_args()
    model, tokenizer = load_lora_model(args.base_model, args.adapter)

    if args.eval_file:
        run_batch_eval(model, tokenizer, args.eval_file, max_samples=args.samples)
    else:
        run_interactive(model, tokenizer)

if __name__ == "__main__":
    main()
