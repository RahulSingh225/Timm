CREATE TABLE "market_alerts" (
	"id" serial PRIMARY KEY NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"agent_source" varchar(50) NOT NULL,
	"signal_type" varchar(20) NOT NULL,
	"close_price" integer,
	"signals" jsonb NOT NULL,
	"summary" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "participant_data" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"participant_type" varchar(20) NOT NULL,
	"net_index_call" integer NOT NULL,
	"net_index_put" integer NOT NULL,
	"net_index_futures" integer NOT NULL,
	"net_stock_futures" integer NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "watchlist" (
	"id" serial PRIMARY KEY NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"asset_type" varchar(20) NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"added_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "watchlist_symbol_unique" UNIQUE("symbol")
);
