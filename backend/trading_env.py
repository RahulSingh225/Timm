# backend/env/trading_env.py
import gym
import numpy as np
from gym import spaces
import pandas as pd
import os
import psycopg2

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
            
        # Observation space: features from candle_vector + market context + 2 GNN embeddings
        self.observation_space = spaces.Box(low=-10, high=10, shape=(14,), dtype=np.float32)
        
        # Action space: -1 (short/put), 0 (hold), 1 (long/call) + position size
        self.action_space = spaces.Discrete(5)  # 0=strong short, 1=short, 2=hold, 3=long, 4=strong long

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
            print(f"Failed to fetch MARL env data: {e}")
            return pd.DataFrame()

    def reset(self):
        self.current_step = 0
        self.equity = 100000.0
        self.position = 0
        return self._get_obs()

    def _get_obs(self):
        row = self.df.iloc[self.current_step]
        
        # Mocking the historical GNN state since we can't run GNN inference sequentially during step() efficiently
        # We proxy GNN 'Bull Rotation' confidence based on trailing return behavior
        trailing_momentum = (row["close"] / self.df.iloc[max(0, self.current_step - 10)]["close"]) - 1 if self.current_step > 10 else 0
        gnn_bull_conf = np.clip(0.5 + (trailing_momentum * 10), 0, 1)
        gnn_rotation_strength = trailing_momentum * 5 # proxy for inter-sector momentum shift
        
        return np.array([
            row["candle_scalar"], row["iv_adjusted_scalar"], row.get("rsi",50)/100,
            row.get("volume_zscore",0), row.get("prev_signal",0),
            self.position, self.equity/100000,  # normalized equity
            # Add more from NEAT/GP if available
            row.get("high_low_range",0), 0.0, 0.0, 0.0, 0.0,
            gnn_bull_conf, gnn_rotation_strength # The new GNN Hybrid integration vectors
        ], dtype=np.float32)

    def step(self, action):
        row = self.df.iloc[self.current_step]
        price_move = row["nifty_returns"]
        
        # Map action to position change
        action_map = {-2: -1, -1: -0.5, 0: 0, 1: 0.5, 2: 1}
        target_pos = action_map.get(action-2, 0)
        
        trade = target_pos - self.position
        cost = abs(trade) * 0.0005 * abs(price_move) * 100000  # slippage + brokerage approx
        
        reward = (price_move * target_pos * 100) - cost - 0.01 * abs(trade)  # P&L minus costs
        
        self.position = target_pos
        self.equity += reward * 1000  # scale for stability
        self.current_step += 1
        
        done = self.current_step >= self.max_steps or self.equity < 50000
        
        return self._get_obs(), reward, done, {"equity": self.equity}