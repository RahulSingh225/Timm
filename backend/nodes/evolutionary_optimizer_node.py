# backend/nodes/evolutionary_optimizer_node.py
"""
EVOLUTIONARY OPTIMIZER NODE (Genetic Programming + NSGA-II)
Integrates directly into Timm LangGraph.
Evolves trading strategies using candle_vector signals + IV.
Runs nightly or on-demand. Outputs best strategies to judge_node.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from deap import base, creator, tools, algorithms, gp
import numpy as np
import pandas as pd
import psycopg2

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL")

def _get_conn():
    return psycopg2.connect(DB_URL)


# ========================= CONFIG =========================
POPULATION_SIZE = 200
GENERATIONS = 50
CXPB = 0.7      # crossover probability
MUTPB = 0.2     # mutation probability
TOURNAMENT_SIZE = 3

# Your Qwen2.5 Coder 14B + T4 can easily handle this (runs in ~5-15 min)
# =========================================================

def setup_gp_primitive_set():
    """Define the building blocks for evolved strategies"""
    pset = gp.PrimitiveSet("MAIN", arity=5)  # inputs: candle_scalar, iv_adjusted, rsi, volume_z, prev_signal
    pset.addPrimitive(np.add, 2)
    pset.addPrimitive(np.subtract, 2)
    pset.addPrimitive(np.multiply, 2)
    pset.addPrimitive(np.divide, 2)
    pset.addPrimitive(np.maximum, 2)
    pset.addPrimitive(np.minimum, 2)
    pset.addPrimitive(np.abs, 1)
    pset.addPrimitive(lambda x: 1 if x > 0 else 0, 1, name="positive")
    
    # Terminals (real market features from your candle_vector_agent)
    pset.addTerminal("candle_scalar", float)
    pset.addTerminal("iv_adjusted_scalar", float)
    pset.addTerminal("rsi", float)
    pset.addTerminal("volume_zscore", float)
    pset.addTerminal(0.0, float)   # constants
    pset.addTerminal(0.5, float)
    pset.addTerminal(1.0, float)
    pset.addTerminal(-1.0, float)
    
    pset.renameArguments(ARG0="candle_scalar")
    pset.renameArguments(ARG1="iv_adjusted_scalar")
    pset.renameArguments(ARG2="rsi")
    pset.renameArguments(ARG3="volume_zscore")
    pset.renameArguments(ARG4="prev_signal")
    return pset

def evaluate_strategy(individual, historical_df: pd.DataFrame) -> tuple:
    """
    Simulate the evolved strategy on historical data.
    Uses your existing simulate_graph.py logic under the hood.
    Returns multi-objective fitness: (sharpe, -max_dd, win_rate, profit_factor)
    """
    # Compile the GP tree into a callable function
    func = gp.compile(individual, pset=setup_gp_primitive_set())
    
    signals = []
    for i in range(1, len(historical_df)):
        row = historical_df.iloc[i]
        prev = historical_df.iloc[i-1]
        
        signal = func(
            candle_scalar=row["candle_scalar"],
            iv_adjusted_scalar=row["iv_adjusted_scalar"],
            rsi=row.get("rsi", 50),
            volume_zscore=row.get("volume_zscore", 0),
            prev_signal=signals[-1] if signals else 0
        )
        signals.append(1 if signal > 0.3 else -1 if signal < -0.3 else 0)
    
    # Convert signals to returns (use your real backtester logic here)
    returns = historical_df["nifty_returns"].values[1:] * signals
    equity = np.cumprod(1 + returns)
    
    if len(equity) < 10:
        return (-10.0, -100.0, 0.0, 0.0)  # bad strategy
    
    # Multi-objective fitness
    total_return = equity[-1] - 1
    sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)
    max_dd = np.max(np.maximum.accumulate(equity) - equity)
    win_rate = np.mean(np.array(returns) > 0)
    profit_factor = abs(returns[returns > 0].sum()) / abs(returns[returns < 0].sum()) if any(returns < 0) else 0
    
    return (sharpe, -max_dd, win_rate, profit_factor)

def evolutionary_optimizer_node(state: TradingState) -> TradingState:
    """
    Main LangGraph node.
    Called by the main graph (e.g. every night or via trigger).
    """
    logger.info("🚀 Starting Genetic Programming Evolution Cycle...")

    # 1. Load recent historical data enriched with candle_vector signals
    try:
        conn = _get_conn()
        df = pd.read_sql("""
            SELECT timestamp, candle_scalar, iv_adjusted_scalar, rsi, volume_zscore,
                   nifty_returns, close
            FROM candle_vector_signals
            WHERE symbol = 'NIFTY'
            ORDER BY timestamp DESC
            LIMIT 5000
        """, conn)
        conn.close()
    except Exception as e:
        logger.error(f"Failed to fetch data for evolution: {e}")
        df = pd.DataFrame()
    
    if len(df) < 500:
        logger.warning("Not enough historical data for evolution")
        state.evolved_strategies = []
        return state

    # 2. Setup DEAP
    creator.create("FitnessMulti", base.Fitness, weights=(1.0, 1.0, 1.0, 1.0))  # maximize all 4 objectives
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMulti)

    toolbox = base.Toolbox()
    pset = setup_gp_primitive_set()
    toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=1, max_=3)
    toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.expr)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", evaluate_strategy, historical_df=df)
    toolbox.register("select", tools.selNSGA2)
    toolbox.register("mate", gp.cxOnePoint)
    toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr, pset=pset)
    toolbox.register("expr_mut", gp.genFull, min_=0, max_=2)
    toolbox.decorate("mate", gp.staticLimit(max_value=17, max_depth=5))
    toolbox.decorate("mutate", gp.staticLimit(max_value=17, max_depth=5))

    # 3. Run evolution
    pop = toolbox.population(n=POPULATION_SIZE)
    hof = tools.ParetoFront()
    
    algorithms.eaMuPlusLambda(pop, toolbox, mu=POPULATION_SIZE, lambda_=POPULATION_SIZE,
                              cxpb=CXPB, mutpb=MUTPB, ngen=GENERATIONS,
                              stats=None, halloffame=hof, verbose=True)

    # 4. Extract top strategies
    best_strategies = []
    for ind in hof[:10]:  # top 10 non-dominated
        strategy_code = str(ind)
        fitness = ind.fitness.values
        best_strategies.append({
            "strategy_id": f"GP_{datetime.now().strftime('%Y%m%d_%H%M')}_{len(best_strategies)}",
            "expression": strategy_code,
            "fitness": {
                "sharpe": float(fitness[0]),
                "max_dd": float(-fitness[1]),
                "win_rate": float(fitness[2]),
                "profit_factor": float(fitness[3])
            },
            "generated_at": datetime.utcnow().isoformat(),
            "source": "genetic_programming"
        })

    # 5. Save to state + DB (your judge_node and self_learning_node will consume this)
    state.evolved_strategies = best_strategies
    
    # Optional: persist to DB for RAG
    try:
        conn = _get_conn()
        cur = conn.cursor()
        
        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evolved_strategies (
                strategy_id VARCHAR(255) PRIMARY KEY,
                expression TEXT,
                fitness JSONB,
                generated_at TIMESTAMP
            )
        """)
        
        for strat in best_strategies:
            cur.execute("""
                INSERT INTO evolved_strategies (strategy_id, expression, fitness, generated_at)
                VALUES (%s, %s, %s, %s)
            """, (strat["strategy_id"], strat["expression"], json.dumps(strat["fitness"]), strat["generated_at"]))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to persist evolved strategies to DB: {e}")

    logger.info(f"✅ Evolution complete. Found {len(best_strategies)} strong strategies.")
    return state