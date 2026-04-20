# backend/nodes/volatility_forecast_node.py
"""
GARCH VOLATILITY FORECAST NODE
Forecasts short-term volatility using GARCH(1,1) on NIFTY returns.
Compares realized vs implied volatility to generate IV premium/discount signals.

Outputs:
  - Forecasted 1D and 5D volatility (annualized)
  - IV-RV spread (premium or discount)
  - Volatility regime (low/normal/high/extreme)
  - Expected move range (in points and %)

Feeds into options_builder_node for smarter strike selection and sizing.
"""

import os
import json
import logging
import pickle
import numpy as np
import pandas as pd
import psycopg2
from datetime import datetime
from typing import Optional

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")
MODEL_PATH = "models/garch_model.pkl"


def _get_conn():
    return psycopg2.connect(DB_URL)


def _load_returns(lookback_days: int = 500) -> pd.Series:
    """Load NIFTY daily returns from candle_vector_signals."""
    try:
        conn = _get_conn()
        df = pd.read_sql(f"""
            SELECT timestamp, returns_1d
            FROM candle_vector_signals
            WHERE symbol = 'NIFTY' AND returns_1d IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT {lookback_days}
        """, conn)
        conn.close()

        if df.empty:
            return pd.Series()

        df = df.sort_values("timestamp")
        return df.set_index("timestamp")["returns_1d"].dropna()

    except Exception as e:
        logger.warning(f"Failed to load returns for GARCH: {e}")
        return pd.Series()


