import { pgTable, serial, text, varchar, timestamp, integer, jsonb, boolean, real } from "drizzle-orm/pg-core";

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
});

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
});
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
});

export const tradewiseFlows = pgTable("tradewise_flows", {
    id: serial("id").primaryKey(),
    tradeDate: timestamp("trade_date").notNull(),
    isin: varchar("isin", { length: 20 }).notNull(),
    buyValue: real("buy_value"),
    sellValue: real("sell_value"),
    netValue: real("net_value"),
    instrumentType: varchar("instrument_type", { length: 10 }), // 'EQ', etc.
    createdAt: timestamp("created_at").defaultNow().notNull(),
});
