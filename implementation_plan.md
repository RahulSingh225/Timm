# Agent Ecosystem Redesign — From Signals to Trading Intelligence

## Your Trading Edge, Encoded

Your process as a retail trader, distilled into what the agents need to replicate:

```
┌────────────────────────────────────────────────────────────┐
│  YOUR DECISION FRAMEWORK (60-70% win rate)                 │
│                                                            │
│  PRE-MARKET (WATCHLIST BUILDING)                           │
│  ├─ Any news catalyst? (earnings, sector shift, global)    │
│  ├─ Global cues: US markets, VIX regime, GIFT Nifty        │
│  ├─ Price Action: Is there a clear trend?                  │
│  ├─ EMA Crossover confirmation (9/21/50/200)               │
│  ├─ BB reversal or squeeze detection                       │
│  ├─ Support/Resistance levels from daily chart             │
│  └─ VERDICT: "This stock has 2%+ move potential today"     │
│                                                            │
│  INTRADAY (ENTRY TIMING)                                   │
│  ├─ Watch price at key S/R levels                          │
│  ├─ 15m EMA stack alignment                                │
│  ├─ VWAP reclaim/rejection                                 │
│  ├─ Volume confirmation                                    │
│  └─ VERDICT: "Enter NOW at ₹X, SL ₹Y, Target ₹Z"         │
└────────────────────────────────────────────────────────────┘
```

---

## Current Agent Audit

| Agent | What It Does Now | Gaps / Problems |
|-------|-----------------|-----------------|
| **Swing Agent** (`swing_agent_ta.py` + `swing_agent_worker.py`) | EMA 50/200 cross, RSI extremes, MACD crossover | ❌ No BB, no S/R levels, no multi-timeframe, no entry/SL/target prices, no `agent_runs` logging |
| **Options Agent** (`options_agent_worker.py`) | ATM IV spike check, PCR volume ratio | ❌ No Max Pain, no OI buildup detection, no IV percentile ranking, no trend-over-time |
| **Vector Agent** (`candle_vector_agent.py`) | 4D candle vector math + linear regression | ❌ Only processes NIFTY, doesn't analyze individual stocks, results are numeric not actionable |
| **Screener Agent** (`screener_agent_worker.py`) | Gap, Volume, ATR, EMA stack, VWAP, RSI filters | ✅ Most complete agent. But ❌ intraday-only, no swing mode, no BB squeeze |
| **Head Analyst** (`head_analyst_worker.py`) | Takes an alert → asks LLM for 3-sentence brief | ❌ No context injection (no global cues, no other agent data), LLM operates blind |
| **Price Monitor** (`price_monitor_worker.py`) | Polls active trades for SL/target hits | ✅ Solid. Works as designed. |

---

## Proposed Agent Hierarchy

```
LEVEL 0 — DATA LAYER (Scrapers/Producers)
═══════════════════════════════════════════
yfinance → news → NSE flows → NSDL → global cues → options bhavcopy
    │          │        │                               │
    ▼          ▼        ▼                               ▼
    └────────── [RabbitMQ Exchange] ─────────────────────┘
                        │
LEVEL 1 — SPECIALIST ANALYSTS (Each stock, each angle)
═══════════════════════════════════════════
    ├── Swing TA Agent ──── trend, EMAs, BB, S/R, MACD
    ├── Options Agent ────── IV regime, OI buildup, Max Pain, PCR trend
    └── Vector Agent ─────── momentum vectors, regression predictions
                        │
                        ▼ (all publish to exchange)
LEVEL 2 — SYNTHESIS (Combine signals into trade ideas)
═══════════════════════════════════════════
    └── Screener Agent ──── multi-signal confluence scoring
        ├── "RELIANCE: 3 bullish signals, confidence 75%"
        ├── "HDFCBANK: BB squeeze + volume spike, confidence 65%"
        └── produces STRUCTURED trade ideas (entry/SL/target)
                        │
                        ▼
LEVEL 3 — INTELLIGENCE (Strategic decision layer)
═══════════════════════════════════════════
    └── Head Analyst ──── receives ALL screener outputs + global cues
        ├── Produces "MORNING BRIEF" (pre-market watchlist)
        ├── Produces "EOD REVIEW" (what happened, what to watch)
        └── Uses LLM with FULL CONTEXT (not blind)
                        │
                        ▼
LEVEL 4 — EXECUTION (Monitor live trades)
═══════════════════════════════════════════
    └── Price Monitor ──── tracks SL/target on active positions
```

---

## Proposed Changes

### Component 1: Swing Agent Upgrade

#### [MODIFY] [swing_agent_ta.py](file:///Users/spacempact/Desktop/git/Timm/backend/swing_agent_ta.py)

