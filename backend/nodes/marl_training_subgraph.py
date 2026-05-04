# backend/nodes/marl_training_subgraph.py
"""
MARL TRAINING SUBGRAPH (Phase 5 Hardened)
Trains PPO agents with curriculum learning: easy regimes first, then hard.
Integrates GNN regime signals into observation space via trading_env.
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

# Curriculum order: train on easy regimes first, then harder ones
CURRICULUM_ORDER = [
    (0, "TRENDING_BULL", 30000),    # Easiest: clear trends
    (2, "MEAN_REVERTING", 30000),   # Medium: range-bound
    (1, "TRENDING_BEAR", 25000),    # Harder: bear markets
    (3, "HIGH_VOL_EXPANSION", 15000),  # Hardest: vol spikes
    (None, "ALL_REGIMES", 50000),   # Final: mixed conditions
]


def marl_training_subgraph(state: TradingState) -> TradingState:
    logger.info("🤖 Starting MARL Training (Phase 5 — Curriculum + Calmar reward)...")

    try:
        latest_model_path = "models/marl_ppo_latest.zip"
        model = None

        for regime_id, regime_name, timesteps in CURRICULUM_ORDER:
            logger.info(f"  📚 Curriculum stage: {regime_name} ({timesteps} steps)...")

            env = DummyVecEnv([
                lambda r=regime_id: NiftyMARLEnv(curriculum_regime=r)
                for _ in range(4)
            ])

            if model is None:
                if os.path.exists(latest_model_path):
                    logger.info(f"  Loading existing PPO model for warm-start")
                    model = PPO.load(latest_model_path, env=env)
                else:
                    model = PPO(
                        "MlpPolicy", env, verbose=0,
                        learning_rate=3e-4, n_steps=2048, batch_size=64,
                        gae_lambda=0.95, gamma=0.99,
                        ent_coef=0.01,  # Encourage exploration
                        tensorboard_log="./tensorboard/marl/",
                        device="cuda" if torch.cuda.is_available() else "cpu",
                    )
            else:
                model.set_env(env)

            model.learn(total_timesteps=timesteps, progress_bar=False,
                        reset_num_timesteps=False)
            logger.info(f"  ✅ {regime_name} stage complete")

        # Save
        os.makedirs("models", exist_ok=True)
        model_path = f"models/marl_ppo_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        model.save(model_path)
        model.save(latest_model_path)

        mean_reward = 0.0
        try:
            if model.logger and hasattr(model.logger, 'name_to_value'):
                mean_reward = float(model.logger.name_to_value.get("rollout/ep_rew_mean", 0))
        except Exception:
            pass

        # Register with model registry
        try:
            from model_registry import register_model, auto_promote_best
            register_model("marl_ppo", "ppo_mlp", model_path,
                           {"mean_reward": mean_reward, "curriculum": True})
            auto_promote_best("marl_ppo", metric_key="mean_reward", min_threshold=0)
        except Exception as e:
            logger.warning(f"Model registry failed: {e}")

        state['marl_policy'] = {
            "model_path": model_path,
            "trained_at": datetime.utcnow().isoformat(),
            "mean_reward": mean_reward,
            "curriculum_stages": len(CURRICULUM_ORDER),
            "description": "PPO with curriculum learning (easy→hard regimes) + Calmar reward",
        }
        logger.info(f"✅ MARL training complete. Policy: {model_path}")

    except Exception as e:
        logger.error(f"❌ MARL training failed: {e}")
        state['marl_policy'] = {
            "model_path": None, "mean_reward": 0.0,
            "error": str(e)[:200],
            "trained_at": datetime.utcnow().isoformat(),
        }

    return state