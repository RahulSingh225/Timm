# backend/trading_env.py
"""
Custom Multi-Agent RL Environment for NIFTY Intraday + Options.
Uses Gymnasium. Phase 5 hardened with:
  - Transaction cost modeling (brokerage + STT + slippage)
  - Calmar-based reward shaping (penalize drawdown, reward risk-adj returns)
  - Regime-aware observation space (regime_id injected from HMM)
  - Position sizing as continuous action output
  - Curriculum learning support (easy→hard regime progression)
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces
import pandas as pd
import os
import psycopg2
import logging

logger = logging.getLogger(__name__)
DB_URL = os.getenv("DATABASE_URL")

# Indian equity transaction costs (per side)
BROKERAGE_PCT = 0.0003       # 0.03% (discount broker)
STT_PCT = 0.001              # 0.1% STT on sell side (equity delivery)
STT_INTRADAY_PCT = 0.00025   # 0.025% STT on sell side (intraday)
EXCHANGE_CHARGES = 0.0000345  # NSE transaction charges
GST_PCT = 0.18               # GST on brokerage
SLIPPAGE_BPS = 2              # 2 bps average slippage


def _get_conn():
    return psycopg2.connect(DB_URL)


class NiftyMARLEnv(gym.Env):
    """Phase 5 hardened Multi-Agent RL Environment."""

    metadata = {"render_modes": []}

    def __init__(self, df=None, max_steps=500, curriculum_regime=None):
        super().__init__()
        self.max_steps = max_steps
        self.current_step = 0
        self.curriculum_regime = curriculum_regime  # None = all, 0-3 = specific regime

        if df is None:
            self.df = self._load_data()
        else:
            self.df = df

        if self.df.empty or len(self.df) < 20:
            logger.warning("No training data — using synthetic random walk")
            self.df = self._generate_synthetic_data()

        # Filter by curriculum regime if specified
        if self.curriculum_regime is not None and 'regime_id' in self.df.columns:
            regime_df = self.df[self.df['regime_id'] == self.curriculum_regime]
            if len(regime_df) > 50:
                self.df = regime_df.reset_index(drop=True)
                logger.info(f"📚 Curriculum: training on regime {self.curriculum_regime} "
                            f"({len(self.df)} samples)")

        # Observation: 16 features (market + position + regime)
        self.observation_space = spaces.Box(low=-10, high=10, shape=(16,), dtype=np.float32)

        # Action: 7 discrete (position sizing: -1.0, -0.5, -0.25, 0, 0.25, 0.5, 1.0)
        self.action_space = spaces.Discrete(7)
        self._action_map = {0: -1.0, 1: -0.5, 2: -0.25, 3: 0.0, 4: 0.25, 5: 0.5, 6: 1.0}

    def _generate_synthetic_data(self):
        n = self.max_steps + 50
        np.random.seed(42)
        close = 22000 + np.cumsum(np.random.randn(n) * 50)
        return pd.DataFrame({
            "candle_scalar": np.random.randn(n) * 0.5,
            "iv_adjusted_scalar": np.random.randn(n) * 0.3,
            "rsi": np.clip(50 + np.random.randn(n) * 15, 10, 90),
            "volume_zscore": np.random.randn(n),
            "prev_signal": np.zeros(n),
            "close": close,
            "nifty_returns": np.diff(close, prepend=close[0]) / close,
            "high_low_range": np.abs(np.random.randn(n) * 0.5),
            "regime_id": np.random.choice([0, 1, 2, 3], n, p=[0.3, 0.2, 0.35, 0.15]),
            "adx_14": np.clip(20 + np.random.randn(n) * 10, 5, 60),
        })

    def _load_data(self):
        try:
            conn = _get_conn()
            df = pd.read_sql("""
                SELECT timestamp, candle_scalar, iv_adjusted_scalar, rsi,
                       volume_zscore, prev_signal, close, nifty_returns,
                       high_low_range, adx_14, atr_14, vwap_deviation
                FROM candle_vector_signals
                WHERE symbol = 'NIFTY' ORDER BY timestamp ASC LIMIT 10000
            """, conn)
            conn.close()
            # Try to merge regime labels
            try:
                conn2 = _get_conn()
                regime_df = pd.read_sql("SELECT date, regime_id FROM regime_history", conn2)
                conn2.close()
                if not regime_df.empty and 'timestamp' in df.columns:
                    df['date'] = pd.to_datetime(df['timestamp']).dt.date
                    regime_df['date'] = pd.to_datetime(regime_df['date']).dt.date
                    df = df.merge(regime_df, on='date', how='left')
                    df['regime_id'] = df['regime_id'].fillna(2).astype(int)
            except Exception:
                df['regime_id'] = 2
            return df
        except Exception as e:
            logger.warning(f"Failed to fetch MARL env data: {e}")
            return pd.DataFrame()

    def _compute_transaction_cost(self, trade_size_abs, price):
        """Compute realistic Indian equity transaction costs."""
        trade_value = trade_size_abs * price
        brokerage = trade_value * BROKERAGE_PCT * 2  # Both sides
        stt = trade_value * STT_INTRADAY_PCT          # Sell side only
        exchange = trade_value * EXCHANGE_CHARGES * 2
        gst = brokerage * GST_PCT
        slippage = trade_value * SLIPPAGE_BPS / 10000
        return brokerage + stt + exchange + gst + slippage

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 10  # Skip warmup rows
        self.equity = 100000.0
        self.peak_equity = 100000.0
        self.position = 0.0
        self.position_size = 0.0
        self.trades = 0
        self.wins = 0
        self.trade_returns = []
        return self._get_obs(), {}

    def _get_obs(self):
        if self.current_step >= len(self.df):
            self.current_step = len(self.df) - 1
        row = self.df.iloc[self.current_step]

        trailing_mom = 0
        if self.current_step > 10:
            trailing_mom = (row["close"] / self.df.iloc[self.current_step - 10]["close"]) - 1
        gnn_bull = np.clip(0.5 + trailing_mom * 10, 0, 1)

        return np.array([
            float(row.get("candle_scalar", 0)),
            float(row.get("iv_adjusted_scalar", 0)),
            float(row.get("rsi", 50)) / 100.0,
            float(row.get("volume_zscore", 0)),
            float(row.get("prev_signal", 0)),
            float(self.position),
            float(self.equity / 100000.0),
            float(row.get("high_low_range", 0)),
            float(row.get("adx_14", 25)) / 50.0,      # Normalized ADX
            float(row.get("regime_id", 2)) / 3.0,       # Regime signal (0-1)
            float(trailing_mom * 10),                    # Momentum
            float(gnn_bull),                             # GNN proxy
            float(self.peak_equity / self.equity - 1),   # Current drawdown
            float(self.trades / 100.0),                  # Trade count (normalized)
            float(self.wins / max(self.trades, 1)),      # Running win rate
            float(trailing_mom * 5),                     # GNN rotation proxy
        ], dtype=np.float32)

    def step(self, action):
        row = self.df.iloc[self.current_step]
        price_move = float(row.get("nifty_returns", 0))
        close_price = float(row.get("close", 22000))

        # Map action to target position with sizing
        target_pos = self._action_map[action]
        trade = target_pos - self.position

        # Transaction costs on position change
        cost = 0.0
        if abs(trade) > 0.01:
            cost = self._compute_transaction_cost(abs(trade), close_price)
            cost = cost / self.equity  # Normalize to portfolio fraction
            self.trades += 1

        # P&L from holding
        pnl = price_move * self.position
        net_pnl = pnl - cost

        if net_pnl > 0:
            self.wins += 1
        self.trade_returns.append(net_pnl)

        self.equity *= (1 + net_pnl)
        self.peak_equity = max(self.peak_equity, self.equity)
        self.position = target_pos
        self.current_step += 1

        # ── Reward shaping (Calmar-inspired) ──
        # Base: risk-adjusted return
        reward = net_pnl * 100  # Scale up

        # Drawdown penalty
        current_dd = (self.peak_equity - self.equity) / self.peak_equity
        if current_dd > 0.05:
            reward -= current_dd * 50  # Harsh penalty above 5% DD
        elif current_dd > 0.02:
            reward -= current_dd * 20

        # Trade frequency penalty (discourage overtrading)
        if abs(trade) > 0.01:
            reward -= 0.1

        # Win rate bonus (encourage consistency)
        if self.trades > 10:
            wr = self.wins / self.trades
            if wr > 0.55:
                reward += 0.05 * (wr - 0.5)

        terminated = (self.current_step >= min(self.max_steps, len(self.df) - 1)
                      or self.equity < 50000)
        truncated = False

        return self._get_obs(), float(reward), terminated, truncated, {
            "equity": self.equity, "drawdown": current_dd,
            "trades": self.trades, "win_rate": self.wins / max(self.trades, 1),
        }