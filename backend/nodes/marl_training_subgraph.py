# backend/nodes/marl_training_subgraph.py
"""
MARL TRAINING SUBGRAPH
Trains multiple agents cooperatively using PPO with parameter sharing.
Integrates GP, NEAT, and candle_vector signals.
Includes graceful fallback when no training data is available.
"""

import os
import logging
from datetime import datetime
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from trading_env import NiftyMARLEnv
from langgraph_state import TradingState

logger = logging.getLogger(__name__)


def marl_training_subgraph(state: TradingState) -> TradingState:
    logger.info("🤖 Starting MARL Training Subgraph (PPO Multi-Agent)...")

    try:
        # Load latest data enriched with all previous signals
        env = DummyVecEnv([lambda: NiftyMARLEnv() for _ in range(4)])  # 4 parallel envs for faster training

        # Check for existing model to warm-start from
        latest_model_path = "models/marl_ppo_latest.zip"
        if os.path.exists(latest_model_path):
            logger.info(f"Loading existing PPO model from {latest_model_path}")
            model = PPO.load(latest_model_path, env=env)
        else:
            model = PPO(
                "MlpPolicy",
                env,
                verbose=1,
                learning_rate=3e-4,
                n_steps=2048,
                batch_size=64,
                gae_lambda=0.95,
                gamma=0.99,
                tensorboard_log="./tensorboard/marl/",
                device="cuda" if torch.cuda.is_available() else "cpu"
            )

        # Train
        model.learn(total_timesteps=100000, progress_bar=True)

        # Save the trained policy (both timestamped and latest)
        os.makedirs("models", exist_ok=True)
        model_path = f"models/marl_ppo_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        model.save(model_path)
        model.save(latest_model_path)

        # Extract mean reward safely
        mean_reward = 0.0
        try:
            if model.logger and hasattr(model.logger, 'name_to_value'):
                mean_reward = float(model.logger.name_to_value.get("rollout/ep_rew_mean", 0))
        except Exception:
            pass

        # Store in state for judge_node and live inference
        state['marl_policy'] = {
            "model_path": model_path,
            "trained_at": datetime.utcnow().isoformat(),
            "mean_reward": mean_reward,
            "description": "Multi-Agent PPO policy for coordinated intraday + options decisions"
        }

        logger.info(f"✅ MARL training complete. Policy saved: {model_path}")

    except Exception as e:
        logger.error(f"❌ MARL training failed: {e}")
        state['marl_policy'] = {
            "model_path": None,
            "trained_at": datetime.utcnow().isoformat(),
            "mean_reward": 0.0,
            "error": str(e)[:200],
            "description": "MARL training failed — see error"
        }

    return state