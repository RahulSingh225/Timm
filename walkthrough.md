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

> [!TIP]
> The orchestrator auto-executes setups with **>75% confidence**, evaluates them against the $T+1$ closing price, and increments the `simulated` strategy weights continuously! You can watch the system evolving in real-time.
