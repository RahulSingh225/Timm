# backend/nodes/llm_hypothesis_generator_node.py
"""
LLM-GUIDED HYPOTHESIS GENERATOR NODE
Uses Qwen2.5 Coder 14B to generate creative trading strategy hypotheses.
Feeds them into the evolutionary_optimizer_node for mutation/evolution.

Phase 3.2 Enhancements:
  - RAG over evolved_strategies and llm_hypotheses tables
  - Feeds back top-performing formulas into LLM prompt
  - Fallback mode when Ollama is unavailable (cached hypotheses from DB)
  - Regime-aware hypothesis generation
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict
import psycopg2
from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")

def _get_conn():
    return psycopg2.connect(DB_URL)


def _init_llm():
    """Initialize LLM with graceful fallback."""
    try:
        from langchain_community.llms import Ollama
        return Ollama(
            model="qwen2.5-coder:14b",
            temperature=0.7,
            num_ctx=8192,
            base_url=os.getenv("OPENAI_API_BASE", "http://host.docker.internal:11434")
        )
    except Exception as e:
        logger.warning(f"Failed to initialize Ollama LLM: {e}")
        return None


def _load_top_strategies(limit: int = 15) -> List[Dict]:
    """RAG: Load top-performing evolved strategies from DB for context injection."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT expression, fitness, regime, source, generated_at
            FROM evolved_strategies
            ORDER BY generated_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        strategies = []
        for r in rows:
            fitness = r[1] if isinstance(r[1], dict) else json.loads(r[1]) if r[1] else {}
            strategies.append({
                "expression": r[0],
                "sharpe": fitness.get("sharpe", 0),
                "ic": fitness.get("ic", 0),
                "win_rate": fitness.get("win_rate", 0),
                "regime": r[2] or "ALL",
                "source": r[3] or "unknown",
            })
        return strategies
    except Exception as e:
        logger.warning(f"Could not load recent strategies: {e}")
        return []


def _load_cached_hypotheses(limit: int = 10) -> List[Dict]:
    """Fallback: Load previously generated hypotheses from DB when LLM is unavailable."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT hypothesis_id, name, description, logic, generated_at
            FROM llm_hypotheses
            ORDER BY generated_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [{
            "hypothesis_id": r[0],
            "name": r[1],
            "description": r[2],
            "logic": r[3],
            "generated_at": str(r[4]),
            "source": "cached_fallback",
        } for r in rows]
    except Exception:
        return []


def _build_rag_context(strategies: List[Dict]) -> str:
    """Build rich context string from top strategies for LLM prompt injection."""
    if not strategies:
        return "No previous strategies evolved yet — this is the first generation."

    lines = []
    for i, s in enumerate(strategies[:10]):
        lines.append(
            f"  {i+1}. [{s['source']}] Regime={s['regime']} | "
            f"Sharpe={s['sharpe']:.2f} IC={s['ic']:.3f} WR={s['win_rate']:.1%}\n"
            f"     Expression: {s['expression'][:120]}"
        )

    return "\n".join(lines)


def generate_hypotheses(state: TradingState, llm, num_hypotheses: int = 8) -> List[Dict]:
    """Use Qwen to generate fresh strategy hypotheses with RAG context."""

    # RAG: Load top strategies for context
    top_strategies = _load_top_strategies(limit=15)
    rag_context = _build_rag_context(top_strategies)

    # Regime context
    detected_regime = state.get("detected_regime", {})
    regime_label = detected_regime.get("regime_label", "UNKNOWN")
    regime_confidence = detected_regime.get("confidence", 0)

    # Volatility context
    vol_forecast = state.get("volatility_forecast", {})
    vol_regime = vol_forecast.get("vol_regime", "UNKNOWN")
    iv_signal = vol_forecast.get("iv_signal", "UNKNOWN")

    prompt = f"""You are an elite quant researcher working on NIFTY intraday and options trading.

