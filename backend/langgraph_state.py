"""
TIMM LangGraph State — Shared state object for the trading workflow.

This TypedDict flows through every node in the graph. Each node reads
what it needs and writes its outputs. The `Annotated[list, add]` fields
use a reducer so multiple nodes can append to the same list.
"""

from typing import TypedDict, Optional, Annotated
from operator import add


class TradingState(TypedDict, total=False):
    """
    Shared state for the entire trading workflow graph.

    Phases:
      1. Pre-Market Research  → populates context + analysis fields
      2. Setup Identification → populates setups + synthesis fields
      3. Human Decision       → populates accepted/skipped trades
      4. Session Monitor      → populates active trade status
      5. EOD Review           → populates results + learning updates
    """

    # ── Phase 1: Market Context ──────────────────────────────
    report_date: str                        # YYYY-MM-DD
    market_regime: str                      # RISK_ON / RISK_OFF / NEUTRAL
    vix: Optional[float]
    defense_mode: bool                      # If VIX > 30 and SPY < 200 SMA -> TRUE
    fii_net: Optional[str]                  # e.g., "+2340 Cr"
    dii_net: Optional[str]
    global_cues: dict                       # Full global context blob
    sector_leaders: list[dict]              # Top sectors by FII flow
    watchlist: list[str]                    # Active symbols from DB

    # ── Phase 1: Temporal Context (from learning_history) ────
    strategy_weights: dict                  # {signal_type: {weight, win_rate, sample_size}}
    recent_performance: dict                # {regime_tradetype: {win_rate, avg_win, avg_loss}}
    lessons_learned: list[dict]             # Extracted from Auto-Reflection EOD runs

    # ── Phase 1: Per-Symbol Analysis ─────────────────────────
    swing_analyses: dict                    # {symbol: swing_report_dict}
    options_analyses: dict                  # {symbol: options_report_dict}
    vector_analyses: dict                   # {symbol: vector_report_dict}

    # ── Phase 2: Trade Setups ────────────────────────────────
    intraday_setups: list[dict]             # Equity LONG/SHORT setups
    options_setups: list[dict]              # Options CALL/PUT scalp setups
    critic_debate: list[dict]               # Critic's arguments against setups
    all_evidence: Annotated[list[dict], add]  # Evidence chain from every node

    # ── Phase 2: LLM Synthesis ───────────────────────────────
    top_picks: list[dict]                   # Ranked trade recommendations
    avoid_list: list[str]                   # Stocks with contradicting signals
    head_analyst_brief: Optional[str]       # LLM-generated morning brief

    # ── Phase 3: Human Decision ──────────────────────────────
    accepted_trades: list[dict]             # Trades user chose to take
    skipped_trades: list[dict]              # Trades user passed on

    # ── Phase 4: Session Monitor ─────────────────────────────
    active_trade_status: dict               # Live P&L tracking

    # ── Phase 5: EOD Review ──────────────────────────────────
    eod_results: list[dict]                 # Final P&L per trade
    learning_updates: list[dict]            # What the system learned today

    # ── Meta ─────────────────────────────────────────────────
    errors: Annotated[list[str], add]       # Errors from any node (appended)
    current_phase: str                      # Current execution phase
    graph_run_id: Optional[int]             # ID in graph_runs table
    
    # ── Simulation Controls (Optional) ───────────────────────
    target_date: Optional[str]              # Historical date for backtesting (YYYY-MM-DD)
    profile: Optional[str]                  # 'live' or 'simulated' to protect real weights
