CREATE TABLE "graph_runs" (
	"id" serial PRIMARY KEY NOT NULL,
	"graph_type" varchar(30) NOT NULL,
	"run_date" timestamp NOT NULL,
	"started_at" timestamp DEFAULT now() NOT NULL,
	"finished_at" timestamp,
	"duration_ms" integer,
	"state_snapshot" jsonb,
	"phase_completed" varchar(30),
	"total_setups" integer,
	"total_accepted" integer,
	"status" varchar(20) DEFAULT 'RUNNING' NOT NULL,
	"error_message" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "learning_history" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"signal_type" varchar(100) NOT NULL,
	"predicted_direction" varchar(10),
	"was_correct" boolean,
	"actual_pnl_pct" real,
	"market_regime" varchar(20),
	"vix_at_time" real,
	"trade_type" varchar(30),
	"session_type" varchar(20),
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "strategy_weights" (
	"id" serial PRIMARY KEY NOT NULL,
	"signal_type" varchar(100) NOT NULL,
	"base_weight" real DEFAULT 1 NOT NULL,
	"user_override" real,
	"win_count" integer DEFAULT 0 NOT NULL,
	"loss_count" integer DEFAULT 0 NOT NULL,
	"avg_pnl_when_correct" real,
	"avg_pnl_when_wrong" real,
	"last_updated" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "strategy_weights_signal_type_unique" UNIQUE("signal_type")
);
--> statement-breakpoint
CREATE TABLE "trade_journal" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"trade_type" varchar(30) NOT NULL,
	"entry_price" real NOT NULL,
	"exit_price" real,
	"stoploss" real,
	"target" real,
	"actual_pnl_pct" real,
	"status" varchar(20) DEFAULT 'OPEN' NOT NULL,
	"predicted_confidence" real,
	"signals_used" jsonb,
	"evidence_chain" jsonb,
	"user_notes" text,
	"entered_at" timestamp DEFAULT now() NOT NULL,
	"exited_at" timestamp,
	"session_type" varchar(20),
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "daily_reports" ALTER COLUMN "watchlist_analysis" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "daily_reports" ADD COLUMN "intraday_setups" jsonb;--> statement-breakpoint
ALTER TABLE "daily_reports" ADD COLUMN "options_setups" jsonb;--> statement-breakpoint
ALTER TABLE "daily_reports" ADD COLUMN "evidence_chain" jsonb;--> statement-breakpoint
ALTER TABLE "daily_reports" ADD COLUMN "created_at" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
ALTER TABLE "daily_reports" DROP COLUMN "generated_at";