CURRENT MARKET STATE:
- HMM Regime: {regime_label} (confidence: {regime_confidence:.0%})
- Volatility Regime: {vol_regime} | IV Signal: {iv_signal}
- Latest candle vector summary: {state.get('latest_candle_vector_summary', 'Neutral')}
- Market sentiment: {state.get('sentiment_summary', 'Mixed')}

TOP PERFORMING EVOLVED STRATEGIES (from GP/PySR evolution):
{rag_context}

AVAILABLE FEATURES for strategy construction:
  candle_scalar, iv_adjusted_scalar, rsi, volume_zscore, vwap_deviation,
  regime_id (0=TrendBull, 1=TrendBear, 2=MeanRev, 3=HighVol),
  atr_14, adx_14, macd_signal, obv_slope, returns_1d, returns_5d

Generate {num_hypotheses} diverse, creative trading strategy hypotheses.
Each must:
1. Be regime-aware (specify which regime it works best in)
2. Combine at least 3 features in a novel way
3. Include specific entry/exit thresholds
4. Address the CURRENT regime ({regime_label}) — at least 3 hypotheses should be optimized for it
5. Be different from the top strategies shown above — propose MUTATIONS or entirely new ideas

Output ONLY valid JSON array:
[
  {{
    "hypothesis_id": "HYP_001",
    "name": "Short but descriptive name",
    "description": "One sentence describing the edge",
    "logic": "if (condition) then BUY/SELL with specific thresholds",
    "target_regime": "{regime_label}",
    "expected_sharpe": 0.5,
    "risk_rules": "SL at X, position size Y%"
  }}
]
"""

    try:
        response = llm.invoke(prompt)
        import re
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        hypotheses = json.loads(json_match.group(0)) if json_match else []
        logger.info(f"✅ Generated {len(hypotheses)} new hypotheses from LLM")
        return hypotheses
    except Exception as e:
        logger.error(f"LLM hypothesis generation failed: {e}")
        return []


def llm_hypothesis_generator_node(state: TradingState) -> TradingState:
    """
    Main LangGraph node — with RAG context and fallback mode.
    Run BEFORE evolutionary_optimizer_node in the training graph.
    """
    logger.info("🧠 LLM Hypothesis Generator started...")

    # Initialize LLM
    llm = _init_llm()

    new_hypotheses = []

    if llm is not None:
        # Primary path: Generate new hypotheses via LLM
        new_hypotheses = generate_hypotheses(state, llm, num_hypotheses=8)

    if not new_hypotheses:
        # Fallback: Use cached hypotheses from previous runs
        logger.info("⚡ LLM unavailable — loading cached hypotheses from DB...")
        new_hypotheses = _load_cached_hypotheses(limit=10)

        if new_hypotheses:
            logger.info(f"  Loaded {len(new_hypotheses)} cached hypotheses as fallback")
        else:
            logger.warning("  No cached hypotheses available either — evolution will run without LLM seeding")

    # Store in state for evolutionary node
    state['llm_generated_hypotheses'] = new_hypotheses

    # Persist new hypotheses to DB for future RAG
    if new_hypotheses and not any(h.get("source") == "cached_fallback" for h in new_hypotheses):
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_hypotheses (
                    hypothesis_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255),
                    description TEXT,
                    logic TEXT,
                    target_regime VARCHAR(50),
                    generated_at TIMESTAMP
                )
            """)
            for hyp in new_hypotheses:
                cur.execute("""
                    INSERT INTO llm_hypotheses (hypothesis_id, name, description, logic, target_regime, generated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hypothesis_id) DO NOTHING
                """, (
                    str(hyp.get("hypothesis_id", f"HYP_{datetime.utcnow().timestamp()}")),
                    str(hyp.get("name", "")),
                    str(hyp.get("description", "")),
                    str(hyp.get("logic", "")),
                    str(hyp.get("target_regime", "ALL")),
                    datetime.utcnow()
                ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist hypotheses to DB: {e}")

    logger.info(f"✅ Injected {len(new_hypotheses)} LLM hypotheses into evolution pipeline.")
    return state