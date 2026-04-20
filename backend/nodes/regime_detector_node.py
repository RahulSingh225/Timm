# backend/nodes/regime_detector_node.py
"""
REGIME DETECTION NODE (Hidden Markov Model)
Detects the current market regime using a 4-state HMM trained on
NIFTY volatility, trend, and flow features.

Regimes:
  0 = Trending Bull   (high ADX, low VIX, positive FII)
  1 = Trending Bear   (high ADX, high VIX, negative FII)
  2 = Mean-Reverting  (low ADX, moderate VIX, range-bound)
  3 = High Vol Expansion (VIX spike, ATR breakout)

This node runs FIRST in the pre-market graph so every downstream
node can condition its analysis on the detected regime.
"""

import os
import json
import pickle
import logging
import numpy as np
import pandas as pd
import psycopg2
from datetime import datetime
from typing import Optional
from hmmlearn.hmm import GaussianHMM

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")
MODEL_PATH = "models/regime_hmm.pkl"

REGIME_LABELS = {
    0: "TRENDING_BULL",
    1: "TRENDING_BEAR",
    2: "MEAN_REVERTING",
    3: "HIGH_VOL_EXPANSION",
}

# Mapping to the existing market_regime field for backward compatibility
REGIME_TO_MARKET = {
    "TRENDING_BULL": "RISK_ON",
    "TRENDING_BEAR": "RISK_OFF",
    "MEAN_REVERTING": "NEUTRAL",
    "HIGH_VOL_EXPANSION": "RISK_OFF",
}


def _get_conn():
    return psycopg2.connect(DB_URL)


def _load_training_features() -> pd.DataFrame:
    """
    Load historical features for HMM training.
    Uses candle_vector_signals + global_cues for a rich feature set.
    """
    try:
        conn = _get_conn()

        # Primary features from candle_vector_signals
        df = pd.read_sql("""
            SELECT 
                timestamp::date as date,
                AVG(atr_14) as atr,
                AVG(adx_14) as adx,
                AVG(rsi) as rsi,
                AVG(volume_zscore) as vol_z,
                AVG(returns_1d) as ret_1d,
                STDDEV(returns_1d) as ret_vol
            FROM candle_vector_signals
            WHERE symbol = 'NIFTY'
            GROUP BY timestamp::date
            ORDER BY date ASC
        """, conn)

        # Try to enrich with VIX and FII data
        try:
            df_macro = pd.read_sql("""
                SELECT 
                    timestamp::date as date,
                    vix_value as vix,
                    fii_net_flow as fii_net
                FROM global_cues
                ORDER BY timestamp ASC
            """, conn)
            if not df_macro.empty:
                df = df.merge(df_macro, on='date', how='left')
        except Exception:
            pass

        conn.close()
        return df

    except Exception as e:
        logger.warning(f"Failed to load HMM training data: {e}")
        return pd.DataFrame()


def _prepare_features(df: pd.DataFrame) -> np.ndarray:
    """Extract and normalize the feature matrix for HMM."""
    feature_cols = []

    # Use available columns
    if 'adx' in df.columns:
        feature_cols.append('adx')
    if 'atr' in df.columns:
        feature_cols.append('atr')
    if 'ret_vol' in df.columns:
        feature_cols.append('ret_vol')
    if 'vol_z' in df.columns:
        feature_cols.append('vol_z')
    if 'vix' in df.columns:
        feature_cols.append('vix')
    if 'fii_net' in df.columns:
        feature_cols.append('fii_net')
    if 'rsi' in df.columns:
        feature_cols.append('rsi')

    if not feature_cols:
        # Fallback: use returns volatility and volume
        feature_cols = ['ret_1d', 'ret_vol']

    X = df[feature_cols].fillna(0).values

    # Z-score normalization (store params for inference)
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds == 0] = 1.0
    X_norm = (X - means) / stds

    return X_norm, means, stds, feature_cols


