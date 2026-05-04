# backend/run_validation.py
"""
WEEKLY VALIDATION RUNNER (Phase 8)
Runs walk-forward validation on all production models,
auto-promotes winners, and retires underperformers.
"""

import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [VALIDATION] - %(message)s')


def run_weekly_validation():
    logging.info("📊 Starting weekly walk-forward validation...")

    try:
        from walk_forward_validator import WalkForwardValidator
        from model_registry import list_models, promote_model, retire_model

        validator = WalkForwardValidator()
        models = list_models()
        prod_models = [m for m in models if m.get("is_production")]

        results = []
        for model in prod_models:
            logging.info(f"  Validating {model['model_name']} v{model['version']}...")
            try:
                oos_sharpe = validator.quick_oos_check(model["model_name"])
                results.append({
                    "model": model["model_name"],
                    "version": model["version"],
                    "oos_sharpe": oos_sharpe,
                })
                logging.info(f"    OOS Sharpe: {oos_sharpe:.3f}")

                # Auto-retire if consistently underperforming
                if oos_sharpe < 0.0:
                    logging.warning(f"    ⚠️ {model['model_name']} underperforming, retiring")
                    retire_model(model["model_name"], model["version"])
            except Exception as e:
                logging.error(f"    Validation failed: {e}")

        # Publish summary
        from aws_training_manager import publish_training_metric
        for r in results:
            publish_training_metric(f"OOS_Sharpe_{r['model']}",
                                    r["oos_sharpe"])

        logging.info(f"✅ Validation complete. {len(results)} models checked.")

    except Exception as e:
        logging.error(f"❌ Validation failed: {e}")


if __name__ == "__main__":
    run_weekly_validation()
