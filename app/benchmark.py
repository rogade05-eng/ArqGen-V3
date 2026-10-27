"""Performance benchmark suite (spec sections 86, 87) — FASE 40.

Deterministic benchmark over the demo project: measures wall-clock time
of the expensive operations with ``time.perf_counter`` and reports ops/s.
No network, no randomness: two runs produce comparable tables.

    benchmark run     measure the standard operations
    benchmark caches  inventory of caches + invalidation keys (spec 87)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BenchResult:
    name: str
    seconds: float
    iterations: int

    @property
    def per_iteration(self) -> float:
        return self.seconds / max(self.iterations, 1)

    @property
    def ops_per_second(self) -> float:
        return (self.iterations / self.seconds) if self.seconds > 0 else 0.0


def _timed(name: str, iterations: int, fn: Callable[[], Any]) -> BenchResult:
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    return BenchResult(name=name, seconds=time.perf_counter() - start,
                       iterations=iterations)


def run_benchmarks(context, iterations: Optional[Dict[str, int]] = None
                   ) -> List[BenchResult]:
    """Benchmark the heavy operations of an open project (deterministic).

    ``context`` is a ProjectContext (e.g. the demo project). Iteration
    counts can be tuned per operation; defaults keep the whole suite
    under a few seconds on modest hardware.
    """
    iters = {
        "geometry_area": 200,
        "spatial_adjacency": 20,
        "qto_compute_all": 3,
        "budget_compute": 2,
        "optimization_current": 5,
        "documentation_memoria": 5,
        "clash_detection": 3,
        "export_json": 5,
        **(iterations or {}),
    }
    results: List[BenchResult] = []

    # 1. Geometry: space polygon areas (spec 86: geometry simplification).
    spaces = context.architecture.list("SPACE", context.project.id)

    def geometry_area() -> None:
        for s in spaces:
            s.area_m2()

    results.append(_timed("geometry_area", iters["geometry_area"], geometry_area))

    # 2. Spatial engine: adjacency computation over all spaces.
    from engines.spatial_engine import SpatialEngine

    def spatial_adjacency() -> None:
        SpatialEngine(context.dna_registry).compute_adjacencies(spaces)

    results.append(_timed("spatial_adjacency",
                          iters["spatial_adjacency"], spatial_adjacency))

    # 3. QTO: full recalculation (cache + formulas).
    from services.quantity_service import QuantityService

    def qto_compute_all() -> None:
        QuantityService(context).compute_all()

    results.append(_timed("qto_compute_all",
                          iters["qto_compute_all"], qto_compute_all))

    # 4. Budget: rebuild from template.
    from services.budget_service import BudgetService

    def budget_compute() -> None:
        service = BudgetService(context)
        service.compute_budget("residential_full_v1", name="benchmark")

    results.append(_timed("budget_compute",
                          iters["budget_compute"], budget_compute))

    # 5. Optimization: the 12 objectives of spec 19.
    from services.optimization_service import OptimizationService

    def optimization_current() -> None:
        OptimizationService(context).evaluate_current()

    results.append(_timed("optimization_current",
                          iters["optimization_current"], optimization_current))

    # 6. Documentation: memoria generation end to end.
    from services.documentation_service import DocumentationService

    def documentation_memoria() -> None:
        DocumentationService(context).generate_memoria()

    results.append(_timed("documentation_memoria",
                          iters["documentation_memoria"],
                          documentation_memoria))

    # 7. Coordination: full clash detection.
    from services.coordination_service import CoordinationService

    def clash_detection() -> None:
        CoordinationService(context).run_detection()

    results.append(_timed("clash_detection",
                          iters["clash_detection"], clash_detection))

    # 8. Export: JSON snapshot of the whole model.
    import tempfile

    from services.export_service import ExportService

    def export_json() -> None:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            target = handle.name
        try:
            ExportService().export(context, "json", target)
        finally:
            import os
            os.unlink(target)

    results.append(_timed("export_json", iters["export_json"], export_json))
    return results


def format_results(results: List[BenchResult]) -> str:
    """Deterministic table for the CLI."""
    header = (f"{'Operación':<24} {'Iter.':>6} {'Total (s)':>10} "
              f"{'Por op. (ms)':>12} {'Ops/s':>10}")
    lines = [header, "-" * len(header)]
    for r in results:
        lines.append(f"{r.name:<24} {r.iterations:>6} {r.seconds:>10.4f} "
                     f"{r.per_iteration * 1000:>12.3f} "
                     f"{r.ops_per_second:>10.1f}")
    return "\n".join(lines)


# -- Cache inventory (spec 87) --------------------------------------------

CACHE_INVENTORY: List[Dict[str, str]] = [
    {"cache": "calculation_cache", "layer": "quantities",
     "contents": "Resultados de cantidades por objeto",
     "invalidation": "input_hash (fingerprint de inputs) + revision"},
    {"cache": "quantities.only_stale", "layer": "quantities",
     "contents": "Recálculo incremental de resultados obsoletos",
     "invalidation": "input_hash distinto al almacenado"},
    {"cache": "rules_cache", "layer": "rules",
     "contents": "Rulesets y reglas cargadas desde JSON",
     "invalidation": "ruleset_version"},
    {"cache": "catalog_cache", "layer": "knowledge",
     "contents": "SpaceDNA y catálogos de recursos",
     "invalidation": "engine_version + carga explícita"},
    {"cache": "routing_cache", "layer": "installations",
     "contents": "Rutas ortogonales de tramos ya ruteados",
     "invalidation": "movimiento del nodo (re-route)"},
    {"cache": "coverage_cache", "layer": "security",
     "contents": "Cobertura FOV por dispositivo",
     "invalidation": "re-cálculo por comando (determinista)"},
    {"cache": "geometry_cache", "layer": "core",
     "contents": "Polígonos derivados de límites de locales",
     "invalidation": "recalculado bajo demanda (spec 86: lazy)"},
]


def cache_inventory() -> List[Dict[str, str]]:
    """Inventory of the caches required by spec 87 and their invalidation."""
    return [dict(row) for row in CACHE_INVENTORY]


__all__ = ["BenchResult", "run_benchmarks", "format_results",
           "cache_inventory", "CACHE_INVENTORY"]
