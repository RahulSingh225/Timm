# backend/llm_finetuning.py
"""
LLM FINE-TUNING MODULE (Phase 9.1)
LoRA fine-tuning on trade journal data for domain-adapted analysis:
  - Extracts training pairs from learning_history and head analyst briefs
  - Generates instruction-tuning dataset (alpaca format)
  - LoRA adapter training via PEFT/Unsloth
  - Evaluation on held-out trade analysis tasks
"""

import os
import json
import logging
import psycopg2
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
DB_URL = os.getenv("DATABASE_URL")
DATASET_PATH = "data/finetune_dataset.jsonl"
ADAPTER_PATH = "models/llm_lora_adapter"


def _get_conn():
    return psycopg2.connect(DB_URL)


def extract_training_pairs() -> List[Dict]:
    """Extract instruction-response pairs from historical trade journal."""
    pairs = []

    try:
        conn = _get_conn()

        # 1. Head analyst briefs → analysis pairs
        df_reports = pd.read_sql("""
            SELECT report_date, market_regime, vix, fii_net, dii_net,
                   head_analyst_brief, top_picks, avoid_list
            FROM daily_reports
            WHERE head_analyst_brief IS NOT NULL
            ORDER BY report_date DESC LIMIT 500
        """, conn)

        for _, row in df_reports.iterrows():
            instruction = (
                f"Analyze the market for {row['report_date']}. "
                f"Market regime: {row['market_regime']}, VIX: {row['vix']}, "
                f"FII Net: {row['fii_net']}, DII Net: {row['dii_net']}. "
                f"Provide a head analyst brief with top picks and stocks to avoid."
            )
            response = f"{row['head_analyst_brief']}\n\nTop Picks: {row['top_picks']}\nAvoid: {row['avoid_list']}"
            pairs.append({"instruction": instruction, "input": "", "output": response})

        # 2. Trade outcomes → learning pairs
        df_trades = pd.read_sql("""
            SELECT lh.trade_date, lh.signal_type, lh.predicted_direction,
                   lh.was_correct, lh.actual_pnl_pct, lh.trade_type
            FROM learning_history lh
            WHERE lh.actual_pnl_pct IS NOT NULL
            ORDER BY lh.trade_date DESC LIMIT 2000
        """, conn)

        for _, row in df_trades.iterrows():
            instruction = (
                f"A {row['signal_type']} signal predicted {row['predicted_direction']} "
                f"for a {row['trade_type']} trade on {row['trade_date']}. "
                f"The outcome was {'correct' if row['was_correct'] else 'incorrect'} "
                f"with {row['actual_pnl_pct']:.2f}% PnL. "
                f"Explain what this tells us about the reliability of this signal."
            )
            outcome = "winning" if row['was_correct'] else "losing"
            response = (
                f"The {row['signal_type']} signal generated a {outcome} trade. "
                f"{'This signal shows edge in identifying ' + row['predicted_direction'].lower() + ' setups.' if row['was_correct'] else 'This signal may be unreliable in current market conditions. Consider reducing position size or requiring additional confirmation.'} "
                f"PnL impact: {row['actual_pnl_pct']:+.2f}%. "
                f"{'Increase weight for this signal type.' if row['was_correct'] else 'Decrease weight and add filters.'}"
            )
            pairs.append({"instruction": instruction, "input": "", "output": response})

        # 3. Strategy evaluation pairs
        df_strategies = pd.read_sql("""
            SELECT sw.signal_type, sw.base_weight, sw.win_count, sw.loss_count
            FROM strategy_weights sw
            WHERE sw.profile = 'production'
        """, conn)

        for _, row in df_strategies.iterrows():
            total = row['win_count'] + row['loss_count']
            if total < 5:
                continue
            wr = row['win_count'] / total
            instruction = (
                f"Evaluate the {row['signal_type']} strategy. "
                f"Win rate: {wr:.1%}, weight: {row['base_weight']:.2f}, "
                f"total trades: {total}."
            )
            response = (
                f"Strategy {row['signal_type']}: {wr:.1%} win rate over {total} trades. "
                f"{'Strong performer — maintain or increase allocation.' if wr > 0.55 else 'Weak performer — reduce allocation and investigate edge decay.' if wr < 0.45 else 'Marginal edge — monitor closely.'} "
                f"Current weight: {row['base_weight']:.2f}."
            )
            pairs.append({"instruction": instruction, "input": "", "output": response})

        conn.close()

    except Exception as e:
        logger.error(f"Failed to extract training pairs: {e}")

    return pairs


def save_dataset(pairs: List[Dict], output_path: str = DATASET_PATH):
    """Save as JSONL (alpaca format) for LoRA training."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    logger.info(f"💾 Saved {len(pairs)} training pairs to {output_path}")


def train_lora_adapter(
    base_model: str = "unsloth/llama-3.2-3b-instruct",
    dataset_path: str = DATASET_PATH,
    output_dir: str = ADAPTER_PATH,
    epochs: int = 3,
    lr: float = 2e-4,
    rank: int = 16,
    lora_alpha: int = 32,
    max_seq_length: int = 2048,
):
    """Train a LoRA adapter on the trade journal dataset."""
    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError:
        logger.error("❌ unsloth/trl not installed. Install with: pip install unsloth trl")
        return False

    logger.info(f"🧠 Starting LoRA fine-tuning...")
    logger.info(f"   Base model: {base_model}")
    logger.info(f"   Dataset: {dataset_path}")
    logger.info(f"   Rank: {rank}, Alpha: {lora_alpha}")

    # Load model with 4-bit quantization
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )

    # Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=rank,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # Load dataset
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    # Format prompt
    alpaca_prompt = """Below is an instruction that describes a task. Write a response.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

    def format_prompts(examples):
        texts = []
        for i in range(len(examples["instruction"])):
            text = alpaca_prompt.format(
                instruction=examples["instruction"][i],
                input=examples["input"][i],
                output=examples["output"][i],
            )
            texts.append(text + tokenizer.eos_token)
        return {"text": texts}

    dataset = dataset.map(format_prompts, batched=True)

    # Training
    os.makedirs(output_dir, exist_ok=True)
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        args=TrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            num_train_epochs=epochs,
            learning_rate=lr,
            fp16=True,
            logging_steps=10,
            save_strategy="epoch",
            optim="adamw_8bit",
        ),
    )

    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    logger.info(f"✅ LoRA adapter saved to {output_dir}")

    return True


def generate_dataset():
    """Extract and save the fine-tuning dataset."""
    pairs = extract_training_pairs()
    if pairs:
        save_dataset(pairs)
        logger.info(f"Generated {len(pairs)} training pairs")
    else:
        logger.warning("No training pairs extracted")
    return pairs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-only", action="store_true", help="Only extract dataset")
    parser.add_argument("--train", action="store_true", help="Train LoRA adapter")
    parser.add_argument("--base-model", default="unsloth/llama-3.2-3b-instruct")
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()

    if args.extract_only or not args.train:
        generate_dataset()

    if args.train:
        if not os.path.exists(DATASET_PATH):
            generate_dataset()
        train_lora_adapter(base_model=args.base_model, epochs=args.epochs)
