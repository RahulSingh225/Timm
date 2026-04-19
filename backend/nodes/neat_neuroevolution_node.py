# backend/nodes/neat_neuroevolution_node.py
"""
NEAT NEUROEVOLUTION NODE
Evolves neural networks using candle_vector signals + IV + other features.
Outputs the best evolved network for use in intraday_builder_node and options_builder_node.
"""

import os
import pickle
import logging
from datetime import datetime
from typing import Dict, Any
import numpy as np
import pandas as pd
import neat
import psycopg2

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")

def _get_conn():
    return psycopg2.connect(DB_URL)


# ========================= CONFIG =========================
GENERATIONS = 80          # Increase slowly as your hardware allows
POPULATION_SIZE = 150
CHECKPOINT_FREQ = 10

# Input features from your candle_vector_agent + GNN
NUM_INPUTS = 10  # candle_scalar, iv_adjusted_scalar, rsi, volume_z, prev_signal, etc. + 2 GNN embeddings
NUM_OUTPUTS = 3  # e.g., [long_prob, short_prob, hold_prob] or position sizing
# =========================================================

def load_training_data() -> pd.DataFrame:
    """Load enriched data from your existing candle_vector_signals table"""
    try:
        conn = _get_conn()
        df = pd.read_sql("""
            SELECT 
                timestamp,
                candle_scalar,
                iv_adjusted_scalar,
                rsi,
                volume_zscore,
                prev_signal,
                nifty_returns,
                close,
                high_low_range
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

def eval_genomes(genomes, config):
    """Fitness function for each evolved network"""
    for genome_id, genome in genomes:
        net = neat.nn.FeedForwardNetwork.create(genome, config)
        
        df = load_training_data()
        returns = []
        
        for i in range(10, len(df)):  # start after warmup
            row = df.iloc[i]
            
            # Proxying the historical GNN state (similar to MARL)
            trailing_momentum = (row["close"] / df.iloc[i-10]["close"]) - 1
            gnn_bull_conf = np.clip(0.5 + (trailing_momentum * 10), 0, 1)
            gnn_rotation_strength = trailing_momentum * 5
            
            inputs = [
                row["candle_scalar"],
                row["iv_adjusted_scalar"],
                row.get("rsi", 50) / 100.0,
                row.get("volume_zscore", 0),
                row.get("prev_signal", 0),
                (row["close"] - df.iloc[i-5:i]["close"].mean()) / df.iloc[i-5:i]["close"].std() if i > 5 else 0,
                row.get("high_low_range", 0),
                1 if row["iv_adjusted_scalar"] > 0 else -1,
                gnn_bull_conf,
                gnn_rotation_strength
            ]
            
            output = net.activate(inputs)
            action = np.argmax(output) - 1  # -1=short, 0=hold, 1=long
            
            ret = row["nifty_returns"] * action
            returns.append(ret)
        
        returns = np.array(returns)
        if len(returns) < 50:
            genome.fitness = -100.0
            continue
            
        sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)
        total_return = np.prod(1 + returns) - 1
        max_dd = np.max(np.maximum.accumulate(np.cumprod(1 + returns)) - np.cumprod(1 + returns))
        
        # Multi-objective fitness (you can expand this)
        genome.fitness = sharpe * (1 + total_return) - 5 * max_dd

def neat_neuroevolution_node(state: TradingState) -> TradingState:
    """Main LangGraph node"""
    logger.info("🧬 Starting NEAT Neuroevolution Cycle...")

    try:
        # Load or create config
        config_path = "config/neat_config.txt"
        if not os.path.exists(config_path):
            logger.error("NEAT config file not found. Create config/neat_config.txt")
            state['neat_best_network'] = None
            return state

        # Check if we have training data before starting expensive evolution
        test_df = load_training_data()
        if test_df.empty or len(test_df) < 50:
            logger.warning("Not enough training data for NEAT evolution — skipping")
            state['neat_best_network'] = {
                "model_path": None,
                "fitness": 0.0,
                "generated_at": datetime.utcnow().isoformat(),
                "description": "NEAT skipped — insufficient training data"
            }
            return state

        config = neat.Config(
            neat.DefaultGenome, neat.DefaultReproduction,
            neat.DefaultSpeciesSet, neat.DefaultStagnation,
            config_path
        )

        # Create population
        pop = neat.Population(config)
        pop.add_reporter(neat.StdOutReporter(True))
        pop.add_reporter(neat.StatisticsReporter())
        pop.add_reporter(neat.Checkpointer(CHECKPOINT_FREQ))

        # Run evolution
        winner = pop.run(eval_genomes, GENERATIONS)

        # Save the best network
        best_net = neat.nn.FeedForwardNetwork.create(winner, config)
        
        model_path = f"models/neat_best_{datetime.now().strftime('%Y%m%d_%H%M')}.pkl"
        os.makedirs("models", exist_ok=True)
        with open(model_path, "wb") as f:
            pickle.dump({"network": best_net, "genome": winner, "config": config}, f)

        # Store in state for other nodes to use
        state['neat_best_network'] = {
            "model_path": model_path,
            "fitness": float(winner.fitness),
            "generated_at": datetime.utcnow().isoformat(),
            "description": "NEAT-evolved network for directional + sizing decisions"
        }

        logger.info(f"✅ NEAT evolution complete. Best fitness: {winner.fitness:.3f}")
        logger.info(f"Best network saved to {model_path}")

    except Exception as e:
        logger.error(f"❌ NEAT evolution failed: {e}")
        state['neat_best_network'] = {
            "model_path": None,
            "fitness": 0.0,
            "generated_at": datetime.utcnow().isoformat(),
            "error": str(e)[:200],
            "description": "NEAT evolution failed — see error"
        }

    return state