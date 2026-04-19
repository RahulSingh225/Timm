# backend/trading_env.py
"""
Custom Multi-Agent RL Environment for NIFTY Intraday + Options.
Uses Gymnasium (the maintained fork of OpenAI Gym).
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

def _get_conn():
    return psycopg2.connect(DB_URL)


class NiftyMARLEnv(gym.Env):
    """Custom Multi-Agent RL Environment for NIFTY Intraday + Options"""
    
    def __init__(self, df: pd.DataFrame = None, max_steps=500):
        super().__init__()
        self.max_steps = max_steps
        self.current_step = 0
        
        if df is None:
            self.df = self._load_data()
        else:
            self.df = df

        # If no data available, create a minimal synthetic dataset for graceful degradation
        if self.df.empty or len(self.df) < 20:
            logger.warning("No training data found — using synthetic random walk for MARL env")
            self.df = self._generate_synthetic_data()
            
        # Observation space: features from candle_vector + market context + 2 GNN embeddings
        self.observation_space = spaces.Box(low=-10, high=10, shape=(14,), dtype=np.float32)
        
        # Action space: -1 (short/put), 0 (hold), 1 (long/call) + position size
        self.action_space = spaces.Discrete(5)  # 0=strong short, 1=short, 2=hold, 3=long, 4=strong long

    def _generate_synthetic_data(self) -> pd.DataFrame:
        """Generate a minimal synthetic dataset so the env doesn't crash on empty DB."""
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
        })

    def _load_data(self):
        try:
            conn = _get_conn()
            df = pd.read_sql("""
                SELECT * FROM candle_vector_signals 
                WHERE symbol = 'NIFTY' ORDER BY timestamp ASC LIMIT 10000
            """, conn)
            conn.close()
            return df
        except Exception as e:
            logger.warning(f"Failed to fetch MARL env data: {e}")
            return pd.DataFrame()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.equity = 100000.0
        self.position = 0
        return self._get_obs(), {}

    def _get_obs(self):
        if self.current_step >= len(self.df):
            self.current_step = len(self.df) - 1

        row = self.df.iloc[self.current_step]
        
        # Proxy GNN 'Bull Rotation' confidence based on trailing return behavior
        trailing_momentum = (row["close"] / self.df.iloc[max(0, self.current_step - 10)]["close"]) - 1 if self.current_step > 10 else 0
        gnn_bull_conf = np.clip(0.5 + (trailing_momentum * 10), 0, 1)
        gnn_rotation_strength = trailing_momentum * 5
        
        return np.array([
            row.get("candle_scalar", 0), row.get("iv_adjusted_scalar", 0), row.get("rsi", 50) / 100,
            row.get("volume_zscore", 0), row.get("prev_signal", 0),
            self.position, self.equity / 100000,
            row.get("high_low_range", 0), 0.0, 0.0, 0.0, 0.0,
            gnn_bull_conf, gnn_rotation_strength
        ], dtype=np.float32)

    def step(self, action):
        row = self.df.iloc[self.current_step]
        price_move = row.get("nifty_returns", 0)
        
        # Map action to position change
        action_map = {-2: -1, -1: -0.5, 0: 0, 1: 0.5, 2: 1}
        target_pos = action_map.get(action - 2, 0)
        
        trade = target_pos - self.position
        cost = abs(trade) * 0.0005 * abs(price_move) * 100000  # slippage + brokerage approx
        
        reward = (price_move * target_pos * 100) - cost - 0.01 * abs(trade)
        
        self.position = target_pos
        self.equity += reward * 1000
        self.current_step += 1
        
        terminated = self.current_step >= min(self.max_steps, len(self.df) - 1) or self.equity < 50000
        truncated = False
        
        return self._get_obs(), reward, terminated, truncated, {"equity": self.equity}