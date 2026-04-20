"""
Screener / Confluence Node — Combines all analyses + applies learned weights.

This is the critical synthesis node that takes raw analysis from swing TA,
options, and vector analysis, then scores each symbol using:
  1. Number and type of signals detected
  2. Learned strategy weights (from past performance)
  3. Market regime context
  4. Cross-analysis agreement (confluence)
"""

import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:SCREENER] - %(message)s')


# Signal type extraction patterns
SIGNAL_TYPE_PATTERNS = {
    "GOLDEN_CROSS": r"GOLDEN CROSS",
    "DEATH_CROSS": r"DEATH CROSS",
    "EMA_RECLAIM": r"EMA RECLAIM",
    "FAST_EMA_CROSS_BULL": r"FAST EMA CROSS.*Bullish",
    "FAST_EMA_CROSS_BEAR": r"FAST EMA CROSS.*Bearish",
    "RSI_BOUNCE": r"RSI BOUNCE",
    "RSI_MOMENTUM": r"RSI MOMENTUM",
    "RSI_OVERBOUGHT": r"RSI OVERBOUGHT",
    "MACD_BULLISH": r"MACD BULLISH",
    "MACD_BEARISH": r"MACD BEARISH",
    "BB_SQUEEZE": r"BB SQUEEZE",
    "BB_REVERSAL": r"BB REVERSAL",
    "BB_BREAKOUT": r"BB BREAKOUT",
    "VOLUME_SPIKE": r"VOLUME SPIKE|MASSIVE VOLUME",
}


def extract_signal_type(signal_text: str) -> str:
    """Extract a canonical signal type from a signal description string."""
    for sig_type, pattern in SIGNAL_TYPE_PATTERNS.items():
        if re.search(pattern, signal_text, re.IGNORECASE):
            return sig_type
    return "OTHER"


