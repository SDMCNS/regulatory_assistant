```python
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer


# ============================================================
# LOGGING
# ============================================================

def log(message: str) -> None:
    print(
        f"[{time.strftime('%H:%M:%S')}] {message}",
        flush=True,
    )


# ============================================================
# GPU INFORMATION
# ============================================================

def show_gpu_info() -> None:
    log("=" * 70)
    log("GPU INFORMATION")
    log("=" * 70)

    if not torch.cuda.is_available():
        log("ERROR: CUDA is not available.")
        log("This script requires an NVIDIA GPU.")
        raise RuntimeError("CUDA is not available.")

    device_count = torch.cuda.device_count()

    log(f"CUDA devices: {device_count}")

    for i in range(device_count):
        props = torch.cuda.get_device_properties(i)

        total_gb = props.total_memory / (1024 ** 3)

        log(
            f"GPU {i}: {props.name} "
            f"({total_gb:.1f} GB VRAM)"
        )

    log(
        f"PyTorch CUDA version: "
        f"{torch.version.cuda}"
    )

    log("")


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Train a QLoRA adapter for a regulatory language model."
    )

    parser.add_argument(
        "--model",
        required=True,
        help=(
            "Hugging Face model ID or local model path. "
            "Example: google/gemma-4-7b-it"
        ),
    )

    parser.add_argument(
        "--data",
        required=True,
        help="Directory containing train.jsonl and validation.jsonl",
    )

    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for the LoRA adapter",
    )

    parser.add_argument(
        "--epochs",
        type=float,
        default=1.0,
        help="Number of training epochs",
    )

    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="Learning rate",
    )

    parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        help="LoRA rank",
    )

    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="LoRA alpha",
    )

    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.05,
        help="LoRA dropout",
    )

    parser.add_argument(
        "--max-length",
        type=int,
        default=2048,
        help="Maximum sequence length",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Per-device training batch size",
    )

    parser.add_argument(
        "--gradient-accumulation",
        type=int,
        default=16,
        help="Gradient accumulation steps",
    )

    parser.add_argument(
        "--logging-steps",
        type=int,
        default=10,
        help="Log every N steps",
    )

    parser.add_argument(
        "--eval-steps",
        type=int,
        default=250,
        help="Run validation every N steps",
    )

    parser.add_argument(
        "--save-steps",
        type=int,
        default=250,
        help="Save checkpoint every N steps",
    )

    parser.add_argument(
        "--save-total-limit",
        type=int,
        default=2,
        help="Maximum number of checkpoints to keep",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the latest checkpoint",
    )

    parser.add_argument(
        "--max-train-samples",
        type=int,
        default=None,
        help=(
            "Optional limit for testing. "
            "Example: --max-train-samples 1000"
        ),
    )

    parser.add_argument(
        "--max-validation-samples",
        type=int,
        default=None,
        help="Optional validation sample limit",
    )

    return parser.parse_args()


# ============================================================
# DATASET
# ============================================================

def load_training_data(
    data_dir: Path,
    max_train_samples: int | None,
    max_validation_samples: int | None,
):

    train_path = data_dir / "train.jsonl"
    validation_path = data_dir / "validation.jsonl"

    if not train_path.exists():
        raise FileNotFoundError(
            f"Training file not found: {train_path}"
        )

    if not validation_path.exists():
        raise FileNotFoundError(
            f"Validation file not found: {validation_path}"
        )

    log("Loading training dataset...")
    log(f"  Train: {train_path}")
    log(f"  Validation: {validation_path}")

    dataset = load_dataset(
        "json",
        data_files={
            "train": str(train_path),
            "validation": str(validation_path),
        },
    )

    log(
        f"  Training examples: "
        f"{len(dataset['train']):,}"
    )

    log(
        f"  Validation examples: "
        f"{len(dataset['validation']):,}"
    )

    if max_train_samples:
        log(
            f"  Limiting training set to "
            f"{max_train_samples:,} examples"
        )

        dataset["train"] = dataset["train"].select(
            range(
                min(
                    max_train_samples,
                    len(dataset["train"]),
                )
            )
        )

    if max_validation_samples:
        log(
            f"  Limiting validation set to "
            f"{max_validation_samples:,} examples"
        )

        dataset["validation"] = dataset[
            "validation"
        ].select(
            range(
                min(
                    max_validation_samples,
                    len(dataset["validation"]),
                )
            )
        )

    log(
        f"  Final training examples: "
        f"{len(dataset['train']):,}"
    )

    log(
        f"  Final validation examples: "
        f"{len(dataset['validation']):,}"
    )

    return dataset


# ============================================================
# TOKENIZER
# ============================================================

def load_tokenizer(model_name: str):

    log("Loading tokenizer...")

    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        use_fast=True,
    )

    if tokenizer.pad_token is None:
        log(
            "Tokenizer has no pad token. "
            "Using EOS token as padding."
        )

        tokenizer.pad_token = tokenizer.eos_token

    log(
        f"  Vocabulary size: "
        f"{len(tokenizer):,}"
    )

    log(
        f"  EOS token: "
        f"{tokenizer.eos_token!r}"
    )

    log(
        f"  PAD token: "
        f"{tokenizer.pad_token!r}"
    )

    log("Tokenizer loaded.")
    log("")

    return tokenizer


# ============================================================
# QUANTISATION
# ============================================================

def create_quantisation_config():

    log("Configuring 4-bit QLoRA quantisation...")

    config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    log("  Quantisation: 4-bit NF4")
    log("  Double quantisation: enabled")
    log("  Compute dtype: float16")
    log("")

    return config


# ============================================================
# MODEL
# ============================================================

def load_model(
    model_name: str,
    quantisation_config,
):

    log("Loading base model...")
    log(f"  Model: {model_name}")
    log("  Loading in 4-bit...")
    log("")

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantisation_config,
        device_map="auto",
        torch_dtype=torch.float16,
    )

    model.config.use_cache = False

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    log("")
    log("Base model loaded.")

    if torch.cuda.is_available():

        allocated = (
            torch.cuda.memory_allocated()
            / (1024 ** 3)
        )

        reserved = (
            torch.cuda.memory_reserved()
            / (1024 ** 3)
        )

        log(
            f"  GPU memory allocated: "
            f"{allocated:.2f} GB"
        )

        log(
            f"  GPU memory reserved: "
            f"{reserved:.2f} GB"
        )

    log("")

    return model


# ============================================================
# LORA
# ============================================================

def create_lora_config(args):

    log("Configuring LoRA...")

    config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",

        # Apply LoRA to all linear layers.
        target_modules="all-linear",
    )

    log(f"  LoRA rank: {args.lora_r}")
    log(f"  LoRA alpha: {args.lora_alpha}")
    log(f"  LoRA dropout: {args.lora_dropout}")
    log("  Target modules: all linear layers")
    log("")

    return config


# ============================================================
# TRAINING CONFIG
# ============================================================

def create_training_config(
    args,
    output_dir: Path,
):

    log("Creating training configuration...")

    config = SFTConfig(
        output_dir=str(output_dir),

        num_train_epochs=args.epochs,

        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,

        gradient_accumulation_steps=(
            args.gradient_accumulation
        ),

        learning_rate=args.learning_rate,

        lr_scheduler_type="cosine",
        warmup_ratio=0.03,

        logging_strategy="steps",
        logging_steps=args.logging_steps,

        eval_strategy="steps",
        eval_steps=args.eval_steps,

        save_strategy="steps",
        save_steps=args.save_steps,

        save_total_limit=args.save_total_limit,

        max_length=args.max_length,

        fp16=True,

        gradient_checkpointing=True,

        optim="paged_adamw_8bit",

        report_to="none",

        dataset_num_proc=1,

        remove_unused_columns=False,

        packing=False,
    )

    log("  Epochs: %s", args.epochs)
    log(f"  Learning rate: {args.learning_rate}")
    log(f"  Batch size: {args.batch_size}")
    log(
        f"  Gradient accumulation: "
        f"{args.gradient_accumulation}"
    )
    log(f"  Effective batch size: "
        f"{args.batch_size * args.gradient_accumulation}"
    )
    log(f"  Max sequence length: {args.max_length}")
    log("  Optimizer: paged_adamw_8bit")
    log("  Gradient checkpointing: enabled")
    log("  FP16: enabled")
    log("")

    return config


# ============================================================
# CHECKPOINT
# ============================================================

def find_latest_checkpoint(
    output_dir: Path,
) -> Path | None:

    checkpoints = list(
        output_dir.glob("checkpoint-*")
    )

    if not checkpoints:
        return None

    checkpoints.sort(
        key=lambda p: int(
            p.name.split("-")[-1]
        )
    )

    return checkpoints[-1]


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.perf_counter()

    args = parse_args()

    data_dir = Path(args.data)
    output_dir = Path(args.out)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    log("=" * 70)
    log("REGULATORY QLoRA TRAINING")
    log("=" * 70)

    log(f"Base model: {args.model}")
    log(f"Dataset:    {data_dir.resolve()}")
    log(f"Output:     {output_dir.resolve()}")
    log("")

    # --------------------------------------------------------
    # GPU
    # --------------------------------------------------------

    show_gpu_info()

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    dataset = load_training_data(
        data_dir,
        args.max_train_samples,
        args.max_validation_samples,
    )

    log("")

    # --------------------------------------------------------
    # TOKENIZER
    # --------------------------------------------------------

    tokenizer = load_tokenizer(
        args.model
    )

    # --------------------------------------------------------
    # QUANTISATION
    # --------------------------------------------------------

    quantisation_config = (
        create_quantisation_config()
    )

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    model = load_model(
        args.model,
        quantisation_config,
    )

    # --------------------------------------------------------
    # LORA
    # --------------------------------------------------------

    lora_config = create_lora_config(args)

    # --------------------------------------------------------
    # TRAINING CONFIG
    # --------------------------------------------------------

    training_config = (
        create_training_config(
            args,
            output_dir,
        )
    )

    # --------------------------------------------------------
    # TRAINER
    # --------------------------------------------------------

    log("Creating SFTTrainer...")

    trainer = SFTTrainer(
        model=model,

        args=training_config,

        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],

        peft_config=lora_config,

        processing_class=tokenizer,
    )

    log("Trainer created.")
    log("")

    # --------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------

    checkpoint = None

    if args.resume:

        checkpoint = find_latest_checkpoint(
            output_dir
        )

        if checkpoint:

            log("=" * 70)
            log("RESUMING TRAINING")
            log("=" * 70)

            log(
                f"Checkpoint: {checkpoint}"
            )

            log("")

        else:

            log(
                "Resume requested but no "
                "checkpoint was found."
            )

            log(
                "Starting a new training run."
            )

            log("")

    else:

        log("=" * 70)
        log("STARTING TRAINING")
        log("=" * 70)
        log("")

    trainer.train(
        resume_from_checkpoint=checkpoint
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("TRAINING COMPLETE")
    log("=" * 70)

    log("Saving final LoRA adapter...")

    trainer.save_model(
        str(output_dir)
    )

    tokenizer.save_pretrained(
        str(output_dir)
    )

    log(
        f"Adapter saved to: "
        f"{output_dir.resolve()}"
    )

    # --------------------------------------------------------
    # GPU SUMMARY
    # --------------------------------------------------------

    if torch.cuda.is_available():

        torch.cuda.empty_cache()

        peak = (
            torch.cuda.max_memory_allocated()
            / (1024 ** 3)
        )

        log(
            f"Peak GPU memory allocated: "
            f"{peak:.2f} GB"
        )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    elapsed = (
        time.perf_counter()
        - start_time
    )

    log("")
    log("=" * 70)
    log("QLoRA TRAINING FINISHED")
    log("=" * 70)

    log(
        f"Training time: "
        f"{elapsed / 60:.1f} minutes"
    )

    log(
        f"Model: {args.model}"
    )

    log(
        f"Adapter: "
        f"{output_dir.resolve()}"
    )

    log("")
    log(
        "The base model has NOT been modified."
    )

    log(
        "The output directory contains "
        "the LoRA adapter."
    )

    log("=" * 70)


if __name__ == "__main__":
    main()
```