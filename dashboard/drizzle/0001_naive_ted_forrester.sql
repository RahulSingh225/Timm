CREATE TABLE "fii_dii_flows" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"fii_net_cash" integer,
	"dii_net_cash" integer,
	"fii_idx_fut_net" integer,
	"pcr" real,
	"sentiment_score" real,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "fii_dii_flows_trade_date_unique" UNIQUE("trade_date")
);
--> statement-breakpoint
CREATE TABLE "news_events" (
	"id" serial PRIMARY KEY NOT NULL,
	"title" text NOT NULL,
	"content" text,
	"source" varchar(50) NOT NULL,
	"url" text,
	"published_at" timestamp NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "news_events_url_unique" UNIQUE("url")
);
--> statement-breakpoint
CREATE TABLE "options_footprint" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"index_name" varchar(20) NOT NULL,
	"expiry_type" varchar(20) NOT NULL,
	"strike_price" integer NOT NULL,
	"option_type" varchar(5) NOT NULL,
	"close_price" integer NOT NULL,
	"open_interest" integer NOT NULL,
	"change_in_oi" integer NOT NULL,
	"volume" integer NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "sector_flows" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"sector_name" varchar(100) NOT NULL,
	"net_investment_cr" integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE "tradewise_flows" (
	"id" serial PRIMARY KEY NOT NULL,
	"trade_date" timestamp NOT NULL,
	"isin" varchar(20) NOT NULL,
	"buy_value" real,
	"sell_value" real,
	"net_value" real,
	"instrument_type" varchar(10),
	"created_at" timestamp DEFAULT now() NOT NULL
);
