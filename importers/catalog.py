"""PRECONS catalog import (spec 59-60, 94): .xlsx/.csv/.json -> ruleset.

Pipeline stages (spec 94):
DETECT (format + sheet sniff) -> PARSE (importers.tables) -> VALIDATE
(required columns) -> MAP (explicit mapping JSON or synonym
auto-detection) -> CONVERT (engines.precons_engine.import_external) ->
PREVIEW (report) -> APPROVE (caller decides) -> IMPORT (write ruleset
JSON) -> AUDIT (caller).

Two external shapes are understood:
- flat: one row per (partida, insumo) with yield/waste columns;
- multi-sheet: items + optional resources/indicators/prices sheets.

An explicit mapping JSON may override every guess::

    {"items_sheet": "PARTIDAS", "resources_sheet": "RECURSOS",
     "indicators_sheet": "RENDIMIENTOS", "prices_sheet": "PRECIOS",
     "version": "2026.1",
     "columns": {"item_code": "CODIGO", "item_name": "DESCRIPCION",
                 "item_unit": "UM", "res_code": "INSUMO",
                 "yield": "CANTIDAD", "waste": "MERMA",
                 "price": "PRECIO"}}
"""

from __future__ import annotations

import json
import os
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from core.errors import ImportErrorARQ
from engines.precons_engine import import_external
from importers.tables import read_table, to_numeric

SHEET_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "items": ("partida", "work_item", "actividade", "trabajo", "concepto",
              "analisis", "análisis"),
    "indicators": ("rendimiento", "indicator", "indicador", "insumo_partida",
                   "desperdicio"),
    "resources": ("recurso", "resource", "insumo", "material", "suministro"),
    "prices": ("precio", "price", "costo", "tarifa", "lista"),
}

COLUMN_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "item_code": ("partida", "codigo_partida", "codigo", "clave", "code",
                  "id_partida", "no_partida", "numero", "num", "item"),
    "item_name": ("nombre", "nombre_partida", "descripcion", "name",
                  "concepto", "detalle", "desc"),
    "item_unit": ("unidad", "um", "u_m", "unidad_medida", "unit"),
    "item_formula": ("qto_formula", "formula", "formula_qto", "qto"),
    "res_code": ("recurso", "insumo", "codigo_recurso", "resource",
                 "codigo_insumo", "clave_recurso", "codigo", "code", "clave"),
    "res_name": ("nombre_recurso", "descripcion_recurso", "resource_name",
                 "nombre_insumo", "descripcion_insumo"),
    "res_kind": ("tipo", "kind", "tipo_recurso", "categoria", "clasificacion"),
    "res_unit": ("unidad_recurso", "um_recurso", "unidad_insumo",
                 "unidad", "um"),
    "yield": ("rendimiento", "cantidad", "coeficiente", "yield", "cant",
              "cantidad_recurso"),
    "waste": ("desperdicio", "merma", "waste", "waste_pct", "pct_merma"),
    "price": ("precio", "price", "costo", "importe", "valor"),
}

RESOURCE_KINDS = ("MATERIAL", "LABOR", "EQUIPMENT", "TRANSPORT", "OTHER")

# -- Formato PRECONS III (libro oficial RoPres) ------------------------------
# Hojas: PORTADA, SECCIONES, RENGLONES_PRECONS, MATERIALES, EQUIPOS,
# MANO_OBRA, PARAMETROS, LIMITES, INSTRUCCIONES. El disparador del shape
# "precons" es la hoja de renglones (RENGLONES_PRECONS).
PRECONS_SHEET_HINTS: Dict[str, Tuple[str, ...]] = {
    "items": ("renglones",),
    "sections": ("seccione",),
    "materials": ("materiales",),
    "equipment": ("equipos",),
    "labor": ("mano_obra", "mano de obra", "manoobra"),
    "parameters": ("parametro",),
    "limits": ("limite",),
    "instructions": ("instruccione",),
}

PRECONS_ITEM_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "item_code": ("codigo precons", "codigo", "code"),
    "item_name": ("descripcion", "nombre"),
    "item_unit": ("unidad", "um"),
    "sec": ("seccion codigo", "seccion"),
    "sec_name": ("seccion",),
    "cap": ("capitulo codigo", "capitulo"),
    "cap_name": ("capitulo",),
    "sub": ("subcapitulo codigo", "subcapitulo"),
    "sub_name": ("subcapitulo",),
    "price_material": ("materiales cup", "materiales"),
    "price_labor": ("mano de obra cup", "mano de obra"),
    "price_equipment": ("equipos cup", "equipos"),
    "price_total": ("total cup", "total"),
}

