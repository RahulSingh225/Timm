# backend/nodes/evolutionary_optimizer_node.py
"""
EVOLUTIONARY OPTIMIZER NODE (Genetic Programming + PySR Symbolic Regression + NSGA-II)
Integrates directly into Timm LangGraph.
Evolves trading strategies using candle_vector signals + IV + regime context.
Runs nightly or on-demand. Outputs best strategies to judge_node.

Phase 3 Enhancements:
  - PySR symbolic regression alongside DEAP for cleaner formula discovery
  - Regime-specific evolution (separate formulas per regime)
  - Information Coefficient (IC) fitness alongside Sharpe
  - LLM-seeded hypothesis injection from llm_hypothesis_generator_node
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
# =========================================================


def _safe_div(a, b):
    """Protected division to avoid ZeroDivisionError in GP trees."""
    try:
        if abs(b) < 1e-10:
            return 0.0
        return a / b
    except:
        return 0.0


def _safe_log(x):
    """Protected log for GP trees."""
    try:
        return np.log(abs(x) + 1e-10)
    except:
        return 0.0


def _safe_sqrt(x):
    """Protected sqrt for GP trees."""
    try:
        return np.sqrt(abs(x))
    except:
        return 0.0


def _neg(x):
    return -x


def _square(x):
    try:
        return min(x * x, 1e6)  # Clamp to avoid overflow
    except:
        return 0.0


def setup_gp_primitive_set():
    """Define the building blocks for evolved strategies — now with regime input."""
    # 7 inputs: candle_scalar, iv_adjusted, rsi, volume_z, prev_signal, regime_id, vwap_dev
    pset = gp.PrimitiveSet("MAIN", arity=7)

    # Arithmetic
    pset.addPrimitive(np.add, 2)
    pset.addPrimitive(np.subtract, 2)
    pset.addPrimitive(np.multiply, 2)
    pset.addPrimitive(_safe_div, 2, name="safe_div")
    pset.addPrimitive(np.maximum, 2)
    pset.addPrimitive(np.minimum, 2)

    # Unary
    pset.addPrimitive(np.abs, 1)
    pset.addPrimitive(_neg, 1, name="neg")
    pset.addPrimitive(_safe_sqrt, 1, name="safe_sqrt")
    pset.addPrimitive(_safe_log, 1, name="safe_log")
    pset.addPrimitive(_square, 1, name="square")
    pset.addPrimitive(lambda x: 1.0 if x > 0 else 0.0, 1, name="positive")
    pset.addPrimitive(lambda x: 1.0 if x > 0.5 else (-1.0 if x < -0.5 else 0.0), 1, name="threshold")

    # Constants
    pset.addEphemeralConstant("rand_const", lambda: round(np.random.uniform(-2, 2), 2))
    pset.addTerminal(0.0)
    pset.addTerminal(0.5)
    pset.addTerminal(1.0)
    pset.addTerminal(-1.0)
    pset.addTerminal(2.0)
    pset.addTerminal(0.3)  # Common threshold

    pset.renameArguments(
        ARG0="candle_scalar",
        ARG1="iv_adjusted",
        ARG2="rsi",
        ARG3="volume_z",
        ARG4="prev_signal",
        ARG5="regime_id",
        ARG6="vwap_dev"
    )
    return pset


def compute_information_coefficient(predictions: np.ndarray, actual_returns: np.ndarray) -> float:
    """
    Information Coefficient (IC) — rank correlation between predicted and actual moves.
    This is the gold-standard fitness metric for systematic trading models.
    """
    if len(predictions) < 20 or np.std(predictions) < 1e-10:
        return 0.0

    from scipy.stats import spearmanr
    ic, _ = spearmanr(predictions, actual_returns)
    return ic if not np.isnan(ic) else 0.0


def evaluate_strategy(individual, historical_df: pd.DataFrame, pset) -> tuple:
    """
    Multi-objective fitness: (Sharpe, IC, -MaxDD, win_rate, profit_factor)
    Now includes Information Coefficient and regime-aware evaluation.
    """
    try:
        func = gp.compile(individual, pset=pset)
    except Exception:
        return (-10.0, 0.0, -100.0, 0.0, 0.0)

    predictions = []
    signals = []

    for i in range(1, len(historical_df)):
        row = historical_df.iloc[i]
        try:
            raw_pred = func(
                float(row.get("candle_scalar", 0)),
                float(row.get("iv_adjusted_scalar", 0)),
                float(row.get("rsi", 50)),
                float(row.get("volume_zscore", 0)),
                float(signals[-1]) if signals else 0.0,
                float(row.get("regime_id", 2)),
                float(row.get("vwap_deviation", 0)),
            )
            # Clamp prediction
            raw_pred = max(-10, min(10, float(raw_pred)))
        except Exception:
            raw_pred = 0.0

        predictions.append(raw_pred)
        signals.append(1 if raw_pred > 0.3 else -1 if raw_pred < -0.3 else 0)

    predictions = np.array(predictions)
    signals = np.array(signals)
    actual_returns = historical_df["nifty_returns"].values[1:]

    if len(actual_returns) != len(signals):
        actual_returns = actual_returns[:len(signals)]

    returns = actual_returns * signals
    equity = np.cumprod(1 + returns)

    if len(equity) < 50:
        return (-10.0, 0.0, -100.0, 0.0, 0.0)

    # Core metrics
    sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)
    ic = compute_information_coefficient(predictions, actual_returns)
    max_dd = np.max(np.maximum.accumulate(equity) - equity)
    win_rate = np.mean(returns > 0) if len(returns) > 0 else 0
    profit_factor = abs(returns[returns > 0].sum()) / (abs(returns[returns < 0].sum()) + 1e-8)

    return (float(sharpe), float(ic), float(-max_dd), float(win_rate), float(profit_factor))


def run_pysr_symbolic_regression(df: pd.DataFrame) -> List[Dict]:
    """
    Run PySR symbolic regression to discover clean mathematical formulas.
    PySR produces human-readable expressions like: expected_move = 0.8 * ATR * (OBV_slope / price)
    """
    try:
        from pysr import PySRRegressor
    except ImportError:
        logger.warning("PySR not installed — skipping symbolic regression. pip install pysr")
        return []

    feature_cols = ["candle_scalar", "iv_adjusted_scalar", "rsi", "volume_zscore", "vwap_deviation"]
    available_cols = [c for c in feature_cols if c in df.columns]

    if len(available_cols) < 3 or len(df) < 200:
        logger.warning("Not enough features/data for PySR")
        return []

    X = df[available_cols].fillna(0).values
    y = df["nifty_returns"].shift(-1).fillna(0).values  # Predict next-day return

    try:
        model = PySRRegressor(
            niterations=20,
            binary_operators=["+", "-", "*", "/"],
            unary_operators=["abs", "square", "neg"],
            populations=15,
            population_size=50,
            maxsize=20,
            parsimony=0.003,  # Prefer simpler formulas
            progress=False,
            verbosity=0,
            temp_equation_file=True,
        )
        model.fit(X, y, variable_names=available_cols)

        # Extract discovered formulas
        formulas = []
        if hasattr(model, 'equations_') and model.equations_ is not None:
            for idx, row in model.equations_.iterrows():
                formulas.append({
                    "strategy_id": f"PySR_{datetime.now().strftime('%Y%m%d_%H%M')}_{idx}",
                    "expression": str(row.get("equation", row.get("sympy_format", "unknown"))),
                    "fitness": {
                        "mse_loss": float(row.get("loss", 999)),
                        "complexity": int(row.get("complexity", 0)),
                        "score": float(row.get("score", 0)),
                    },
                    "generated_at": datetime.utcnow().isoformat(),
                    "source": "pysr_symbolic_regression",
                    "human_readable": True,
                })

        logger.info(f"✅ PySR discovered {len(formulas)} symbolic formulas")
        return formulas[-5:]  # Return top 5 simplest high-scoring formulas

    except Exception as e:
        logger.error(f"PySR regression failed: {e}")
        return []


def run_regime_specific_evolution(df: pd.DataFrame, regime_id: int, regime_label: str,
                                   pset, generations: int = 30) -> List[Dict]:
    """
    Evolve strategies specific to a single regime.
    This produces formulas optimized for bull-only, bear-only, etc.
    """
    regime_df = df[df.get("regime_id", pd.Series([2]*len(df))) == regime_id]
    if len(regime_df) < 100:
        logger.info(f"  Regime {regime_label}: insufficient data ({len(regime_df)} rows), skipping")
        return []

    logger.info(f"  Evolving strategies for regime: {regime_label} ({len(regime_df)} samples)...")

    # Use a smaller population for per-regime evolution
    if not hasattr(creator, "FitnessMulti"):
        creator.create("FitnessMulti", base.Fitness, weights=(1.0, 1.0, 1.0, 1.0, 1.0))
    if not hasattr(creator, "Individual"):
        creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMulti)

    toolbox = base.Toolbox()
    toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=1, max_=3)
    toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.expr)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", evaluate_strategy, historical_df=regime_df, pset=pset)
    toolbox.register("select", tools.selNSGA2)
    toolbox.register("mate", gp.cxOnePoint)
    toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr, pset=pset)
    toolbox.decorate("mate", gp.staticLimit(key=lambda x: x.height, max_value=5))
    toolbox.decorate("mutate", gp.staticLimit(key=lambda x: x.height, max_value=5))

    pop = toolbox.population(n=100)
    hof = tools.ParetoFront()

    algorithms.eaMuPlusLambda(pop, toolbox, mu=100, lambda_=100,
                              cxpb=CXPB, mutpb=MUTPB, ngen=generations,
                              stats=None, halloffame=hof, verbose=False)

    strategies = []
    for ind in hof[:3]:  # Top 3 per regime
        fitness = ind.fitness.values
        strategies.append({
            "strategy_id": f"GP_{regime_label}_{datetime.now().strftime('%Y%m%d_%H%M')}_{len(strategies)}",
            "expression": str(ind),
            "fitness": {
                "sharpe": float(fitness[0]),
                "ic": float(fitness[1]),
                "max_dd": float(-fitness[2]),
                "win_rate": float(fitness[3]),
                "profit_factor": float(fitness[4]),
            },
            "regime": regime_label,
            "generated_at": datetime.utcnow().isoformat(),
            "source": f"gp_regime_{regime_label.lower()}"
        })

    return strategies


def evolutionary_optimizer_node(state: TradingState) -> TradingState:
    """
    Main LangGraph node — enhanced with PySR + regime-specific evolution.
    """
    logger.info("🚀 Starting Enhanced Evolutionary Optimizer (GP + PySR + Regime)...")

    # 1. Load historical data
    try:
        conn = _get_conn()
        df = pd.read_sql("""
            SELECT timestamp, candle_scalar, iv_adjusted_scalar, rsi, volume_zscore,
                   nifty_returns, close, vwap_deviation, adx_14, atr_14
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
        state['evolved_strategies'] = []
        return state

    # Sort chronologically for proper backtesting
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Add regime labels from regime_history if available
    try:
        conn = _get_conn()
        regime_df = pd.read_sql("SELECT date, regime_id FROM regime_history ORDER BY date", conn)
        conn.close()
        if not regime_df.empty:
            df['date'] = pd.to_datetime(df['timestamp']).dt.date
            regime_df['date'] = pd.to_datetime(regime_df['date']).dt.date
            df = df.merge(regime_df, on='date', how='left')
            df['regime_id'] = df['regime_id'].fillna(2).astype(int)
        else:
            df['regime_id'] = 2
    except Exception:
        df['regime_id'] = 2  # Default to MEAN_REVERTING

    all_strategies = []
    pset = setup_gp_primitive_set()

    # ─── 2a. Global GP Evolution (DEAP NSGA-II) ───────────────
    logger.info("📊 Phase 1: Global DEAP/NSGA-II evolution...")
    try:
        if not hasattr(creator, "FitnessMulti"):
            creator.create("FitnessMulti", base.Fitness, weights=(1.0, 1.0, 1.0, 1.0, 1.0))
        if not hasattr(creator, "Individual"):
            creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMulti)

        toolbox = base.Toolbox()
        toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=1, max_=3)
        toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.expr)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", evaluate_strategy, historical_df=df, pset=pset)
        toolbox.register("select", tools.selNSGA2)
        toolbox.register("mate", gp.cxOnePoint)
        toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr, pset=pset)
        toolbox.decorate("mate", gp.staticLimit(key=lambda x: x.height, max_value=5))
        toolbox.decorate("mutate", gp.staticLimit(key=lambda x: x.height, max_value=5))

        pop = toolbox.population(n=POPULATION_SIZE)
        hof = tools.ParetoFront()

        algorithms.eaMuPlusLambda(pop, toolbox, mu=POPULATION_SIZE, lambda_=POPULATION_SIZE,
                                  cxpb=CXPB, mutpb=MUTPB, ngen=GENERATIONS,
                                  stats=None, halloffame=hof, verbose=True)

        for ind in hof[:10]:
            fitness = ind.fitness.values
            all_strategies.append({
                "strategy_id": f"GP_GLOBAL_{datetime.now().strftime('%Y%m%d_%H%M')}_{len(all_strategies)}",
                "expression": str(ind),
                "fitness": {
                    "sharpe": float(fitness[0]),
                    "ic": float(fitness[1]),
                    "max_dd": float(-fitness[2]),
                    "win_rate": float(fitness[3]),
                    "profit_factor": float(fitness[4]),
                },
                "regime": "ALL",
                "generated_at": datetime.utcnow().isoformat(),
                "source": "gp_global_nsga2"
            })

        logger.info(f"  Global GP: {len(all_strategies)} strategies evolved")
    except Exception as e:
        logger.error(f"Global GP evolution failed: {e}")

    # ─── 2b. Regime-Specific Evolution ────────────────────────
    logger.info("📊 Phase 2: Regime-specific evolution...")
    regime_map = {0: "TRENDING_BULL", 1: "TRENDING_BEAR", 2: "MEAN_REVERTING", 3: "HIGH_VOL_EXPANSION"}
    for rid, rlabel in regime_map.items():
        try:
            regime_strats = run_regime_specific_evolution(df, rid, rlabel, pset, generations=30)
            all_strategies.extend(regime_strats)
        except Exception as e:
            logger.warning(f"  Regime {rlabel} evolution failed: {e}")

    # ─── 2c. PySR Symbolic Regression ─────────────────────────
    logger.info("📊 Phase 3: PySR symbolic regression for clean formulas...")
    pysr_formulas = run_pysr_symbolic_regression(df)
    all_strategies.extend(pysr_formulas)

    # ─── 3. Save to state + DB ────────────────────────────────
    state['evolved_strategies'] = all_strategies

    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evolved_strategies (
                strategy_id VARCHAR(255) PRIMARY KEY,
                expression TEXT,
                fitness JSONB,
                regime VARCHAR(50),
                source VARCHAR(50),
                generated_at TIMESTAMP
            )
        """)
        for strat in all_strategies:
            cur.execute("""
                INSERT INTO evolved_strategies (strategy_id, expression, fitness, regime, source, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (strategy_id) DO NOTHING
            """, (
                strat["strategy_id"], strat["expression"],
                json.dumps(strat.get("fitness", {})),
                strat.get("regime", "ALL"), strat.get("source", "unknown"),
                strat["generated_at"]
            ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to persist evolved strategies to DB: {e}")

    logger.info(f"✅ Evolution complete. Found {len(all_strategies)} strategies "
                f"(Global: {sum(1 for s in all_strategies if s.get('source') == 'gp_global_nsga2')}, "
                f"Regime-specific: {sum(1 for s in all_strategies if 'regime_' in s.get('source', ''))}, "
                f"PySR: {sum(1 for s in all_strategies if s.get('source') == 'pysr_symbolic_regression')})")
    return state