def _load_current_iv() -> Optional[float]:
    """Load latest NIFTY ATM implied volatility from options data or global_cues."""
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Try options data first
        cur.execute("""
            SELECT vix_value FROM global_cues
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row and row[0]:
            return float(row[0])  # VIX as IV proxy
        return None

    except Exception:
        return None


def fit_garch(returns: pd.Series) -> dict:
    """
    Fit GARCH(1,1) model and forecast volatility.
    Returns model summary + forecasted volatility.
    """
    try:
        from arch import arch_model
    except ImportError:
        logger.error("arch library not installed. pip install arch")
        return {"error": "arch not installed"}

    # Scale returns to percentage for numerical stability
    scaled_returns = returns * 100

    if len(scaled_returns) < 100:
        return {"error": f"Insufficient data: {len(scaled_returns)} points (need 100+)"}

    try:
        # Fit GARCH(1,1)
        model = arch_model(
            scaled_returns,
            vol="Garch",
            p=1, q=1,
            mean="Constant",
            dist="t",  # Student-t for fat tails
        )
        result = model.fit(disp="off", show_warning=False)

        # 1-day ahead forecast
        forecast_1d = result.forecast(horizon=1)
        var_1d = forecast_1d.variance.values[-1, 0]
        vol_1d = np.sqrt(var_1d) / 100  # Scale back to decimal

        # 5-day ahead forecast
        forecast_5d = result.forecast(horizon=5)
        var_5d = forecast_5d.variance.values[-1, :]
        vol_5d = np.sqrt(np.mean(var_5d)) / 100

        # Annualize
        vol_1d_ann = vol_1d * np.sqrt(252)
        vol_5d_ann = vol_5d * np.sqrt(252)

        # Realized volatility (20-day)
        rv_20d = returns.tail(20).std() * np.sqrt(252)

        # Historical vol percentile (how current vol compares to history)
        rolling_vol = returns.rolling(20).std() * np.sqrt(252)
        current_vol = rolling_vol.iloc[-1]
        vol_percentile = (rolling_vol < current_vol).mean() * 100

        # Save model
        os.makedirs("models", exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump({
                "result_params": {
                    "omega": float(result.params.get("omega", 0)),
                    "alpha[1]": float(result.params.get("alpha[1]", 0)),
                    "beta[1]": float(result.params.get("beta[1]", 0)),
                },
                "vol_1d_ann": float(vol_1d_ann),
                "vol_5d_ann": float(vol_5d_ann),
                "rv_20d": float(rv_20d),
                "vol_percentile": float(vol_percentile),
                "trained_at": datetime.utcnow().isoformat(),
                "n_observations": len(returns),
            }, f)

        return {
            "vol_1d_forecast": float(vol_1d_ann),
            "vol_5d_forecast": float(vol_5d_ann),
            "realized_vol_20d": float(rv_20d),
            "vol_percentile": float(vol_percentile),
            "garch_params": {
                "omega": float(result.params.get("omega", 0)),
                "alpha": float(result.params.get("alpha[1]", 0)),
                "beta": float(result.params.get("beta[1]", 0)),
                "persistence": float(result.params.get("alpha[1]", 0) + result.params.get("beta[1]", 0)),
            },
            "aic": float(result.aic),
            "bic": float(result.bic),
        }

    except Exception as e:
        logger.error(f"GARCH fitting failed: {e}")
        return {"error": str(e)}


def classify_vol_regime(vol_percentile: float) -> str:
    """Classify current volatility into a regime bucket."""
    if vol_percentile < 20:
        return "LOW_VOL"
    elif vol_percentile < 50:
        return "NORMAL_VOL"
    elif vol_percentile < 80:
        return "HIGH_VOL"
    else:
        return "EXTREME_VOL"


def compute_expected_move(vol_1d: float, current_price: float) -> dict:
    """
    Compute expected move range (1-sigma and 2-sigma) from forecasted volatility.
    This is what options market makers use for pricing.
    """
    daily_vol = vol_1d / np.sqrt(252)
    move_1d_pct = daily_vol * 100
    move_1d_pts = current_price * daily_vol

    return {
        "expected_move_1d_pct": round(float(move_1d_pct), 2),
        "expected_move_1d_points": round(float(move_1d_pts), 1),
        "range_1sigma": {
            "low": round(float(current_price - move_1d_pts), 1),
            "high": round(float(current_price + move_1d_pts), 1),
        },
        "range_2sigma": {
            "low": round(float(current_price - 2 * move_1d_pts), 1),
            "high": round(float(current_price + 2 * move_1d_pts), 1),
        },
    }


def _persist_volatility(date_str: str, result: dict):
    """Save volatility forecast to DB."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS volatility_forecasts (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL UNIQUE,
                vol_1d_forecast REAL,
                vol_5d_forecast REAL,
                realized_vol_20d REAL,
                iv_rv_spread REAL,
                vol_regime VARCHAR(20),
                vol_percentile REAL,
                expected_move_pct REAL,
                garch_params JSONB,
                computed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            INSERT INTO volatility_forecasts
            (date, vol_1d_forecast, vol_5d_forecast, realized_vol_20d, iv_rv_spread,
             vol_regime, vol_percentile, expected_move_pct, garch_params)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                vol_1d_forecast = EXCLUDED.vol_1d_forecast,
                vol_5d_forecast = EXCLUDED.vol_5d_forecast,
                computed_at = NOW()
        """, (
            date_str,
            result.get("vol_1d_forecast"),
            result.get("vol_5d_forecast"),
            result.get("realized_vol_20d"),
            result.get("iv_rv_spread"),
            result.get("vol_regime"),
            result.get("vol_percentile"),
            result.get("expected_move", {}).get("expected_move_1d_pct"),
            json.dumps(result.get("garch_params", {})),
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to persist volatility forecast: {e}")


def volatility_forecast_node(state: TradingState) -> TradingState:
    """
    LangGraph node: GARCH(1,1) volatility forecasting.
    Runs early in the pre-market graph (after regime detection).
    """
    logger.info("📉 GARCH Volatility Forecast starting...")

    report_date = state.get("report_date", datetime.utcnow().strftime("%Y-%m-%d"))

    # Load historical returns
    returns = _load_returns(lookback_days=500)
    if returns.empty or len(returns) < 100:
        logger.warning("Not enough return data for GARCH — using fallback")
        state['volatility_forecast'] = {
            "vol_1d_forecast": 0.15,
            "vol_5d_forecast": 0.15,
            "vol_regime": "NORMAL_VOL",
            "iv_rv_spread": 0.0,
            "method": "fallback_no_data",
        }
        return state

    # Fit GARCH
    garch_result = fit_garch(returns)

    if "error" in garch_result:
        logger.error(f"GARCH failed: {garch_result['error']}")
        state['volatility_forecast'] = {
            "vol_1d_forecast": float(returns.tail(20).std() * np.sqrt(252)),
            "vol_regime": "NORMAL_VOL",
            "iv_rv_spread": 0.0,
            "method": "fallback_realized_vol",
        }
        return state

    # Load current implied vol (VIX as proxy)
    current_iv = _load_current_iv()
    iv_rv_spread = 0.0
    if current_iv is not None:
        # VIX is in percentage points (e.g., 15 = 15%)
        iv_decimal = current_iv / 100
        rv = garch_result["realized_vol_20d"]
        iv_rv_spread = iv_decimal - rv  # Positive = IV premium, Negative = IV discount

    # Classify vol regime
    vol_regime = classify_vol_regime(garch_result["vol_percentile"])

    # Compute expected move
    # Try to get current NIFTY price
    current_price = 22500.0  # Default
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT close FROM candle_vector_signals
            WHERE symbol = 'NIFTY' ORDER BY timestamp DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            current_price = float(row[0])
        cur.close()
        conn.close()
    except Exception:
        pass

    expected_move = compute_expected_move(garch_result["vol_1d_forecast"], current_price)

    # Build complete forecast
    forecast = {
        "vol_1d_forecast": garch_result["vol_1d_forecast"],
        "vol_5d_forecast": garch_result["vol_5d_forecast"],
        "realized_vol_20d": garch_result["realized_vol_20d"],
        "vol_percentile": garch_result["vol_percentile"],
        "vol_regime": vol_regime,
        "iv_current": current_iv / 100 if current_iv else None,
        "iv_rv_spread": round(float(iv_rv_spread), 4),
        "iv_signal": "IV_PREMIUM" if iv_rv_spread > 0.02 else "IV_DISCOUNT" if iv_rv_spread < -0.02 else "FAIR_VALUE",
        "expected_move": expected_move,
        "garch_params": garch_result.get("garch_params", {}),
        "method": "garch_1_1_student_t",
        "computed_at": datetime.utcnow().isoformat(),
    }

    state['volatility_forecast'] = forecast

    # Persist
    forecast_persist = {**forecast, "garch_params": garch_result.get("garch_params", {})}
    _persist_volatility(report_date, forecast_persist)

    logger.info(
        f"✅ GARCH Forecast: 1D Vol={garch_result['vol_1d_forecast']:.1%} | "
        f"5D Vol={garch_result['vol_5d_forecast']:.1%} | "
        f"Regime={vol_regime} | "
        f"IV-RV Spread={iv_rv_spread:+.2%} ({forecast['iv_signal']}) | "
        f"Expected Move: ±{expected_move['expected_move_1d_pct']:.1f}% "
        f"(₹{expected_move['expected_move_1d_points']:.0f})"
    )

    return state