**Add the analysis techniques you actually use:**

| New Analysis | What It Detects |
|-------------|----------------|
| **Bollinger Band Squeeze** | Low volatility → imminent breakout (BB width < 20-day avg) |
| **BB Reversal** | Price touches lower BB then closes inside (mean reversion) |
| **Pivot Point S/R** | Classic, Fibonacci, and Camarilla pivot levels for today |
| **Daily Support/Resistance** | Recent swing highs/lows as S/R zones |
| **ATR-based Targets** | Realistic ₹ targets using ATR (2% move validation) |
| **Multi-timeframe Trend** | Weekly + Daily trend agreement |

**Enhanced output structure:**
```python
{
  "symbol": "RELIANCE",
  "close_price": 2841.50,
  "trend": {
    "daily": "BULLISH",      # Price > 50 EMA > 200 EMA
    "weekly": "BULLISH",     # Weekly close > weekly 50 EMA
    "alignment": "STRONG"    # Both agree
  },
  "support_resistance": {
    "nearest_support": 2790,
    "nearest_resistance": 2900,
    "pivot": 2845,
    "r1": 2875, "r2": 2910,
    "s1": 2810, "s2": 2780
  },
  "signals": [...],
  "move_potential_pct": 2.3,  # ATR-based expected move
  "signal_type": "BULLISH",
  "confidence": 72
}
```

---

#### [MODIFY] [swing_agent_worker.py](file:///Users/spacempact/Desktop/git/Timm/backend/swing_agent_worker.py)

- Use the upgraded `swing_agent_ta.py` analysis
- **Log every run to `agent_runs` table** (start time, duration, symbols processed, errors)
- Publish richer alert payloads with S/R levels and entry/SL/target

---

### Component 2: Options Agent Upgrade

#### [MODIFY] [options_agent_worker.py](file:///Users/spacempact/Desktop/git/Timm/backend/options_agent_worker.py)

**New analysis capabilities:**

| Feature | Description |
|---------|-------------|
| **Max Pain** | Strike where most options expire worthless → magnetic price level |
| **OI Buildup Detection** | Significant OI increase = smart money positioning |
| **IV Percentile** | Current IV vs 30-day range → "is premium cheap or expensive?" |
| **PCR Trend** | PCR over last 5 sessions → directional conviction of smart money |
| **Strangle Analysis** | ATM straddle premium → implied expected move for the week |

**Enhanced output:**
```python
{
  "symbol": "NIFTY",
  "agent": "Options",
  "max_pain": 24500,
  "current_iv_percentile": 65,
  "expected_move_pct": 1.8,
  "pcr_5day_trend": "RISING",    # Smart money buying protection
  "key_oi_levels": {
    "call_wall": 25000,           # Resistance
    "put_wall": 24000,            # Support
  },
  "signals": [...],
  "verdict": "NEUTRAL_BEARISH"    # Max pain below CMP + rising PCR
}
```

---

### Component 3: Vector Agent Extension

#### [MODIFY] [candle_vector_agent.py](file:///Users/spacempact/Desktop/git/Timm/backend/candle_vector_agent.py)

- **Process individual stocks** (not just NIFTY) — add routing for `market.eod.*`
- Classify vectors into **accumulation/distribution** patterns
- Produce human-readable verdicts: "Strong accumulation detected, 3rd consecutive bullish vector with expanding confidence"

---

### Component 4: Screener Agent — Add Swing Mode

#### [MODIFY] [screener_agent_worker.py](file:///Users/spacempact/Desktop/git/Timm/backend/screener_agent_worker.py)

Add new filters:

| Filter | For |
|--------|-----|
| **BB Squeeze Screen** | Identify compression before breakout (swing) |
| **Sector Strength** | Only pick stocks from strong sectors (using NSDL data) |
| **Swing Mode** | Hold 3-7 days, larger targets (5-8%), wider SL (2-3%) |
| **Options Swing Mode** | Identify high-IV-percentile stocks for premium selling, or low-IV for buying |

- New trade_type: `SWING`, `OPTIONS_SWING` (in addition to existing `INTRADAY`)
- Integrate global cues more deeply: VIX regime affects preferred strategy

---

### Component 5: Head Analyst — From Parrot to Strategist

#### [MODIFY] [head_analyst_worker.py](file:///Users/spacempact/Desktop/git/Timm/backend/head_analyst_worker.py)

This is the biggest mindset change. Currently the Head Analyst receives a single alert and asks the LLM "summarize this". That's wasteful. Instead:

**New Workflow:**
1. **Batch mode**: Collect all alerts from the last analysis cycle (not one-at-a-time)
2. **Inject full context** into the LLM prompt:
   - Current global cues (VIX, US markets, bias)
   - All screener results (which stocks passed, their confidence)
   - FII/DII flow directional bias
   - Sector rotation signals from NSDL data
