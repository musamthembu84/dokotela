"""
Fine-tuning ClinicalBERT locally in Python using Hugging Face Transformers.

Use case:
- Binary classification of medical text (e.g., urgent vs non-urgent)
- Model: emilyalsentzer/Bio_ClinicalBERT

Install dependencies:
    pip install transformers datasets torch scikit-learn pandas

Expected CSV format (train.csv and valid.csv):
    text,label
    "Patient has chest pain and shortness of breath",1
    "Mild headache for two days",0
"""

from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
import numpy as np

# -------------------------------------------------------------------
# 1. Configuration
# -------------------------------------------------------------------
MODEL_NAME = "emilyalsentzer/Bio_ClinicalBERT"
NUM_LABELS = 2
MAX_LENGTH = 256

TRAIN_FILE = "train.csv"
VALID_FILE = "valid.csv"

OUTPUT_DIR = "./clinicalbert-finetuned"

# -------------------------------------------------------------------
# 2. Load dataset from local CSV files
# -------------------------------------------------------------------
dataset = load_dataset(
    "csv",
    data_files={
        "train": TRAIN_FILE,
        "validation": VALID_FILE,
    }
)

# -------------------------------------------------------------------
# 3. Load tokenizer
# -------------------------------------------------------------------
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# -------------------------------------------------------------------
# 4. Tokenization function
# -------------------------------------------------------------------
def tokenize_function(examples):
    return tokenizer(
        examples["text"],
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
    )

tokenized_datasets = dataset.map(
    tokenize_function,
    batched=True
)

# Rename label column if needed
tokenized_datasets = tokenized_datasets.rename_column("label", "labels")

# Set PyTorch format
tokenized_datasets.set_format(
    type="torch",
    columns=["input_ids", "attention_mask", "labels"]
)

# -------------------------------------------------------------------
# 5. Load pre-trained ClinicalBERT model
# -------------------------------------------------------------------
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=NUM_LABELS
)

# -------------------------------------------------------------------
# 6. Metrics
# -------------------------------------------------------------------
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)

    precision, recall, f1, _ = precision_recall_fscore_support(
        labels,
        predictions,
        average="binary"
    )

    acc = accuracy_score(labels, predictions)

    return {
        "accuracy": acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }

# -------------------------------------------------------------------
# 7. Training configuration
# -------------------------------------------------------------------
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    eval_strategy="epoch",
    save_strategy="epoch",
    logging_strategy="steps",
    logging_steps=50,
    learning_rate=2e-5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    num_train_epochs=3,
    weight_decay=0.01,
    load_best_model_at_end=True,
    metric_for_best_model="f1",
    greater_is_better=True,
    save_total_limit=2,
    fp16=False,
    report_to="none",
)

# -------------------------------------------------------------------
# 8. Trainer
# -------------------------------------------------------------------
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets["train"],
    eval_dataset=tokenized_datasets["validation"],
    tokenizer=tokenizer,
    compute_metrics=compute_metrics,
)

# -------------------------------------------------------------------
# 9. Train
# -------------------------------------------------------------------
trainer.train()

# -------------------------------------------------------------------
# 10. Evaluate
# -------------------------------------------------------------------
results = trainer.evaluate()
print("Evaluation Results:")
print(results)

# -------------------------------------------------------------------
# 11. Save model and tokenizer locally
# -------------------------------------------------------------------
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"Model saved to: {OUTPUT_DIR}")

# -------------------------------------------------------------------
# 12. Local inference example
# -------------------------------------------------------------------
from transformers import pipeline

classifier = pipeline(
    "text-classification",
    model=OUTPUT_DIR,
    tokenizer=OUTPUT_DIR
)

sample_text = """
The patient reports severe chest pain radiating to the left arm,
shortness of breath, and nausea.
"""

prediction = classifier(sample_text)
print("Prediction:", prediction)