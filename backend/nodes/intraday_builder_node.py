"""
Intraday Builder Node — Builds equity intraday setups (LONG or SHORT).

Takes the screener's scored setups and constructs complete trade plans
with entry/SL/target, evidence chains, and direction logic.
"""

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:INTRADAY_BUILDER] - %(message)s')


def intraday_builder_node(state: dict) -> dict:
    """
    Build structured intraday equity trade setups.

    Rules:
      - Can go LONG or SHORT
      - Entry/SL/Target from swing TA (ATR-based)
      - Minimum confidence: 40%
      - Includes full evidence chain for justification

    Reads:
      - top_picks: scored setups from screener
      - strategy_weights: for evidence annotation

    Writes:
      - intraday_setups: list of trade setup dicts
      - all_evidence: evidence entries
    """
    top_picks = state.get("top_picks", [])
    weights = state.get("strategy_weights", {})

    logging.info(f"📈 Building intraday equity setups from {len(top_picks)} scored symbols...")

    setups = []
    evidence = []

    for setup in top_picks:
        confidence = setup.get("confidence", 0)
        signal_type = setup.get("signal_type", "NEUTRAL")

        # Skip neutral or low-confidence
        if signal_type == "NEUTRAL" or confidence < 40:
            continue

        symbol = setup["symbol"]
        trade_idea = setup.get("trade_idea")
        trend = setup.get("trend", {})

        # Determine direction
        if signal_type == "BULLISH":
            direction = "LONG"
        elif signal_type == "BEARISH":
            direction = "SHORT"
        else:
            continue

        # Build evidence chain for this trade
        trade_evidence = []
        trade_evidence.append(f"Direction: {direction} based on {signal_type} signal confluence")
        trade_evidence.append(f"Trend: Daily={trend.get('daily')}, Micro={trend.get('micro')}, "
                              f"Alignment={trend.get('alignment')}")

        # Signals breakdown
        for sig in setup.get("signals", []):
            trade_evidence.append(f"Signal: {sig}")

        # Confidence breakdown
        breakdown = setup.get("confidence_breakdown", {})
        if breakdown:
            trade_evidence.append(
                f"Confidence: {confidence}% "
                f"(base={breakdown.get('base_signals')}, "
                f"weight_adj={breakdown.get('weight_adjusted')}, "
                f"alignment={breakdown.get('alignment_bonus')}, "
                f"confluence={breakdown.get('confluence_bonus')}, "
                f"regime={breakdown.get('regime_bonus')})"
            )

        # Options context if available
        opt = setup.get("options_data")
        if opt:
            trade_evidence.append(
                f"Options: {opt.get('verdict')} | Max Pain: ₹{opt.get('max_pain')} | "
                f"Expected Move: ±{opt.get('expected_move_pct')}%"
            )

        # Vector context if available
        vec = setup.get("vector_data")
        if vec:
            trade_evidence.append(
                f"Vector: {vec.get('classification')} | "
                f"Predicted: {vec.get('predicted_next_move_pct', 0):+.2f}%"
            )

        # Learned weight context
        used_signals = setup.get("signal_types", [])
        for sig_type in used_signals:
            w = weights.get(sig_type)
            if w and w.get("sample_size", 0) > 5:
                trade_evidence.append(
                    f"History: {sig_type} has {w['win_rate']:.0%} win rate "
                    f"over {w['sample_size']} trades (weight={w['weight']:.2f})"
                )

        intraday_setup = {
            "symbol": symbol,
            "trade_type": f"INTRADAY_{direction}",
            "direction": direction,
            "close_price": setup.get("close_price"),
            "entry": trade_idea.get("entry") if trade_idea else setup.get("close_price"),
            "stoploss": trade_idea.get("stoploss") if trade_idea else None,
            "target": trade_idea.get("target") if trade_idea else None,
            "risk_reward": trade_idea.get("risk_reward") if trade_idea else None,
            "confidence": confidence,
            "signal_type": signal_type,
            "signals": setup.get("signals", []),
            "signal_types": used_signals,
            "move_potential_pct": setup.get("move_potential_pct"),
            "support_resistance": setup.get("support_resistance"),
            "evidence": trade_evidence,
            "confidence_breakdown": breakdown,
        }

        setups.append(intraday_setup)

    # Sort by confidence
    setups.sort(key=lambda x: x["confidence"], reverse=True)

    logging.info(f"  Built {len(setups)} intraday setups:")
    for s in setups[:5]:
        logging.info(
            f"    {'🟢' if s['direction'] == 'LONG' else '🔴'} {s['symbol']}: "
            f"{s['direction']} | {s['confidence']}% | "
            f"Entry: ₹{s.get('entry')} → Target: ₹{s.get('target')} | SL: ₹{s.get('stoploss')}"
        )

    evidence.append({
        "node": "intraday_builder",
        "total_setups": len(setups),
        "long_count": sum(1 for s in setups if s["direction"] == "LONG"),
        "short_count": sum(1 for s in setups if s["direction"] == "SHORT"),
    })

    return {
        "intraday_setups": setups,
        "all_evidence": evidence,
    }
