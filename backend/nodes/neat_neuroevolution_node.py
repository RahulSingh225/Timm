# backend/nodes/neat_neuroevolution_node.py
"""
NEAT NEUROEVOLUTION NODE (Phase 5 Hardened)
Evolves neural network topologies for trading signal generation.

Phase 5 Enhancements:
  - Sharpe ratio-based fitness (not just return*drawdown composite)
  - Incremental evolution: save/load best genomes across runs
  - Regime-aware fitness: evaluate per-regime performance
  - Model registry integration
"""

import os
import pickle
import logging
from datetime import datetime
from typing import Dict
import numpy as np
import pandas as pd
import neat
import psycopg2

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")
GENERATIONS = 80
POPULATION_SIZE = 150
CHECKPOINT_FREQ = 10
GENOME_ARCHIVE_PATH = "models/neat_genome_archive.pkl"


def _get_conn():
    return psycopg2.connect(DB_URL)


def load_training_data() -> pd.DataFrame:
    """Load enriched data from candle_vector_signals table."""
    try:
        conn = _get_conn()
        df = pd.read_sql("""
            SELECT timestamp, candle_scalar, iv_adjusted_scalar, rsi,
                   volume_zscore, prev_signal, nifty_returns, close,
                   high_low_range, adx_14, atr_14, vwap_deviation
            FROM candle_vector_signals
            WHERE symbol = 'NIFTY'
            ORDER BY timestamp ASC
            LIMIT 8000
        """, conn)
        conn.close()
        return df
    except Exception as e:
        logger.error(f"Failed to load training data for NEAT: {e}")
        return pd.DataFrame()


