"""Documentation engine (spec sections 68, 69, 70, 106) — pure functions.

FASE 34 - DOCUMENTATION. No project access here: the service layer feeds
project data in and receives rendered text/structures back. Everything is
deterministic so the regression suite can hash the outputs.

    * render_template   {{VAR}} substitution with a strict variable map
                        (unknown variables are an error, spec 82 contract)
    * available_variables / collect_variables
    * build_titleblock  title block of a sheet from project + drawing data
    * dimension_text    dimension annotation text at a given scale
    * area_table / openings_table / elements_table — cuadros y listados
    * module_doc        automatic per-module documentation (spec 106)
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.errors import DataError

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_.]+)\}\}")

# DocTemplate building blocks (spec 70) accepted by the renderer.
TEMPLATE_BLOCKS: Tuple[str, ...] = (
    "variables", "sections", "tables", "images", "drawings", "styles",
    "headers", "footers",
)


def collect_placeholders(text: str) -> List[str]:
    """Sorted unique {{VAR}} names referenced by a text."""
    return sorted(set(PLACEHOLDER.findall(text or "")))


def render_template(text: str, variables: Dict[str, Any]) -> str:
    """Substitute every ``{{VAR}}`` using the variable map.

    Unknown or missing variables raise DataError (ARQ-DAT-DOC) listing the
    missing names — the renderer never leaves silent placeholders.
    """
    found = PLACEHOLDER.findall(text or "")
    missing = sorted({name for name in found if name not in variables})
    if missing:
        raise DataError(
            message="Variables sin resolver en la plantilla: "
                    + ", ".join("{{%s}}" % m for m in missing),
            code="ARQ-DAT-DOC-010",
            context={"missing": missing,
                     "available": sorted(variables)},
            suggested_action="Defina las variables o revise la plantilla "
                             "('docs variables' lista las disponibles).")
    return PLACEHOLDER.sub(
        lambda m: _to_text(variables[m.group(1)]), text or "")


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def build_titleblock(project: Dict[str, Any], drawing: Dict[str, Any],
                     app_version: str = "") -> Dict[str, str]:
    """Title block fields of one sheet (spec 69: titleblock)."""
    return {
        "PROJECT": str(project.get("name", "")),
        "CLIENT": str(project.get("client", "")),
        "ADDRESS": str(project.get("address", "")),
        "SHEET": str(drawing.get("sheet", "")),
        "SCALE": str(drawing.get("scale", "")),
        "VIEW": str(drawing.get("view", "")),
        "ORIENTATION": str(drawing.get("orientation", "")),
        "SIZE": str(drawing.get("sheet_size", "")),
        "APP_VERSION": app_version,
    }


def dimension_text(real_mm: float, scale_denominator: int,
                   unit: str = "m", decimals: int = 2) -> str:
    """Dimension annotation: real length drawn at 1:scale_denominator."""
    real_units = real_mm / 1000.0
    return f"{real_units:.{decimals}f} {unit}"


def area_table(spaces: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cuadro de superficies: one row per space + TOTAL row.

    Each input row needs name, area (m2), perimeter (m), occupancy (pers).
    """
    rows: List[Dict[str, Any]] = []
    total_area = 0.0
    total_perimeter = 0.0
    total_occ = 0.0
    for s in spaces:
        area = float(s.get("area", 0.0))
        perimeter = float(s.get("perimeter", 0.0))
        occupancy = float(s.get("occupancy", 0.0))
        total_area += area
        total_perimeter += perimeter
        total_occ += occupancy
        rows.append({
            "name": s.get("name", ""), "area": area,
            "perimeter": perimeter, "occupancy": occupancy,
            "area_per_person": (area / occupancy) if occupancy > 0 else 0.0,
        })
    rows.append({"name": "TOTAL", "area": total_area,
                 "perimeter": total_perimeter, "occupancy": total_occ,
                 "area_per_person": (total_area / total_occ) if total_occ > 0 else 0.0,
                 "total": True})
    return rows