def train_regime_model(min_samples: int = 100) -> Optional[GaussianHMM]:
    """
    Train a 4-state Gaussian HMM on historical NIFTY features.
    Saves the model to disk for reuse.
    """
    logger.info("🔬 Training Regime Detection HMM...")

    df = _load_training_features()
    if df.empty or len(df) < min_samples:
        logger.warning(f"Not enough data for HMM training ({len(df)} rows, need {min_samples})")
        return None

    X, means, stds, feature_cols = _prepare_features(df)

    # Fit 4-state Gaussian HMM
    model = GaussianHMM(
        n_components=4,
        covariance_type="full",
        n_iter=200,
        random_state=42,
        tol=0.01,
    )

    try:
        model.fit(X)
    except Exception as e:
        logger.error(f"HMM training failed: {e}")
        return None

    # Decode to assign regime labels
    hidden_states = model.predict(X)

    # Auto-label regimes based on feature means per state
    # Higher ADX/ATR/VIX = more volatile/trending states
    state_profiles = {}
    for state_id in range(4):
        mask = hidden_states == state_id
        if mask.sum() > 0:
            state_profiles[state_id] = {
                col: float(X[mask, i].mean())
                for i, col in enumerate(feature_cols)
            }
            state_profiles[state_id]['count'] = int(mask.sum())

    logger.info(f"  HMM State Profiles: {json.dumps(state_profiles, indent=2)}")

    # Save model + normalization params
    os.makedirs("models", exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({
            "model": model,
            "means": means,
            "stds": stds,
            "feature_cols": feature_cols,
            "state_profiles": state_profiles,
            "trained_at": datetime.utcnow().isoformat(),
            "training_samples": len(df),
        }, f)

    logger.info(f"✅ Regime HMM trained on {len(df)} days, saved to {MODEL_PATH}")
    return model


def infer_regime(features_today: dict) -> dict:
    """
    Run regime inference on a single day's features.
    Returns regime label, confidence, and transition matrix.
    """
    if not os.path.exists(MODEL_PATH):
        logger.warning("No trained HMM model found — training now...")
        model = train_regime_model()
        if model is None:
            return {
                "regime_label": "NEUTRAL",
                "regime_id": 2,
                "confidence": 0.0,
                "method": "fallback_no_model",
            }

    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)

    model = saved["model"]
    means = saved["means"]
    stds = saved["stds"]
    feature_cols = saved["feature_cols"]

    # Build feature vector from today's data
    x = np.array([features_today.get(col, 0.0) for col in feature_cols]).reshape(1, -1)
    x_norm = (x - means) / stds

    # Predict
    state = model.predict(x_norm)[0]
    state_probs = model.predict_proba(x_norm)[0]

    # Get transition probabilities from current state
    trans_probs = model.transmat_[state].tolist()

    regime_label = REGIME_LABELS.get(state, "UNKNOWN")
    confidence = float(state_probs[state])

    return {
        "regime_label": regime_label,
        "regime_id": int(state),
        "confidence": round(confidence, 3),
        "state_probabilities": {REGIME_LABELS[i]: round(float(p), 3) for i, p in enumerate(state_probs)},
        "transition_probs": {REGIME_LABELS[i]: round(float(p), 3) for i, p in enumerate(trans_probs)},
        "features_used": {col: features_today.get(col, 0.0) for col in feature_cols},
        "method": "hmm_gaussian_4state",
    }


def _persist_regime(date_str: str, result: dict):
    """Save regime detection result to regime_history table."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS regime_history (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL UNIQUE,
                regime_label VARCHAR(30) NOT NULL,
                regime_id INTEGER NOT NULL,
                confidence REAL,
                vix REAL,
                adx REAL,
                fii_net_5d REAL,
                atr_percentile REAL,
                transition_probs JSONB,
                computed_at TIMESTAMP DEFAULT NOW()
            )
        """)

        features = result.get("features_used", {})
        cur.execute("""
            INSERT INTO regime_history
            (date, regime_label, regime_id, confidence, vix, adx, transition_probs)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                regime_label = EXCLUDED.regime_label,
                regime_id = EXCLUDED.regime_id,
                confidence = EXCLUDED.confidence,
                computed_at = NOW()
        """, (
            date_str,
            result["regime_label"],
            result["regime_id"],
            result["confidence"],
            features.get("vix"),
            features.get("adx"),
            json.dumps(result.get("transition_probs", {})),
        ))

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to persist regime: {e}")


def regime_detector_node(state: TradingState) -> TradingState:
    """
    LangGraph node: Detect current market regime.
    Runs as the FIRST node in pre-market graph.
    """
    logger.info("🔬 Regime Detection starting...")

    report_date = state.get("report_date", datetime.utcnow().strftime("%Y-%m-%d"))

    # Gather today's features from whatever is already in state
    features_today = {
        "adx": state.get("vix", 15) * 2,  # Rough proxy if real ADX not available yet
        "atr": 0.5,
        "ret_vol": 0.01,
        "vol_z": 0.0,
        "rsi": 50.0,
    }

    # Try to pull latest features from DB
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT adx_14, atr_14, volume_zscore, rsi, returns_1d
            FROM candle_vector_signals
            WHERE symbol = 'NIFTY'
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            features_today.update({
                "adx": row[0] or 0,
                "atr": row[1] or 0,
                "vol_z": row[2] or 0,
                "rsi": row[3] or 50,
                "ret_1d": row[4] or 0,
            })

        # Pull VIX
        cur.execute("""
            SELECT vix_value, fii_net_flow
            FROM global_cues
            ORDER BY timestamp DESC LIMIT 1
        """)
        macro_row = cur.fetchone()
        if macro_row:
            features_today["vix"] = macro_row[0] or 15
            features_today["fii_net"] = macro_row[1] or 0

        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not fetch latest features for regime: {e}")

    # Run HMM inference
    result = infer_regime(features_today)

    # Map to backward-compatible market_regime
    regime_label = result["regime_label"]
    market_regime = REGIME_TO_MARKET.get(regime_label, "NEUTRAL")

    # Update state
    state['market_regime'] = market_regime
    state['detected_regime'] = result

    # Also update defense_mode based on regime
    if regime_label in ("HIGH_VOL_EXPANSION", "TRENDING_BEAR"):
        state['defense_mode'] = True
    else:
        state['defense_mode'] = False

    # Persist
    _persist_regime(report_date, result)

    logger.info(
        f"✅ Regime detected: {regime_label} → {market_regime} "
        f"(confidence: {result['confidence']:.1%}) "
        f"| Defense mode: {state.get('defense_mode', False)}"
    )

    return state