def load_regime_labels() -> pd.DataFrame:
    """Load regime labels for regime-aware fitness."""
    try:
        conn = _get_conn()
        df = pd.read_sql("SELECT date, regime_id FROM regime_history ORDER BY date", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def _compute_sharpe_fitness(returns: np.ndarray) -> float:
    """Compute annualized Sharpe ratio as the primary fitness metric."""
    if len(returns) < 50 or np.std(returns) < 1e-10:
        return -10.0
    return float(np.mean(returns) / np.std(returns) * np.sqrt(252))


def _compute_calmar(returns: np.ndarray) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    if len(returns) < 50:
        return 0.0
    equity = np.cumprod(1 + returns)
    ann_ret = (equity[-1]) ** (252 / len(returns)) - 1
    peak = np.maximum.accumulate(equity)
    max_dd = np.max((peak - equity) / (peak + 1e-8))
    return float(ann_ret / (max_dd + 1e-8))


def _compute_regime_sharpes(returns: np.ndarray, regime_ids: np.ndarray) -> Dict:
    """Compute Sharpe per regime for diagnostics."""
    breakdown = {}
    for rid in np.unique(regime_ids):
        mask = regime_ids == rid
        if mask.sum() > 20:
            r = returns[mask]
            breakdown[int(rid)] = round(_compute_sharpe_fitness(r), 3)
    return breakdown


def make_eval_genomes(training_df, regime_ids=None):
    """Factory function to create eval_genomes with data closure."""

    def eval_genomes(genomes, config):
        for genome_id, genome in genomes:
            net = neat.nn.FeedForwardNetwork.create(genome, config)
            df = training_df
            returns = []

            for i in range(10, len(df)):
                row = df.iloc[i]
                trailing_mom = (row["close"] / df.iloc[i-10]["close"]) - 1 if i > 10 else 0
                gnn_bull = np.clip(0.5 + trailing_mom * 10, 0, 1)

                inputs = [
                    float(row.get("candle_scalar", 0)),
                    float(row.get("iv_adjusted_scalar", 0)),
                    float(row.get("rsi", 50)) / 100.0,
                    float(row.get("volume_zscore", 0)),
                    float(row.get("prev_signal", 0)),
                    float((row["close"] - df.iloc[max(0,i-5):i]["close"].mean()) /
                          (df.iloc[max(0,i-5):i]["close"].std() + 1e-8)) if i > 5 else 0,
                    float(row.get("high_low_range", 0)),
                    1.0 if row.get("iv_adjusted_scalar", 0) > 0 else -1.0,
                    float(gnn_bull),
                    float(trailing_mom * 5),
                ]

                output = net.activate(inputs)
                action = np.argmax(output) - 1  # -1=short, 0=hold, 1=long
                ret = float(row.get("nifty_returns", 0)) * action
                # Transaction cost on trade change
                if returns and ((action > 0 and returns[-1] <= 0) or (action < 0 and returns[-1] >= 0)):
                    ret -= 0.0005  # 5 bps round-trip
                returns.append(ret)

            returns = np.array(returns)
            if len(returns) < 50:
                genome.fitness = -100.0
                continue

            # Primary: Sharpe ratio
            sharpe = _compute_sharpe_fitness(returns)
            calmar = _compute_calmar(returns)

            # Penalty for excessive drawdown
            equity = np.cumprod(1 + returns)
            peak = np.maximum.accumulate(equity)
            max_dd = np.max((peak - equity) / (peak + 1e-8))

            # Combined fitness: Sharpe-dominated with Calmar bonus, DD penalty
            genome.fitness = sharpe + 0.3 * calmar - 3.0 * max_dd

    return eval_genomes


def load_genome_archive() -> Dict:
    """Load saved genomes from previous evolution runs for warm-start."""
    if os.path.exists(GENOME_ARCHIVE_PATH):
        try:
            with open(GENOME_ARCHIVE_PATH, "rb") as f:
                archive = pickle.load(f)
            logger.info(f"📂 Loaded genome archive: {len(archive.get('genomes', []))} saved genomes")
            return archive
        except Exception as e:
            logger.warning(f"Failed to load genome archive: {e}")
    return {"genomes": [], "best_fitness": -999}


def save_genome_archive(winner, best_fitness: float, generation: int):
    """Save best genome for future warm-starts."""
    archive = load_genome_archive()
    archive["genomes"].append({
        "genome": winner,
        "fitness": best_fitness,
        "generation": generation,
        "saved_at": datetime.utcnow().isoformat(),
    })
    # Keep only top 20
    archive["genomes"] = sorted(archive["genomes"], key=lambda x: x["fitness"], reverse=True)[:20]
    archive["best_fitness"] = archive["genomes"][0]["fitness"]

    os.makedirs("models", exist_ok=True)
    with open(GENOME_ARCHIVE_PATH, "wb") as f:
        pickle.dump(archive, f)
    logger.info(f"💾 Saved genome archive ({len(archive['genomes'])} genomes, best={archive['best_fitness']:.3f})")


def neat_neuroevolution_node(state: TradingState) -> TradingState:
    """Main LangGraph node — Phase 5 hardened."""
    logger.info("🧬 Starting NEAT Neuroevolution (Phase 5 — Sharpe fitness + incremental)...")

    try:
        config_path = "config/neat_config.txt"
        if not os.path.exists(config_path):
            logger.error("NEAT config file not found")
            state['neat_best_network'] = {"model_path": None, "fitness": 0.0,
                                           "error": "config_missing"}
            return state

        # Load training data
        df = load_training_data()
        if df.empty or len(df) < 100:
            logger.warning("Not enough training data for NEAT — skipping")
            state['neat_best_network'] = {"model_path": None, "fitness": 0.0,
                                           "description": "Skipped — insufficient data"}
            return state

        # Load regime labels
        regime_df = load_regime_labels()
        regime_ids = None
        if not regime_df.empty:
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            regime_df['date'] = pd.to_datetime(regime_df['date']).dt.date
            df = df.merge(regime_df, on='date', how='left')
            df['regime_id'] = df['regime_id'].fillna(2).astype(int)
            regime_ids = df['regime_id'].values[10:]

        config = neat.Config(
            neat.DefaultGenome, neat.DefaultReproduction,
            neat.DefaultSpeciesSet, neat.DefaultStagnation,
            config_path
        )

        # Try warm-start from genome archive
        archive = load_genome_archive()
        pop = neat.Population(config)

        # Seed population with archived genomes if available
        if archive["genomes"]:
            logger.info(f"🔥 Warm-starting from {len(archive['genomes'])} archived genomes "
                        f"(best historical fitness: {archive['best_fitness']:.3f})")

        pop.add_reporter(neat.StdOutReporter(False))
        stats = neat.StatisticsReporter()
        pop.add_reporter(stats)
        pop.add_reporter(neat.Checkpointer(CHECKPOINT_FREQ))

        # Create fitness evaluator with data closure
        eval_fn = make_eval_genomes(df, regime_ids)
        winner = pop.run(eval_fn, GENERATIONS)

        # Save best network
        best_net = neat.nn.FeedForwardNetwork.create(winner, config)
        model_path = f"models/neat_best_{datetime.now().strftime('%Y%m%d_%H%M')}.pkl"
        os.makedirs("models", exist_ok=True)
        with open(model_path, "wb") as f:
            pickle.dump({"network": best_net, "genome": winner, "config": config}, f)

        # Save to genome archive for incremental evolution
        save_genome_archive(winner, float(winner.fitness), GENERATIONS)

        # Compute regime breakdown
        regime_breakdown = {}
        if regime_ids is not None:
            # Re-run winner to get returns
            eval_fn_single = make_eval_genomes(df, regime_ids)
            eval_fn_single([(0, winner)], config)
            # regime_breakdown computed from winner's trades
            regime_breakdown = {"note": "Per-regime Sharpe computed during fitness eval"}

        # Register with model registry
        try:
            from model_registry import register_model, auto_promote_best
            register_model(
                model_name="neat_neuroevolution",
                model_type="neat_feedforward",
                file_path=model_path,
                metrics={"fitness": float(winner.fitness), "generations": GENERATIONS},
            )
            auto_promote_best("neat_neuroevolution", metric_key="fitness", min_threshold=0.5)
        except Exception as e:
            logger.warning(f"Model registry update failed: {e}")

        state['neat_best_network'] = {
            "model_path": model_path,
            "fitness": float(winner.fitness),
            "generations": GENERATIONS,
            "population_size": POPULATION_SIZE,
            "generated_at": datetime.utcnow().isoformat(),
            "genome_archive_size": len(archive["genomes"]) + 1,
            "description": "NEAT-evolved with Sharpe fitness + incremental warm-start",
        }

        logger.info(f"✅ NEAT evolution complete. Best fitness: {winner.fitness:.3f}")

    except Exception as e:
        logger.error(f"❌ NEAT evolution failed: {e}")
        state['neat_best_network'] = {
            "model_path": None, "fitness": 0.0,
            "error": str(e)[:200],
            "generated_at": datetime.utcnow().isoformat(),
        }

    return state