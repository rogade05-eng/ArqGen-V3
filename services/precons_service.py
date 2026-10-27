"""PreconsService (spec sections 59, 60, 102).

Facade of the PRECONS III integration and the SIECONS-like engine:
loads versioned rulesets from resources, resolves work items against
QTO totals (formula mapping), builds price analyses with project price
lists, compares variants and imports external databases through an
explicit column mapping. Analyses travel as CalculationResult records
(calculation type PRE, spec 102) — reproducible and auditable.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.errors import DomainError
from engines.precons_engine import (
    PreconsRuleset, PriceAnalysis, compare_analyses, import_external,
    is_official_item, price_analysis,
)
from services.context import ProjectContext


class PreconsService:
    """Facade of the PRECONS / SIECONS-like module (spec 59-60)."""

    def __init__(self, context: ProjectContext,
                 ruleset: Optional[PreconsRuleset] = None) -> None:
        self.ctx = context
        self.ruleset = ruleset

    # -- rulesets ------------------------------------------------------------
    def load_ruleset(self, code: str) -> PreconsRuleset:
        """Carga un ruleset PRECONS versionado desde resources (spec 59)."""
        from app.paths import resource_path
        path = resource_path("rulesets", f"{code}.json")
        self.ruleset = PreconsRuleset.from_file(path)
        return self.ruleset

    # -- consulta de catálogo (PRECONS III completo) -----------------------------
    def search_items(self, term: str = "", section: str = "",
                     limit: int = 50) -> List[Dict[str, Any]]:
        """Busca renglones del catálogo por código/nombre y sección."""
        ruleset = self._require_ruleset()
        return ruleset.search(term, section=section, limit=limit)

    def sections(self) -> List[Dict[str, Any]]:
        """Índice de secciones del catálogo (código, nombre, renglones)."""
        ruleset = self._require_ruleset()
        return ruleset.sections()

    def official_price(self, item_code: str) -> Dict[str, Any]:
        """Precio oficial de lista de un renglón con desglose CUP."""
        ruleset = self._require_ruleset()
        return ruleset.official_price(item_code)

    def _require_ruleset(self) -> PreconsRuleset:
        if self.ruleset is None:
            raise DomainError(
                message="No hay ruleset PRECONS cargado",
                code="ARQ-PRE-012",
                suggested_action="Use precons --ruleset <código> para cargarlo.")
        return self.ruleset

    # -- price list ------------------------------------------------------------
    def _prices_from_project(self, price_list_code: str = "GENERAL"
                             ) -> Dict[str, float]:
        """Último precio por recurso de la lista indicada (spec 61).

        Nunca se sobrescribe el histórico: se lee la vigencia más
        reciente con valid_from <= hoy.
        """
        repo = self.ctx.budget_repo
        plist = repo.get_price_list_by_code(self.ctx.project.id, price_list_code)
        if plist is None:
            raise DomainError(
                message=f"Lista de precios no encontrada: {price_list_code}",
                code="ARQ-PRE-013",
                suggested_action="Cree la lista con 'price set' antes de analizar.")
        rows = repo.session.query_all(
            """
            SELECT r.code AS code, p.price AS price
            FROM prices p
            JOIN resources r ON r.id = p.resource_id
            WHERE p.project_id = ? AND p.price_list_id = ?
              AND p.valid_from <= date('now')
            AND p.id = (
                SELECT p2.id FROM prices p2
                WHERE p2.resource_id = p.resource_id
                  AND p2.price_list_id = p.price_list_id
                  AND p2.valid_from <= date('now')
                ORDER BY p2.valid_from DESC, p2.created_at DESC LIMIT 1)
            """,
            (self.ctx.project.id, plist["id"]))
        prices: Dict[str, float] = {}
        for row in rows:
            prices[row["code"]] = float(row["price"])
        return prices

    # -- analyses ------------------------------------------------------------------
    def analyze_item(self, item_code: str, quantity: float,
                     variant: str = "BASE",
                     prices: Optional[Dict[str, float]] = None) -> PriceAnalysis:
        """Análisis de precio de una partida (price analysis).

        Los renglones con precio oficial directo (catálogo PRECONS III
        real) se analizan sin lista de precios de recursos.
        """
        ruleset = self._require_ruleset()
        work_item = ruleset.item(item_code)
        if is_official_item(work_item):
            prices = prices or {}
        else:
            prices = prices if prices is not None \
                else self._prices_from_project()
        analysis = price_analysis(ruleset, item_code, quantity, prices, variant)
        self._store(analysis, parameters={"variant": variant})
        return analysis

    def analyze_project(self, variant: str = "BASE",
                        prices: Optional[Dict[str, float]] = None
                        ) -> Dict[str, Any]:
        """Análisis del proyecto: partidas alimentadas por QTO (spec 59)."""
        ruleset = self._require_ruleset()
        prices = prices if prices is not None else self._prices_from_project()
        from services.quantity_service import QuantityService
        totals = QuantityService(self.ctx).totals_by_formula()
        analyses: List[PriceAnalysis] = []
        skipped: List[Dict[str, str]] = []
        for work_item in ruleset.work_items:
            formula = work_item.get("qto_formula", "")
            if not formula:
                skipped.append({"item": work_item["code"],
                                "reason": "sin fórmula QTO asociada"})
                continue
            quantity = totals.get(formula, 0.0)
            if quantity <= 0:
                skipped.append({"item": work_item["code"],
                                "reason": f"sin cantidades de {formula}"})
                continue
            missing = [i["resource"] for i in work_item.get("indicators", [])
                       if i["resource"] not in prices]
            if missing:
                skipped.append({"item": work_item["code"],
                                "reason": "sin precios: " + ", ".join(missing)})
                continue
            analyses.append(price_analysis(ruleset, work_item["code"],
                                           quantity, prices, variant))
        total = sum(a.total_price for a in analyses)
        for analysis in analyses:
            self._store(analysis, parameters={"variant": variant,
                                              "source": "project"})
        self.ctx.commit()
        return {
            "ruleset": ruleset.code, "version": ruleset.version,
            "variant": variant, "currency": ruleset.currency,
            "analyses": [a.to_dict() for a in analyses],
            "skipped": skipped,
            "total": round(total, 2),
        }

    def compare_variants(self, item_code: str, quantity: float,
                         variants: Optional[List[str]] = None,
                         prices: Optional[Dict[str, float]] = None
                         ) -> Dict[str, Any]:
        """Comparación de variantes de la ruleset (spec 60, 62)."""
        ruleset = self._require_ruleset()
        prices = prices if prices is not None else self._prices_from_project()
        variants = variants or [v.get("code", "BASE") for v in ruleset.variants] \
            or ["BASE"]
        analyses = [price_analysis(ruleset, item_code, quantity, prices, variant)
                    for variant in variants]
        for analysis in analyses:
            self._store(analysis, parameters={"source": "compare"})
        return compare_analyses(analyses)

    # -- importador (spec 60) ---------------------------------------------------
    def import_ruleset(self, data: Any, mapping: Dict[str, str],
                       code: str = "imported", name: str = "",
                       out_path: str = "") -> PreconsRuleset:
        """Importa una base externa con mapa de columnas (spec 60)."""
        ruleset = import_external(data, mapping, code=code, name=name)
        if out_path:
            import json
            directory = os.path.dirname(out_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump({
                    "code": ruleset.code, "name": ruleset.name,
                    "description": "Ruleset importado vía mapa de columnas",
                    "version": ruleset.version,
                    "currency": ruleset.currency,
                    "coefficients": ruleset.coefficients,
                    "resources": ruleset.resources,
                    "work_items": ruleset.work_items,
                    "variants": ruleset.variants,
                }, handle, ensure_ascii=False, indent=2)
        return ruleset

    # -- reporte (spec 60) ---------------------------------------------------------
    def report(self, variant: str = "BASE") -> Dict[str, Any]:
        """Reporte del análisis del proyecto (reportes)."""
        return self.analyze_project(variant=variant)

    # -- persistence -----------------------------------------------------------------
    def _store(self, analysis: PriceAnalysis,
               parameters: Optional[Dict[str, Any]] = None) -> None:
        result_calc = self.ctx.calculations_repo
        from core.calculations.contracts import (
            CalculationMode, CalculationResult, CalculationStatus,
        )
        ruleset = self._require_ruleset()
        result = CalculationResult(
            calculation_type="PRE",
            input_objects=[],
            parameters={"item": analysis.item, "ruleset": ruleset.code,
                        "ruleset_version": ruleset.version,
                        **(parameters or {})},
            values={
                "quantity": round(analysis.quantity, 4),
                "direct_cost": round(analysis.direct_cost, 2),
                "indirect_cost": round(analysis.indirect_cost, 2),
                "benefit": round(analysis.benefit, 2),
                "unit_price": round(analysis.unit_price, 2),
                "total_price": round(analysis.total_price, 2),
            },
            units={"quantity": analysis.unit, "unit_price": analysis.currency,
                   "total_price": analysis.currency},
            errors=[], mode=CalculationMode.BALANCED,
            status=CalculationStatus.COMPLETED, objects_processed=1)
        result_calc.save(result, self.ctx.project.id)


# -- certificación del catálogo oficial (integridad del recurso embebido) -----
# Línea base del libro PRECONS III (RoPres 3.30) certificado 1:1 contra el
# XLSX oficial del repositorio de origen. Cualquier desviación indica un
# catálogo corrupto o una actualización no controlada.

CATALOG_BASELINE: Dict[str, int] = {
    "work_items": 15981,
    "resources": 4383,
    "materials": 3569,
    "equipment": 671,
    "labor": 143,
    "sections": 38,
    "parameters": 8,
    "limits": 4,
}


def certificar_catalogo(code: str = "precons_iii_rospres_330") -> Dict[str, Any]:
    """Certifica la integridad del catálogo PRECONS III embebido (sin proyecto).

    Comprueba los recuentos oficiales (renglones, recursos por tipo,
    secciones, parámetros y límites), la unicidad de códigos, la
    consistencia del desglose de precios (materiales + mano de obra +
    equipos = total) y devuelve el SHA256 del fichero empaquetado.
    Nunca lanza: los fallos viajan en ``report["failures"]``.
    """
    import hashlib
    import json

    from app.paths import resource_path

    path = resource_path("rulesets", f"{code}.json")
    report: Dict[str, Any] = {"code": code, "ok": True, "checks": [],
                              "failures": []}
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        report["ok"] = False
        report["failures"].append(f"catálogo ilegible: {exc}")
        return report
    report["sha256"] = hashlib.sha256(raw).hexdigest()
    report["bytes"] = len(raw)
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        report["ok"] = False
        report["failures"].append(f"JSON corrupto: {exc}")
        return report
    report["version"] = str(data.get("version", ""))

    items = data.get("work_items", [])
    resources = data.get("resources", [])
    sections = {w.get("sec") for w in items if w.get("sec")}
    kinds: Dict[str, int] = {}
    for resource in resources:
        kind = str(resource.get("kind", "OTHER"))
        kinds[kind] = kinds.get(kind, 0) + 1

    real = {
        "work_items": len(items),
        "resources": len(resources),
        "materials": kinds.get("MATERIAL", 0),
        "equipment": kinds.get("EQUIPMENT", 0),
        "labor": kinds.get("LABOR", 0),
        "sections": len(sections),
        "parameters": len(data.get("parameters", {})),
        "limits": len(data.get("limits", {})),
    }
    report["counts"] = real
    for key, expected in CATALOG_BASELINE.items():
        if real[key] == expected:
            report["checks"].append(f"{key}={real[key]}")
        else:
            report["ok"] = False
            report["failures"].append(
                f"{key}: esperado {expected}, obtenido {real[key]}")

    item_codes = [w.get("code") for w in items]
    if len(set(item_codes)) == len(item_codes):
        report["checks"].append("códigos de renglón únicos")
    else:
        report["ok"] = False
        report["failures"].append("códigos de renglón duplicados")
    res_codes = [r.get("code") for r in resources]
    if len(set(res_codes)) == len(res_codes):
        report["checks"].append("códigos de recurso únicos")
    else:
        report["ok"] = False
        report["failures"].append("códigos de recurso duplicados")

    bad = sum(1 for w in items
              if abs((float(w.get("price_material", 0.0) or 0.0)
                      + float(w.get("price_labor", 0.0) or 0.0)
                      + float(w.get("price_equipment", 0.0) or 0.0))
                     - float(w.get("price_ref", 0.0) or 0.0)) > 0.011)
    if bad:
        report["ok"] = False
        report["failures"].append(
            f"desglose materiales+MO+equipos inconsistente en {bad} renglones")
    else:
        report["checks"].append(
            f"desglose de precios consistente ({len(items)} renglones)")
    return report


__all__ = ["PreconsService", "certificar_catalogo", "CATALOG_BASELINE"]
