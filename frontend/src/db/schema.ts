import { pgTable, serial, text, varchar, timestamp, integer, jsonb, boolean, real, unique } from "drizzle-orm/pg-core";

// 1. DYNAMIC WATCHLIST
// Controls what the Python agents actually track.
export const watchlist = pgTable("watchlist", {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 50 }).notNull().unique(),
    assetType: varchar("asset_type", { length: 20 }).notNull(), // e.g., 'INDEX', 'EQUITY'
    isActive: boolean("is_active").default(true).notNull(),
    addedAt: timestamp("added_at").defaultNow().notNull(),
});

// 2. MARKET EVENTS & ALERTS
// Stores the JSON payloads from your specialized Python agents.
// This is heavily queried by the RAG system to give the LLM context.
export const marketAlerts = pgTable("market_alerts", {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 50 }).notNull(),
    agentSource: varchar("agent_source", { length: 50 }).notNull(), // e.g., 'Swing', 'Options', 'News'
    signalType: varchar("signal_type", { length: 20 }).notNull(), // 'BULLISH', 'BEARISH', 'NEUTRAL'
    closePrice: integer("close_price"), // Storing as integer (paisa) or float depending on your precision needs
    signals: jsonb("signals").notNull(), // Stores the array of technical strings
    summary: text("summary"), // Optional: The LLM's generated voice script
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// 3. SMART MONEY POSITIONING (NSE Participant Data)
// Ingested daily at 5:30 PM. Crucial for Options Scalper context.
export const participantData = pgTable("participant_data", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    participantType: varchar("participant_type", { length: 20 }).notNull(), // 'FII', 'DII', 'PRO', 'CLIENT'

    // Net Long vs Short positions (Contracts)
    netIndexCall: integer("net_index_call").notNull(),
    netIndexPut: integer("net_index_put").notNull(),
    netIndexFutures: integer("net_index_futures").notNull(),
    netStockFutures: integer("net_stock_futures").notNull(),

    createdAt: timestamp("created_at").defaultNow().notNull(),
}, (table) => [
    unique("participant_data_unique").on(table.tradeDate, table.participantType),
]);

// 4. MACRO & FINANCIAL NEWS
export const newsEvents = pgTable("news_events", {
    id: serial("id").primaryKey(),
    title: text("title").notNull(),
    content: text("content"),
    source: varchar("source", { length: 50 }).notNull(), // 'Moneycontrol', 'Mint', etc.
    url: text("url").unique(),
    publishedAt: timestamp("published_at").notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// 5. OPTIONS FOOTPRINT (Smart Money Tracker)
export const optionsFootprint = pgTable("options_footprint", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    indexName: varchar("index_name", { length: 20 }).notNull(), // 'NIFTY' or 'SENSEX'
    expiryType: varchar("expiry_type", { length: 20 }).notNull(), // 'WEEKLY' or 'MONTHLY'
    strikePrice: integer("strike_price").notNull(),
    optionType: varchar("option_type", { length: 5 }).notNull(), // 'CE' or 'PE'
    closePrice: integer("close_price").notNull(), // Store in paisa or float
    openInterest: integer("open_interest").notNull(),
    changeInOI: integer("change_in_oi").notNull(),
    volume: integer("volume").notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
}, (table) => [
    unique("options_footprint_unique").on(table.tradeDate, table.indexName, table.strikePrice, table.optionType),
]);
// Stores data from your fetch_data.js (Cash Flows, F&O OI, PCR)
export const fiiDiiFlows = pgTable("fii_dii_flows", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull().unique(),
    fiiNetCash: integer("fii_net_cash"),
    diiNetCash: integer("dii_net_cash"),
    fiiIdxFutNet: integer("fii_idx_fut_net"),
    pcr: real("pcr"),
    sentimentScore: real("sentiment_score"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// Stores data from your fetch_tradewise_backfill.js (Sector Allocations)
export const sectorFlows = pgTable("sector_flows", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    sectorName: varchar("sector_name", { length: 100 }).notNull(),
    netInvestmentCr: integer("net_investment_cr").notNull(),
}, (table) => [
    unique("sector_flows_unique").on(table.tradeDate, table.sectorName),
]);

export const tradewiseFlows = pgTable("tradewise_flows", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    isin: varchar("isin", { length: 20 }).notNull(),
    buyValue: real("buy_value"),
    sellValue: real("sell_value"),
    netValue: real("net_value"),
    instrumentType: varchar("instrument_type", { length: 10 }), // 'EQ', etc.
    createdAt: timestamp("created_at").defaultNow().notNull(),
}, (table) => [
    unique("tradewise_flows_unique").on(table.tradeDate, table.isin),
]);

// 8. VECTOR SIGNALS
export const vectorSignals = pgTable("vector_signals", {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 50 }).notNull(),
    timestamp: timestamp("timestamp"),
    rawScalar: real("raw_scalar"),
    ivAdjustedScalar: real("iv_adjusted_scalar"),
    currentAtmIv: real("current_atm_iv"),
    signedAccumulation: real("signed_accumulation"),
    predictedNextMove: real("predicted_next_move"),
    linearM: real("linear_m"),
    linearB: real("linear_b"),
    confidence: real("confidence"),
    signal: varchar("signal", { length: 20 }),
    candleVector: jsonb("candle_vector"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
}, (table) => [
    unique("vector_signals_unique").on(table.symbol, table.timestamp),
]);