def openings_table(openings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cuadro de vanos: doors/windows with widths, heights and areas."""
    rows: List[Dict[str, Any]] = []
    for o in openings:
        width = float(o.get("width", 0.0))
        height = float(o.get("height", 0.0))
        rows.append({
            "code": o.get("code", ""), "kind": o.get("kind", ""),
            "host": o.get("host", ""), "width": width, "height": height,
            "area": round(width * height, 4),
        })
    return rows


def elements_table(entities: Iterable[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Any]]:
    """Generic listing: project rows restricted to the chosen columns."""
    rows: List[Dict[str, Any]] = []
    for e in entities:
        rows.append({c: e.get(c, "") for c in columns})
    return rows


def format_table(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> str:
    """Render a markdown table deterministically (cuadros/listados)."""
    if not rows:
        return "(sin datos)"
    if columns is None:
        seen: List[str] = []
        for r in rows:
            for key in r:
                if key not in seen:
                    seen.append(key)
        columns = seen
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("-" * len(c) for c in columns) + " |"
    lines = [header, separator]
    for r in rows:
        lines.append("| " + " | ".join(_to_text(r.get(c, "")) for c in columns) + " |")
    return "\n".join(lines)


def module_doc(module_name: str, summary: Dict[str, Any]) -> str:
    """Automatic per-module documentation (spec 106).

    ``summary`` keys: purpose, api (list of callables), data_model (list),
    rules (list), formulas (list), tests (list), changelog (list).
    """
    lines: List[str] = [f"# {module_name}", ""]
    lines.append("## README")
    lines.append(str(summary.get("purpose", "")))
    lines.append("")
    lines.append("## API")
    api = summary.get("api") or []
    lines.extend(f"- `{item}`" for item in api) if api else lines.append("(sin elementos)")
    lines.append("")
    lines.append("## DATA MODEL")
    dm = summary.get("data_model") or []
    lines.extend(f"- {item}" for item in dm) if dm else lines.append("(sin elementos)")
    lines.append("")
    lines.append("## RULES")
    rules = summary.get("rules") or []
    lines.extend(f"- {item}" for item in rules) if rules else lines.append("(sin elementos)")
    lines.append("")
    lines.append("## FORMULAS")
    formulas = summary.get("formulas") or []
    lines.extend(f"- {item}" for item in formulas) if formulas else lines.append("(sin elementos)")
    lines.append("")
    lines.append("## TESTS")
    tests = summary.get("tests") or []
    lines.extend(f"- {item}" for item in tests) if tests else lines.append("(sin elementos)")
    lines.append("")
    lines.append("## CHANGELOG")
    changelog = summary.get("changelog") or []
    lines.extend(f"- {item}" for item in changelog) if changelog else lines.append("(sin elementos)")
    return "\n".join(lines)


def render_markdown_document(title: str, sections: List[Tuple[str, str]],
                             header: str = "", footer: str = "") -> str:
    """Assemble a markdown document: header, titled sections, footer."""
    parts: List[str] = []
    if header:
        parts.append(header.strip())
        parts.append("")
    parts.append(f"# {title}")
    parts.append("")
    for section_title, body in sections:
        parts.append(f"## {section_title}")
        parts.append("")
        parts.append((body or "").strip())
        parts.append("")
    if footer:
        parts.append(footer.strip())
    return "\n".join(parts).strip() + "\n"


def render_html_document(title: str, markdown_text: str) -> str:
    """Minimal deterministic markdown → HTML for the doc exporter.

    Supports the subset produced by this module: headings (#, ##),
    bullet lists (-), tables (| ... |), bold (**x**) and paragraphs.
    """
    out: List[str] = ["<!DOCTYPE html>", "<html>", "<head>",
                      f"<title>{_escape(title)}</title>", "</head>", "<body>"]
    table_buf: List[str] = []
    list_buf: List[str] = []

    def flush_table() -> None:
        if not table_buf:
            return
        rows = [r for r in table_buf if not set(r.replace("|", "").strip()) <= {"-", " ", ":"}]
        out.append("<table>")
        for i, r in enumerate(rows):
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            tag = "th" if i == 0 else "td"
            out.append("<tr>" + "".join(
                f"<{tag}>{_escape(c)}</{tag}>" for c in cells) + "</tr>")
        out.append("</table>")
        table_buf.clear()

    def flush_list() -> None:
        if not list_buf:
            return
        out.append("<ul>")
        out.extend(f"<li>{_escape(item)}</li>" for item in list_buf)
        out.append("</ul>")
        list_buf.clear()

    for raw in (markdown_text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("|"):
            flush_list()
            table_buf.append(stripped)
            continue
        flush_table()
        if stripped.startswith("- "):
            list_buf.append(stripped[2:])
            continue
        flush_list()
        if stripped.startswith("## "):
            out.append(f"<h2>{_escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{_escape(stripped[2:])}</h1>")
        elif stripped:
            out.append(f"<p>{_escape(stripped)}</p>")
    flush_table()
    flush_list()
    out.append("</body>")
    out.append("</html>")
    return "\n".join(out)


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


__all__ = [
    "collect_placeholders", "render_template", "build_titleblock",
    "dimension_text", "area_table", "openings_table", "elements_table",
    "format_table", "module_doc", "render_markdown_document",
    "render_html_document", "TEMPLATE_BLOCKS",
]
