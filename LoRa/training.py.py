from datasets import load_dataset
from peft import LoraConfig
from trl import SFTConfig, SFTTrainer


MODEL = "YOUR_BASE_MODEL"

DATASET_PATH = r"C:\Projects\Regulation_assistant\training\regulatory_sft"

OUTPUT_DIR = r"C:\Projects\Regulation_assistant\models\regulatory-lora"


dataset = load_dataset(
    "json",
    data_files={
        "train": f"{DATASET_PATH}/train.jsonl",
        "validation": f"{DATASET_PATH}/validation.jsonl",
        "test": f"{DATASET_PATH}/test.jsonl",
    },
)


lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules="all-linear",
)


training_config = SFTConfig(
    output_dir=OUTPUT_DIR,

    num_train_epochs=1,

    per_device_train_batch_size=1,
    gradient_accumulation_steps=16,

    learning_rate=2e-4,

    logging_steps=10,
    eval_strategy="steps",
    eval_steps=500,

    save_strategy="steps",
    save_steps=500,

    save_total_limit=2,

    fp16=True,

    max_length=4096,

    report_to="none",
)


trainer = SFTTrainer(
    model=MODEL,
    args=training_config,

    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],

    peft_config=lora_config,
)


trainer.train()

trainer.save_model(OUTPUT_DIR)