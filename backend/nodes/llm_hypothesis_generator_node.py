# backend/nodes/llm_hypothesis_generator_node.py
"""
LLM-GUIDED HYPOTHESIS GENERATOR NODE
Uses Qwen2.5 Coder 14B to generate creative trading strategy hypotheses.
Feeds them into the evolutionary_optimizer_node for mutation/evolution.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict
from langchain_community.llms import Ollama  # or your existing Qwen setup
from ..state import TimmState
from ..database import SessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Configure your local Qwen2.5 Coder 14B
llm = Ollama(
    model="qwen2.5-coder:14b",
    temperature=0.7,
    num_ctx=8192,
    base_url="http://localhost:11434"  # adjust if needed
)

def generate_hypotheses(state: TimmState, num_hypotheses: int = 8) -> List[Dict]:
    """Use Qwen to generate fresh strategy hypotheses"""
    
    # Pull recent context from your DB / state
    with SessionLocal() as db:
        recent = db.execute(text("""
            SELECT expression, fitness, generated_at 
            FROM evolved_strategies 
            ORDER BY generated_at DESC LIMIT 15
        """)).fetchall()
    
    recent_strats = "\n".join([f"- {r[0]} (Sharpe: {r[1].get('sharpe',0):.2f})" for r in recent]) if recent else "No previous strategies yet."

    prompt = f"""
You are an elite quant researcher working on NIFTY intraday and options trading.

Current market context:
- Latest candle vector signals: {state.get('latest_candle_vector_summary', 'Neutral')}
- Recent sentiment & global cues: {state.get('sentiment_summary', 'Mixed')}
- Top performing evolved strategies so far:
{recent_strats}

Generate {num_hypotheses} diverse, creative, and actionable trading strategy hypotheses.
Each hypothesis must:
1. Combine candle_vector (raw_scalar + iv_adjusted_scalar), IV regime, RSI, volume, and sector trends.
2. Be specific enough to be turned into a GP expression or rule.
3. Include entry/exit logic and risk management.
4. Be different from previous strategies.

Output ONLY valid JSON array:
[
  {{
    "hypothesis_id": "HYP_001",
    "name": "Short name",
    "description": "One sentence",
    "logic": "if (iv_adjusted_scalar > 0.7 AND rsi < 40) then ...",
    "expected_regime": "high_iv_trending | low_iv_mean_reverting | etc",
    "risk_rules": "..."
  }}
]
"""

    try:
        response = llm.invoke(prompt)
        # Extract JSON (Qwen is usually good at this)
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        hypotheses = json.loads(json_match.group(0)) if json_match else []
        logger.info(f"✅ Generated {len(hypotheses)} new hypotheses from Qwen2.5")
        return hypotheses
    except Exception as e:
        logger.error(f"LLM hypothesis generation failed: {e}")
        return []


def llm_hypothesis_generator_node(state: TimmState) -> TimmState:
    """
    Main LangGraph node.
    Run this BEFORE evolutionary_optimizer_node in your graph.
    """
    logger.info("🧠 LLM Hypothesis Generator started...")

    new_hypotheses = generate_hypotheses(state, num_hypotheses=8)
    
    # Store in state so evolutionary node can seed them
    state.llm_generated_hypotheses = new_hypotheses
    
    # Optional: persist to DB for RAG and historical analysis
    with SessionLocal() as db:
        for hyp in new_hypotheses:
            db.execute(text("""
                INSERT INTO llm_hypotheses (hypothesis_id, name, description, logic, generated_at)
                VALUES (:hypothesis_id, :name, :description, :logic, :generated_at)
            """), {
                **hyp,
                "generated_at": datetime.utcnow().isoformat()
            })
        db.commit()

    logger.info(f"✅ Injected {len(new_hypotheses)} LLM hypotheses into evolution pipeline.")
    return state