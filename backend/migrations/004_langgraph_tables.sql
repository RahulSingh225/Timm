-- TIMM LangGraph Migration — New tables for trade journal, learning system, and graph execution tracking
-- Run this migration against your PostgreSQL database before using the LangGraph workflow.

-- 1. Trade Journal: Every trade entered through the system
CREATE TABLE IF NOT EXISTS trade_journal (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    trade_type VARCHAR(30) NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    stoploss REAL,
    target REAL,
    actual_pnl_pct REAL,
    status VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    predicted_confidence REAL,
    signals_used JSONB,
    evidence_chain JSONB,
    user_notes TEXT,
    entered_at TIMESTAMP DEFAULT NOW(),
    exited_at TIMESTAMP,
    session_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Learning History: Per-signal accuracy tracking
CREATE TABLE IF NOT EXISTS learning_history (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    signal_type VARCHAR(100) NOT NULL,
    predicted_direction VARCHAR(10),
    was_correct BOOLEAN,
    actual_pnl_pct REAL,
    market_regime VARCHAR(20),
    vix_at_time REAL,
    trade_type VARCHAR(30),
    session_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. Strategy Weights: Adjustable per-signal confidence multipliers
CREATE TABLE IF NOT EXISTS strategy_weights (
    id SERIAL PRIMARY KEY,
    signal_type VARCHAR(100) UNIQUE NOT NULL,
    base_weight REAL DEFAULT 1.0,
    user_override REAL,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    avg_pnl_when_correct REAL,
    avg_pnl_when_wrong REAL,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- 4. Graph Runs: Tracks every LangGraph execution
CREATE TABLE IF NOT EXISTS graph_runs (
    id SERIAL PRIMARY KEY,
    graph_type VARCHAR(30) NOT NULL,
    run_date DATE NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP,
    duration_ms INTEGER,
    state_snapshot JSONB,
    phase_completed VARCHAR(30),
    total_setups INTEGER,
    total_accepted INTEGER,
    status VARCHAR(20) DEFAULT 'RUNNING',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. Add intraday_setups and options_setups columns to daily_reports (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_reports' AND column_name = 'intraday_setups'
    ) THEN
        ALTER TABLE daily_reports ADD COLUMN intraday_setups JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_reports' AND column_name = 'options_setups'
    ) THEN
        ALTER TABLE daily_reports ADD COLUMN options_setups JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'daily_reports' AND column_name = 'evidence_chain'
    ) THEN
        ALTER TABLE daily_reports ADD COLUMN evidence_chain JSONB;
    END IF;
END $$;

-- 6. Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_trade_journal_date ON trade_journal(trade_date);
CREATE INDEX IF NOT EXISTS idx_trade_journal_symbol ON trade_journal(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_journal_status ON trade_journal(status);
CREATE INDEX IF NOT EXISTS idx_learning_history_date ON learning_history(trade_date);
CREATE INDEX IF NOT EXISTS idx_learning_history_signal ON learning_history(signal_type);
CREATE INDEX IF NOT EXISTS idx_graph_runs_date ON graph_runs(run_date);
CREATE INDEX IF NOT EXISTS idx_graph_runs_type ON graph_runs(graph_type);
