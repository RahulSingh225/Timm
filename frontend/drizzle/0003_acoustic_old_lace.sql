CREATE TABLE "active_trades" (
	"id" serial PRIMARY KEY NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"trade_type" varchar(30) NOT NULL,
	"entry_price" real NOT NULL,
	"stoploss" real NOT NULL,
	"target" real NOT NULL,
	"current_price" real,
	"entry_time" timestamp DEFAULT now() NOT NULL,
	"exit_time" timestamp,
	"status" varchar(20) DEFAULT 'OPEN' NOT NULL,
	"pnl_pct" real,
	"notes" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "global_cues" (
	"id" serial PRIMARY KEY NOT NULL,
	"captured_at" timestamp DEFAULT now() NOT NULL,
	"spy_change_pct" real,
	"qqq_change_pct" real,
	"dji_change_pct" real,
	"vix_value" real,
	"vix_change_pct" real,
	"sgx_nifty" real,
	"sgx_change_pct" real,
	"usd_inr" real,
	"gift_nifty" real,
	"overall_bias" varchar(20)
);
--> statement-breakpoint
CREATE TABLE "intraday_candles" (
	"id" serial PRIMARY KEY NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"timeframe" varchar(10) NOT NULL,
	"candle_time" timestamp NOT NULL,
	"open" real NOT NULL,
	"high" real NOT NULL,
	"low" real NOT NULL,
	"close" real NOT NULL,
	"volume" integer NOT NULL,
	"fetched_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "intraday_candles_unique" UNIQUE("symbol","timeframe","candle_time")
);
--> statement-breakpoint
CREATE TABLE "screened_stocks" (
	"id" serial PRIMARY KEY NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"screened_at" timestamp DEFAULT now() NOT NULL,
	"timeframe" varchar(10) NOT NULL,
	"trade_type" varchar(20) NOT NULL,
	"setup_type" varchar(50) NOT NULL,
	"entry_price" real,
	"target_price" real,
	"stoploss_price" real,
	"target_pct" real,
	"risk_pct" real,
	"confidence" real,
	"signals" jsonb NOT NULL,
	"status" varchar(20) DEFAULT 'ACTIVE' NOT NULL
);