3. **Produce structured output**:
   - **TOP 3 TRADE IDEAS** with entry/SL/target
   - **AVOID LIST** — stocks that look good but have contradicting signals
   - **MACRO VERDICT** — brief on global positioning

**Enhanced system prompt (key excerpt):**
```
You are a senior prop desk analyst. You have:
- {N} stocks that passed screening with scores above 60
- Global bias is {RISK_ON/OFF}, VIX is {value}
- FII were net {BUY/SELL} ₹{amount}Cr yesterday
- Top sectors by FII flow: {sector_list}

Rank the top 3 trade ideas by conviction. For each:
1. State the stock and direction (LONG/SHORT)
2. State the primary setup (e.g., "BB squeeze breakout + volume spike")
3. Give exact ENTRY, STOPLOSS, TARGET
4. State the risk: what would invalidate this trade?
```

---

### Component 6: New — Daily Report Generator

#### [NEW] [daily_report_generator.py](file:///Users/spacempact/Desktop/git/Timm/backend/daily_report_generator.py)

A **batch-mode orchestrator** that can be triggered from the scheduler or dashboard:

1. Fetches all watchlist symbols
2. Runs Swing TA on each → produces per-stock analysis
3. Runs Screener filters → identifies high-conviction setups
4. Queries DB for latest global cues + FII flows
5. Assembles everything into a structured JSON report
6. Publishes to a new `daily_report` routing key → stored in DB
7. Triggers Head Analyst for the final LLM-powered brief

**Output format for dashboard consumption:**
```python
{
  "report_date": "2026-04-02",
  "market_regime": "RISK_ON",
  "vix": 14.2,
  "fii_net": "+2340 Cr",
  "watchlist_analysis": [
    {
      "symbol": "RELIANCE",
      "daily_trend": "BULLISH",
      "signals_count": 4,
      "confidence": 78,
      "screener_verdict": "PASS",
      "trade_idea": {
        "direction": "LONG",
        "entry": 2842,
        "stoploss": 2810,
        "target": 2910,
        "risk_reward": "1:2.4"
      },
      "key_signals": ["EMA RECLAIM", "BB REVERSAL", "VOLUME SPIKE", "RSI BOUNCE"]
    },
    ...
  ],
  "top_picks": ["RELIANCE", "HDFCBANK", "INFY"],
  "avoid": ["TATASTEEL"],
  "head_analyst_brief": "..."
}
```

---

### Component 7: New API + Dashboard Page

#### [NEW] `api/system/daily-report/route.ts` — Fetch the latest daily report

#### [MODIFY] `page.tsx` — Add "Daily Intelligence" card showing top picks + brief

---

## Execution Order (Phase 1 — Immediate: Get Readable Output)

> [!IMPORTANT]
> **Phase 1 focuses on making every agent produce real, actionable, readable output.** Before adding new analysis techniques, we first ensure the existing pipeline produces results end-to-end.

1. **Upgrade `swing_agent_ta.py`** — Add BB, S/R levels, ATR targets, structured output
2. **Upgrade `swing_agent_worker.py`** — Use new TA + agent_runs logging
3. **Upgrade `options_agent_worker.py`** — Max Pain + OI buildup + structured output
4. **Upgrade `candle_vector_agent.py`** — Process individual stocks + readable verdicts
5. **Upgrade `head_analyst_worker.py`** — Context-rich prompts + structured LLM output
6. **Create `daily_report_generator.py`** — Batch orchestrator
7. **Add Swing mode to screener** — BB squeeze + swing parameters

---

## Open Questions

> [!IMPORTANT]  
> **Strategy Encoding**: You mentioned specific observations that work 60-70% of the time. Beyond EMA crossovers and BB reversals, are there any specific patterns/rules you want hardcoded? For example:
> - "If stock gaps up 1%+ with volume, it usually continues 2% same direction"
> - "If FII bought heavily in a sector, stocks in that sector rally next day"
> - Any specific stocks or sectors you prefer to trade?

> [!WARNING]
> **LLM Dependency**: The Head Analyst currently depends on Ollama running. If the LLM is offline, the batch report should still generate — just without the narrative brief. Is this acceptable?

## Verification Plan

### Automated Tests
- Run each agent in `--dry-run` mode against a test symbol (RELIANCE)
- Verify structured JSON output matches expected schema
- Verify `agent_runs` table gets populated with run metadata

### Manual Verification
- Trigger the daily report generator from the dashboard
- Review the output for correctness against actual market data
- Confirm the Head Analyst produces actionable, non-generic commentary
