# backend/nodes/position_sizing_node.py
"""
POSITION SIZING NODE
Half-Kelly + ATR-based sizing with regime-adjusted risk limits.
Max portfolio heat: 2%. Regime-adjusted multipliers.
"""

import logging
import numpy as np
from typing import Dict
from langgraph_state import TradingState

logger = logging.getLogger(__name__)

MAX_PORTFOLIO_HEAT = 0.02
MAX_SINGLE_TRADE_RISK = 0.01
ACCOUNT_SIZE = 500000

REGIME_RISK_MULT = {
    "TRENDING_BULL": 1.0, "TRENDING_BEAR": 0.5,
    "MEAN_REVERTING": 0.75, "HIGH_VOL_EXPANSION": 0.3,
}


def kelly_criterion(win_rate, avg_win, avg_loss):
    if avg_loss == 0 or win_rate <= 0:
        return 0.0
    b = abs(avg_win / avg_loss)
    kelly = (b * win_rate - (1 - win_rate)) / b
    return max(0, min(kelly, 0.25))


def size_setup(setup, account, regime_label, vol_regime, weights):
    symbol = setup.get("symbol", "?")
    entry = setup.get("entry") or setup.get("close_price", 0)
    confidence = setup.get("confidence", 50)

    win_rate, avg_win, avg_loss = 0.5, 0.01, -0.01
    for sig in setup.get("signal_types", []):
        w = weights.get(sig, {})
        if w.get("sample_size", 0) > 0:
            win_rate = w.get("win_rate", 0.5)
            avg_win = w.get("avg_win", 0.01)
            avg_loss = w.get("avg_loss", -0.01)

    kelly_f = kelly_criterion(win_rate, avg_win, avg_loss) * 0.5
    conf_mult = 0.5 + (confidence / 200)
    regime_mult = REGIME_RISK_MULT.get(regime_label, 0.75)
    if vol_regime == "EXTREME_VOL":
        regime_mult *= 0.5

    adj_risk = min(MAX_SINGLE_TRADE_RISK * conf_mult * regime_mult, MAX_SINGLE_TRADE_RISK)
    risk_amt = account * adj_risk

    atr = (setup.get("indicators") or {}).get("atr", 0) or 0
    if atr <= 0 and setup.get("stoploss") and entry:
        atr = abs(entry - setup["stoploss"]) / 2
    if atr <= 0:
        atr = entry * 0.02

    shares = int(risk_amt / atr) if atr > 0 else 0
    return {
        "shares": shares, "position_value": round(shares * entry, 2),
        "risk_amount": round(risk_amt, 2), "risk_pct": round(adj_risk * 100, 2),
        "kelly_half": round(kelly_f, 4), "regime_mult": round(regime_mult, 3),
    }


def position_sizing_node(state: TradingState) -> TradingState:
    logger.info("📐 Position Sizing node starting...")
    regime_label = state.get("detected_regime", {}).get("regime_label", "MEAN_REVERTING")
    vol_regime = state.get("volatility_forecast", {}).get("vol_regime", "NORMAL_VOL")
    weights = state.get("strategy_weights", {})
    total_risk = 0.0
    sized_intraday, sized_options, evidence = [], [], []

    for s in state.get("intraday_setups", []):
        sz = size_setup(s, ACCOUNT_SIZE, regime_label, vol_regime, weights)
        if total_risk + sz["risk_amount"] > ACCOUNT_SIZE * MAX_PORTFOLIO_HEAT:
            continue
        total_risk += sz["risk_amount"]
        s["position_sizing"] = sz
        sized_intraday.append(s)
        logger.info(f"  {s['symbol']}: {sz['shares']} shares | Risk ₹{sz['risk_amount']:,.0f}")

    for s in state.get("options_setups", []):
        lots = max(1, int(ACCOUNT_SIZE * 0.005 / 2500))
        risk = lots * 50 * 50 * 0.3
        if total_risk + risk > ACCOUNT_SIZE * MAX_PORTFOLIO_HEAT:
            continue
        total_risk += risk
        s["position_sizing"] = {"lots": lots, "risk_amount": round(risk, 2)}
        sized_options.append(s)

    evidence.append({"node": "position_sizing", "total_risk": round(total_risk, 2),
                     "heat_pct": round(total_risk / ACCOUNT_SIZE * 100, 2)})
    logger.info(f"✅ Sized {len(sized_intraday)} intraday + {len(sized_options)} options | "
                f"Heat: {total_risk/ACCOUNT_SIZE:.1%}")

    state["intraday_setups"] = sized_intraday
    state["options_setups"] = sized_options
    return {**state, "all_evidence": evidence}
