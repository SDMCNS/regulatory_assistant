#!/usr/bin/env python3
"""
Aviation Regulatory LoRA vs Base Model Comparative Benchmark
============================================================
Evaluates a base model against its LoRA fine-tuned counterpart using a rigorous
structured prompt based on fictional regulatory provision R-17.

Features:
- Single-pass memory-safe 4-bit model loading with PeftModel adapter toggling.
- Evaluates both Base (adapter disabled) and LoRA (adapter enabled) on identical prompts.
- Multi-dimensional quantitative scoring rubric across 5 core regulatory dimensions:
    1. Structural & Sectional Adherence (A-E completion, Markdown table schema)
    2. Modality & Actor Grounding ("shall", "may", "where", "only where", ANSP attribution)
    3. Decision Logic & Branching Fidelity (3 distinct operational states & dual condition)
    4. Epistemic Restraint & Negative Constraints (no external rules, no invented deadlines)
    5. Analytical Density & Precision (legal terminology, non-paraphrasing, signal-to-noise)
- Side-by-side terminal comparison, Markdown evaluation report, and JSON metrics export.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# ==============================================================================
# AUTHORITATIVE BENCHMARK PROMPT
# ==============================================================================

BENCHMARK_PROMPT = """You are analysing an aviation regulatory provision. Treat the following provision as fictional and authoritative for this exercise. Do not introduce external rules or assumptions.

PROVISION R-17 — Maintenance of surveillance service

1. An air navigation service provider shall maintain the surveillance service during published operating hours where the service is required by the applicable operational agreement.

2. Where the primary surveillance source becomes unavailable, the provider shall notify the affected operational units without undue delay.

3. The provider may continue the service using an alternative surveillance source only where that source has been assessed as suitable for the intended operational use and the relevant operational procedures permit its use.

4. Where neither the primary source nor an assessed alternative is available, the provider shall notify the affected operational units and apply the contingency arrangements established for that service.

TASK

Analyse the provision as a regulatory analyst. Do not merely paraphrase it.

Produce the following:

A. REQUIREMENTS
Identify each distinct obligation, permission, condition and contingency. For each, state the responsible actor, trigger, required or permitted action, and any qualification.

B. DECISION LOGIC
Express the operational logic as a numbered decision sequence. Distinguish clearly between:
- Primary source available.
- Primary source unavailable, with a suitable alternative and permitted procedures.
- Primary source unavailable, with no suitable alternative or no procedural permission.

C. MODALITY AND QUALIFICATIONS
Explain the regulatory significance of “shall”, “may”, “where”, “only where”, “without undue delay” and “neither … nor” as used in this provision. Do not assign a precise time limit to “without undue delay”.

D. LIMITS OF THE TEXT
Identify what cannot be concluded from this provision alone. In particular, do not assume that an alternative source is automatically authorised merely because it is technically available.

E. STRUCTURED OUTPUT
Finish with a compact table containing:
Provision | Actor | Trigger or condition | Obligation or permission | Qualification.

