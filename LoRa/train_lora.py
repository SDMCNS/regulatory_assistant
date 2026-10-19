#!/usr/bin/env python3
"""
Aviation LoRA QLoRA Fine-Tuning Pipeline
=========================================
Trains a parameter-efficient QLoRA adapter on aviation regulatory & operations Q&A datasets.
Designed for NVIDIA GPUs (e.g. RTX 5060 Ti / RTX 4090 / A100) using 4-bit NormalFloat (NF4) quantization.

Features:
- Compatible with Hugging Face AutoModelForCausalLM / google/gemma-4-E4B-it.
- Supports chat-formatted datasets (OpenAI/ChatML messages format: system, user, assistant).
- 4-bit BitsAndBytes quantization with bfloat16 / float16 compute.
- Paged AdamW 8-bit optimizer to eliminate VRAM fragmentation.
- Gradient checkpointing for memory efficiency.
- Auto checkpoint recovery / resume.
- Adapter saving + tokenizer saving.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer

# ==============================================================================
# LOGGING
# ==============================================================================

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def show_gpu_info() -> None:
    log("=" * 70)
    log("GPU & HARDWARE ENVIRONMENT")
    log("=" * 70)
    if not torch.cuda.is_available():
        log("ERROR: CUDA is not available. An NVIDIA GPU with CUDA is required for QLoRA.")
        raise RuntimeError("CUDA is not available.")

    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        vram = props.total_memory / (1024 ** 3)
        log(f"Device {i}: {props.name} | Total VRAM: {vram:.2f} GB")

    log(f"PyTorch Version: {torch.__version__} | CUDA Version: {torch.version.cuda}")
    log("")


def prepare_kbit_model_safe(model: torch.nn.Module) -> torch.nn.Module:
    """
    Safely prepares a 4-bit quantized model for LoRA fine-tuning without
    upcasting massive non-quantized layers (such as Gemma-4's 5.4 GB embedding table)
    from bfloat16 to float32. Standard PEFT prepare_model_for_kbit_training blindly
    casts all non-4bit parameters to fp32, which doubles embedding memory and
    causes VRAM usage to exceed 21 GB on a 16 GB GPU, crashing Windows.
    """
    for param in model.parameters():
        param.requires_grad = False

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    else:
        def make_inputs_require_grad(module, input, output):
            output.requires_grad_(True)
        model.get_input_embeddings().register_forward_hook(make_inputs_require_grad)

    return model

# ==============================================================================
# CLI ARGUMENTS
# ==============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a QLoRA adapter for Aviation Regulatory Assistant (e.g. google/gemma-4-E4B-it)"
    )

    parser.add_argument(
        "--model",
        type=str,
        default="google/gemma-4-E4B-it",
        help="Hugging Face model ID or local directory containing weights. Default: google/gemma-4-E4B-it"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="dataset_splits",
        help="Directory containing train.jsonl and validation.jsonl"
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="models/aviation-gemma-lora",
        help="Destination directory for the saved LoRA adapter"
    )
    parser.add_argument(
        "--epochs",
        type=float,
        default=1.0,
        help="Number of training epochs (default: 1.0)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Per-device training batch size (default: 1 for 16GB VRAM)"
    )
    parser.add_argument(
        "--gradient-accumulation",
        type=int,
        default=16,
        help="Gradient accumulation steps (effective batch size = batch_size * grad_acc)"
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="Initial learning rate with cosine decay (default: 2e-4)"
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=2048,
        help="Maximum token sequence length (default: 2048)"
    )
    parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        help="LoRA rank dimension (default: 16)"
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="LoRA scaling factor alpha (default: 32)"
    )
    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.05,
        help="LoRA dropout rate (default: 0.05)"
    )
    parser.add_argument(
        "--logging-steps",
        type=int,
        default=10,
        help="Log metrics every N steps"
    )
    parser.add_argument(
        "--eval-steps",
        type=int,
        default=100,
        help="Run validation evaluation every N steps"
    )
    parser.add_argument(
        "--save-steps",
        type=int,
        default=200,
        help="Save intermediate checkpoint every N steps"
    )
    parser.add_argument(
        "--save-total-limit",
        type=int,
        default=2,
        help="Maximum checkpoints retained"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the latest available checkpoint in --out-dir"
    )
    parser.add_argument(
        "--max-train-samples",
        type=int,
        default=None,
        help="Cap training samples (useful for dry runs)"
    )
    parser.add_argument(
        "--max-eval-samples",
        type=int,
        default=None,
        help="Cap validation samples"
    )

    return parser.parse_args()

# ==============================================================================
# DATASET LOADING & FORMATTING
# ==============================================================================

def load_training_dataset(data_dir: Path, max_train: Optional[int], max_eval: Optional[int]):
    train_file = data_dir / "train.jsonl"
    val_file = data_dir / "validation.jsonl"

    if not train_file.exists():
        raise FileNotFoundError(f"Training dataset not found: {train_file}")

    data_files = {"train": str(train_file)}
    if val_file.exists():
        data_files["validation"] = str(val_file)

    log(f"Loading dataset from: {data_dir.resolve()}...")
    raw_dataset = load_dataset("json", data_files=data_files)

    train_data = raw_dataset["train"]
    if max_train and len(train_data) > max_train:
        train_data = train_data.select(range(max_train))

    val_data = None
    if "validation" in raw_dataset:
        val_data = raw_dataset["validation"]
        if max_eval and len(val_data) > max_eval:
            val_data = val_data.select(range(max_eval))

    log(f"  Training samples:   {len(train_data):,}")
    log(f"  Validation samples: {len(val_data):,}" if val_data else "  Validation samples: None")
    return train_data, val_data

# ==============================================================================
# MAIN TRAINING WORKFLOW
# ==============================================================================

def main():
    args = parse_args()
    start_time = time.perf_counter()

    log("=" * 70)
    log("AVIATION REGULATORY QLoRA TRAINING")
    log("=" * 70)
    log(f"Base Model:  {args.model}")
    log(f"Data Dir:    {Path(args.data_dir).resolve()}")
    log(f"Output Dir:  {Path(args.out_dir).resolve()}")
    log("")

    show_gpu_info()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Dataset
    train_dataset, eval_dataset = load_training_dataset(
        Path(args.data_dir),
        args.max_train_samples,
        args.max_eval_samples
    )

    # 2. Tokenizer
    log("Loading Tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        trust_remote_code=True,
        use_fast=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        log("Assigned tokenizer.eos_token to pad_token.")

    # 3. 4-bit Quantization Configuration
    log("Configuring 4-bit NF4 Quantization (QLoRA)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # 4. Base Model
    log(f"Loading Base Model ({args.model}) in 4-bit...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )
    model.config.use_cache = False

    # Prepare for k-bit training safely without ballooning frozen embeddings to fp32
    model = prepare_kbit_model_safe(model)

    # 5. LoRA Adapter Configuration
    log("Configuring LoRA Adapter...")
    # For multimodal Gemma-4 models, target only language_model layers to avoid
    # custom ClippableLinear layers in vision/audio towers which PEFT does not support.
    if "gemma-4" in args.model.lower():
        target_modules = r".*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)"
        exclude_modules = r".*(vision_tower|audio_tower).*"
    else:
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        exclude_modules = None

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_modules,
        exclude_modules=exclude_modules
    )

    log("Applying LoRA adapter to model...")
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 6. SFT Training Configuration
    compute_dtype = "bf16" if torch.cuda.is_bf16_supported() else "fp16"
    log(f"Compute precision: {compute_dtype.upper()}")

    training_config = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_strategy="steps",
        logging_steps=args.logging_steps,
        eval_strategy="steps" if eval_dataset else "no",
        eval_steps=args.eval_steps if eval_dataset else None,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=args.save_total_limit,
        max_length=args.max_length,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to="none",
        loss_type="nll",
        dataset_num_proc=None,
        packing=False
    )

    # 7. SFT Trainer
    log("Initializing SFTTrainer...")
    trainer = SFTTrainer(
        model=model,
        args=training_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    # 8. Resume / Train
    checkpoint = None
    if args.resume:
        checkpoints = sorted(out_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[-1]))
        if checkpoints:
            checkpoint = str(checkpoints[-1])
            log(f"Resuming training from checkpoint: {checkpoint}")

    log("=" * 70)
    log("LAUNCHING TRAINING LOOP")
    log("=" * 70)
    trainer.train(resume_from_checkpoint=checkpoint)

    # 9. Save LoRA Adapter & Tokenizer
    log("")
    log("Training completed! Saving LoRA adapter...")
    trainer.model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    log(f"LoRA adapter and tokenizer saved to: {out_dir.resolve()}")

    # 10. Summary
    if torch.cuda.is_available():
        peak_vram = torch.cuda.max_memory_allocated() / (1024 ** 3)
        log(f"Peak GPU VRAM Allocated: {peak_vram:.2f} GB")

    elapsed = time.perf_counter() - start_time
    log(f"Total time elapsed: {elapsed / 60:.2f} minutes")
    log("=" * 70)

if __name__ == "__main__":
    main()