PRECONS_RESOURCE_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "res_code": ("codigo", "code"),
    "res_name": ("descripcion", "nombre"),
    "res_unit": ("unidad", "um"),
    "price": ("precio oficial cup", "tarifa horaria cup", "precio oficial",
              "tarifa horaria", "precio"),
    "peso": ("peso kg", "peso"),
}

PRECONS_PARAM_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "code": ("codigo", "code"),
    "name": ("parametro", "nombre"),
    "value": ("valor",),
    "unit": ("unidad",),
    "note": ("nota",),
}

PRECONS_LIMIT_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "code": ("codigo", "code"),
    "name": ("limite / coeficiente", "limite", "nombre"),
    "value": ("valor",),
    "unit": ("unidad",),
    "note": ("referencia", "nota"),
}

PRECONS_SECTION_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "code": ("codigo", "code"),
    "name": ("seccion", "nombre"),
    "count": ("renglones",),
}

PRECONS_INSTRUCTION_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "tema": ("tema",),
    "detalle": ("detalle",),
}

PRECONS_RESOURCE_KINDS: Dict[str, str] = {
    "materials": "MATERIAL",
    "equipment": "EQUIPMENT",
    "labor": "LABOR",
}

FLAT_ITEM_FIELDS = ("item_code", "item_name", "item_unit", "item_formula",
                    "res_code", "res_name", "res_kind", "res_unit",
                    "yield", "waste")
ITEM_FIELDS = ("item_code", "item_name", "item_unit", "item_formula")
RESOURCE_FIELDS = ("res_code", "res_name", "res_kind", "res_unit")
PRICE_FIELDS = ("res_code", "item_code", "price")


