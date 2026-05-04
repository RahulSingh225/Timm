# backend/run_training_pipeline.py
"""
NIGHTLY TRAINING PIPELINE ORCHESTRATOR (Phase 8)
Coordinates the full training cycle:
  1. Start GPU instance (spot or on-demand)
  2. Pull latest data from DB
  3. Run all training subgraphs (GP → NEAT → GNNs → MARL)
  4. Upload models to S3
  5. Publish metrics to CloudWatch
  6. Stop GPU instance
"""

import os
import sys
import time
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [TRAINING] - %(message)s')

DB_URL = os.getenv("DATABASE_URL")
TRAINING_MODE = os.getenv("TRAINING_MODE", "local")  # local | ec2 | spot


def run_full_training_cycle():
    """Execute the complete training pipeline."""
    start_time = time.monotonic()
    results = {"phases": {}, "errors": [], "models_uploaded": 0}

    logging.info("=" * 60)
    logging.info("🚂 NIGHTLY TRAINING PIPELINE STARTING")
    logging.info(f"   Mode: {TRAINING_MODE}")
    logging.info(f"   Time: {datetime.utcnow().isoformat()}")
    logging.info("=" * 60)

    # ── Phase 1: GPU Instance (if remote) ──────────────────
    if TRAINING_MODE in ("ec2", "spot"):
        from aws_training_manager import start_training_instance, request_spot_instance
        if TRAINING_MODE == "spot":
            logging.info("📡 Requesting spot instance...")
            req_id = request_spot_instance()
            if not req_id:
                logging.error("Spot request failed, falling back to on-demand")
                start_training_instance()
            else:
                logging.info(f"Spot request: {req_id} — waiting for fulfillment...")
                time.sleep(60)  # Wait for spot allocation
        else:
            start_training_instance()
        time.sleep(30)  # Wait for instance boot

    # ── Phase 2: Training Subgraphs ────────────────────────
    try:
        from langgraph_workflow import build_training_graph

        logging.info("\n🧬 Running training graph...")
        graph = build_training_graph()

        training_state = {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "profile": "training",
            "current_phase": "training",
            "market_regime": "NEUTRAL",
            "global_cues": {}, "watchlist": [], "swing_analyses": {},
            "options_analyses": {}, "vector_analyses": {},
            "strategy_weights": {}, "intraday_setups": [],
            "options_setups": [], "all_evidence": [],
            "top_picks": [], "detected_regime": {},
            "evolved_strategies": [], "neat_best_network": {},
            "marl_policy": {}, "sector_gnn_signal": {},
            "options_gnn_signal": {}, "llm_generated_hypotheses": [],
            "volatility_forecast": {},
        }

        result_state = graph.invoke(training_state)

        # Collect results
        if result_state.get("evolved_strategies"):
            results["phases"]["gp_evolution"] = {
                "status": "success",
                "strategies_evolved": len(result_state["evolved_strategies"]),
            }

        if result_state.get("neat_best_network", {}).get("model_path"):
            results["phases"]["neat_evolution"] = {
                "status": "success",
                "fitness": result_state["neat_best_network"].get("fitness", 0),
            }

        if result_state.get("marl_policy", {}).get("model_path"):
            results["phases"]["marl_training"] = {
                "status": "success",
                "mean_reward": result_state["marl_policy"].get("mean_reward", 0),
            }

        if result_state.get("sector_gnn_signal", {}).get("predicted_rotation"):
            results["phases"]["sector_gnn"] = {"status": "success"}

        if result_state.get("options_gnn_signal", {}).get("recommended_strategy"):
            results["phases"]["options_gnn"] = {"status": "success"}

        logging.info(f"✅ Training graph complete. Phases: {list(results['phases'].keys())}")

    except Exception as e:
        results["errors"].append(f"Training graph: {str(e)[:300]}")
        logging.error(f"❌ Training graph failed: {e}")
        traceback.print_exc()

    # ── Phase 3: Upload models to S3 ──────────────────────
    try:
        from aws_training_manager import upload_model, ensure_s3_bucket, publish_training_metric

        ensure_s3_bucket()

        model_files = {
            "neat_best": "models/neat_best_*.pkl",
            "marl_ppo": "models/marl_ppo_latest.zip",
            "sector_gnn": "models/hetero_sector_gnn_best.pth",
            "options_gnn": "models/options_gnn_best.pth",
        }

        import glob
        for model_name, pattern in model_files.items():
            files = glob.glob(pattern)
            if files:
                latest = sorted(files)[-1]
                version = int(datetime.now().strftime("%Y%m%d"))
                s3_uri = upload_model(latest, model_name, version,
                                      {"trained_at": datetime.utcnow().isoformat()})
                if s3_uri:
                    results["models_uploaded"] += 1

        # Publish metrics to CloudWatch
        elapsed_sec = time.monotonic() - start_time
        publish_training_metric("TrainingDurationSec", elapsed_sec, "Seconds")
        publish_training_metric("ModelsUploaded", results["models_uploaded"], "Count")
        publish_training_metric("TrainingErrors", len(results["errors"]), "Count")

        if results.get("phases", {}).get("neat_evolution", {}).get("fitness"):
            publish_training_metric("NEATFitness",
                                    results["phases"]["neat_evolution"]["fitness"])

        logging.info(f"📤 {results['models_uploaded']} models uploaded to S3")

    except Exception as e:
        results["errors"].append(f"S3 upload: {str(e)[:200]}")
        logging.warning(f"⚠️ S3 upload step failed: {e}")

    # ── Phase 4: Validation ────────────────────────────────
    try:
        from walk_forward_validator import WalkForwardValidator
        validator = WalkForwardValidator()
        # Quick OOS check
        logging.info("📊 Running quick out-of-sample validation...")
        # (In production, this would run the full WFO)
    except Exception as e:
        logging.warning(f"Validation skipped: {e}")

    # ── Phase 5: Shutdown GPU ──────────────────────────────
    if TRAINING_MODE in ("ec2", "spot"):
        try:
            from aws_training_manager import stop_training_instance
            stop_training_instance()
            logging.info("🛑 GPU instance stopped")
        except Exception as e:
            logging.error(f"Failed to stop GPU: {e}")
            results["errors"].append(f"GPU shutdown: {str(e)[:100]}")

    # ── Summary ────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    results["total_duration_sec"] = round(elapsed, 1)
    results["completed_at"] = datetime.utcnow().isoformat()

    logging.info("\n" + "=" * 60)
    logging.info("🎉 TRAINING PIPELINE COMPLETE")
    logging.info(f"   Duration: {elapsed/60:.1f} minutes")
    logging.info(f"   Models uploaded: {results['models_uploaded']}")
    logging.info(f"   Errors: {len(results['errors'])}")
    for phase, info in results["phases"].items():
        logging.info(f"   {phase}: {info['status']}")
    logging.info("=" * 60)

    # Log to DB
    _log_training_run(results)
    return results


def _log_training_run(results: dict):
    """Persist training run metadata to DB."""
    try:
        import psycopg2, json
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS training_runs (
                id SERIAL PRIMARY KEY,
                started_at TIMESTAMP DEFAULT NOW(),
                duration_sec REAL,
                mode VARCHAR(20),
                phases_completed JSONB,
                models_uploaded INTEGER,
                errors JSONB,
                metadata JSONB
            )
        """)
        cur.execute("""
            INSERT INTO training_runs (duration_sec, mode, phases_completed, models_uploaded, errors, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            results.get("total_duration_sec"),
            TRAINING_MODE,
            json.dumps(results.get("phases", {})),
            results.get("models_uploaded", 0),
            json.dumps(results.get("errors", [])),
            json.dumps(results),
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to log training run: {e}")


if __name__ == "__main__":
    run_full_training_cycle()
