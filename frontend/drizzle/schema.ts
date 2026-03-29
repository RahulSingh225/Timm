import { pgTable, serial, varchar, integer, jsonb, text, timestamp, unique, boolean, real } from "drizzle-orm/pg-core"
import { sql } from "drizzle-orm"



export const marketAlerts = pgTable("market_alerts", {
	id: serial().primaryKey().notNull(),
	symbol: varchar({ length: 50 }).notNull(),
	agentSource: varchar("agent_source", { length: 50 }).notNull(),
	signalType: varchar("signal_type", { length: 20 }).notNull(),
	closePrice: integer("close_price"),
	signals: jsonb().notNull(),
	summary: text(),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});

export const participantData = pgTable("participant_data", {
	id: serial().primaryKey().notNull(),
	tradeDate: timestamp("trade_date", { mode: 'string' }).notNull(),
	participantType: varchar("participant_type", { length: 20 }).notNull(),
	netIndexCall: integer("net_index_call").notNull(),
	netIndexPut: integer("net_index_put").notNull(),
	netIndexFutures: integer("net_index_futures").notNull(),
	netStockFutures: integer("net_stock_futures").notNull(),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});

export const watchlist = pgTable("watchlist", {
	id: serial().primaryKey().notNull(),
	symbol: varchar({ length: 50 }).notNull(),
	assetType: varchar("asset_type", { length: 20 }).notNull(),
	isActive: boolean("is_active").default(true).notNull(),
	addedAt: timestamp("added_at", { mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	unique("watchlist_symbol_unique").on(table.symbol),
]);

export const fiiDiiFlows = pgTable("fii_dii_flows", {
	id: serial().primaryKey().notNull(),
	tradeDate: timestamp("trade_date", { mode: 'string' }).notNull(),
	fiiNetCash: integer("fii_net_cash"),
	diiNetCash: integer("dii_net_cash"),
	fiiIdxFutNet: integer("fii_idx_fut_net"),
	pcr: real(),
	sentimentScore: real("sentiment_score"),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	unique("fii_dii_flows_trade_date_unique").on(table.tradeDate),
]);

export const newsEvents = pgTable("news_events", {
	id: serial().primaryKey().notNull(),
	title: text().notNull(),
	content: text(),
	source: varchar({ length: 50 }).notNull(),
	url: text(),
	publishedAt: timestamp("published_at", { mode: 'string' }).notNull(),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	unique("news_events_url_unique").on(table.url),
]);

export const optionsFootprint = pgTable("options_footprint", {
	id: serial().primaryKey().notNull(),
	tradeDate: timestamp("trade_date", { mode: 'string' }).notNull(),
	indexName: varchar("index_name", { length: 20 }).notNull(),
	expiryType: varchar("expiry_type", { length: 20 }).notNull(),
	strikePrice: integer("strike_price").notNull(),
	optionType: varchar("option_type", { length: 5 }).notNull(),
	closePrice: integer("close_price").notNull(),
	openInterest: integer("open_interest").notNull(),
	changeInOi: integer("change_in_oi").notNull(),
	volume: integer().notNull(),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});

export const sectorFlows = pgTable("sector_flows", {
	id: serial().primaryKey().notNull(),
	tradeDate: timestamp("trade_date", { mode: 'string' }).notNull(),
	sectorName: varchar("sector_name", { length: 100 }).notNull(),
	netInvestmentCr: integer("net_investment_cr").notNull(),
});

export const tradewiseFlows = pgTable("tradewise_flows", {
	id: serial().primaryKey().notNull(),
	tradeDate: timestamp("trade_date", { mode: 'string' }).notNull(),
	isin: varchar({ length: 20 }).notNull(),
	buyValue: real("buy_value"),
	sellValue: real("sell_value"),
	netValue: real("net_value"),
	instrumentType: varchar("instrument_type", { length: 10 }),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});

export const vectorSignals = pgTable("vector_signals", {
	id: serial().primaryKey().notNull(),
	symbol: varchar({ length: 50 }).notNull(),
	timestamp: timestamp({ mode: 'string' }),
	rawScalar: real("raw_scalar"),
	ivAdjustedScalar: real("iv_adjusted_scalar"),
	currentAtmIv: real("current_atm_iv"),
	signedAccumulation: real("signed_accumulation"),
	predictedNextMove: real("predicted_next_move"),
	linearM: real("linear_m"),
	linearB: real("linear_b"),
	confidence: real(),
	signal: varchar({ length: 20 }),
	candleVector: jsonb("candle_vector"),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});

export const activeTrades = pgTable("active_trades", {
	id: serial().primaryKey().notNull(),
	symbol: varchar({ length: 50 }).notNull(),
	tradeType: varchar("trade_type", { length: 30 }).notNull(),
	entryPrice: real("entry_price").notNull(),
	stoploss: real().notNull(),
	target: real().notNull(),
	currentPrice: real("current_price"),
	entryTime: timestamp("entry_time", { mode: 'string' }).defaultNow().notNull(),
	exitTime: timestamp("exit_time", { mode: 'string' }),
	status: varchar({ length: 20 }).default('OPEN').notNull(),
	pnlPct: real("pnl_pct"),
	notes: text(),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});

export const globalCues = pgTable("global_cues", {
	id: serial().primaryKey().notNull(),
	capturedAt: timestamp("captured_at", { mode: 'string' }).defaultNow().notNull(),
	spyChangePct: real("spy_change_pct"),
	qqqChangePct: real("qqq_change_pct"),
	djiChangePct: real("dji_change_pct"),
	vixValue: real("vix_value"),
	vixChangePct: real("vix_change_pct"),
	sgxNifty: real("sgx_nifty"),
	sgxChangePct: real("sgx_change_pct"),
	usdInr: real("usd_inr"),
	giftNifty: real("gift_nifty"),
	overallBias: varchar("overall_bias", { length: 20 }),
});

export const intradayCandles = pgTable("intraday_candles", {
	id: serial().primaryKey().notNull(),
	symbol: varchar({ length: 50 }).notNull(),
	timeframe: varchar({ length: 10 }).notNull(),
	candleTime: timestamp("candle_time", { mode: 'string' }).notNull(),
	open: real().notNull(),
	high: real().notNull(),
	low: real().notNull(),
	close: real().notNull(),
	volume: integer().notNull(),
	fetchedAt: timestamp("fetched_at", { mode: 'string' }).defaultNow().notNull(),
}, (table) => [
	unique("intraday_candles_unique").on(table.symbol, table.timeframe, table.candleTime),
]);

export const screenedStocks = pgTable("screened_stocks", {
	id: serial().primaryKey().notNull(),
	symbol: varchar({ length: 50 }).notNull(),
	screenedAt: timestamp("screened_at", { mode: 'string' }).defaultNow().notNull(),
	timeframe: varchar({ length: 10 }).notNull(),
	tradeType: varchar("trade_type", { length: 20 }).notNull(),
	setupType: varchar("setup_type", { length: 50 }).notNull(),
	entryPrice: real("entry_price"),
	targetPrice: real("target_price"),
	stoplossPrice: real("stoploss_price"),
	targetPct: real("target_pct"),
	riskPct: real("risk_pct"),
	confidence: real(),
	signals: jsonb().notNull(),
	status: varchar({ length: 20 }).default('ACTIVE').notNull(),
});

export const agentRuns = pgTable("agent_runs", {
	id: serial().primaryKey().notNull(),
	agentName: varchar("agent_name", { length: 50 }).notNull(),
	runStatus: varchar("run_status", { length: 20 }).default('RUNNING').notNull(),
	startedAt: timestamp("started_at", { mode: 'string' }).defaultNow().notNull(),
	finishedAt: timestamp("finished_at", { mode: 'string' }),
	durationMs: integer("duration_ms"),
	llmModel: varchar("llm_model", { length: 50 }),
	llmPromptTokens: integer("llm_prompt_tokens"),
	llmCompletionTokens: integer("llm_completion_tokens"),
	llmPromptPreview: text("llm_prompt_preview"),
	llmResponsePreview: text("llm_response_preview"),
	symbolProcessed: varchar("symbol_processed", { length: 50 }),
	messageCount: integer("message_count"),
	errorMessage: text("error_message"),
	metadata: jsonb(),
	createdAt: timestamp("created_at", { mode: 'string' }).defaultNow().notNull(),
});