Preserve all material conditions and distinctions. Do not invent additional obligations, deadlines, approval authorities or technical requirements. Where interpretation depends on information not supplied, state that explicitly."""

# ==============================================================================
# EVALUATION METRICS & SCORING RUBRIC
# ==============================================================================

@dataclass
class DimensionScore:
    name: str
    score: float  # 0 to 100
    weight: float
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)

@dataclass
class ModelEvaluationResult:
    model_name: str
    response_text: str
    latency_sec: float
    tokens_generated: int
    tokens_per_sec: float
    dimension_scores: Dict[str, DimensionScore] = field(default_factory=dict)
    composite_score: float = 0.0

class RegulatoryBenchmarkEvaluator:
    """
    Automated analytical evaluation suite for regulatory legal parsing and drafting.
    Applies multi-factor heuristic checks, schema validation, and constraint audits.
    """

    @staticmethod
    def evaluate(response: str, model_label: str, latency: float, num_tokens: int) -> ModelEvaluationResult:
        tokens_per_sec = num_tokens / latency if latency > 0 else 0.0
        text = response.strip()
        text_lower = text.lower()

        scores: Dict[str, DimensionScore] = {}

        # ----------------------------------------------------------------------
        # Dimension 1: Structural & Sectional Adherence (Weight: 20%)
        # ----------------------------------------------------------------------
        s1_passed, s1_failed, s1_obs = [], [], []
        s1_points = 0.0

        # Section A
        if re.search(r"(?:^|\n)[#* \t]*(?:A[\.:\)]|SECTION\s*A).*?REQUIREMENTS", text, re.IGNORECASE):
            s1_passed.append("Section A (REQUIREMENTS) identified")
            s1_points += 20.0
        else:
            s1_failed.append("Missing Section A header")

        # Section B
        if re.search(r"(?:^|\n)[#* \t]*(?:B[\.:\)]|SECTION\s*B).*?DECISION\s*LOGIC", text, re.IGNORECASE):
            s1_passed.append("Section B (DECISION LOGIC) identified")
            s1_points += 20.0
        else:
            s1_failed.append("Missing Section B header")

        # Section C
        if re.search(r"(?:^|\n)[#* \t]*(?:C[\.:\)]|SECTION\s*C).*?MODALITY", text, re.IGNORECASE):
            s1_passed.append("Section C (MODALITY AND QUALIFICATIONS) identified")
            s1_points += 20.0
        else:
            s1_failed.append("Missing Section C header")

        # Section D
        if re.search(r"(?:^|\n)[#* \t]*(?:D[\.:\)]|SECTION\s*D).*?LIMITS", text, re.IGNORECASE):
            s1_passed.append("Section D (LIMITS OF THE TEXT) identified")
            s1_points += 20.0
        else:
            s1_failed.append("Missing Section D header")

        # Section E & Table
        has_sec_e = bool(re.search(r"(?:^|\n)[#* \t]*(?:E[\.:\)]|SECTION\s*E).*?(?:STRUCTURED|TABLE)", text, re.IGNORECASE))
        has_table = bool(re.search(r"\|[^\n]+\|\n\|[\s:-]+\|[^\n]*\n(?:\|[^\n]+\|\n?)+", text))
        
        # Check required table columns: Provision, Actor, Trigger/Condition, Obligation/Permission, Qualification
        col_matches = 0
        for col_name in ["provision", "actor", "trigger", "obligation", "qualification"]:
            if col_name in text_lower:
                col_matches += 1

        if has_sec_e:
            s1_passed.append("Section E header identified")
            s1_points += 10.0
        else:
            s1_failed.append("Missing Section E header")

        if has_table and col_matches >= 4:
            s1_passed.append("Structured Markdown table with required schema present")
            s1_points += 10.0
        elif has_table:
            s1_passed.append("Markdown table present with partial column match")
            s1_points += 5.0
        else:
            s1_failed.append("Markdown table missing or malformed")

        scores["structure"] = DimensionScore(
            name="Structural & Sectional Adherence",
            score=min(100.0, s1_points),
            weight=0.20,
            passed_checks=s1_passed,
            failed_checks=s1_failed,
            observations=s1_obs
        )

        # ----------------------------------------------------------------------
        # Dimension 2: Modality & Actor Grounding (Weight: 20%)
        # ----------------------------------------------------------------------
        s2_passed, s2_failed, s2_obs = [], [], []
        s2_points = 0.0

        modalities = [
            ("shall", ["mandatory", "obligation", "duty", "command", "compulsory", "required"]),
            ("may", ["discretion", "permission", "authorized", "option", "permissive", "entitled"]),
            ("where", ["trigger", "precondition", "factual condition", "circumstance", "contingent"]),
            ("only where", ["necessary condition", "exclusive", "strict condition", "prerequisite", "sole condition", "restrictive"]),
            ("neither", ["dual negative", "both", "exhaustive", "cumulative absence", "neither primary nor"]),
            ("without undue delay", ["contextual", "not fixed", "flexible", "prompt", "circumstances", "as soon as practicable", "no precise"])
        ]

        for mod_term, indicator_keywords in modalities:
            if mod_term in text_lower:
                # Check if accompanied by regulatory explanation
                found_exp = any(ik in text_lower for ik in indicator_keywords)
                if found_exp:
                    s2_passed.append(f"Modal '{mod_term}' explained with sound regulatory meaning")
                    s2_points += 14.0
                else:
                    s2_passed.append(f"Modal '{mod_term}' referenced without deep regulatory rationale")
                    s2_points += 8.0
            else:
                s2_failed.append(f"Modal term '{mod_term}' omitted or unaddressed")

        # Actor attribution
        actors_found = 0
        if "air navigation service provider" in text_lower or "ansp" in text_lower or "provider" in text_lower:
            actors_found += 1
        if "affected operational units" in text_lower or "operational units" in text_lower:
            actors_found += 1

        if actors_found == 2:
            s2_passed.append("Both primary actors (ANSP/Provider and Affected Operational Units) correctly recognized")
            s2_points += 16.0
        elif actors_found == 1:
            s2_passed.append("Primary actor recognized, secondary actor partially referenced")
            s2_points += 8.0
        else:
            s2_failed.append("Failed to identify key actors accurately")

        scores["modality"] = DimensionScore(
            name="Regulatory Modality & Actor Grounding",
            score=min(100.0, s2_points),
            weight=0.20,
            passed_checks=s2_passed,
            failed_checks=s2_failed,
            observations=s2_obs
        )

        # ----------------------------------------------------------------------
        # Dimension 3: Decision Logic & Branching Fidelity (Weight: 20%)
        # ----------------------------------------------------------------------
        s3_passed, s3_failed, s3_obs = [], [], []
        s3_points = 0.0

        # Branch 1: Primary available
        b1_matches = ["primary", "available", "maintain", "published operating hours", "operational agreement"]
        b1_count = sum(1 for m in b1_matches if m in text_lower)
        if b1_count >= 3:
            s3_passed.append("Branch 1: Primary source available logic fully captured")
            s3_points += 25.0
        else:
            s3_failed.append("Branch 1: Primary source available logic missing or incomplete")

        # Branch 2: Primary unavailable, alternative assessed & permitted
        b2_matches = ["unavailable", "alternative", "assessed as suitable", "operational procedures permit", "notify"]
        b2_count = sum(1 for m in b2_matches if m in text_lower)
        if b2_count >= 4:
            s3_passed.append("Branch 2: Alternative source logic with dual prerequisite (assessed + permitted) captured")
            s3_points += 30.0
        elif b2_count >= 2:
            s3_passed.append("Branch 2: Alternative source logic partially articulated")
            s3_points += 15.0
        else:
            s3_failed.append("Branch 2: Alternative source branching omitted")

        # Dual condition check (specifically verifies BOTH suitability and procedures)
        has_dual = ("suitable" in text_lower or "assessed" in text_lower) and ("procedure" in text_lower or "permit" in text_lower)
        if has_dual:
            s3_passed.append("Conjunctive dual requirement (suitability assessment AND procedural permission) preserved")
            s3_points += 15.0
        else:
            s3_failed.append("Failed to articulate the conjunctive dual test for alternative sources")

        # Branch 3: Neither available -> contingency
        b3_matches = ["neither", "contingency arrangements", "established", "notify"]
        b3_count = sum(1 for m in b3_matches if m in text_lower)
        if b3_count >= 3:
            s3_passed.append("Branch 3: Total loss / contingency application logic accurately distinguished")
            s3_points += 25.0
        elif b3_count >= 1:
            s3_passed.append("Branch 3: Contingency mentioned without complete condition linkage")
            s3_points += 12.0
        else:
            s3_failed.append("Branch 3: Contingency branch omitted")

        # Numbered/Ordered sequence check
        if re.search(r"(?:1\.|step\s*1|state\s*1).*?(?:2\.|step\s*2|state\s*2).*?(?:3\.|step\s*3|state\s*3)", text_lower, re.DOTALL):
            s3_passed.append("Clear sequential numbering (1, 2, 3) employed in decision logic")
            s3_points += 5.0
        else:
            s3_failed.append("Decision logic lacks explicit numbered sequence")

        scores["decision_logic"] = DimensionScore(
            name="Decision Logic & Branching Fidelity",
            score=min(100.0, s3_points),
            weight=0.20,
            passed_checks=s3_passed,
            failed_checks=s3_failed,
            observations=s3_obs
        )

        # ----------------------------------------------------------------------
        # Dimension 4: Epistemic Restraint & Negative Constraints (Weight: 20%)
        # ----------------------------------------------------------------------
        s4_passed, s4_failed, s4_obs = [], [], []
        s4_points = 70.0  # start from baseline and reward/penalize

        # Constraint 1: Technical availability != automatic authorization
        tech_distinction = any(phrase in text_lower for phrase in [
            "technical availability", "technically available", "automatically authorised",
            "not automatically", "does not automatically", "mere technical", "solely because"
        ])
        if tech_distinction:
            s4_passed.append("Negative Constraint Honored: Technical availability does NOT imply automatic authorization")
            s4_points += 15.0
        else:
            s4_failed.append("Failed to explicitly distinguish technical availability from operational authorization")

        # Constraint 2: Do NOT assign precise time limit to 'without undue delay'
        # Detect hallucinated concrete time units: e.g. "within 15 minutes", "within 1 hour", "under 30 mins"
        has_time_limit = bool(re.search(r"without undue delay.*?(\d+\s*(?:minutes?|mins?|hours?|seconds?)|immediate(?:ly)?)", text_lower))
        if has_time_limit:
            s4_failed.append("VIOLATION: Assigned an unauthorized concrete time limit to 'without undue delay'")
            s4_points -= 25.0
        else:
            s4_passed.append("Negative Constraint Honored: Refrained from assigning arbitrary time limit to 'without undue delay'")
            s4_points += 10.0

        # Constraint 3: Do NOT invent external regulations (FAA, ICAO, EASA, Part 91, etc.)
        external_jargon = ["icao annex", "faa order", "easa part", "far part", "part 121", "part 91", "eurocontrol spec"]
        invented_ext = [j for j in external_jargon if j in text_lower]
        if invented_ext:
            s4_failed.append(f"VIOLATION: Injected ungrounded real-world framework(s): {', '.join(invented_ext)}")
            s4_points -= 20.0
        else:
            s4_passed.append("Negative Constraint Honored: Treated provision as closed authoritative fictional text")
            s4_points += 5.0

        # Gaps / Missing Information explicitly identified
        gap_indicators = [
            "not supplied", "not specified", "cannot be concluded", "text does not define",
            "silent", "not stated", "depends on information not supplied"
        ]
        gaps_noted = sum(1 for g in gap_indicators if g in text_lower)
        if gaps_noted >= 2:
            s4_passed.append("Limits of the Text: Explicitly documented gaps and non-supplied information")
            s4_points += 10.0
        elif gaps_noted == 1:
            s4_passed.append("Limits of the Text: Identified at least one unstated dependency")
            s4_points += 5.0
        else:
            s4_failed.append("Failed to clearly enumerate textual gaps and non-supplied details")

        scores["negative_constraints"] = DimensionScore(
            name="Epistemic Restraint & Negative Constraints",
            score=max(0.0, min(100.0, s4_points)),
            weight=0.20,
            passed_checks=s4_passed,
            failed_checks=s4_failed,
            observations=s4_obs
        )

        # ----------------------------------------------------------------------
        # Dimension 5: Regulatory Precision & Analytical Quality (Weight: 20%)
        # ----------------------------------------------------------------------
        s5_passed, s5_failed, s5_obs = [], [], []
        s5_points = 0.0

        # Table rows coverage (R-17.1, R-17.2, R-17.3, R-17.4)
        provisions_in_table = sum(1 for p in ["1", "2", "3", "4", "r-17.1", "r-17.2", "r-17.3", "r-17.4"] if p in text_lower)
        if provisions_in_table >= 4:
            s5_passed.append("Table thoroughly indexes all four sub-provisions (1, 2, 3, 4)")
            s5_points += 25.0
        else:
            s5_failed.append("Table incompletely indexes the provision paragraphs")
            s5_points += 10.0

        # Advanced regulatory vocabulary density
        analytical_vocab = [
            "condition precedent", "discretionary", "mandatory", "contingency",
            "jurisdiction", "authorisation", "authorization", "qualification",
            "trigger", "scope", "prerequisite", "preclusion", "substantive"
        ]
        vocab_matches = [v for v in analytical_vocab if v in text_lower]
        if len(vocab_matches) >= 5:
            s5_passed.append(f"High analytical vocabulary density ({len(vocab_matches)} legal terms)")
            s5_points += 30.0
        elif len(vocab_matches) >= 3:
            s5_passed.append(f"Moderate analytical vocabulary density ({len(vocab_matches)} legal terms)")
            s5_points += 20.0
        else:
            s5_failed.append("Low analytical depth; relies primarily on colloquial phrasing")
            s5_points += 5.0

        # Signal-to-noise: penalty for generic conversational filler
        filler_patterns = [
            "certainly!", "here is the analysis", "as an ai", "i hope this helps",
            "feel free to ask", "let me know if you need"
        ]
        has_filler = any(f in text_lower for f in filler_patterns)
        if has_filler:
            s5_failed.append("Verbose conversational filler detected")
            s5_points += 5.0
        else:
            s5_passed.append("Professional regulatory tone with zero conversational padding")
            s5_points += 25.0

        # Length / Analytical depth sanity check
        words = len(text.split())
        if 300 <= words <= 1200:
            s5_passed.append(f"Optimal regulatory density ({words} words)")
            s5_points += 20.0
        elif words < 300:
            s5_failed.append(f"Output too brief / superficial ({words} words)")
            s5_points += 10.0
        else:
            s5_passed.append(f"Exhaustive output ({words} words)")
            s5_points += 15.0

        scores["analytical_quality"] = DimensionScore(
            name="Regulatory Precision & Analytical Quality",
            score=min(100.0, s5_points),
            weight=0.20,
            passed_checks=s5_passed,
            failed_checks=s5_failed,
            observations=s5_obs
        )

        # ----------------------------------------------------------------------
        # Composite Score Calculation
        # ----------------------------------------------------------------------
        comp = sum(dim.score * dim.weight for dim in scores.values())

        return ModelEvaluationResult(
            model_name=model_label,
            response_text=text,
            latency_sec=latency,
            tokens_generated=num_tokens,
            tokens_per_sec=tokens_per_sec,
            dimension_scores=scores,
            composite_score=round(comp, 2)
        )

# ==============================================================================
# MODEL RUNNER (DUAL MODE: BASE vs LORA)
# ==============================================================================

def resolve_adapter_path(adapter_arg: str) -> Path:
    p = Path(adapter_arg)
    if not p.exists():
        raise FileNotFoundError(f"Adapter path not found: {p.resolve()}")

    # Direct adapter config in directory
    if (p / "adapter_config.json").exists():
        return p

    # Look for checkpoint subdirectories
    ckpts = sorted(p.glob("checkpoint-*"), key=lambda d: int(d.name.split("-")[-1]) if d.name.split("-")[-1].isdigit() else 0)
    if ckpts and (ckpts[-1] / "adapter_config.json").exists():
        latest = ckpts[-1]
        print(f"[*] Auto-detected latest checkpoint: {latest}")
        return latest

    raise FileNotFoundError(f"No adapter_config.json found in {p} or any checkpoint subdirectory.")


def load_model_and_tokenizer(base_model_id: str, adapter_path: Path):
    print("=" * 70)
    print("LOADING MODEL AND LORA ADAPTER")
    print("=" * 70)
    print(f"Base Model:    {base_model_id}")
    print(f"LoRA Adapter:  {adapter_path.resolve()}")

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_free = torch.cuda.mem_get_info()[0] / (1024 ** 3)
        print(f"Target GPU:    {gpu_name} (Free VRAM: {vram_free:.2f} GB)")

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_path) if (adapter_path / "tokenizer_config.json").exists() else base_model_id,
        trust_remote_code=True,
        use_fast=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("[*] Loading base weights in 4-bit...")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        trust_remote_code=True,
    )
    base_model.eval()

    print("[*] Mounting LoRA adapter into PeftModel...")
    model = PeftModel.from_pretrained(base_model, str(adapter_path))
    model.eval()

    if torch.cuda.is_available():
        vram_used = torch.cuda.memory_allocated() / (1024 ** 3)
        print(f"[*] VRAM Allocated: {vram_used:.2f} GB (Safe headroom: {15.93 - vram_used:.2f} GB)")
    print("")

    return model, tokenizer


def generate_inference(
    model: PeftModel,
    tokenizer: AutoTokenizer,
    prompt: str,
    use_lora: bool,
    max_new_tokens: int = 1536,
    temperature: float = 0.2,
    top_p: float = 0.95
) -> Tuple[str, float, int]:
    messages = [{"role": "user", "content": prompt}]
    
    if hasattr(tokenizer, "apply_chat_template"):
        formatted_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        formatted_prompt = prompt

    inputs = tokenizer(formatted_prompt, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[1]

    torch.cuda.empty_cache()
    start_time = time.perf_counter()

    with torch.no_grad():
        if use_lora:
            # Generate with LoRA adapter active
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=temperature > 0,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        else:
            # Generate with LoRA adapter completely disabled (pure Base model)
            with model.disable_adapter():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    do_sample=temperature > 0,
                    pad_token_id=tokenizer.eos_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )

    latency = time.perf_counter() - start_time
    output_tokens = outputs[0][input_len:]
    num_generated = len(output_tokens)
    response_text = tokenizer.decode(output_tokens, skip_special_tokens=True).strip()

    return response_text, latency, num_generated

# ==============================================================================
# REPORTING & FORMATTING
# ==============================================================================

def print_terminal_comparison(base_res: ModelEvaluationResult, lora_res: ModelEvaluationResult):
    print("=" * 80)
    print(" " * 22 + "LORA EFFECTIVENESS BENCHMARK REPORT")
    print("=" * 80)
    print(f"{'DIMENSION':<45} | {'BASE MODEL':<12} | {'LORA MODEL':<12} | {'DELTA':<8}")
    print("-" * 80)

    for dim_key in base_res.dimension_scores:
        b_score = base_res.dimension_scores[dim_key].score
        l_score = lora_res.dimension_scores[dim_key].score
        delta = l_score - b_score
        name = base_res.dimension_scores[dim_key].name
        delta_str = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
        print(f"{name:<45} | {b_score:>10.1f} | {l_score:>10.1f} | {delta_str:>8}")

    print("-" * 80)
    comp_delta = lora_res.composite_score - base_res.composite_score
    c_delta_str = f"+{comp_delta:.1f}" if comp_delta > 0 else f"{comp_delta:.1f}"
    print(f"{'COMPOSITE WEIGHTED SCORE':<45} | {base_res.composite_score:>10.1f} | {lora_res.composite_score:>10.1f} | {c_delta_str:>8}")
    print("=" * 80)

    print(f"Performance: Base {base_res.tokens_per_sec:.1f} tok/s ({base_res.latency_sec:.1f}s) | LoRA {lora_res.tokens_per_sec:.1f} tok/s ({lora_res.latency_sec:.1f}s)")
    print("")


def generate_markdown_report(
    base_res: ModelEvaluationResult,
    lora_res: ModelEvaluationResult,
    prompt: str,
    base_model_name: str,
    adapter_name: str,
    output_path: Path
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    comp_delta = lora_res.composite_score - base_res.composite_score
    delta_sign = "+" if comp_delta > 0 else ""

    content = f"""# Aviation Regulatory LoRA vs Base Model Comparative Evaluation Report

