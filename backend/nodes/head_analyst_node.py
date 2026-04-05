"""
Head Analyst Node — LLM synthesis with full context via Ollama.

Produces the final morning brief by feeding the LLM:
  - All scored setups (top picks)
  - Global market context
  - FII/DII flows
  - Evidence chains from all analysis nodes
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:HEAD_ANALYST] - %(message)s')

OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "llama3")


def head_analyst_node(state: dict) -> dict:
    """
    Generate LLM-powered synthesis of all trade recommendations.

    Reads:
      - top_picks, avoid_list
      - intraday_setups, options_setups
      - market_regime, vix, fii_net, dii_net
      - sector_leaders

    Writes:
      - head_analyst_brief: string (LLM-generated morning brief)
      - all_evidence: evidence entry for the LLM synthesis
    """
    top_picks = state.get("top_picks", [])
    intraday_setups = state.get("intraday_setups", [])
    options_setups = state.get("options_setups", [])
    market_regime = state.get("market_regime", "NEUTRAL")
    vix = state.get("vix", "N/A")
    fii_net = state.get("fii_net", "N/A")
    dii_net = state.get("dii_net", "N/A")
    sectors = state.get("sector_leaders", [])
    avoid_list = state.get("avoid_list", [])

    if not top_picks and not intraday_setups and not options_setups:
        logging.info("No setups to analyze — skipping LLM brief.")
        return {
            "head_analyst_brief": "No actionable setups identified today.",
            "all_evidence": [{
                "node": "head_analyst",
                "action": "skipped",
                "reason": "No setups to analyze",
            }],
        }

    logging.info("🧠 Generating Head Analyst brief via LLM...")

    # ── Build context for the LLM ────────────────────────────
    # Top equity setups
    equity_section = ""
    for setup in (intraday_setups or top_picks)[:5]:
        sym = setup.get("symbol", "???")
        sig_type = setup.get("signal_type", "NEUTRAL")
        conf = setup.get("confidence", 0)
        signals = setup.get("signals", [])
        trade_idea = setup.get("trade_idea", {})

        equity_section += f"\n{sym}: {sig_type} | Confidence: {conf}%"
        if signals:
            equity_section += f"\n  Signals: {', '.join(signals[:3])}"
        if trade_idea and trade_idea.get("entry"):
            equity_section += (
                f"\n  Entry: ₹{trade_idea['entry']} → Target: ₹{trade_idea.get('target')} "
                f"| SL: ₹{trade_idea.get('stoploss')} | R:R {trade_idea.get('risk_reward')}"
            )

    # Options setups
    options_section = ""
    for setup in (options_setups or [])[:3]:
        sym = setup.get("symbol", "???")
        action = setup.get("option_action", "???")
        conf = setup.get("confidence", 0)
        exp_move = setup.get("expected_move_pct", 0)
        options_section += f"\n{sym}: {action} | Confidence: {conf}% | Expected Move: ±{exp_move}%"

    # Sectors
    sector_list = ", ".join(f"{s['sector']} (₹{s['net_cr']}Cr)" for s in sectors[:3]) if sectors else "N/A"

    prompt = f"""You are a senior prop desk analyst writing the MORNING BRIEF for a retail trader.

MARKET CONDITIONS:
- Regime: {market_regime}
- India VIX: {vix}
- FII: {fii_net} | DII: {dii_net}
- Top Sectors by FII Flow: {sector_list}

EQUITY INTRADAY SETUPS (can go LONG or SHORT):
{equity_section if equity_section else "None today."}

OPTIONS SCALPING SETUPS (BUY CALL or BUY PUT only, max ₹50 per lot):
{options_section if options_section else "None today."}

AVOID LIST: {', '.join(avoid_list) if avoid_list else 'None'}

YOUR TASK:
1. Give a 2-sentence market bias summary
2. Pick your TOP 2 conviction trades (can be equity or options) with clear reasoning
3. For each trade: state direction, key trigger, and the #1 risk factor
4. If there are options plays, note the preferred strike approach (near OTM)
5. End with ONE sentence on what would invalidate today's thesis

Be direct. No pleasantries. Sound like a fast-paced trading desk. Max 200 words."""

    brief = None
    try:
        from openai import OpenAI
        client = OpenAI(base_url=OPENAI_API_BASE, api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a prop desk morning briefing analyst. Punchy. Actionable. No fluff."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )

        brief = response.choices[0].message.content.strip()
        usage = response.usage

        logging.info(f"\n{'─' * 60}")
        logging.info(f"📝 MORNING BRIEF:")
        logging.info(brief)
        logging.info(f"{'─' * 60}")

        if usage:
            logging.info(
                f"  LLM: {AI_MODEL} | Prompt: {usage.prompt_tokens} tokens | "
                f"Completion: {usage.completion_tokens} tokens"
            )

    except Exception as e:
        logging.warning(f"  LLM brief generation failed (graceful fallback): {e}")

        # Fallback: build a non-LLM summary
        top = (intraday_setups or top_picks)[:2]
        if top:
            names = ", ".join(t.get("symbol", "?") for t in top)
            brief = (
                f"Market Regime: {market_regime}. VIX: {vix}. "
                f"Top setups: {names}. "
                f"[LLM offline — review evidence chains manually]"
            )
        else:
            brief = f"Market Regime: {market_regime}. No high-conviction setups today. [LLM offline]"

    evidence = [{
        "node": "head_analyst",
        "model": AI_MODEL,
        "llm_available": brief is not None and "LLM offline" not in (brief or ""),
        "setups_analyzed": len(top_picks),
        "options_analyzed": len(options_setups or []),
    }]

    return {
        "head_analyst_brief": brief,
        "all_evidence": evidence,
    }