def _norm(text: Any) -> str:
    value = str(text or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    return "".join(c for c in value if not unicodedata.combining(c))


def _resolve_columns(columns: List[str], keys: Tuple[str, ...],
                     extra: Tuple[str, ...] = ()) -> Optional[str]:
    """First header matching a synonym (accent/case insensitive)."""
    normalized = {_norm(c): c for c in columns if c}
    for key in tuple(keys) + tuple(extra):
        if _norm(key) in normalized:
            return normalized[_norm(key)]
    return None


class CatalogImporter:
    """Import pipeline for external PRECONS bases with explicit mapping."""

    def __init__(self, mapping: Optional[Dict[str, Any]] = None) -> None:
        self.mapping = dict(mapping or {})
        self.report: Dict[str, Any] = {}

    # -- DETECT + PARSE ------------------------------------------------------
    def _load_sheets(self, path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Returns (parsed, warnings). JSON goes through the dict path."""
        if path.lower().endswith(".json"):
            with open(path, "r", encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except ValueError as exc:
                    raise ImportErrorARQ(
                        message=f"JSON ilegible: {exc}", code="ARQ-IMP-021",
                        context={"path": path}) from exc
            if not isinstance(data, dict):
                raise ImportErrorARQ(
                    message="El JSON externo debe ser un objeto",
                    code="ARQ-IMP-041", context={"path": path})
            return {"format": "json", "data": data}, []
        parsed = read_table(path)
        return parsed, []

    def _detect_precons_sheets(self, parsed: Dict[str, Any]
                               ) -> Dict[str, List[Dict[str, Any]]]:
        """Hojas del libro oficial PRECONS III (shape "precons").

        Devuelve {} salvo que exista la hoja de renglones. Las claves
        ``<role>_sheet`` del mapping anulan la detección por nombre.
        """
        named: Dict[str, List[Dict[str, Any]]] = {}
        for name, rows in parsed["sheets"].items():
            if not rows:
                continue
            low = _norm(name)
            for role, hints in PRECONS_SHEET_HINTS.items():
                if role in named:
                    continue
                if any(hint in low for hint in hints):
                    named[role] = rows
                    break
        for role in PRECONS_SHEET_HINTS:
            explicit = self.mapping.get(f"{role}_sheet")
            if explicit:
                for name, rows in parsed["sheets"].items():
                    if _norm(name) == _norm(explicit):
                        named[role] = rows
                        break
        return named

    def _precons_cols(self, rows: List[Dict[str, Any]],
                      synonyms: Dict[str, Tuple[str, ...]]) -> Dict[str, str]:
        """Resolución de columnas PRECONS III con overrides del mapping."""
        overrides = self.mapping.get("columns", {}) or {}
        columns = self._sheet_columns(rows)
        resolved: Dict[str, str] = {}
        for field, keys in synonyms.items():
            override = overrides.get(field)
            header = override if override in columns else None
            if header is None:
                header = _resolve_columns(columns, keys)
            if header is not None:
                resolved[field] = header
        return resolved

    def _role_of_sheet(self, name: str) -> Optional[str]:
        low = _norm(name)
        for role, hints in SHEET_SYNONYMS.items():
            for hint in hints:
                if hint in low:
                    return role
        return None

    def _sheet_columns(self, rows: List[Dict[str, Any]]) -> List[str]:
        return list(rows[0].keys()) if rows else []

    # -- MAP -----------------------------------------------------------------
    def _detect_roles(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        detected: Dict[str, Any] = {"shape": "multi"}
        sheets = parsed["sheets"]
        named: Dict[str, List[Dict[str, Any]]] = {}
        unmatched: List[str] = []
        for name, rows in sheets.items():
            if not rows:
                continue
            low = _norm(name)
            detected_role = self._role_of_sheet(name)
            role = None
            if detected_role:
                explicit = self.mapping.get(f"{detected_role}_sheet")
                if explicit is None or _norm(explicit) == low:
                    role = detected_role
            if role and role not in named:
                named[role] = rows
                detected[f"{role}_sheet"] = name
            else:
                unmatched.append(name)
        if "items" not in named:
            data_rows = list(sheets.values())
            filled = [rows for rows in data_rows if rows]
            if len(filled) == 1:
                named["items"] = filled[0]
                detected["shape"] = "flat"
                detected["items_sheet"] = next(
                    n for n, r in sheets.items() if r is filled[0])
            else:
                raise ImportErrorARQ(
                    message="No se detectó ninguna hoja de partidas",
                    code="ARQ-IMP-040",
                    context={"sheets": list(sheets.keys())},
                    suggested_action="Renombre la hoja de partidas "
                    "(p. ej. PARTIDAS) o proporcione un mapa JSON con "
                    "items_sheet/resources_sheet/indicators_sheet.")
        detected["_named"] = named
        detected["_unmatched"] = unmatched
        return detected

    def _columns_for(self, rows: List[Dict[str, Any]],
                     fields: Tuple[str, ...]) -> Dict[str, str]:
        overrides = self.mapping.get("columns", {}) or {}
        columns = self._sheet_columns(rows)
        resolved: Dict[str, str] = {}
        for field in fields:
            override = overrides.get(field)
            header = override if override in columns else None
            if header is None:
                header = _resolve_columns(columns, COLUMN_SYNONYMS[field])
            if header is not None:
                resolved[field] = header
        return resolved

    # -- CONVERT -------------------------------------------------------------
    def _value(self, row: Dict[str, Any], header: Optional[str]) -> Any:
        if header is None:
            return None
        return row.get(header)

    def _build_flat(self, rows: List[Dict[str, Any]], cols: Dict[str, str],
                    warnings: List[str], skipped: List[int]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        index: Dict[str, Dict[str, Any]] = {}
        for position, row in enumerate(rows, start=1):
            code = self._value(row, cols.get("item_code"))
            if code is None or not str(code).strip():
                skipped.append(position)
                continue
            code = str(code).strip()
            item = index.get(code)
            if item is None:
                item = {"code": code, "name": "", "unit": "",
                        "qto_formula": "", "indicators": []}
                index[code] = item
                items.append(item)
            if not item["name"] and self._value(row, cols.get("item_name")):
                item["name"] = str(self._value(row, cols["item_name"])).strip()
            if not item["unit"] and self._value(row, cols.get("item_unit")):
                item["unit"] = str(self._value(row, cols["item_unit"])).strip()
            res = self._value(row, cols.get("res_code"))
            if res is None or not str(res).strip():
                warnings.append(f"Fila {position}: partida {code} sin insumo; "
                                "se ignora el renglón")
                continue
            item["indicators"].append({
                "resource": str(res).strip(),
                "yield": to_numeric(self._value(row, cols.get("yield")), 0.0),
                "waste_pct": to_numeric(self._value(row, cols.get("waste")), 0.0),
            })
        return items

    def _build_multi(self, named: Dict[str, List[Dict[str, Any]]],
                     detected: Dict[str, Any], warnings: List[str],
                     skipped: List[int]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        item_cols = self._columns_for(named["items"], ITEM_FIELDS)
        items: List[Dict[str, Any]] = []
        index: Dict[str, Dict[str, Any]] = {}
        for position, row in enumerate(named["items"], start=1):
            code = self._value(row, item_cols.get("item_code"))
            if code is None or not str(code).strip():
                skipped.append(position)
                continue
            code = str(code).strip()
            if code in index:
                warnings.append(f"Hoja {detected.get('items_sheet')}: "
                                f"partida duplicada {code}; se conserva la primera")
                continue
            item = {
                "code": code,
                "name": str(self._value(row, item_cols.get("item_name")) or "").strip(),
                "unit": str(self._value(row, item_cols.get("item_unit")) or "").strip(),
                "qto_formula": str(self._value(row, item_cols.get("item_formula")) or "").strip(),
                "indicators": [],
            }
            index[code] = item
            items.append(item)

        resources: List[Dict[str, Any]] = []
        if "resources" in named:
            res_cols = self._columns_for(named["resources"], RESOURCE_FIELDS)
            seen = set()
            for position, row in enumerate(named["resources"], start=1):
                code = self._value(row, res_cols.get("res_code"))
                if code is None or not str(code).strip():
                    skipped.append(position)
                    continue
                code = str(code).strip()
                if code in seen:
                    continue
                seen.add(code)
                kind = str(self._value(row, res_cols.get("res_kind")) or "OTHER").strip().upper()
                resources.append({
                    "code": code,
                    "name": str(self._value(row, res_cols.get("res_name")) or "").strip(),
                    "kind": kind if kind in RESOURCE_KINDS else "OTHER",
                    "unit": str(self._value(row, res_cols.get("res_unit")) or "").strip(),
                })

        if "indicators" in named:
            ind_rows = named["indicators"]
            ind_cols = {
                "item_code": (self.mapping.get("columns", {}) or {}).get("item_code")
                or _resolve_columns(self._sheet_columns(ind_rows),
                                    COLUMN_SYNONYMS["item_code"]),
                "resource": (self.mapping.get("columns", {}) or {}).get("res_code")
                or _resolve_columns(self._sheet_columns(ind_rows),
                                    COLUMN_SYNONYMS["res_code"]),
                "yield": (self.mapping.get("columns", {}) or {}).get("yield")
                or _resolve_columns(self._sheet_columns(ind_rows),
                                    COLUMN_SYNONYMS["yield"]),
                "waste": (self.mapping.get("columns", {}) or {}).get("waste")
                or _resolve_columns(self._sheet_columns(ind_rows),
                                    COLUMN_SYNONYMS["waste"]),
            }
            for position, row in enumerate(ind_rows, start=1):
                code = self._value(row, ind_cols["item_code"])
                res = self._value(row, ind_cols["resource"])
                if not code or not res:
                    skipped.append(position)
                    continue
                code, res = str(code).strip(), str(res).strip()
                if code not in index:
                    warnings.append(f"Indicador de partida inexistente {code}; "
                                    "se ignora")
                    continue
                index[code]["indicators"].append({
                    "resource": res,
                    "yield": to_numeric(self._value(row, ind_cols["yield"]), 0.0),
                    "waste_pct": to_numeric(self._value(row, ind_cols["waste"]), 0.0),
                })
        return items, resources

    # -- shape precons -------------------------------------------------------
    def _convert_precons(self, path: str, parsed: Dict[str, Any],
                         named: Dict[str, List[Dict[str, Any]]],
                         warnings: List[str], skipped: List[int]
                         ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """Convierte el libro oficial PRECONS III en ruleset + precios.

        RENGLONES_PRECONS -> work_items con jerarquía (sección/capítulo/
        subcapítulo) y desglose oficial CUP; MATERIALES/EQUIPOS/MANO_OBRA
        -> resources con precio oficial (y peso de materiales);
        PARAMETROS/LIMITES/INSTRUCCIONES -> metadatos del ruleset.
        """
        item_cols = self._precons_cols(named["items"], PRECONS_ITEM_SYNONYMS)
        if "item_code" not in item_cols:
            raise ImportErrorARQ(
                message="La hoja de renglones no tiene columna de código",
                code="ARQ-IMP-044",
                context={"columns": self._sheet_columns(named["items"])},
                suggested_action="Renombre la columna de código (p. ej. "
                "'Código PRECONS') o use un mapa JSON con columns.item_code.")

        items: List[Dict[str, Any]] = []
        seen: set = set()
        for position, row in enumerate(named["items"], start=1):
            code = self._value(row, item_cols.get("item_code"))
            if code is None or not str(code).strip():
                skipped.append(position)
                continue
            code = str(code).strip()
            if code in seen:
                warnings.append(
                    f"Hoja {named.get('_items_sheet_name', 'renglones')}: "
                    f"renglón duplicado {code}; se conserva el primero")
                continue
            seen.add(code)
            pm = to_numeric(self._value(row, item_cols.get("price_material")), 0.0)
            pl = to_numeric(self._value(row, item_cols.get("price_labor")), 0.0)
            pe = to_numeric(self._value(row, item_cols.get("price_equipment")), 0.0)
            pt = to_numeric(self._value(row, item_cols.get("price_total")), None)
            if pt is None:
                pt = round(pm + pl + pe, 2)
            items.append({
                "code": code,
                "name": str(self._value(row, item_cols.get("item_name")) or "").strip(),
                "unit": str(self._value(row, item_cols.get("item_unit")) or "").strip(),
                "sec": str(self._value(row, item_cols.get("sec")) or "").strip(),
                "sec_name": str(self._value(row, item_cols.get("sec_name")) or "").strip(),
                "cap": str(self._value(row, item_cols.get("cap")) or "").strip(),
                "cap_name": str(self._value(row, item_cols.get("cap_name")) or "").strip(),
                "sub": str(self._value(row, item_cols.get("sub")) or "").strip(),
                "sub_name": str(self._value(row, item_cols.get("sub_name")) or "").strip(),
                "price_material": round(pm, 2),
                "price_labor": round(pl, 2),
                "price_equipment": round(pe, 2),
                "price_ref": round(float(pt), 2),
                "indicators": [],
            })

        resources: List[Dict[str, Any]] = []
        prices: Dict[str, float] = {}
        for role in ("materials", "equipment", "labor"):
            rows = named.get(role)
            if not rows:
                continue
            cols = self._precons_cols(rows, PRECONS_RESOURCE_SYNONYMS)
            seen_res: set = set()
            for position, row in enumerate(rows, start=1):
                code = self._value(row, cols.get("res_code"))
                if code is None or not str(code).strip():
                    skipped.append(position)
                    continue
                code = str(code).strip()
                if code in seen_res:
                    continue
                seen_res.add(code)
                price = to_numeric(self._value(row, cols.get("price")), 0.0)
                resource: Dict[str, Any] = {
                    "code": code,
                    "name": str(self._value(row, cols.get("res_name")) or "").strip(),
                    "kind": PRECONS_RESOURCE_KINDS[role],
                    "unit": str(self._value(row, cols.get("res_unit")) or "").strip(),
                    "price_ref": round(price, 2),
                }
                if cols.get("peso"):
                    peso = to_numeric(self._value(row, cols.get("peso")), None)
                    if peso is not None:
                        resource["peso_kg"] = round(peso, 4)
                resources.append(resource)
                prices[code] = round(price, 2)

        parameters: Dict[str, Any] = {}
        if "parameters" in named:
            cols = self._precons_cols(named["parameters"],
                                      PRECONS_PARAM_SYNONYMS)
            for row in named["parameters"]:
                code = self._value(row, cols.get("code"))
                if code is None or not str(code).strip():
                    continue
                raw_value = self._value(row, cols.get("value"))
                value = to_numeric(raw_value, raw_value)
                parameters[str(code).strip()] = {
                    "name": str(self._value(row, cols.get("name")) or "").strip(),
                    "value": value,
                    "unit": str(self._value(row, cols.get("unit")) or "").strip(),
                    "note": str(self._value(row, cols.get("note")) or "").strip(),
                }

        limits: Dict[str, Any] = {}
        if "limits" in named:
            cols = self._precons_cols(named["limits"],
                                      PRECONS_LIMIT_SYNONYMS)
            for row in named["limits"]:
                code = self._value(row, cols.get("code"))
                if code is None or not str(code).strip():
                    continue
                raw_value = self._value(row, cols.get("value"))
                value = to_numeric(raw_value, raw_value)
                limits[str(code).strip()] = {
                    "name": str(self._value(row, cols.get("name")) or "").strip(),
                    "value": value,
                    "unit": str(self._value(row, cols.get("unit")) or "").strip(),
                    "reference": str(self._value(row, cols.get("note")) or "").strip(),
                }

        instrucciones: List[Dict[str, str]] = []
        if "instructions" in named:
            cols = self._precons_cols(named["instructions"],
                                      PRECONS_INSTRUCTION_SYNONYMS)
            for row in named["instructions"]:
                tema = str(self._value(row, cols.get("tema")) or "").strip()
                detalle = str(self._value(row, cols.get("detalle")) or "").strip()
                if tema or detalle:
                    instrucciones.append({"tema": tema, "detalle": detalle})

        source, generated, rospres = self._precons_source(parsed)
        if instrucciones:
            source["instrucciones"] = instrucciones
        self._validate_precons_totals(parsed, items, resources, warnings)

        # validación de secciones (conteo por sección)
        if "sections" in named:
            cols = self._precons_cols(named["sections"], PRECONS_SECTION_SYNONYMS)
            counted: Dict[str, int] = {}
            for item in items:
                counted[item["sec"]] = counted.get(item["sec"], 0) + 1
            for row in named["sections"]:
                code = self._value(row, cols.get("code"))
                expected = to_numeric(self._value(row, cols.get("count")), None)
                if code is None or expected is None:
                    continue
                got = counted.get(str(code).strip(), 0)
                if got != int(expected):
                    warnings.append(
                        f"Sección {code}: {got} renglones en el libro "
                        f"vs {int(expected)} declarados")

        if not items:
            raise ImportErrorARQ(
                message="No se detectó ningún renglón válido en el libro",
                code="ARQ-IMP-045",
                context={"sheets": list(parsed["sheets"].keys())},
                suggested_action="Verifique que la hoja RENGLONES_PRECONS "
                "tenga datos y columna de código.")

        payload: Dict[str, Any] = {
            "code": self.mapping.get("code", "imported"),
            "name": self.mapping.get("name", "") or "Catálogo PRECONS III",
            "version": str(self.mapping.get("version") or rospres or "1.0"),
            "currency": "CUP",
            "description": f"Catálogo PRECONS III importado desde "
                           f"{os.path.basename(path)}",
            "coefficients": dict(self.mapping.get("coefficients", {}) or {}),
            "resources": resources,
            "work_items": items,
            "variants": [{"code": "BASE", "multiplier": 1.0,
                          "description": "Base del catálogo oficial"}],
            "parameters": parameters,
            "limits": limits,
            "source": source,
            "generated": generated,
        }
        from engines.precons_engine import PreconsRuleset
        PreconsRuleset.from_dict(payload)  # VALIDATE: carga estructural

        sample = [{"code": code, "price": price}
                  for code, price in list(prices.items())[:5]]
        prices_preview = {
            "count": len(prices), "sample": sample,
            "sheet": "+".join(
                role for role in ("materials", "equipment", "labor")
                if role in named),
        }
        warnings.append(
            f"{len(prices)} precios oficiales de recursos detectados: "
            "disponibles para la lista de precios del proyecto.")

        report: Dict[str, Any] = {
            "file": path, "format": parsed["format"], "shape": "precons",
            "sheets": {name: len(rows)
                       for name, rows in parsed["sheets"].items()},
            "detected": {f"{role}_sheet": True for role in named},
            "columns": {"items": item_cols},
            "counts": {"work_items": len(items), "resources": len(resources),
                       "parameters": len(parameters), "limits": len(limits),
                       "instructions": len(instrucciones),
                       "prices": len(prices), "skipped_rows": len(skipped)},
            "warnings": warnings, "errors": [],
        }
        self.report = report
        return payload, report, prices_preview

    @staticmethod
    def _portada_rows(parsed: Dict[str, Any]) -> List[List[str]]:
        """Filas de la PORTADA como listas de valores no vacíos.

        read_table toma la primera fila como encabezado (aquí el título
        del libro), así que los pares clave-valor se leen de los valores
        de cada fila, no de sus claves.
        """
        rows_out: List[List[str]] = []
        for name, rows in parsed["sheets"].items():
            if "portada" not in _norm(name):
                continue
            for row in rows:
                cells = [str(value).strip() for value in row.values()
                         if value is not None and str(value).strip()]
                if cells:
                    rows_out.append(cells)
        return rows_out

    def _precons_source(self, parsed: Dict[str, Any]
                        ) -> Tuple[Dict[str, Any], str, str]:
        """Metadatos de la PORTADA (versión RoPres, fecha, fuentes).

        La PORTADA del libro PRECONS III es una lista de pares
        clave-valor ('Versión de RoPres' | '3.30'). Devuelve
        (source, generated, rospres).
        """
        source: Dict[str, Any] = {}
        generated = ""
        rospres = ""
        fuentes: List[str] = []
        for cells in self._portada_rows(parsed):
            for index, cell in enumerate(cells):
                key = _norm(cell)
                nxt = cells[index + 1] if index + 1 < len(cells) else ""
                if "ropres" in key and nxt:
                    rospres = nxt.replace(",", ".")
                elif "fecha" in key and nxt:
                    generated = nxt
                elif key.startswith("fuente") and nxt:
                    fuentes.append(nxt)
        if fuentes:
            source["fuentes"] = fuentes
        if rospres:
            source["rospres"] = rospres
        return source, generated, rospres

    def _validate_precons_totals(self, parsed: Dict[str, Any],
                                 items: List[Dict[str, Any]],
                                 resources: List[Dict[str, Any]],
                                 warnings: List[str]) -> None:
        """Contrasta los conteos declarados en PORTADA con los importados."""
        expected: Dict[str, int] = {}
        for cells in self._portada_rows(parsed):
            for index, cell in enumerate(cells):
                if index + 1 >= len(cells):
                    continue
                value = to_numeric(cells[index + 1], None)
                key = _norm(cell)
                if value is not None and key and "ropres" not in key:
                    expected[key] = int(value)
        by_kind: Dict[str, int] = {"MATERIAL": 0, "EQUIPMENT": 0, "LABOR": 0}
        for resource in resources:
            kind = resource.get("kind", "OTHER")
            by_kind[kind] = by_kind.get(kind, 0) + 1
        checks = (("renglones de listas de costos", len(items)),
                  ("materiales", by_kind["MATERIAL"]),
                  ("equipos", by_kind["EQUIPMENT"]),
                  ("mano de obra", by_kind["LABOR"]))
        for key, got in checks:
            declared = None
            for declared_key, value in expected.items():
                if key in declared_key:
                    declared = value
                    break
            if declared is not None and declared != got:
                warnings.append(
                    f"PORTADA declara {declared} {key} pero el libro "
                    f"contiene {got}")

    # -- stages --------------------------------------------------------------
    def preview(self, path: str) -> Dict[str, Any]:
        """DETECT+PARSE+VALIDATE+MAP+CONVERT -> report (no files written)."""
        _, report, _ = self.convert(path)
        return report

    def convert(self, path: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """Returns (ruleset_dict, report, prices_preview)."""
        parsed, warnings = self._load_sheets(path)
        skipped: List[int] = []
        if parsed["format"] == "json":
            data = parsed["data"]
            mapping = {"work_items": "work_items", "resources": "resources",
                       "indicators": "indicators"}
            ruleset = import_external(
                data, mapping,
                code=self.mapping.get("code", "imported"),
                name=self.mapping.get("name", ""),
                version=str(self.mapping.get("version", "1.0")))
            report = {
                "file": path, "format": "json", "shape": "dict",
                "counts": {"resources": len(ruleset.resources),
                           "work_items": len(ruleset.work_items)},
                "warnings": warnings, "errors": [],
            }
            return self._ruleset_to_dict(ruleset), report, {}

        precons_named = self._detect_precons_sheets(parsed)
        if "items" in precons_named:
            return self._convert_precons(
                path, parsed, precons_named, warnings, skipped)
        detected = self._detect_roles(parsed)
        named = detected["_named"]
        prices_preview: Dict[str, Any] = {}
        if "items" in named and detected["shape"] == "flat":
            cols = self._columns_for(named["items"], FLAT_ITEM_FIELDS)
            if cols.get("res_code") is not None and \
                    cols.get("res_code") == cols.get("item_code"):
                cols.pop("res_code")  # same column cannot be both roles
            if "res_code" not in cols:
                raise ImportErrorARQ(
                    message="La hoja plana no tiene columna de insumo/recurso",
                    code="ARQ-IMP-042",
                    context={"columns": self._sheet_columns(named["items"])},
                    suggested_action="Renombre la columna del insumo o use un "
                    "mapa JSON con columns.res_code.")
            items: List[Dict[str, Any]] = self._build_flat(
                named["items"], cols, warnings, skipped)
            resources: List[Dict[str, Any]] = []
        else:
            items, resources = self._build_multi(
                named, detected, warnings, skipped)

        if "prices" in named:
            price_cols = self._columns_for(named["prices"], PRICE_FIELDS)
            price_header = price_cols.get("price") or next(
                (c for c in self._sheet_columns(named["prices"])
                 if "precio" in _norm(c) or c.lower() == "price"), None)
            code_header = price_cols.get("res_code") or price_cols.get("item_code")
            count = 0
            sample: List[Dict[str, Any]] = []
            for row in named["prices"]:
                code = self._value(row, code_header)
                price = to_numeric(self._value(row, price_header), None) \
                    if price_header else None
                if code is None or price is None:
                    continue
                count += 1
                if len(sample) < 5:
                    sample.append({"code": str(code).strip(), "price": price})
            if count:
                prices_preview = {"count": count, "sample": sample,
                                  "sheet": detected.get("prices_sheet")}
                warnings.append(
                    f"{count} precios detectados en '{detected.get('prices_sheet')}': "
                    "los precios se cargan en el proyecto con 'price set' "
                    "(no van dentro del ruleset).")

        errors: List[str] = []
        if not items:
            errors.append("No se detectó ninguna partida válida")
        empty_indicators = [i["code"] for i in items if not i["indicators"]]
        if empty_indicators:
            warnings.append(f"{len(empty_indicators)} partidas sin indicadores: "
                            f"{', '.join(empty_indicators[:5])}"
                            + ("…" if len(empty_indicators) > 5 else ""))

        item_codes = {i["code"] for i in items}
        resource_codes = {i["resource"] for i in
                          (ind for item in items for ind in item["indicators"])}
        missing = sorted(resource_codes - {r["code"] for r in resources})
        if missing and "resources" in named:
            warnings.append(
                f"{len(missing)} insumos usados en indicadores no están en la "
                f"hoja de recursos: {', '.join(missing[:5])}"
                + ("…" if len(missing) > 5 else ""))

        mapping = {"work_items": "work_items", "resources": "resources",
                   "indicators": "indicators"}
        ruleset = import_external(
            {"work_items": items, "resources": resources}, mapping,
            code=self.mapping.get("code", "imported"),
            name=self.mapping.get("name", ""),
            version=str(self.mapping.get("version", "1.0")))
        _ = item_codes  # reserved for future strict validation
        report = {
            "file": path, "format": parsed["format"],
            "shape": detected["shape"],
            "sheets": {name: len(rows) for name, rows in parsed["sheets"].items()},
            "detected": {k: detected[k] for k in
                         ("shape", "items_sheet", "resources_sheet",
                          "indicators_sheet", "prices_sheet") if k in detected},
            "columns": {role: self._columns_for(
                named[role],
                FLAT_ITEM_FIELDS if role == "items"
                and detected["shape"] == "flat"
                else ITEM_FIELDS if role == "items"
                else RESOURCE_FIELDS if role == "resources"
                else PRICE_FIELDS)
                for role in named if role != "indicators"},
            "counts": {"resources": len(ruleset.resources),
                       "work_items": len(ruleset.work_items),
                       "indicators": sum(len(i["indicators"]) for i in items),
                       "skipped_rows": len(skipped)},
            "warnings": warnings, "errors": errors,
        }
        self.report = report
        return self._ruleset_to_dict(ruleset), report, prices_preview

    def apply(self, path: str, code: str = "imported", name: str = "",
              out_path: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """APPROVE+IMPORT: writes the ruleset JSON and returns (dict, report)."""
        ruleset, report, _ = self.convert(path)
        if report["errors"]:
            raise ImportErrorARQ(
                message=f"La importación tiene errores de validación: "
                f"{report['errors']}",
                code="ARQ-IMP-043", context={"file": path})
        payload = dict(ruleset)
        payload["code"] = code or payload["code"]
        payload["name"] = name or payload["name"]
        payload["description"] = f"Catálogo importado desde {os.path.basename(path)}"
        if out_path:
            directory = os.path.dirname(os.path.abspath(out_path))
            os.makedirs(directory, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        report["applied"] = bool(out_path)
        report["out_path"] = out_path
        self.report = report
        return payload, report

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _ruleset_to_dict(ruleset) -> Dict[str, Any]:
        return {
            "code": ruleset.code, "name": ruleset.name,
            "version": ruleset.version, "currency": ruleset.currency,
            "coefficients": ruleset.coefficients,
            "resources": ruleset.resources,
            "work_items": ruleset.work_items,
            "variants": ruleset.variants,
        }


__all__ = ["CatalogImporter", "SHEET_SYNONYMS", "COLUMN_SYNONYMS",
           "PRECONS_SHEET_HINTS", "PRECONS_ITEM_SYNONYMS",
           "PRECONS_RESOURCE_SYNONYMS"]
