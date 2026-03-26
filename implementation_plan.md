# TIMM Co-Pilot Expansion — Implementation Plan

## Goal

Transform TIMM from a passive alerting system into an **active trading co-pilot** that:
1. **Screens stocks** for intraday trades targeting 2-3% moves
2. **Tracks NIFTY/SENSEX** for options scalping setups (20-30%+ target)
3. **Monitors global cues** (US markets, VIX, global events) as background confidence signals
4. **Tracks active trades** with stop-loss and target alerts
5. Analyzes across **multiple timeframes** (5m, 15m, 1h, 1d)

## User Review Required

> [!IMPORTANT]
> **Screener Logic**: You mentioned you have custom screening criteria for intraday trades. The plan below implements a **baseline screener** with common institutional-grade filters (gap-up/down, volume spike, VWAP, ATR). After Phase 2 is built, we'll iterate on teaching it your exact personal rules. Please review the proposed filters below and tell me what to add/change.

> [!IMPORTANT]
> **Data Source for Intraday**: Yahoo Finance ([yfinance](file:///c:/Users/blkhrt/Documents/git/Timm/main.py#151-155)) provides intraday data (5m, 15m, 1h) but with limitations:
> - 5-min data: only last **60 days** of history
> - 15-min data: only last **60 days**
> - Data is **delayed by ~15 minutes** (not real-time)
>
> For truly real-time intraday screening, we'd eventually need Zerodha WebSocket or a paid data feed. For now, yfinance gives us enough to build and validate the screener logic. Is this acceptable for the first version?

> [!WARNING]
> **Scope**: This is a large expansion (~15 new/modified files). I recommend building it in phases — shipping Phase 1+2 first, then 3+4+5. Do you want all phases built at once, or iteratively?

---

## Proposed Changes

### Phase 1 — Database Schema & Foundation

#### [MODIFY] [schema.ts](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/src/db/schema.ts)

Add 3 new tables:

```typescript
// SCREENED STOCKS — Output of the Screener Agent
screened_stocks: {
  id, symbol, screened_at,
  timeframe,           // '5m', '15m', '1h', '1d'
  trade_type,          // 'INTRADAY', 'SWING'
  setup_type,          // 'GAP_UP', 'VOLUME_SPIKE', 'VWAP_RECLAIM', etc.
  entry_price, target_price, stoploss_price,
  target_pct, risk_pct,
  confidence,          // 0-100 score combining TA + global cues
  signals (JSONB),     // Array of reasons this stock was screened
  status               // 'ACTIVE', 'TRIGGERED', 'EXPIRED'
}

// ACTIVE TRADES — SL/Target Tracking
active_trades: {
  id, symbol, trade_type,    // 'INTRADAY_STOCK', 'OPTIONS_SCALP', 'SWING'
  entry_price, stoploss, target,
  current_price,
  entry_time, exit_time,
  status,              // 'OPEN', 'SL_HIT', 'TARGET_HIT', 'MANUAL_EXIT'
  pnl_pct,
  notes
}

// GLOBAL CUES — Background Confidence Signals
global_cues: {
  id, captured_at,
  spy_change_pct, qqq_change_pct, dji_change_pct,
  vix_value, vix_change_pct,
  sgx_nifty, sgx_change_pct,
  usd_inr,
  gift_nifty,
  overall_bias          // 'RISK_ON', 'RISK_OFF', 'NEUTRAL'
}
```

#### [MODIFY] [drizzle/schema.ts](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/drizzle/schema.ts)

Will be auto-synced by running `npx drizzle-kit generate` + `npx drizzle-kit push`.

#### [MODIFY] [db_vault_worker.py](file:///c:/Users/blkhrt/Documents/git/Timm/db_vault_worker.py)

Add handlers for 3 new routing keys:
- `screener.intraday.*` → insert into `screened_stocks`
- `trade.active.*` → insert/update `active_trades`
- `market.global.cues` → insert into `global_cues`
- `alert.stoploss.*` and `alert.target.*` → update `active_trades` status

Add queue bindings for all new routing keys.

---

### Phase 2 — Intraday Screener Agent + Multi-Timeframe

#### [NEW] [screener_agent_worker.py](file:///c:/Users/blkhrt/Documents/git/Timm/screener_agent_worker.py)

The core new module. A RabbitMQ worker that:

1. **Subscribes to** `market.eod.*` (daily data from yfinance producer)
2. **On receiving daily data**, fetches multi-timeframe data (15m, 1h) for that symbol via yfinance
3. **Runs screening filters** on each stock:

**Baseline Intraday Filters (2-3% target):**
| Filter | Logic | Why |
|--------|-------|-----|
| Gap-Up/Down | Open > prev close by 1%+ | Momentum gap trades |
| Volume Spike | Volume > 2x 20-day avg in first 30 mins | Institutional participation |
| VWAP Reclaim | Price dips below VWAP then closes above | Mean-reversion setup |
| ATR Expansion | Current ATR > 1.5x 14-day avg ATR | Volatility = opportunity |
| EMA Stack (15m) | 9 EMA > 21 EMA > 50 EMA | Multi-timeframe trend alignment |
| RSI Reversal (15m) | RSI crosses above 40 from below | Early momentum shift |

4. **Calculates entry/target/SL** based on ATR and percentage criteria
5. **Scores confidence** (0-100) combining TA signals + latest global cues from DB
6. **Publishes** screened results to `screener.intraday.{symbol}`

#### [MODIFY] [yfinance_producer.py](file:///c:/Users/blkhrt/Documents/git/Timm/yfinance_producer.py)

Add a new function `fetch_and_publish_intraday_data(channel, symbol)`:
- Fetches 15m and 1h candles (last 5 days)
- Publishes to `market.intraday.{symbol}` with timeframe metadata
- Called alongside the existing EOD fetch

#### [MODIFY] [main.py](file:///c:/Users/blkhrt/Documents/git/Timm/main.py)

Add `"screener": "screener_agent_worker.py"` to `workers_registry`.

---

### Phase 3 — Global Cues Producer

#### [NEW] [global_cues_producer.py](file:///c:/Users/blkhrt/Documents/git/Timm/global_cues_producer.py)

Runs as a scheduled task (triggered pre-market ~8:30 AM IST):
1. Fetches via yfinance:
   - **SPY** (S&P 500 ETF) — overnight % change
   - **QQQ** (NASDAQ ETF) — overnight % change
   - **^DJI** (Dow Jones) — overnight % change
   - **^VIX** — current VIX value + % change
   - **^NSEI** (Nifty 50) — previous close reference
   - **USDINR=X** — USD/INR rate
2. Calculates `overall_bias`:
   - RISK_ON: SPY/QQQ green + VIX < 18
   - RISK_OFF: SPY/QQQ red + VIX > 25
   - NEUTRAL: mixed signals
3. Publishes to `market.global.cues`

#### [MODIFY] [api/rag/route.ts](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/src/app/api/rag/route.ts)

Add global cues + screened stocks to the RAG context envelope:
```
[GLOBAL CUES (Pre-Market)]
SPY: +0.3%, QQQ: +0.5%, VIX: 16.2 (-3.1%), Bias: RISK_ON

[SCREENED INTRADAY CANDIDATES]
- TATAMOTOR: GAP_UP +1.8%, Volume 3.2x avg, Confidence: 78%
- INFY: VWAP_RECLAIM, EMA stacked, Confidence: 65%
```

---

### Phase 4 — Stop-Loss / Target Alert System

#### [NEW] [price_monitor_worker.py](file:///c:/Users/blkhrt/Documents/git/Timm/price_monitor_worker.py)

A persistent worker that:
1. Every 60 seconds, queries `active_trades` for all `OPEN` positions
2. Fetches current price via yfinance for each symbol
3. Checks: `current_price <= stoploss` → publish `alert.stoploss.{symbol}`
4. Checks: `current_price >= target` → publish `alert.target.{symbol}`
5. Updates `current_price` and `pnl_pct` in the DB
6. On SL/target hit, sets trade status to `SL_HIT` or `TARGET_HIT`

#### [MODIFY] [main.py](file:///c:/Users/blkhrt/Documents/git/Timm/main.py)

Add `"price_monitor": "price_monitor_worker.py"` to `workers_registry`.

---

### Phase 5 — Dashboard UI

#### [NEW] [app/screener/page.tsx](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/src/app/screener/page.tsx)

**Intraday Screener Dashboard:**
- Table of screened stocks with columns: Symbol, Setup Type, Entry, Target (%), SL, Confidence, Timeframe, Screened At
- Color-coded confidence badges (green > 70, yellow 40-70, red < 40)
- Button to "Track This Trade" → creates an entry in `active_trades`
- SSE stream for live screener results
- Filter by trade_type (INTRADAY / SWING)

#### [NEW] [app/trades/page.tsx](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/src/app/trades/page.tsx)

**Active Trades Tracker:**
- Table of open trades with real-time P&L %
- SL/Target progress bar visualization
- Status badges: OPEN (blue), SL_HIT (red), TARGET_HIT (green)
- Trade history log with win/loss ratio
- Manual entry form for new trades

#### [NEW] API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/screener/results` | GET | Latest screened stocks from DB |
| `/api/screener` | SSE | Live stream of new screener results |
| `/api/trades` | GET/POST | List/create active trades |
| `/api/trades/[id]` | PATCH/DELETE | Update/close a trade |
| `/api/global` | GET | Latest global cues |

#### [MODIFY] [Navigation.tsx](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/src/components/Navigation.tsx)

Add new nav items: "Screener" and "Trades".

#### [MODIFY] Command Center ([page.tsx](file:///c:/Users/blkhrt/Documents/git/Timm/dashboard/src/app/page.tsx))

Add a "Global Cues" mini-widget showing SPY/QQQ/VIX with colored arrows.

---

## New Dependencies

**Python** ([requirements.txt](file:///c:/Users/blkhrt/Documents/git/Timm/requirements.txt)):
- `schedule` — for timed pre-market global cues fetch
- `numpy` — already used by vector agent, needed for ATR calculations

**No new npm packages needed** — everything uses existing Drizzle, Lucide, Next.js.

---

## Verification Plan

### Automated Tests

No existing test suite exists. Since this is an event-driven system with external APIs, verification is done through integration checks:

1. **Schema migration check**:
   ```bash
   cd dashboard && npx drizzle-kit generate && npx drizzle-kit push
   ```
   Verify all 3 new tables exist in PostgreSQL.

2. **Worker startup check**:
   ```bash
   python main.py
   ```
   Verify all workers (including new screener + price_monitor) start without import errors.

3. **Screener dry-run test** (standalone):
   ```bash
   python screener_agent_worker.py --dry-run
   ```
   We'll add a `--dry-run` flag that fetches data for one stock (RELIANCE) and prints screener output without publishing to RabbitMQ.

### Manual Verification

1. **Start the full stack**: `python main.py` (backend) + `cd dashboard && yarn dev` (frontend)
2. **Run yfinance producer**: `python yfinance_producer.py` — check that data flows through RabbitMQ
3. **Check screener page**: Navigate to `http://localhost:3000/screener` — verify screened stocks appear
4. **Test trade tracking**: Click "Track This Trade" on a screened stock → check it appears on `/trades`
5. **Check global cues**: Run `python global_cues_producer.py` → verify data shows on Command Center
6. **Test RAG context**: Go to `/chat` and ask "What are today's intraday setups?" → verify screener data appears in response
7. **Test SL/target**: Create a trade with a tight SL → verify alert fires when price is below SL

> [!NOTE]
> Since yfinance data is delayed, SL/target alerts will have ~15 min latency. For verification, we can set an artificially close SL to trigger quickly.
