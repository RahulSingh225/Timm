# Walkthrough: The LangGraph Time Machine ⏳

I have successfully built the **Historical Simulation Engine**, allowing your trading agents to backtest daily market data from 2022 to the present, auto-evaluating trades and learning organically without risking production metrics.

## 1. Simulation Orchestrator
A new master script, [`simulate_graph.py`](file:///c:/Users/blkhrt/Documents/git/Timm/backend/simulate_graph.py), serves as the time-travel controller.
- It iterates through every business day in your specified date range.
- It intercepts the LangGraph state to inject a strict `target_date`, completely preventing any of the data nodes from accidentally peeking into future data.

## 2. Point-In-Time Constrained Analysis
To keep the simulation mathematically pure, I re-engineered the data fetchers:
- [**Swing Node**](file:///c:/Users/blkhrt/Documents/git/Timm/backend/nodes/swing_ta_node.py): Now calculates its 1-year historical window backwards exactly from the `target_date`.
- [**Vector Node**](file:///c:/Users/blkhrt/Documents/git/Timm/backend/nodes/vector_node.py): Extracts precisely the final 100 days directly preceding the simulation date.

## 3. Environment Isolation ('Live' vs 'Simulated')
We implemented **Split Environments** so your production trading brain remains clean.
- I updated the database schema so the `strategy_weights` table now supports a `profile` tag.
- The Time Machine automatically logs all of its auto-executed trades to the journal tagged with `is_simulated = TRUE`.
- The temporal context node dynamically loads the `simulated` weight multipliers during the backtest, allowing it to adapt to historical regime shifts (e.g. the 2022 bull trap) without destroying the accuracy of your live `strategy_weights`.

## How to Start the Time Machine
Because the backend dependencies (like `psycopg2` and LangGraph) are housed inside the Docker container, you should launch the simulation from within the container context:

```bash
docker compose exec backend python simulate_graph.py --start-date 2022-01-01 --end-date 2024-04-05
```

## 4. Advanced Indicators & Market Context
The Swing Analysis node now utilizes `pandas-ta` to compute advanced momentum and risk indicators:
- **ATR:** Dynamically sizes Stop-Loss and Targets based on rolling volatility.
- **ADX & VWAP:** Determines the strength of the trend vs institutional benchmarks.
- **OBV:** Detects bullish/bearish divergence where price action contradicts smart money flow.
- **MTFC:** The node assesses Weekly chart data behind the scenes to verify the macro trend aligns.
- **SPY 200-SMA Defense Mode:** The `global_cues_node` now tracks SPY's distance from its 200 SMA. If VIX spikes > 30 and SPY is below the 200 SMA, the system triggers `defense_mode`, aggressively halving position sizes.

## 5. Primary vs Critic vs Judge (Agent Debate Architecture)
I restructured the LangGraph engine into a true debate framework:
- **Primary Agent (`intraday_builder`):** Scans the indicators and builds a bullish/bearish trade plan.
- **Adversarial Critic (`llama3.1:8b`):** Reads the Primary Agent's trade plan and is strictly prompted to find flaws, counter-arguments, and hidden risks in the technical structure.
- **The Judge (`qwen2.5-coder:14b`):** The final arbiter. Reads the Primary Agent's evidence, the Critic's argument, and the current Market Regime. It outputs a final JSON decision (`APPROVED`, `REJECTED`, or `MODIFIED_TO_SCALP`).

## 6. Auto-Reflection Memory Injection
When a simulated trade loses money, the system learns from its mistakes:
- The **Self Learning Node** intercepts the failed trades.
- It asks the primary LLM to extract the exact technical trap into a 2-sentence **Lessons Learned** summary (`lessons_learned.json`).
- EVERY morning, the **Temporal Context Node** loads these lessons and explicitly injects them into the **Judge Node**'s system prompt (e.g., "Do not buy breakouts when OBV is down based on yesterday's lesson"). The Judge explicitly considers these historical text lessons when evaluating the Critic's debate!