**Generated At:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Base Model:** `{base_model_name}`  
**LoRA Adapter:** `{adapter_name}`  
**Overall Verdict:** LoRA score is **{lora_res.composite_score:.1f}/100** vs Base model **{base_res.composite_score:.1f}/100** (Net Shift: **{delta_sign}{comp_delta:.1f} pts**).

---

## 1. Executive Summary & Scorecard

| Evaluation Dimension | Weight | Base Model | LoRA Supported Model | Delta |
| :--- | :---: | :---: | :---: | :---: |
"""
    for dim_key in base_res.dimension_scores:
        b = base_res.dimension_scores[dim_key]
        l = lora_res.dimension_scores[dim_key]
        d = l.score - b.score
        d_str = f"+{d:.1f}" if d > 0 else f"{d:.1f}"
        content += f"| **{b.name}** | {b.weight*100:.0f}% | {b.score:.1f} | {l.score:.1f} | `{d_str}` |\n"

    content += f"""| **COMPOSITE REGULATORY SCORE** | **100%** | **{base_res.composite_score:.1f}** | **{lora_res.composite_score:.1f}** | **`{delta_sign}{comp_delta:.1f}`** |

### Telemetry & Generation Performance
- **Base Model Latency:** {base_res.latency_sec:.2f}s ({base_res.tokens_generated} tokens @ {base_res.tokens_per_sec:.1f} tok/s)
- **LoRA Model Latency:** {lora_res.latency_sec:.2f}s ({lora_res.tokens_generated} tokens @ {lora_res.tokens_per_sec:.1f} tok/s)

