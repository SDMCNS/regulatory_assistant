# Aviation Regulatory & Operations LoRA Adaptation Suite

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LoRA](https://img.shields.io/badge/LoRA-PEFT-green.svg)](https://github.com/huggingface/peft)
[![Model](https://img.shields.io/badge/Target_Model-google%2Fgemma--4--E4B--it-orange.svg)](https://huggingface.co/google/gemma-4-E4B-it)

An end-to-end pipeline for adapting Large Language Models to **Aviation Regulations, Operational Procedures, and Incident Investigations** using synthetic Q&A data distillation and 4-bit Parameter-Efficient Fine-Tuning (QLoRA).

---

## 🛫 Overview & Motivation

Aviation documentation spans decades of international treaties, national regulatory codes (FAA FARs, EASA CS, ICAO Annexes), standard operating procedures (SOPs), and investigative accident findings. 

Adapting an LLM like `google/gemma-4-E4B-it` for aviation operations poses two unique challenges:
1. **Knowledge Timelessness & Contact Scrubbing:** Standard documents contain transient points of contact (emails, phone numbers, liaison officers). The pipeline enforces strict regex and prompt filtering to scrub ephemeral contacts while preserving recognized scholarly authors and domain pioneers (e.g., James Reason, Rasmussen).
2. **Corpus Volume & Diversity:** Raw document dumps contain massive volumes of tables of contents, raw FDR telemetry tables, and legal boilerplate. This suite uses **non-LLM algorithmic distillation** to extract high-salience directives before applying QLoRA adaptation.

---

## 📁 Repository Structure

```text
├── chunks/                        # Raw chunks directory (excluded from git, see chunks/README.md)
│   └── README.md                  # Detailed specification for raw document chunks
├── chunks_sample/                 # Sample chunk files illustrating input format
│   ├── sample.chunks.json         # Standard document-level chunk format
│   └── sample_chunks.jsonl        # Line-delimited chunk structure
├── golden_chunks.jsonl            # Curated 20,490 high-salience golden chunks across 84 categories
├── golden_corpus_summary.json     # Category breakdown and statistics of the golden corpus
├── distill_corpus.py              # High-speed (~90s) non-LLM distillation engine
├── generate_qa_pipeline.py        # LM Studio Q&A generation pipeline (round-robin, resumeable)
├── prepare_lora_dataset.py        # Hygiene scrubbing & document-isolated train/val/test splitter
├── train_lora.py                  # PyTorch + PEFT QLoRA 4-bit fine-tuning script
├── evaluate_lora.py               # Interactive CLI & batch test evaluation tool
├── compare_lora.py                # Comparative LoRA vs. Base model benchmark with 5D scoring
├── reports/                       # Generated comparative evaluation benchmark reports (Markdown + JSON)
├── aviation_qa_lora.jsonl         # Active synthetic Q&A dataset in ChatML format
├── qa_generation_state.db         # SQLite checkpoint DB preventing duplicate inference
└── archive/                       # Deprecated/scratch scripts (excluded from git)
```

---

## ⚡ Quick Start: End-to-End Workflow

### Step 1: Environment Setup

Ensure you have Python 3.10+ and a CUDA-capable GPU (e.g. RTX 3060/4060/5060 Ti or higher):

```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install core dependencies
pip install torch transformers peft bitsandbytes datasets accelerate
```

---

### Step 2: Algorithmic Corpus Distillation (Non-LLM)

If you have raw `.chunks.json` files in `chunks/`, run the non-LLM distillation engine to filter out boilerplate and extract high-salience chunks into `golden_chunks.jsonl`:

```powershell
python distill_corpus.py --chunks-dir chunks --out-file golden_chunks.jsonl --max-per-doc 4 --min-score 6.0
```

> [!NOTE]
> `golden_chunks.jsonl` is already included in this repository with **20,490 pre-filtered chunks** across 84 aviation categories. You can proceed directly to Step 3.

---

### Step 3: Synthetic Q&A Generation via LM Studio

1. Open **LM Studio**.
2. Load the base model (e.g., `google/gemma-4-e4b` or GGUF equivalent).
3. Start the local server at `http://127.0.0.1:1234`.
4. Run the generator:

```powershell
# Run with an 8-hour overnight budget across all categories in balanced round-robin
python generate_qa_pipeline.py --golden-chunks golden_chunks.jsonl --max-hours 8.0 --workers 1
```

- **Resumeable:** Uses `qa_generation_state.db` so you can cancel (`Ctrl+C`) and restart at any time without duplicating previously generated pairs.
- **Output:** Appends validated ChatML-formatted Q&A pairs to `aviation_qa_lora.jsonl`.

#### Realistic Processing Times & Throughput Telemetry

Based on empirical runtime logs from a 10.6-hour continuous production run on a local GPU (RTX 5060 Ti 16 GB, LM Studio serving `google/gemma-4-e4b`):

| Metric | Measured Baseline (`--workers 1`) | Multi-Worker Scaling (`--workers 2` to `4`) |
| :--- | :--- | :--- |
| **Average Latency** | **17.58 seconds / chunk** (median: 15.00s) | Shared GPU inference latency |
| **Generation Rate** | **~205 chunks / hour** (~3.4 chunks / min) | **~350–500 chunks / hour** (multi-slot LM Studio) |
| **Dataset Yield** | **~410 Q&A pairs / hour** (~2 pairs / chunk) | **~700–1,000 Q&A pairs / hour** |

#### Golden Corpus Completion Projections (`golden_chunks.jsonl`)

The distilled golden corpus contains **20,490 high-salience chunks**:
- **Currently Processed:** **1,500 chunks** (~3,000 pairs contributing to the initial 4,350 dataset).
- **Remaining Chunks:** **18,990 chunks** (expected yield: ~37,980 additional Q&A pairs).

| Workload Scenario | Chunks | Single-Worker (`--workers 1`) | Dual-Worker (`--workers 2`) | 4-Worker (`--workers 4`) | High-Throughput API (Flash / Batch) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Remaining Golden Chunks** | 18,990 | **~92.7 hrs (~3.9 days)** | **~50–55 hrs (~2.2 days)** | **~35–45 hrs (~1.6 days)** | **~15–25 minutes** |
| **Full Corpus (From Scratch)** | 20,490 | **~100.1 hrs (~4.2 days)** | **~55–60 hrs (~2.4 days)** | **~40–48 hrs (~1.8 days)** | **~20–30 minutes** |

> [!TIP]
> **Recommended Production Strategy:** 
> - **Local Overnight Batches:** Run in 8-hour sessions (`--max-hours 8.0`). The SQLite database will safely resume from where it left off each morning.
> - **LM Studio Concurrency:** Since quantized Gemma-4-E4B requires only ~3.5–4.5 GB VRAM, configure LM Studio with 2–4 parallel request slots in server settings to cut generation time in half.


---

### Step 4: Split Dataset with Document Isolation

To prevent data leakage, training and validation splits are partitioned by `document_id`:

```powershell
python prepare_lora_dataset.py `
  --inputs aviation_qa_lora.jsonl `
  --out-dir dataset_splits `
  --train-ratio 0.85 `
  --val-ratio 0.10 `
  --test-ratio 0.05
```

This generates:
- `dataset_splits/train.jsonl` (85%)
- `dataset_splits/validation.jsonl` (10%)
- `dataset_splits/test.jsonl` (5%)

---

### Step 5: QLoRA 4-Bit Fine-Tuning

Fine-tune the base model using Hugging Face PEFT and BitsAndBytes 4-bit NF4 quantization:

```powershell
python train_lora.py `
  --model google/gemma-4-E4B-it `
  --data-dir dataset_splits `
  --out-dir models/aviation-gemma-lora `
  --epochs 1.0 `
  --batch-size 1 `
  --gradient-accumulation 16 `
  --lr 2e-4 `
  --lora-r 16 `
  --lora-alpha 32
```

- **Empirical Training Runtime (RTX 5060 Ti 16 GB):** **41.76 minutes** (2,492s) for 1.0 epoch across 3,617 training samples (227 steps @ 10.98s/step, effective batch size 16), achieving peak VRAM of **9.71 GB** and final loss of **1.599**.
- **Memory Footprint:** Safely constrained under 10 GB VRAM via bf16 embedding preservation.
- **Target Modules:** All linear projection layers (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`).
- **Checkpoints:** Saved under `models/aviation-gemma-lora/`.

---

### Step 6: Interactive & Batch Model Evaluation

Test the adapted model against the held-out test split or interactively query it:

```powershell
# Interactive console test
python evaluate_lora.py `
  --base-model google/gemma-4-E4B-it `
  --adapter-path models/aviation-gemma-lora `
  --interactive

# Batch evaluation against test.jsonl
python evaluate_lora.py `
  --base-model google/gemma-4-E4B-it `
  --adapter-path models/aviation-gemma-lora `
  --eval-file dataset_splits/test.jsonl
```

---

### Step 7: Comparative LoRA vs. Base Model Benchmark (`compare_lora.py`)

Quantitatively evaluate the effectiveness of the LoRA adapter against the unadapted base model using a structured, authoritative regulatory parsing prompt (fictional provision R-17):

```powershell
# Run benchmark on current adapter / checkpoint
python compare_lora.py --base-model google/gemma-4-E4B-it --adapter models/aviation-gemma-lora
```

#### How it works:
- **Zero-Reload Single Pass:** Loads the base model in 4-bit NF4 and dynamically toggles the adapter using `model.disable_adapter()` to evaluate both Base and LoRA without restarting or reloading weights.
- **5-Dimensional Analytical Rubric:** Evaluates both outputs on a 0–100 scale:
  1. **Structural & Sectional Adherence:** Sections A–E presence and markdown table schema verification.
  2. **Regulatory Modality & Actor Grounding:** Rigorous parsing of *shall*, *may*, *where*, *only where*, *neither...nor*, and ANSP/unit actor attribution.
  3. **Decision Logic & Branching Fidelity:** Disentanglement of normal, degraded, and contingency operational states, preserving the conjunctive dual requirement (*assessed as suitable* AND *procedures permit*).
  4. **Epistemic Restraint & Negative Constraints:** Verifies that technical availability is not conflated with operational authorization, prevents arbitrary time assignments to *"without undue delay"*, and prohibits hallucinated real-world frameworks.
  5. **Analytical Density & Precision:** Legal vocabulary richness, zero conversational padding, and complete provision indexing.
- **Outputs:** Terminal scorecard, comprehensive Markdown report (`reports/lora_vs_base_benchmark_<timestamp>.md`), and JSON metrics export.

---

## 🛡️ Personnel Contact Scrubbing Rules

All generation and preprocessing scripts enforce the following policy:
- ❌ **Prohibited:** Email addresses, phone numbers, office room codes, enquiry liaisons, transient desk officers.
-  **Preserved:** Scientific literature authors, lead safety framework developers (Reason Swiss Cheese model, Rasmussen Socio-Technical model), and lead technical investigators.

---

## 📄 License

This repository is licensed under the Apache 2.0 License. Aeronautical texts and regulations referenced remain the intellectual property of their respective publishing bodies (ICAO, EASA, FAA, ATSB, AAIB, NTSB, EUROCONTROL).