def screener_node(state: dict) -> dict:
    """
    Combine all analyses into scored, ranked setups.

    Reads:
      - swing_analyses, options_analyses, vector_analyses
      - strategy_weights (from temporal_context_node)
      - recent_performance (from temporal_context_node)
      - market_regime, vix

    Writes:
      - top_picks: ranked list of all scored setups
      - avoid_list: symbols with contradicting signals
      - all_evidence: confluence evidence
    """
    swing = state.get("swing_analyses", {})
    options = state.get("options_analyses", {})
    vectors = state.get("vector_analyses", {})
    weights = state.get("strategy_weights", {})
    recent_perf = state.get("recent_performance", {})
    market_regime = state.get("market_regime", "NEUTRAL")
    vix = state.get("vix")

    logging.info(f"🔍 Running confluence screening across {len(swing)} symbols...")
    logging.info(f"  Market regime: {market_regime} | VIX: {vix}")
    logging.info(f"  Strategy weights loaded: {len(weights)} | Performance contexts: {len(recent_perf)}")

    # ── Regime-Aware Scoring Parameters ────────────────────
    detected_regime = state.get("detected_regime", {})
    regime_label = detected_regime.get("regime_label", "UNKNOWN")
    regime_confidence = detected_regime.get("confidence", 0)
    transition_probs = detected_regime.get("transition_probs", {})

    # Regime-specific thresholds
    REGIME_CONFIG = {
        "TRENDING_BULL":     {"long_boost": 10, "short_penalty": -10, "min_confidence": 35},
        "TRENDING_BEAR":     {"long_boost": -10, "short_penalty": 10, "min_confidence": 50},
        "MEAN_REVERTING":    {"long_boost": 0,  "short_penalty": 0,  "min_confidence": 45},
        "HIGH_VOL_EXPANSION":{"long_boost": -15, "short_penalty": -5, "min_confidence": 60},
    }
    regime_cfg = REGIME_CONFIG.get(regime_label, {"long_boost": 0, "short_penalty": 0, "min_confidence": 40})

    logging.info(f"  HMM Regime: {regime_label} (confidence: {regime_confidence:.0%}) | "
                 f"Long boost: {regime_cfg['long_boost']}, Short adj: {regime_cfg['short_penalty']}")
    logging.info(f"  Strategy weights loaded: {len(weights)} | Performance contexts: {len(recent_perf)}")

    scored_setups = []
    avoid_list = []
    evidence = []

    # Get all unique symbols across all analyses
    all_symbols = set(list(swing.keys()) + list(options.keys()) + list(vectors.keys()))

    for symbol in all_symbols:
        sw = swing.get(symbol)
        opt = options.get(symbol)
        vec = vectors.get(symbol)

        if not sw:
            continue  # Need at least swing analysis

        signals = sw.get("signals", [])
        if not signals:
            continue

        # ── 1. Base confidence from signal count ──────────────
        base_confidence = min(len(signals) * 15, 60)

        # ── 2. Apply learned weights ──────────────────────────
        weighted_score = 0
        signal_types_used = []
        for sig in signals:
            sig_type = extract_signal_type(sig)
            signal_types_used.append(sig_type)
            w = weights.get(sig_type, {})
            weight_multiplier = w.get("weight", 1.0)
            weighted_score += 15 * weight_multiplier

        weighted_confidence = min(weighted_score, 70)

        # ── 3. Trend alignment bonus ──────────────────────────
        trend = sw.get("trend", {})
        daily_trend = trend.get("daily", "NEUTRAL")
        micro_trend = trend.get("micro", "NEUTRAL")
        alignment_bonus = 0
        if daily_trend == micro_trend and daily_trend != "NEUTRAL":
            alignment_bonus = 15

        # ── 4. Cross-analysis confluence ──────────────────────
        confluence_bonus = 0
        signal_type = sw.get("signal_type", "NEUTRAL")

        # Options agreement
        if opt:
            opt_verdict = opt.get("verdict", "NEUTRAL")
            if signal_type == opt_verdict:
                confluence_bonus += 10  # Both agree on direction
            elif signal_type != "NEUTRAL" and opt_verdict != "NEUTRAL" and signal_type != opt_verdict:
                confluence_bonus -= 10  # Contradiction

        # Vector agreement
        if vec:
            vec_signal = vec.get("signal", "neutral")
            if (signal_type == "BULLISH" and vec_signal == "bullish") or \
               (signal_type == "BEARISH" and vec_signal == "bearish"):
                confluence_bonus += 10
            elif vec.get("classification") == "ACCUMULATION" and signal_type == "BULLISH":
                confluence_bonus += 5
            elif vec.get("classification") == "DISTRIBUTION" and signal_type == "BEARISH":
                confluence_bonus += 5

        # ── 5. Market regime context ──────────────────────────
        regime_bonus = 0
        perf_key = f"{market_regime}_INTRADAY"
        regime_perf = recent_perf.get(perf_key, {})
        if regime_perf:
            historical_wr = regime_perf.get("win_rate", 0.5)
            regime_bonus = int((historical_wr - 0.5) * 40)  # -20 to +20

        # HMM regime-specific directional adjustment
        if signal_type == "BULLISH":
            regime_bonus += regime_cfg["long_boost"]
        elif signal_type == "BEARISH":
            regime_bonus += regime_cfg["short_penalty"]

        # Regime transition risk: if high probability of flipping, reduce confidence
        staying_prob = transition_probs.get(regime_label, 0)
        if staying_prob < 0.5 and regime_confidence > 0.5:
            regime_bonus -= 5  # Regime likely changing → less conviction

        # VIX context
        vix_bonus = 0
        if vix:
            if vix < 15:
                vix_bonus = 5   # Low VIX = stable, good for trend trades
            elif vix > 25:
                vix_bonus = -5  # High VIX = choppy, reduce confidence

        # ── 6. Volume confirmation ────────────────────────────
        volume_bonus = 0
        if any("VOLUME" in s for s in signals):
            volume_bonus = 5

        # ── 7. Move potential ─────────────────────────────────
        move_bonus = 0
        move_pct = sw.get("move_potential_pct", 0)
        if move_pct >= 2.0:
            move_bonus = 5

        # ── Final confidence score ────────────────────────────
        final_confidence = max(10, min(100,
            weighted_confidence +
            alignment_bonus +
            confluence_bonus +
            regime_bonus +
            vix_bonus +
            volume_bonus +
            move_bonus
        ))

        # Build result
        setup = {
            "symbol": symbol,
            "close_price": sw.get("close_price"),
            "signal_type": signal_type,
            "signals": signals,
            "signal_types": signal_types_used,
            "confidence": final_confidence,
            "move_potential_pct": move_pct,
            "trend": trend,
            "trade_idea": sw.get("trade_idea"),
            "support_resistance": sw.get("support_resistance"),
            "bollinger": sw.get("bollinger"),
            "indicators": sw.get("indicators"),
            "options_data": opt,
            "vector_data": vec,
            "confidence_breakdown": {
                "base_signals": base_confidence,
                "weight_adjusted": round(weighted_confidence, 1),
                "alignment_bonus": alignment_bonus,
                "confluence_bonus": confluence_bonus,
                "regime_bonus": regime_bonus,
                "vix_bonus": vix_bonus,
                "volume_bonus": volume_bonus,
                "move_bonus": move_bonus,
            },
        }

        scored_setups.append(setup)

        # Check if this should be on the avoid list
        if signal_type == "BEARISH" and final_confidence >= 50:
            avoid_list.append(symbol)

        # If options contradicts swing strongly
        if opt and signal_type != "NEUTRAL":
            opt_verdict = opt.get("verdict", "NEUTRAL")
            if opt_verdict != "NEUTRAL" and opt_verdict != signal_type:
                if symbol not in avoid_list:
                    avoid_list.append(symbol)

        # Add evidence
        evidence.append({
            "node": "screener",
            "symbol": symbol,
            "final_confidence": final_confidence,
            "breakdown": setup["confidence_breakdown"],
            "regime_label": regime_label,
            "regime_confidence": regime_confidence,
            "used_learned_weights": bool(weights),
            "confluence_sources": [
                s for s in ["swing", "options", "vector"]
                if {"swing": sw, "options": opt, "vector": vec}.get(s)
            ],
        })

    # Sort by confidence
    scored_setups.sort(key=lambda x: x["confidence"], reverse=True)

    logging.info(f"\n  ── SCREENING RESULTS ──")
    logging.info(f"  Total scored: {len(scored_setups)}")
    for s in scored_setups[:5]:
        logging.info(
            f"  {'🟢' if s['signal_type'] == 'BULLISH' else '🔴' if s['signal_type'] == 'BEARISH' else '⚪'} "
            f"{s['symbol']}: {s['signal_type']} | {s['confidence']}% | "
            f"Signals: {len(s['signals'])} | Move: {s['move_potential_pct']}%"
        )
    if avoid_list:
        logging.info(f"  🚫 Avoid: {', '.join(avoid_list)}")

    return {
        "top_picks": scored_setups,
        "avoid_list": avoid_list,
        "all_evidence": evidence,
    }