// ============================================================
// CO-PILOT EXPANSION TABLES
// ============================================================

// 9. INTRADAY CANDLES CACHE
// Stores fetched intraday data to avoid re-hitting yfinance rate limits.
// Unique on (symbol, timeframe, candle_time) prevents duplicates on refetch.
export const intradayCandles = pgTable("intraday_candles", {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 50 }).notNull(),
    timeframe: varchar("timeframe", { length: 10 }).notNull(), // '5m', '15m', '1h', '1d'
    candleTime: timestamp("candle_time").notNull(),
    open: real("open").notNull(),
    high: real("high").notNull(),
    low: real("low").notNull(),
    close: real("close").notNull(),
    volume: integer("volume").notNull(),
    fetchedAt: timestamp("fetched_at").defaultNow().notNull(),
}, (table) => [
    unique("intraday_candles_unique").on(table.symbol, table.timeframe, table.candleTime),
]);

// 10. SCREENED STOCKS — Output of the Screener Agent
// Stocks that passed screening filters for intraday or swing setups.
export const screenedStocks = pgTable("screened_stocks", {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 50 }).notNull(),
    screenedAt: timestamp("screened_at").defaultNow().notNull(),
    timeframe: varchar("timeframe", { length: 10 }).notNull(), // '5m', '15m', '1h', '1d'
    tradeType: varchar("trade_type", { length: 20 }).notNull(), // 'INTRADAY', 'SWING'
    setupType: varchar("setup_type", { length: 50 }).notNull(), // 'GAP_UP', 'VOLUME_SPIKE', 'VWAP_RECLAIM', etc.
    entryPrice: real("entry_price"),
    targetPrice: real("target_price"),
    stoplossPrice: real("stoploss_price"),
    targetPct: real("target_pct"),  // e.g. 2.5 for 2.5%
    riskPct: real("risk_pct"),      // e.g. 1.0 for 1% risk
    confidence: real("confidence"), // 0-100
    signals: jsonb("signals").notNull(), // Array of reasons this stock was screened
    status: varchar("status", { length: 20 }).default("ACTIVE").notNull(), // 'ACTIVE', 'TRIGGERED', 'EXPIRED'
});

