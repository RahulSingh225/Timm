# backend/model_registry.py
"""
MODEL REGISTRY
Tracks model versions, training dates, performance metrics.
Auto-promotes best models. Rollback capability. S3-ready.
"""

import os
import json
import shutil
import logging
import pickle
from datetime import datetime
from typing import Optional, Dict, List
import psycopg2

logger = logging.getLogger(__name__)
DB_URL = os.getenv("DATABASE_URL")
MODEL_DIR = os.getenv("MODEL_DIR", "models")


def _get_conn():
    return psycopg2.connect(DB_URL)


def _ensure_table():
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_registry (
                id SERIAL PRIMARY KEY,
                model_name VARCHAR(100) NOT NULL,
                version INTEGER NOT NULL,
                model_type VARCHAR(50),
                file_path VARCHAR(500),
                metrics JSONB,
                is_production BOOLEAN DEFAULT FALSE,
                promoted_at TIMESTAMP,
                retired_at TIMESTAMP,
                training_date DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(model_name, version)
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to create model_registry table: {e}")


def register_model(
    model_name: str, model_type: str, file_path: str,
    metrics: Dict, training_date: Optional[str] = None,
) -> int:
    """Register a new model version. Returns the version number."""
    _ensure_table()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(version), 0) FROM model_registry WHERE model_name = %s",
                     (model_name,))
        next_version = cur.fetchone()[0] + 1
        cur.execute("""
            INSERT INTO model_registry (model_name, version, model_type, file_path,
                                        metrics, training_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (model_name, next_version, model_type, file_path,
              json.dumps(metrics), training_date or datetime.utcnow().strftime("%Y-%m-%d")))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"📦 Registered {model_name} v{next_version} (type={model_type})")
        return next_version
    except Exception as e:
        logger.error(f"Failed to register model: {e}")
        return -1


def promote_model(model_name: str, version: int):
    """Promote a model version to production. Demotes previous production version."""
    _ensure_table()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE model_registry SET is_production = FALSE, retired_at = NOW()
            WHERE model_name = %s AND is_production = TRUE
        """, (model_name,))
        cur.execute("""
            UPDATE model_registry SET is_production = TRUE, promoted_at = NOW()
            WHERE model_name = %s AND version = %s
        """, (model_name, version))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"🚀 Promoted {model_name} v{version} to production")
    except Exception as e:
        logger.error(f"Failed to promote model: {e}")


def get_production_model(model_name: str) -> Optional[Dict]:
    """Get the current production model info."""
    _ensure_table()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT version, file_path, metrics, promoted_at
            FROM model_registry
            WHERE model_name = %s AND is_production = TRUE
        """, (model_name,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return {"version": row[0], "file_path": row[1],
                    "metrics": row[2], "promoted_at": str(row[3])}
        return None
    except Exception:
        return None


def auto_promote_best(model_name: str, metric_key: str = "sharpe",
                      min_threshold: float = 0.5):
    """Auto-promote the best model if it exceeds the threshold."""
    _ensure_table()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT version, metrics FROM model_registry
            WHERE model_name = %s ORDER BY created_at DESC LIMIT 10
        """, (model_name,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        best_version, best_score = None, -999
        for v, m in rows:
            metrics = m if isinstance(m, dict) else json.loads(m) if m else {}
            score = metrics.get(metric_key, 0)
            if score > best_score:
                best_score = score
                best_version = v

        if best_version and best_score > min_threshold:
            promote_model(model_name, best_version)
            logger.info(f"🏆 Auto-promoted {model_name} v{best_version} "
                        f"({metric_key}={best_score:.3f})")
        else:
            logger.info(f"No model exceeds threshold {min_threshold} for {model_name}")

    except Exception as e:
        logger.error(f"Auto-promote failed: {e}")


def list_models(model_name: Optional[str] = None) -> List[Dict]:
    """List all registered models."""
    _ensure_table()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        if model_name:
            cur.execute("""
                SELECT model_name, version, model_type, is_production, metrics, created_at
                FROM model_registry WHERE model_name = %s ORDER BY version DESC
            """, (model_name,))
        else:
            cur.execute("""
                SELECT model_name, version, model_type, is_production, metrics, created_at
                FROM model_registry ORDER BY model_name, version DESC
            """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"model_name": r[0], "version": r[1], "type": r[2],
                 "is_production": r[3], "metrics": r[4], "created_at": str(r[5])}
                for r in rows]
    except Exception:
        return []
