CREATE TABLE "agent_runs" (
	"id" serial PRIMARY KEY NOT NULL,
	"agent_name" varchar(50) NOT NULL,
	"run_status" varchar(20) DEFAULT 'RUNNING' NOT NULL,
	"started_at" timestamp DEFAULT now() NOT NULL,
	"finished_at" timestamp,
	"duration_ms" integer,
	"llm_model" varchar(50),
	"llm_prompt_tokens" integer,
	"llm_completion_tokens" integer,
	"llm_prompt_preview" text,
	"llm_response_preview" text,
	"symbol_processed" varchar(50),
	"message_count" integer,
	"error_message" text,
	"metadata" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "daily_reports" (
	"id" serial PRIMARY KEY NOT NULL,
	"report_date" varchar(10) NOT NULL,
	"market_regime" varchar(20),
	"vix" real,
	"fii_net" varchar(50),
	"dii_net" varchar(50),
	"watchlist_analysis" jsonb NOT NULL,
	"top_picks" jsonb,
	"avoid_list" jsonb,
	"head_analyst_brief" text,
	"total_stocks_analyzed" integer,
	"total_signals" integer,
	"generated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "daily_reports_report_date_unique" UNIQUE("report_date")
);
--> statement-breakpoint
ALTER TABLE "options_footprint" ADD CONSTRAINT "options_footprint_unique" UNIQUE("trade_date","index_name","strike_price","option_type");--> statement-breakpoint
ALTER TABLE "participant_data" ADD CONSTRAINT "participant_data_unique" UNIQUE("trade_date","participant_type");--> statement-breakpoint
ALTER TABLE "sector_flows" ADD CONSTRAINT "sector_flows_unique" UNIQUE("trade_date","sector_name");--> statement-breakpoint
ALTER TABLE "tradewise_flows" ADD CONSTRAINT "tradewise_flows_unique" UNIQUE("trade_date","isin");--> statement-breakpoint
ALTER TABLE "vector_signals" ADD CONSTRAINT "vector_signals_unique" UNIQUE("symbol","timestamp");