// 11. ACTIVE TRADES — Stop-Loss / Target Tracking
// Tracks trades you enter, monitors against SL and target levels.
export const activeTrades = pgTable("active_trades", {
    id: serial("id").primaryKey(),
    symbol: varchar("symbol", { length: 50 }).notNull(),
    tradeType: varchar("trade_type", { length: 30 }).notNull(), // 'INTRADAY_STOCK', 'OPTIONS_SCALP', 'SWING'
    entryPrice: real("entry_price").notNull(),
    stoploss: real("stoploss").notNull(),
    target: real("target").notNull(),
    currentPrice: real("current_price"),
    entryTime: timestamp("entry_time").defaultNow().notNull(),
    exitTime: timestamp("exit_time"),
    status: varchar("status", { length: 20 }).default("OPEN").notNull(), // 'OPEN', 'SL_HIT', 'TARGET_HIT', 'MANUAL_EXIT'
    pnlPct: real("pnl_pct"),
    notes: text("notes"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// 12. GLOBAL CUES — Background Confidence Signals
// Pre-market data from US markets, VIX, SGX Nifty, USD/INR.
export const globalCues = pgTable("global_cues", {
    id: serial("id").primaryKey(),
    capturedAt: timestamp("captured_at").defaultNow().notNull(),
    spyChangePct: real("spy_change_pct"),
    qqqChangePct: real("qqq_change_pct"),
    djiChangePct: real("dji_change_pct"),
    vixValue: real("vix_value"),
    vixChangePct: real("vix_change_pct"),
    sgxNifty: real("sgx_nifty"),
    sgxChangePct: real("sgx_change_pct"),
    usdInr: real("usd_inr"),
    giftNifty: real("gift_nifty"),
    overallBias: varchar("overall_bias", { length: 20 }), // 'RISK_ON', 'RISK_OFF', 'NEUTRAL'
});

// 13. AGENT RUNS — Observability for Agent + LLM Invocations
// Tracks every agent run, LLM request/response, and errors for full pipeline visibility.
export const agentRuns = pgTable("agent_runs", {
    id: serial("id").primaryKey(),
    agentName: varchar("agent_name", { length: 50 }).notNull(), // 'swing', 'head_analyst', 'screener', 'options', 'vector', etc.
    runStatus: varchar("run_status", { length: 20 }).default("RUNNING").notNull(), // 'RUNNING', 'SUCCESS', 'FAILED', 'TIMEOUT'
    startedAt: timestamp("started_at").defaultNow().notNull(),
    finishedAt: timestamp("finished_at"),
    durationMs: integer("duration_ms"),
    // LLM metadata
    llmModel: varchar("llm_model", { length: 50 }), // e.g. 'llama3.2', null if no LLM call
    llmPromptTokens: integer("llm_prompt_tokens"),
    llmCompletionTokens: integer("llm_completion_tokens"),
    llmPromptPreview: text("llm_prompt_preview"), // First 500 chars of prompt
    llmResponsePreview: text("llm_response_preview"), // First 500 chars of response
    // Context
    symbolProcessed: varchar("symbol_processed", { length: 50 }),
    messageCount: integer("message_count"), // How many messages processed in this run
    errorMessage: text("error_message"),
    metadata: jsonb("metadata"), // Flexible field for extra context
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// 14. DAILY REPORTS — Batch Intelligence Reports
// Generated by daily_report_generator.py, combines all agent outputs + global context.
export const dailyReports = pgTable("daily_reports", {
    id: serial("id").primaryKey(),
    reportDate: varchar("report_date", { length: 10 }).notNull().unique(), // '2026-04-02'
    marketRegime: varchar("market_regime", { length: 20 }), // 'RISK_ON', 'RISK_OFF', 'NEUTRAL'
    vix: real("vix"),
    fiiNet: varchar("fii_net", { length: 50 }), // '+2340 Cr'
    diiNet: varchar("dii_net", { length: 50 }),
    watchlistAnalysis: jsonb("watchlist_analysis"), // Array of per-stock analysis
    topPicks: jsonb("top_picks"), // Array of symbol strings
    avoidList: jsonb("avoid_list"), // Array of symbol strings
    headAnalystBrief: text("head_analyst_brief"), // LLM-generated narrative
    totalStocksAnalyzed: integer("total_stocks_analyzed"),
    totalSignals: integer("total_signals"),
    intradaySetups: jsonb("intraday_setups"), // LangGraph: equity LONG/SHORT setups
    optionsSetups: jsonb("options_setups"), // LangGraph: options CALL/PUT setups
    evidenceChain: jsonb("evidence_chain"), // LangGraph: evidence chain from all nodes
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// ============================================================
// LANGGRAPH AGENTIC WORKFLOW TABLES
// ============================================================

// 15. TRADE JOURNAL — Every trade entered through the LangGraph system
export const tradeJournal = pgTable("trade_journal", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    symbol: varchar("symbol", { length: 50 }).notNull(),
    tradeType: varchar("trade_type", { length: 30 }).notNull(), // INTRADAY_LONG, INTRADAY_SHORT, OPTIONS_CALL, OPTIONS_PUT
    entryPrice: real("entry_price").notNull(),
    exitPrice: real("exit_price"),
    stoploss: real("stoploss"),
    target: real("target"),
    actualPnlPct: real("actual_pnl_pct"),
    status: varchar("status", { length: 20 }).default("OPEN").notNull(), // OPEN, SL_HIT, TARGET_HIT, MANUAL_EXIT, EXPIRED
    predictedConfidence: real("predicted_confidence"),
    signalsUsed: jsonb("signals_used"), // Signals that generated this recommendation
    evidenceChain: jsonb("evidence_chain"), // Full evidence trail from every node
    userNotes: text("user_notes"),
    isSimulated: boolean("is_simulated").default(false).notNull(),
    enteredAt: timestamp("entered_at").defaultNow().notNull(),
    exitedAt: timestamp("exited_at"),
    sessionType: varchar("session_type", { length: 20 }), // MORNING, AFTERNOON, EXPIRY
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// 16. LEARNING HISTORY — Per-signal accuracy tracking for self-learning
export const learningHistory = pgTable("learning_history", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    signalType: varchar("signal_type", { length: 100 }).notNull(), // BB_SQUEEZE, GOLDEN_CROSS, etc.
    predictedDirection: varchar("predicted_direction", { length: 10 }), // BULLISH, BEARISH
    wasCorrect: boolean("was_correct"),
    actualPnlPct: real("actual_pnl_pct"),
    marketRegime: varchar("market_regime", { length: 20 }), // RISK_ON, RISK_OFF, NEUTRAL
    vixAtTime: real("vix_at_time"),
    tradeType: varchar("trade_type", { length: 30 }), // INTRADAY, OPTIONS
    sessionType: varchar("session_type", { length: 20 }),
    isSimulated: boolean("is_simulated").default(false).notNull(),
    createdAt: timestamp("created_at").defaultNow().notNull(),
});

// 17. STRATEGY WEIGHTS — Self-adjusting confidence multipliers per signal
export const strategyWeights = pgTable("strategy_weights", {
    id: serial("id").primaryKey(),
    signalType: varchar("signal_type", { length: 100 }).notNull(),
    profile: varchar("profile", { length: 20 }).default("live").notNull(), // 'live', 'simulated'
    baseWeight: real("base_weight").default(1.0).notNull(), // System-calculated weight
    userOverride: real("user_override"), // Manual override (always takes priority)
    winCount: integer("win_count").default(0).notNull(),
    lossCount: integer("loss_count").default(0).notNull(),
    avgPnlWhenCorrect: real("avg_pnl_when_correct"),
    avgPnlWhenWrong: real("avg_pnl_when_wrong"),
    lastUpdated: timestamp("last_updated").defaultNow().notNull(),
}, (table) => [
    unique("strategy_weights_unique").on(table.signalType, table.profile),
]);

// 18. GRAPH RUNS — Tracks every LangGraph execution for observability
export const graphRuns = pgTable("graph_runs", {
    id: serial("id").primaryKey(),
    graphType: varchar("graph_type", { length: 30 }).notNull(), // PREMARKET, EOD_REVIEW
    runDate: timestamp("run_date").notNull(),
    startedAt: timestamp("started_at").defaultNow().notNull(),
    finishedAt: timestamp("finished_at"),
    durationMs: integer("duration_ms"),
    stateSnapshot: jsonb("state_snapshot"), // Serialized graph state
    phaseCompleted: varchar("phase_completed", { length: 30 }),
    totalSetups: integer("total_setups"),
    totalAccepted: integer("total_accepted"),
    status: varchar("status", { length: 20 }).default("RUNNING").notNull(),
    errorMessage: text("error_message"),
    createdAt: timestamp("created_at").defaultNow().notNull(),
});
