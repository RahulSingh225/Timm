"""
TIMM LangGraph Workflow — StateGraph definitions for trading phases.

Two graphs:
  1. Pre-Market Graph: Research → Analysis → Screening → Trade Building → LLM Synthesis
  2. EOD Graph: Review trades → Self-learning → Update weights

The pre-market graph runs at 8:00 AM IST (before market open).
The EOD graph runs at 4:30 PM IST (after market close).
"""

import logging
from langgraph.graph import StateGraph, END
from langgraph_state import TradingState

# Import all node functions
from nodes.global_cues_node import global_cues_node
from nodes.fii_dii_node import fii_dii_node
from nodes.watchlist_node import watchlist_node
from nodes.temporal_context_node import temporal_context_node
from nodes.swing_ta_node import swing_ta_node
from nodes.options_node import options_analysis_node
from nodes.vector_node import vector_analysis_node
from nodes.screener_node import screener_node
from nodes.intraday_builder_node import intraday_builder_node
from nodes.options_builder_node import options_builder_node
from nodes.head_analyst_node import head_analyst_node
from nodes.eod_review_node import eod_review_node
from nodes.self_learning_node import self_learning_node

# New ML Agents
from nodes.evolutionary_optimizer_node import evolutionary_optimizer_node
from nodes.neat_neuroevolution_node import neat_neuroevolution_node
from nodes.llm_hypothesis_generator_node import llm_hypothesis_generator_node
from nodes.marl_training_subgraph import marl_training_subgraph
from nodes.sector_gnn_node import sector_gnn_node

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [GRAPH] - %(message)s')


def build_premarket_graph():
    """
    Build the pre-market analysis graph.

    Flow:
      global_cues → fii_dii → watchlist → temporal_context
        → [swing_analysis, options_analysis, vector_analysis] (parallel fan-out)
        → screener (fan-in)
        → [intraday_builder, options_builder] (parallel)
        → head_analyst
        → END

    The graph produces:
      - intraday_setups: equity LONG/SHORT recommendations
      - options_setups: BUY CALL/PUT recommendations
      - head_analyst_brief: LLM-generated morning brief
      - all_evidence: complete evidence chain for every recommendation
    """
    logging.info("Building pre-market analysis graph...")

    graph = StateGraph(TradingState)

    # ── Phase 1: Market Context (sequential — each depends on previous) ──
    graph.add_node("global_cues", global_cues_node)
    graph.add_node("fii_dii", fii_dii_node)
    graph.add_node("load_watchlist", watchlist_node)
    graph.add_node("temporal_context", temporal_context_node)
  
    # ── Phase 1: Analysis (fan-out — all run on the watchlist) ──
    graph.add_node("swing_analysis", swing_ta_node)
    graph.add_node("options_analysis", options_analysis_node)
    graph.add_node("vector_analysis", vector_analysis_node)

    # ── Phase 2: Synthesis ──
    graph.add_node("screener", screener_node)
    graph.add_node("intraday_builder", intraday_builder_node)
    graph.add_node("options_builder", options_builder_node)
    graph.add_node("head_analyst", head_analyst_node)

    # ── Edges: Phase 1 sequential context loading ──
    graph.set_entry_point("global_cues")
    graph.add_edge("global_cues", "fii_dii")
    graph.add_edge("fii_dii", "load_watchlist")
    graph.add_edge("load_watchlist", "temporal_context")

    # ── Edges: Fan-out to parallel analysis ──
    # LangGraph handles fan-out: when temporal_context has multiple outgoing
    # edges, all targets run (sequentially in basic mode, parallel with async)
    graph.add_edge("temporal_context", "swing_analysis")

    # Options and vector run after swing (they may read swing_analyses)
    graph.add_edge("swing_analysis", "options_analysis")
    graph.add_edge("options_analysis", "vector_analysis")

    # ── Edges: Fan-in to screener ──
    graph.add_edge("vector_analysis", "screener")

    # ── Edges: Split to trade builders ──
    graph.add_edge("screener", "intraday_builder")
    graph.add_edge("screener", "options_builder")

    # ── Edges: Converge to LLM synthesis ──
    graph.add_edge("intraday_builder", "head_analyst")
    graph.add_edge("options_builder", "head_analyst")
    graph.add_edge("head_analyst", END)

    compiled = graph.compile()
    logging.info("✅ Pre-market graph compiled successfully")
    return compiled


def build_eod_graph():
    """
    Build the end-of-day review + self-learning graph.

    Flow:
      eod_review → self_learning → END

    The graph:
      - Compares predicted trades vs actual outcomes
      - Updates strategy weights for tomorrow's analysis
    """
    logging.info("Building EOD review graph...")

    graph = StateGraph(TradingState)

    graph.add_node("eod_review", eod_review_node)
    graph.add_node("self_learning", self_learning_node)

    graph.set_entry_point("eod_review")
    graph.add_edge("eod_review", "self_learning")
    graph.add_edge("self_learning", END)

    compiled = graph.compile()
    logging.info("✅ EOD graph compiled successfully")
    return compiled


def build_training_graph():
    """
    Build the asynchronous/offline Training graph for ML optimization.

    Flow:
      llm_hypothesis_generator → evolutionary_optimizer → neat_neuroevolution → marl_training → sector_gnn → END
    """
    logging.info("Building ML Training graph...")

    graph = StateGraph(TradingState)

    graph.add_node("llm_hypothesis_generator", llm_hypothesis_generator_node)
    graph.add_node("evolutionary_optimizer", evolutionary_optimizer_node)
    graph.add_node("neat_neuroevolution", neat_neuroevolution_node)
    graph.add_node("marl_training", marl_training_subgraph)
    graph.add_node("sector_gnn", sector_gnn_node)

    graph.set_entry_point("llm_hypothesis_generator")
    graph.add_edge("llm_hypothesis_generator", "evolutionary_optimizer")
    graph.add_edge("evolutionary_optimizer", "neat_neuroevolution")
    graph.add_edge("neat_neuroevolution", "marl_training")
    graph.add_edge("marl_training", "sector_gnn")
    graph.add_edge("sector_gnn", END)

    compiled = graph.compile()
    logging.info("✅ ML Training graph compiled successfully")
    return compiled