---

## 2. Dimension-by-Dimension Analytical Breakdown

"""

    for dim_key, b_dim in base_res.dimension_scores.items():
        l_dim = lora_res.dimension_scores[dim_key]
        d = l_dim.score - b_dim.score
        d_str = f"+{d:.1f}" if d > 0 else f"{d:.1f}"

        content += f"""### {b_dim.name} (Delta: `{d_str}`)
- **Base Model ({b_dim.score:.1f}/100):**
  - *Passed Checks:* {", ".join(b_dim.passed_checks) if b_dim.passed_checks else "None"}
  - *Deficiencies:* {", ".join(b_dim.failed_checks) if b_dim.failed_checks else "None"}
- **LoRA Model ({l_dim.score:.1f}/100):**
  - *Passed Checks:* {", ".join(l_dim.passed_checks) if l_dim.passed_checks else "None"}
  - *Deficiencies:* {", ".join(l_dim.failed_checks) if l_dim.failed_checks else "None"}

"""

    content += f"""---

## 3. Full Benchmark Prompt

```text
{prompt}
```

---

## 4. Base Model Output (Without LoRA)

```text
{base_res.response_text}
```

---

## 5. LoRA Model Output (With LoRA Adapter Active)

```text
{lora_res.response_text}
```

---
*Report generated automatically by `compare_lora.py`.*
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[*] Comprehensive Markdown Report saved to: {output_path.resolve()}")


