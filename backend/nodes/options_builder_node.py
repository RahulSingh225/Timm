"""
Options Scalp Builder Node — Builds options scalping setups.

Constructs BUY CALL / BUY PUT recommendations for:
  - NIFTY, SENSEX, and stock options
  - Near-to-far OTM strikes
  - Max ₹50 premium per lot
  - Prefers expiry-day / near-expiry for gamma
"""

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [NODE:OPTIONS_BUILDER] - %(message)s')


def options_builder_node(state: dict) -> dict:
    """
    Build options scalping setups from confluence data.

    Rules (user's trading style):
      - Only BUY CALLS or BUY PUTS (no selling/writing)
      - Instruments: NIFTY, SENSEX, and stock options
      - Strikes: Near-to-far OTM
      - Max premium: ₹50 per lot
      - Prefer near-expiry / expiry-day for max gamma
      - SL: 30% of premium
      - Target: 50-100% of premium

    Reads:
      - top_picks: scored setups from screener
      - swing_analyses, options_analyses
      - strategy_weights

    Writes:
      - options_setups: list of options scalp setups
      - all_evidence: evidence entries
    """
    top_picks = state.get("top_picks", [])
    swing_analyses = state.get("swing_analyses", {})
    options_analyses = state.get("options_analyses", {})
    weights = state.get("strategy_weights", {})
    detected_regime = state.get("detected_regime", {})
    regime_label = detected_regime.get("regime_label", "UNKNOWN")
    regime_confidence = detected_regime.get("confidence", 0)
    defense_mode = state.get("defense_mode", False)

    # Regime-adjusted minimum confidence for options
    min_confidence = 50
    if regime_label == "HIGH_VOL_EXPANSION":
        min_confidence = 65  # Options are expensive during vol spikes
    elif regime_label == "TRENDING_BEAR":
        min_confidence = 55
    elif defense_mode:
        min_confidence = 70

    logging.info(f"📊 Building options scalp setups... Regime: {regime_label} | Min confidence: {min_confidence}%")

    # GARCH volatility forecast for expected move and IV signal
    vol_forecast = state.get("volatility_forecast", {})
    garch_expected_move = vol_forecast.get("expected_move", {})
    garch_move_pct = garch_expected_move.get("expected_move_1d_pct", 0)
    iv_signal = vol_forecast.get("iv_signal", "UNKNOWN")
    vol_regime = vol_forecast.get("vol_regime", "UNKNOWN")
    iv_rv_spread = vol_forecast.get("iv_rv_spread", 0)

    setups = []
    evidence = []

    for setup in top_picks:
        symbol = setup.get("symbol", "")
        confidence = setup.get("confidence", 0)
        signal_type = setup.get("signal_type", "NEUTRAL")

        # Need regime-adjusted confidence for options scalps
        if confidence < min_confidence or signal_type == "NEUTRAL":
            continue

        # Defense mode / bear regime: only allow BUY_PUT
        if defense_mode and signal_type == "BULLISH":
            logging.info(f"  ⚠️ Skipping {symbol} BUY_CALL — defense mode active")
            continue

        # Get options data for this symbol
        opt = options_analyses.get(symbol)
        swing = swing_analyses.get(symbol)

        if not opt:
            continue

        # ── Determine BUY CALL or BUY PUT ────────────────────
        if signal_type == "BULLISH":
            option_action = "BUY_CALL"
            # BUY CALL when: bullish swing + options confirm or neutral
            if opt.get("verdict") == "BEARISH" and confidence < 70:
                continue  # Skip if options contradict and confidence isn't very high
        elif signal_type == "BEARISH":
            option_action = "BUY_PUT"
            if opt.get("verdict") == "BULLISH" and confidence < 70:
                continue
        else:
            continue

        # ── Strike selection logic (GARCH-enhanced) ─────────
        close_price = setup.get("close_price", 0)
        opt_expected_move = opt.get("expected_move_pct", 0)

        # Use GARCH expected move if available (more reliable than options chain estimate)
        expected_move = garch_move_pct if garch_move_pct > 0 else opt_expected_move

        # Determine OTM range based on expected move
        if expected_move and expected_move > 2.0:
            strike_approach = "NEAR_OTM"  # High expected move → near OTM for higher delta
        elif expected_move and expected_move > 1.0:
            strike_approach = "OTM_1_2"   # Moderate move → 1-2 strikes OTM
        else:
            strike_approach = "FAR_OTM"    # Low expected move → far OTM (cheaper, more leverage)

        # IV Premium penalty: if options are overpriced, reduce confidence
        iv_adjustment = 0
        if iv_signal == "IV_PREMIUM":
            iv_adjustment = -5  # Options overpriced → less attractive
        elif iv_signal == "IV_DISCOUNT":
            iv_adjustment = 5   # Options cheap → more attractive

        # ── Build evidence chain ─────────────────────────────
        trade_evidence = [
            f"Regime: {regime_label} ({regime_confidence:.0%}) | Min conf: {min_confidence}%",
            f"GARCH Vol: {vol_regime} | IV Signal: {iv_signal} (spread: {iv_rv_spread:+.2%})",
            f"Expected Move: ±{expected_move:.1f}% (GARCH: {garch_move_pct:.1f}%, Chain: {opt_expected_move}%)",
            f"Action: {option_action} on {symbol}",
            f"Swing: {signal_type} with {len(setup.get('signals', []))} signals, confidence {confidence}%",
            f"Options verdict: {opt.get('verdict')} | Max Pain: ₹{opt.get('max_pain')}",
            f"Strike approach: {strike_approach}",
            f"PCR: {opt.get('pcr_volume')} | Call Wall: {opt.get('call_wall')} | Put Wall: {opt.get('put_wall')}",
            f"Premium cap: ₹50/lot | SL: 30% of premium | Target: 50-100% of premium",
        ]

        # Add vector context
        vec = setup.get("vector_data")
        if vec:
            trade_evidence.append(
                f"Vector: {vec.get('classification')} | "
                f"Predicted: {vec.get('predicted_next_move_pct', 0):+.2f}%"
            )

        # Add learned weight context
        for sig_type in setup.get("signal_types", []):
            w = weights.get(sig_type)
            if w and w.get("sample_size", 0) > 5:
                trade_evidence.append(
                    f"History: {sig_type} → {w['win_rate']:.0%} win rate "
                    f"({w['sample_size']} trades)"
                )

        # ── Apply weight adjustment to confidence ────────────
        weight_adjustment = 0
        for sig_type in setup.get("signal_types", []):
            w = weights.get(sig_type, {})
            weight_adjustment += (w.get("weight", 1.0) - 1.0) * 10

        adjusted_confidence = max(10, min(100, int(confidence + weight_adjustment)))

        options_setup = {
            "symbol": symbol,
            "trade_type": "OPTIONS_SCALP",
            "option_action": option_action,
            "strike_approach": strike_approach,
            "max_premium_per_lot": 50,
            "underlying_price": close_price,
            "confidence": adjusted_confidence,
            "original_confidence": confidence,
            "max_pain": opt.get("max_pain"),
            "call_wall": opt.get("call_wall"),
            "put_wall": opt.get("put_wall"),
            "expected_move_pct": expected_move,
            "pcr_volume": opt.get("pcr_volume"),
            "pcr_oi": opt.get("pcr_oi"),
            "atm_call_iv": opt.get("atm_call_iv"),
            "atm_put_iv": opt.get("atm_put_iv"),
            "stoploss_rule": "30% of premium paid",
            "target_rule": "50-100% of premium paid",
            "signals": setup.get("signals", []),
            "evidence": trade_evidence,
        }

        setups.append(options_setup)

    # Sort by confidence
    setups.sort(key=lambda x: x["confidence"], reverse=True)

    logging.info(f"  Built {len(setups)} options scalp setups:")
    for s in setups[:5]:
        logging.info(
            f"    {'📗' if s['option_action'] == 'BUY_CALL' else '📕'} {s['symbol']}: "
            f"{s['option_action']} | {s['confidence']}% | "
            f"Strike: {s['strike_approach']} | "
            f"Expected Move: ±{s.get('expected_move_pct')}%"
        )

    evidence.append({
        "node": "options_builder",
        "total_setups": len(setups),
        "call_count": sum(1 for s in setups if s["option_action"] == "BUY_CALL"),
        "put_count": sum(1 for s in setups if s["option_action"] == "BUY_PUT"),
    })

    return {
        "options_setups": setups,
        "all_evidence": evidence,
    }
