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
