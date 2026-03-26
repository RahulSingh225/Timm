CREATE TABLE "vector_signals" (
	"id" serial PRIMARY KEY NOT NULL,
	"symbol" varchar(50) NOT NULL,
	"timestamp" timestamp,
	"raw_scalar" real,
	"iv_adjusted_scalar" real,
	"current_atm_iv" real,
	"signed_accumulation" real,
	"predicted_next_move" real,
	"linear_m" real,
	"linear_b" real,
	"confidence" real,
	"signal" varchar(20),
	"candle_vector" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
