# backend/inference_optimizer.py
"""
INFERENCE OPTIMIZATION (Phase 8.3)
Production model serving with:
  - torch.compile for 2-3x speedup
  - INT8 dynamic quantization for CPU deployment
  - Model warmup and caching
  - Batch inference support
"""

import os
import time
import logging
import torch
import pickle
from typing import Dict, List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


class OptimizedInference:
    """Production inference wrapper with compile + quantize support."""

    def __init__(self, device: str = "auto"):
        self.device = torch.device(
            "cuda" if device == "auto" and torch.cuda.is_available()
            else device if device != "auto" else "cpu"
        )
        self._compiled_models: Dict[str, torch.nn.Module] = {}
        self._quantized_models: Dict[str, torch.nn.Module] = {}
        self._warmup_done: set = set()

        logger.info(f"🔧 Inference engine initialized (device={self.device})")

    def load_and_optimize(self, model_name: str, model_path: str,
                          model_class=None, quantize: bool = True,
                          compile_mode: str = "reduce-overhead") -> torch.nn.Module:
        """Load, compile, and optionally quantize a model."""

        # Load model
        if model_path.endswith(".pth"):
            if model_class is None:
                raise ValueError("model_class required for .pth files")
            model = model_class()
            model.load_state_dict(torch.load(model_path, map_location=self.device))
        elif model_path.endswith(".pkl"):
            with open(model_path, "rb") as f:
                data = pickle.load(f)
            model = data.get("network") or data.get("model")
            if model is None:
                raise ValueError("No model found in pickle")
            # NEAT networks aren't torch modules, return as-is
            if not isinstance(model, torch.nn.Module):
                logger.info(f"  {model_name}: Non-torch model, skipping optimization")
                return model
        else:
            raise ValueError(f"Unsupported format: {model_path}")

        model = model.to(self.device)
        model.eval()
        original_name = model_name

        # Step 1: INT8 quantization (CPU only, ~2x memory reduction)
        if quantize and self.device.type == "cpu":
            try:
                quantized = torch.ao.quantization.quantize_dynamic(
                    model, {torch.nn.Linear}, dtype=torch.qint8
                )
                self._quantized_models[model_name] = quantized
                model = quantized
                logger.info(f"  {model_name}: INT8 quantized ✅")
            except Exception as e:
                logger.warning(f"  {model_name}: Quantization failed ({e}), using FP32")

        # Step 2: torch.compile (PyTorch 2.0+)
        try:
            if hasattr(torch, "compile"):
                compiled = torch.compile(model, mode=compile_mode)
                self._compiled_models[model_name] = compiled
                model = compiled
                logger.info(f"  {model_name}: torch.compile ({compile_mode}) ✅")
        except Exception as e:
            logger.warning(f"  {model_name}: torch.compile failed ({e})")

        return model

    def warmup(self, model: torch.nn.Module, model_name: str,
               input_spec: Dict[str, tuple]):
        """Run warmup inference to trigger JIT compilation."""
        if model_name in self._warmup_done:
            return

        logger.info(f"  {model_name}: Warming up...")
        try:
            with torch.no_grad():
                dummy_inputs = {
                    k: torch.randn(*shape, device=self.device)
                    for k, shape in input_spec.items()
                }
                for _ in range(3):  # 3 warmup passes
                    if hasattr(model, "forward"):
                        model(**dummy_inputs) if len(dummy_inputs) > 1 else model(list(dummy_inputs.values())[0])
            self._warmup_done.add(model_name)
            logger.info(f"  {model_name}: Warmup complete ✅")
        except Exception as e:
            logger.warning(f"  {model_name}: Warmup failed ({e})")

    def benchmark(self, model: torch.nn.Module, model_name: str,
                  input_tensor: torch.Tensor, n_runs: int = 100) -> Dict:
        """Benchmark inference latency."""
        model.eval()
        latencies = []
        with torch.no_grad():
            for _ in range(n_runs):
                start = time.perf_counter()
                _ = model(input_tensor)
                latencies.append((time.perf_counter() - start) * 1000)

        import numpy as np
        arr = np.array(latencies)
        result = {
            "model": model_name,
            "device": str(self.device),
            "n_runs": n_runs,
            "mean_ms": round(float(arr.mean()), 3),
            "p50_ms": round(float(np.percentile(arr, 50)), 3),
            "p99_ms": round(float(np.percentile(arr, 99)), 3),
            "throughput_per_sec": round(1000 / float(arr.mean()), 1),
        }
        logger.info(f"  {model_name}: {result['mean_ms']:.1f}ms avg, "
                     f"{result['throughput_per_sec']:.0f}/sec")
        return result


# ── Singleton for production use ──
_engine: Optional[OptimizedInference] = None

def get_inference_engine() -> OptimizedInference:
    global _engine
    if _engine is None:
        _engine = OptimizedInference()
    return _engine


def optimize_all_production_models() -> Dict:
    """Load and optimize all production models."""
    engine = get_inference_engine()
    results = {}

    model_paths = {
        "sector_gnn": "models/hetero_sector_gnn_best.pth",
        "options_gnn": "models/options_gnn_best.pth",
    }

    for name, path in model_paths.items():
        if os.path.exists(path):
            try:
                from nodes.sector_gnn_node import AdvancedSectorGNN
                from nodes.options_gnn_node import OptionsIVGNN
                model_class = AdvancedSectorGNN if "sector" in name else OptionsIVGNN
                model = engine.load_and_optimize(name, path, model_class)
                results[name] = {"status": "optimized", "path": path}
            except Exception as e:
                results[name] = {"status": "failed", "error": str(e)[:200]}
        else:
            results[name] = {"status": "not_found"}

    # NEAT models (non-torch, skip optimization)
    import glob
    neat_files = glob.glob("models/neat_best_*.pkl")
    if neat_files:
        results["neat"] = {"status": "loaded", "path": sorted(neat_files)[-1]}

    return results
