# backend/walk_forward_validator.py
"""
WALK-FORWARD OPTIMIZATION & VALIDATION
Implements rolling window train/validate/test splits with regime-specific reporting.

This is the gold-standard validation approach for time-series trading models:
  1. Train on window [0, T]
  2. Validate on [T, T+V] 
  3. Test on [T+V, T+V+S]
  4. Roll forward by step_size and repeat

Prevents overfitting by ensuring models are always evaluated on unseen future data.
Reports per-regime performance so you never average across different market conditions.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DB_URL)


class WalkForwardValidator:
    """
    Rolling-window walk-forward optimizer.
    
    Usage:
        wfv = WalkForwardValidator(
            train_pct=0.70, val_pct=0.15, test_pct=0.15,
            step_size=60, min_train_days=252
        )
        results = wfv.run(df, strategy_func)
    """

    def __init__(
        self,
        train_pct: float = 0.70,
        val_pct: float = 0.15,
        test_pct: float = 0.15,
        step_size: int = 60,          # Roll forward 60 days per fold
        min_train_days: int = 252,    # Minimum 1 year of training data
        transaction_cost_bps: float = 5.0,  # 5 bps round-trip
    ):
        self.train_pct = train_pct
        self.val_pct = val_pct
        self.test_pct = test_pct
        self.step_size = step_size
        self.min_train_days = min_train_days
        self.transaction_cost_bps = transaction_cost_bps

    def _compute_metrics(self, returns: np.ndarray, signals: np.ndarray,
                         regime_labels: Optional[np.ndarray] = None) -> Dict:
        """Compute comprehensive trading metrics from returns and signals."""
        if len(returns) == 0 or len(signals) == 0:
            return self._empty_metrics()

        # Strategy returns = market return * position
        strat_returns = returns * signals

        # Apply transaction costs on trade entries/exits
        trades = np.diff(signals, prepend=0)
        cost_per_trade = self.transaction_cost_bps / 10000
        costs = np.abs(trades) * cost_per_trade
        net_returns = strat_returns - costs

        # Equity curve
        equity = np.cumprod(1 + net_returns)

        # Core metrics
        total_return = float(equity[-1] - 1)
        ann_return = float((1 + total_return) ** (252 / max(len(returns), 1)) - 1)
        ann_vol = float(np.std(net_returns) * np.sqrt(252))
        sharpe = ann_return / (ann_vol + 1e-8)

        # Drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / (peak + 1e-8)
        max_dd = float(np.max(drawdown))
        calmar = ann_return / (max_dd + 1e-8)

        # Win rate & profit factor
        winning = net_returns[net_returns > 0]
        losing = net_returns[net_returns < 0]
        win_rate = float(len(winning) / max(len(net_returns[net_returns != 0]), 1))
        profit_factor = float(abs(winning.sum()) / (abs(losing.sum()) + 1e-8))

        # Trade statistics
        n_trades = int(np.sum(np.abs(trades) > 0))
        avg_win = float(winning.mean()) if len(winning) > 0 else 0
        avg_loss = float(losing.mean()) if len(losing) > 0 else 0
        edge_per_trade = float(net_returns[net_returns != 0].mean()) if n_trades > 0 else 0

        # Consecutive losses
        is_loss = net_returns < 0
        max_consec_loss = 0
        current_streak = 0
        for loss in is_loss:
            if loss:
                current_streak += 1
                max_consec_loss = max(max_consec_loss, current_streak)
            else:
                current_streak = 0

        metrics = {
            "total_return": round(total_return, 4),
            "annualized_return": round(ann_return, 4),
            "annualized_vol": round(ann_vol, 4),
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_dd, 4),
            "calmar": round(calmar, 3),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 3),
            "n_trades": n_trades,
            "n_days": len(returns),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "edge_per_trade": round(edge_per_trade, 6),
            "max_consecutive_losses": max_consec_loss,
            "transaction_costs_total": round(float(costs.sum()), 6),
        }

        # Regime-specific breakdown
        if regime_labels is not None and len(regime_labels) == len(returns):
            regime_breakdown = {}
            for regime in np.unique(regime_labels):
                mask = regime_labels == regime
                if mask.sum() > 10:
                    r_returns = returns[mask]
                    r_signals = signals[mask]
                    r_strat = r_returns * r_signals
                    r_equity = np.cumprod(1 + r_strat)
                    r_peak = np.maximum.accumulate(r_equity)
                    r_dd = np.max((r_peak - r_equity) / (r_peak + 1e-8))

                    regime_breakdown[str(regime)] = {
                        "n_days": int(mask.sum()),
                        "return": round(float(r_strat.sum()), 4),
                        "sharpe": round(float(r_strat.mean() / (r_strat.std() + 1e-8) * np.sqrt(252)), 3),
                        "max_dd": round(float(r_dd), 4),
                        "win_rate": round(float(np.mean(r_strat > 0)), 4),
                    }
            metrics["regime_breakdown"] = regime_breakdown

        return metrics

    def _empty_metrics(self) -> Dict:
        return {
            "total_return": 0, "sharpe": 0, "max_drawdown": 0, "calmar": 0,
            "win_rate": 0, "profit_factor": 0, "n_trades": 0, "n_days": 0,
        }

    def run(self, df: pd.DataFrame, strategy_func, regime_col: str = "regime_id") -> Dict:
        """
        Execute walk-forward validation.
        
        Args:
            df: DataFrame with columns [returns, ...features]
            strategy_func: callable(train_df) -> callable that takes a row and returns signal
            regime_col: column name for regime labels
            
        Returns:
            Dict with per-fold and aggregate metrics
        """
        n = len(df)
        if n < self.min_train_days + 60:
            logger.warning(f"Insufficient data for WFO: {n} rows (need {self.min_train_days + 60})")
            return {"error": "insufficient_data", "n_rows": n}

        window_size = int(n * (self.train_pct + self.val_pct + self.test_pct))
        if window_size > n:
            window_size = n

        train_size = int(window_size * self.train_pct)
        val_size = int(window_size * self.val_pct)
        test_size = window_size - train_size - val_size

        fold_results = []
        fold_id = 0
        start = 0

        logger.info(f"📊 Starting Walk-Forward Validation: {n} rows, "
                     f"window={window_size} (train={train_size}, val={val_size}, test={test_size}), "
                     f"step={self.step_size}")

        while start + train_size + val_size + test_size <= n:
            train_end = start + train_size
            val_end = train_end + val_size
            test_end = val_end + test_size

            train_df = df.iloc[start:train_end]
            val_df = df.iloc[train_end:val_end]
            test_df = df.iloc[val_end:test_end]

            logger.info(f"  Fold {fold_id}: Train [{start}:{train_end}] "
                         f"Val [{train_end}:{val_end}] Test [{val_end}:{test_end}]")

            try:
                # Train the strategy
                signal_generator = strategy_func(train_df)

                # Validate
                val_signals = np.array([signal_generator(row) for _, row in val_df.iterrows()])
                val_returns = val_df["returns_1d"].values if "returns_1d" in val_df.columns else val_df["nifty_returns"].values
                val_regimes = val_df[regime_col].values if regime_col in val_df.columns else None
                val_metrics = self._compute_metrics(val_returns, val_signals, val_regimes)

                # Test (out-of-sample)
                test_signals = np.array([signal_generator(row) for _, row in test_df.iterrows()])
                test_returns = test_df["returns_1d"].values if "returns_1d" in test_df.columns else test_df["nifty_returns"].values
                test_regimes = test_df[regime_col].values if regime_col in test_df.columns else None
                test_metrics = self._compute_metrics(test_returns, test_signals, test_regimes)

                fold_results.append({
                    "fold_id": fold_id,
                    "train_range": [start, train_end],
                    "val_range": [train_end, val_end],
                    "test_range": [val_end, test_end],
                    "validation": val_metrics,
                    "test_oos": test_metrics,
                    "overfit_ratio": round(val_metrics["sharpe"] / (test_metrics["sharpe"] + 1e-8), 3),
                })

            except Exception as e:
                logger.error(f"  Fold {fold_id} failed: {e}")
                fold_results.append({
                    "fold_id": fold_id,
                    "error": str(e)[:200],
                })

            start += self.step_size
            fold_id += 1

        # Aggregate
        valid_folds = [f for f in fold_results if "test_oos" in f]
        if valid_folds:
            agg_test_sharpe = np.mean([f["test_oos"]["sharpe"] for f in valid_folds])
            agg_test_dd = np.mean([f["test_oos"]["max_drawdown"] for f in valid_folds])
            agg_test_wr = np.mean([f["test_oos"]["win_rate"] for f in valid_folds])
            agg_overfit = np.mean([f["overfit_ratio"] for f in valid_folds])
        else:
            agg_test_sharpe = agg_test_dd = agg_test_wr = agg_overfit = 0

        result = {
            "n_folds": len(fold_results),
            "n_valid_folds": len(valid_folds),
            "aggregate": {
                "avg_oos_sharpe": round(float(agg_test_sharpe), 3),
                "avg_oos_max_dd": round(float(agg_test_dd), 4),
                "avg_oos_win_rate": round(float(agg_test_wr), 4),
                "avg_overfit_ratio": round(float(agg_overfit), 3),
                "passes_minimum_bar": agg_test_sharpe > 0.5,
            },
            "folds": fold_results,
            "config": {
                "train_pct": self.train_pct,
                "val_pct": self.val_pct,
                "test_pct": self.test_pct,
                "step_size": self.step_size,
                "transaction_cost_bps": self.transaction_cost_bps,
            },
            "computed_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"✅ Walk-Forward complete: {len(valid_folds)} folds | "
                     f"Avg OOS Sharpe: {agg_test_sharpe:.3f} | "
                     f"Avg OOS MaxDD: {agg_test_dd:.2%} | "
                     f"Overfit Ratio: {agg_overfit:.2f} | "
                     f"{'✅ PASSES' if agg_test_sharpe > 0.5 else '❌ FAILS'} minimum bar")

        return result

    def persist_results(self, results: Dict, strategy_name: str):
        """Save WFO results to database."""
        try:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS wfo_results (
                    id SERIAL PRIMARY KEY,
                    strategy_name VARCHAR(255),
                    n_folds INTEGER,
                    avg_oos_sharpe REAL,
                    avg_oos_max_dd REAL,
                    avg_oos_win_rate REAL,
                    overfit_ratio REAL,
                    passes_minimum_bar BOOLEAN,
                    full_results JSONB,
                    computed_at TIMESTAMP DEFAULT NOW()
                )
            """)
            agg = results.get("aggregate", {})
            cur.execute("""
                INSERT INTO wfo_results 
                (strategy_name, n_folds, avg_oos_sharpe, avg_oos_max_dd,
                 avg_oos_win_rate, overfit_ratio, passes_minimum_bar, full_results)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                strategy_name,
                results.get("n_valid_folds", 0),
                agg.get("avg_oos_sharpe"),
                agg.get("avg_oos_max_dd"),
                agg.get("avg_oos_win_rate"),
                agg.get("avg_overfit_ratio"),
                agg.get("passes_minimum_bar", False),
                json.dumps(results),
            ))
            conn.commit()
            cur.close()
            conn.close()
            logger.info(f"💾 WFO results persisted for strategy: {strategy_name}")
        except Exception as e:
            logger.error(f"Failed to persist WFO results: {e}")