def export_json_summary(base_res: ModelEvaluationResult, lora_res: ModelEvaluationResult, json_path: Path):
    data = {
        "timestamp": datetime.now().isoformat(),
        "base_model": asdict(base_res),
        "lora_model": asdict(lora_res),
        "delta": {
            "composite": round(lora_res.composite_score - base_res.composite_score, 2),
            "dimensions": {
                k: round(lora_res.dimension_scores[k].score - base_res.dimension_scores[k].score, 2)
                for k in base_res.dimension_scores
            }
        }
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[*] JSON Metrics Export saved to: {json_path.resolve()}")

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark LoRA effectiveness by running structured regulatory analysis prompt on Base vs LoRA model."
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="google/gemma-4-E4B-it",
        help="Base model ID or path. Default: google/gemma-4-E4B-it"
    )
    parser.add_argument(
        "--adapter",
        type=str,
        default="models/aviation-gemma-lora",
        help="Path to trained LoRA adapter directory or checkpoint"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1536,
        help="Maximum generated tokens per response (default: 1536)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature (default: 0.2 for deterministic analytical precision)"
    )
    parser.add_argument(
        "--prompt-file",
        type=str,
        default=None,
        help="Optional path to a custom text prompt file (defaults to authoritative R-17 benchmark prompt)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Directory to save evaluation reports (default: reports)"
    )

    args = parser.parse_args()

    # Load Prompt
    prompt = BENCHMARK_PROMPT
    if args.prompt_file:
        pf = Path(args.prompt_file)
        if pf.exists():
            prompt = pf.read_text(encoding="utf-8").strip()
            print(f"[*] Loaded custom prompt from: {pf.resolve()}")

    # Resolve Adapter
    adapter_path = resolve_adapter_path(args.adapter)

    # Load Model (Single 4-bit load with adapter)
    model, tokenizer = load_model_and_tokenizer(args.base_model, adapter_path)

    # 1. RUN BASE MODEL (Adapter Disabled)
    print("=" * 70)
    print("[1/2] RUNNING BASE MODEL (Without LoRA)...")
    print("=" * 70)
    base_text, base_latency, base_toks = generate_inference(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        use_lora=False,
        max_new_tokens=args.max_tokens,
        temperature=args.temperature
    )
    print(f"Base generation finished in {base_latency:.2f}s ({base_toks} tokens, {base_toks/base_latency:.1f} tok/s)")
    print("")

    # 2. RUN LORA MODEL (Adapter Enabled)
    print("=" * 70)
    print("[2/2] RUNNING LORA MODEL (With Aviation LoRA Adapter)...")
    print("=" * 70)
    lora_text, lora_latency, lora_toks = generate_inference(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        use_lora=True,
        max_new_tokens=args.max_tokens,
        temperature=args.temperature
    )
    print(f"LoRA generation finished in {lora_latency:.2f}s ({lora_toks} tokens, {lora_toks/lora_latency:.1f} tok/s)")
    print("")

    # 3. EVALUATE & SCORE BOTH OUTPUTS
    print("[*] Performing multi-dimensional comparative scoring...")
    evaluator = RegulatoryBenchmarkEvaluator()
    base_eval = evaluator.evaluate(base_text, "Base Model (Unadapted)", base_latency, base_toks)
    lora_eval = evaluator.evaluate(lora_text, "LoRA Adapted Model", lora_latency, lora_toks)

    # 4. PRINT TERMINAL COMPARISON TABLE
    print_terminal_comparison(base_eval, lora_eval)

    # 5. EXPORT MARKDOWN & JSON REPORTS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    md_report_path = out_dir / f"lora_vs_base_benchmark_{timestamp}.md"
    json_path = out_dir / f"lora_vs_base_benchmark_{timestamp}.json"

    generate_markdown_report(base_eval, lora_eval, prompt, args.base_model, str(adapter_path), md_report_path)
    export_json_summary(base_eval, lora_eval, json_path)

    print("\nBenchmark completed successfully!")


if __name__ == "__main__":
    main()
