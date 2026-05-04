# backend/nodes/ensemble_metalearner_node.py
"""
ENSEMBLE META-LEARNER (Phase 9.2)
Stacking ensemble that combines signals from:
  - GP evolved strategies (symbolic regression)
  - NEAT neuroevolution networks
  - MARL PPO policy
  - Sector GNN rotation signal
  - Options GNN IV surface prediction
  - GARCH volatility forecast

Uses a lightweight gradient-boosted tree (XGBoost) as the meta-model,
trained on each sub-model's out-of-sample predictions.
"""

import os
import logging
import pickle
import numpy as np
from datetime import datetime
from typing import Dict

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

META_MODEL_PATH = "models/ensemble_meta_learner.pkl"
REGIME_WEIGHTS = {
    "TRENDING_BULL": {"gp": 0.3, "neat": 0.25, "marl": 0.2, "sector_gnn": 0.15, "vol": 0.1},
    "TRENDING_BEAR": {"gp": 0.2, "neat": 0.2, "marl": 0.3, "sector_gnn": 0.1, "vol": 0.2},
    "MEAN_REVERTING": {"gp": 0.35, "neat": 0.2, "marl": 0.15, "sector_gnn": 0.2, "vol": 0.1},
    "HIGH_VOL_EXPANSION": {"gp": 0.15, "neat": 0.15, "marl": 0.25, "sector_gnn": 0.1, "vol": 0.35},
}
DEFAULT_WEIGHTS = {"gp": 0.25, "neat": 0.2, "marl": 0.2, "sector_gnn": 0.15, "vol": 0.2}


def _extract_sub_signals(state: TradingState) -> Dict:
    """Extract prediction signals from each sub-model."""
    signals = {}

    # GP strategies → average conviction direction
    gp = state.get("evolved_strategies", [])
    if gp:
        directions = [s.get("direction", 0) for s in gp if isinstance(s, dict)]
        signals["gp_direction"] = np.mean(directions) if directions else 0
        signals["gp_confidence"] = np.mean([s.get("fitness", 0) for s in gp]) if gp else 0
    else:
        signals["gp_direction"] = 0
        signals["gp_confidence"] = 0

    # NEAT → fitness as a confidence proxy
    neat = state.get("neat_best_network", {})
    signals["neat_fitness"] = neat.get("fitness", 0)

    # MARL → mean reward as signal
    marl = state.get("marl_policy", {})
    signals["marl_reward"] = marl.get("mean_reward", 0)

    # Sector GNN → rotation direction
    sgnn = state.get("sector_gnn_signal", {})
    rotation = sgnn.get("predicted_rotation", "")
    signals["sector_rotation"] = 1 if "Bull" in rotation else -1 if "Bear" in rotation else 0
    signals["sector_confidence"] = sgnn.get("confidence", 0)

    # Options GNN → IV expansion/crush
    ognn = state.get("options_gnn_signal", {})
    signals["iv_call_conf"] = ognn.get("atm_call_iv_confidence", 0.5)
    signals["iv_put_conf"] = ognn.get("atm_put_iv_confidence", 0.5)

    # Volatility forecast
    vol = state.get("volatility_forecast", {})
    signals["vol_1d"] = vol.get("vol_1d", 0)
    signals["iv_signal"] = 1 if vol.get("iv_signal") == "IV_DISCOUNT" else \
                           -1 if vol.get("iv_signal") == "IV_PREMIUM" else 0

    return signals


def _weighted_ensemble(signals: Dict, regime: str) -> Dict:
    """Weighted ensemble based on regime-specific model weights."""
    weights = REGIME_WEIGHTS.get(regime, DEFAULT_WEIGHTS)

    # Model scores (directional conviction, -1 to +1)
    gp_score = np.clip(signals["gp_direction"] * signals["gp_confidence"], -1, 1)
    neat_score = np.clip(signals["neat_fitness"] / 5.0, -1, 1)  # Normalize fitness
    marl_score = np.clip(signals["marl_reward"] / 100.0, -1, 1)
    sector_score = signals["sector_rotation"] * signals["sector_confidence"]
    vol_score = signals["iv_signal"] * 0.5

    # Weighted combination
    ensemble_signal = (
        weights["gp"] * gp_score +
        weights["neat"] * neat_score +
        weights["marl"] * marl_score +
        weights["sector_gnn"] * sector_score +
        weights["vol"] * vol_score
    )

    # Compute confidence as agreement level
    individual = [gp_score, neat_score, marl_score, sector_score, vol_score]
    signs = [np.sign(s) for s in individual if abs(s) > 0.1]
    agreement = abs(sum(signs)) / max(len(signs), 1)

    direction = "BULLISH" if ensemble_signal > 0.1 else "BEARISH" if ensemble_signal < -0.1 else "NEUTRAL"

    return {
        "ensemble_signal": round(float(ensemble_signal), 4),
        "direction": direction,
        "confidence": round(float(agreement), 3),
        "model_agreement_pct": round(agreement * 100, 1),
        "model_scores": {
            "gp": round(float(gp_score), 3),
            "neat": round(float(neat_score), 3),
            "marl": round(float(marl_score), 3),
            "sector_gnn": round(float(sector_score), 3),
            "volatility": round(float(vol_score), 3),
        },
        "regime_weights_used": weights,
    }


def _xgb_ensemble(signals: Dict) -> Dict:
    """Use trained XGBoost meta-learner if available."""
    if not os.path.exists(META_MODEL_PATH):
        return None

    try:
        with open(META_MODEL_PATH, "rb") as f:
            meta_model = pickle.load(f)

        features = np.array([[
            signals["gp_direction"], signals["gp_confidence"],
            signals["neat_fitness"], signals["marl_reward"],
            signals["sector_rotation"], signals["sector_confidence"],
            signals["iv_call_conf"], signals["iv_put_conf"],
            signals["vol_1d"], signals["iv_signal"],
        ]])

        pred = meta_model.predict_proba(features)[0]
        direction = "BULLISH" if pred[1] > 0.55 else "BEARISH" if pred[0] > 0.55 else "NEUTRAL"

        return {
            "ensemble_signal": round(float(pred[1] - pred[0]), 4),
            "direction": direction,
            "confidence": round(float(max(pred)), 3),
            "method": "xgboost_meta",
        }
    except Exception as e:
        logger.warning(f"XGB meta-learner failed: {e}")
        return None


def ensemble_metalearner_node(state: TradingState) -> TradingState:
    """LangGraph node — combines all ML sub-model signals."""
    logger.info("🧩 Ensemble Meta-Learner running...")

    signals = _extract_sub_signals(state)
    regime = state.get("detected_regime", {}).get("regime_label", "UNKNOWN")

    # Try XGBoost meta-learner first
    xgb_result = _xgb_ensemble(signals)
    if xgb_result:
        result = xgb_result
        logger.info(f"  Using XGBoost meta-learner: {result['direction']} ({result['confidence']:.0%})")
    else:
        result = _weighted_ensemble(signals, regime)
        result["method"] = "regime_weighted"
        logger.info(f"  Using weighted ensemble: {result['direction']} ({result['confidence']:.0%})")

    result["regime"] = regime
    result["sub_signals"] = signals
    result["generated_at"] = datetime.utcnow().isoformat()

    state["ensemble_signal"] = result

    logger.info(f"✅ Ensemble: {result['direction']} | Signal: {result['ensemble_signal']:.3f} | "
                f"Agreement: {result.get('model_agreement_pct', 0):.0f}%")
    return state
