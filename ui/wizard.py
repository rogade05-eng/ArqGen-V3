"""Asistente dinámico de diseño (v1.7.2): arma tu local paso a paso.

El usuario pidió «un asistente que me pida datos para llenar e ir
armando mi local». Este módulo concentra TODA la lógica (headless,
sin Tk) para que sea verificable con unittest:

- WIZARD_STEPS    — los 4 pasos y su texto orientador.
- LocalWizardData — los datos que el usuario va llenando.
- validate_step() — validación amable paso a paso (errores en español).
- build_plan()    — plan declarativo de creación (nivel, local, 4
  muros, puerta y ventana) a partir de los datos.
- apply_plan()    — ejecuta el plan por las mismas fachadas que la CLI
  (CommandBus, auditoría y eventos), en una sola transacción.
- step_summary()  — resumen legible para el paso de revisión.

La ventana (ui.app_window.open_design_wizard) solo dibuja formularios
y llama a estas funciones: misma separación widgets/lógica que el
resto de la FASE 90.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict, List, Tuple

# -- Definición de los pasos --------------------------------------------------

WIZARD_STEPS: Tuple[Tuple[str, str, str], ...] = (
    ("1", "¿Dónde va el local?",
     "Elige el nivel de la edificación (o crea uno nuevo aquí mismo) y "
     "ponle un nombre que reconozcas después."),
    ("2", "¿De qué tamaño?",
     "Dinos el ancho y el fondo del local en metros, y en qué punto del "
     "plano colocamos su esquina inferior izquierda."),
    ("3", "¿Puerta y ventana?",
     "Marca lo que quieras incluir. Sugerimos puerta de 0,9 m en el "
     "frente y, si quieres, una ventana en el fondo."),
    ("4", "Resumen y creación",
     "Revisa tranquilo: si algo no convence, «Atrás» para corregirlo. "
     "Al crear, el local queda dibujado con sus muros y vanos."),
)

# Lados disponibles para vanos, en el orden en que se recorren los
# muros (sentido horario empezando por el frente).
DOOR_SIDES: Tuple[str, ...] = ("Frente", "Derecha", "Fondo", "Izquierda")

# Lado → índice del muro en build_plan (mismo orden que DOOR_SIDES).
SIDE_INDEX: Dict[str, int] = {"Frente": 0, "Derecha": 1, "Fondo": 2,
                              "Izquierda": 3}

NUEVO_NIVEL = "＋ Crear un nivel nuevo…"


@dataclass
class LocalWizardData:
    """Datos que el usuario llena a lo largo de los 4 pasos."""

    # Paso 1 — ubicación
    level_ref: str = ""            # nombre del nivel existente
    new_level: bool = False        # «crear un nivel nuevo» marcado
    new_level_name: str = ""
    new_level_elevation_m: float = 0.0
    name: str = ""                 # nombre del local
    space_type: str = "ROOM"

    # Paso 2 — medidas
    x0_m: float = 0.0
    y0_m: float = 0.0
    width_m: float = 4.0
    depth_m: float = 3.0
    thickness_m: float = 0.2

    # Paso 3 — vanos
    with_door: bool = True
    door_width_m: float = 0.9
    door_height_m: float = 2.1
    door_side: str = "Frente"
    with_window: bool = False
    window_width_m: float = 1.2
    window_height_m: float = 1.2
    window_sill_m: float = 0.9
    window_side: str = "Fondo"


def parse_float_es(text: str, field_name: str) -> float:
    """Convierte texto a float aceptando coma decimal («3,5» → 3.5).

    Lanza ValueError con mensaje en español para mostrarlo tal cual en
    el asistente.
    """
    raw = (text or "").strip().replace(",", ".")
    if not raw:
        raise ValueError(f"«{field_name}» necesita un número.")
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(
            f"«{field_name}» no es un número válido: «{text}».") from None
    return value


# -- Validación paso a paso -----------------------------------------------------

def _side_length(data: LocalWizardData, side: str) -> float:
    """Longitud del muro del lado elegido (ancho o fondo del local)."""
    return data.depth_m if side in ("Izquierda", "Derecha") else data.width_m


def side_wall(data: LocalWizardData, side: str) -> Tuple[Tuple[float, float],
                                                         Tuple[float, float]]:
    """Segmento (inicio, fin) del muro del lado elegido, sent. horario."""
    x0, y0, w, d = data.x0_m, data.y0_m, data.width_m, data.depth_m
    return (
        ((x0, y0), (x0 + w, y0)) if side == "Frente" else
        ((x0 + w, y0), (x0 + w, y0 + d)) if side == "Derecha" else
        ((x0 + w, y0 + d), (x0, y0 + d)) if side == "Fondo" else
        ((x0, y0 + d), (x0, y0))
    )


def validate_step(step: int, data: LocalWizardData) -> List[str]:
    """Devuelve la lista de problemas del paso (vacía = todo bien).

    Los mensajes hablan en primera persona del local («necesito un
    nombre») para acompañar sin regañar.
    """
    errors: List[str] = []
    if step == 0:  # ¿Dónde?
        if data.new_level:
            if not data.new_level_name.strip():
                errors.append("Para crear un nivel nuevo necesito su "
                              "nombre (por ejemplo, «Piso 2»).")
        elif not data.level_ref.strip() or \
                data.level_ref == NUEVO_NIVEL:
            errors.append("Elige el nivel donde irá el local, o marca "
                          "«Crear un nivel nuevo».")
        if not data.name.strip():
            errors.append("Necesito un nombre para el local (por "
                          "ejemplo, «Sala de reuniones»).")
    elif step == 1:  # ¿Tamaño?
        if data.width_m <= 0 or data.depth_m <= 0:
            errors.append("El ancho y el fondo deben ser mayores que "
                          "cero metros.")
        elif data.width_m > 500 or data.depth_m > 500:
            errors.append("¿Seguro? Medidas de más de 500 m suelen ser "
                          "un error de tecleo.")
        if data.thickness_m <= 0:
            errors.append("El espesor del muro debe ser positivo "
                          "(0,2 m = 20 cm es lo habitual).")
        elif data.thickness_m * 2 >= min(data.width_m, data.depth_m):
            errors.append("El espesor de los muros se come el local: "
                          "baja el espesor o agranda las medidas.")
    elif step == 2:  # ¿Vanos?
        if data.with_door:
            length = _side_length(data, data.door_side)
            if data.door_width_m <= 0 or data.door_height_m <= 0:
                errors.append("La puerta necesita ancho y alto "
                              "positivos.")
            elif data.door_width_m > length:
                errors.append(
                    f"La puerta ({data.door_width_m:.2f} m) no cabe en "
                    f"el muro {data.door_side.lower()} "
                    f"({length:.2f} m).")
            if data.with_window and data.window_side == data.door_side \
                    and data.window_width_m + data.door_width_m > length:
                errors.append(
                    "La puerta y la ventana no caben juntas en el mismo "
                    "muro: cambia alguna de lado.")
        if data.with_window:
            length = _side_length(data, data.window_side)
            if data.window_width_m <= 0 or data.window_height_m <= 0:
                errors.append("La ventana necesita ancho y alto "
                              "positivos.")
            elif data.window_width_m > length:
                errors.append(
                    f"La ventana ({data.window_width_m:.2f} m) no cabe "
                    f"en el muro {data.window_side.lower()} "
                    f"({length:.2f} m).")
            if data.window_sill_m < 0:
                errors.append("El antepecho de la ventana no puede ser "
                              "negativo.")
    # Paso 3 (resumen) no valida nada: siempre se puede revisar.
    return errors


# -- Plan declarativo y ejecución -------------------------------------------------

def build_plan(data: LocalWizardData) -> List[Tuple[str, Dict[str, Any]]]:
    """Plan declarativo de creación a partir de los datos del asistente.

    Orden garantizado: (nivel nuevo si toca) → local → 4 muros →
    puerta → ventana. La GUI y las pruebas pueden inspeccionarlo antes
    de ejecutarlo.
    """
    plan: List[Tuple[str, Dict[str, Any]]] = []
    level_ref = data.level_ref
    if data.new_level:
        level_ref = data.new_level_name.strip()
        plan.append(("LEVEL", {
            "name": level_ref,
            "elevation_m": data.new_level_elevation_m,
            "height_m": 3.0,
        }))
    x0, y0, w, d = data.x0_m, data.y0_m, data.width_m, data.depth_m
    boundary = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + d), (x0, y0 + d)]
    plan.append(("SPACE", {
        "level_ref": level_ref, "name": data.name.strip(),
        "space_type": data.space_type.strip() or "ROOM",
        "boundary": boundary,
    }))
    walls = [side_wall(data, side) for side in DOOR_SIDES]
    for start, end in walls:
        plan.append(("WALL", {
            "level_ref": level_ref, "start": start, "end": end,
            "thickness_m": data.thickness_m,
        }))
    if data.with_door:
        length = data.depth_m if data.door_side in ("Izquierda",
                                                    "Derecha") \
            else data.width_m
        offset = max(0.0, (length - data.door_width_m) / 2.0)
        plan.append(("DOOR", {
            "wall_ref": _wall_code_hint(plan, SIDE_INDEX[data.door_side]),
            "width_m": data.door_width_m,
            "height_m": data.door_height_m,
            "offset_m": offset,
        }))
    if data.with_window:
        length = data.depth_m if data.window_side in ("Izquierda",
                                                      "Derecha") \
            else data.width_m
        offset = max(0.0, (length - data.window_width_m) / 2.0)
        plan.append(("WINDOW", {
            "wall_ref": _wall_code_hint(plan, SIDE_INDEX[data.window_side]),
            "width_m": data.window_width_m,
            "height_m": data.window_height_m,
            "offset_m": offset,
            "sill_height_m": data.window_sill_m,
        }))
    return plan


def _wall_code_hint(plan: List[Tuple[str, Dict[str, Any]]],
                    wall_index: int) -> int:
    """Índice del comando WALL dentro del plan (para vincular vanos).

    Los muros se crean justo después del local; el vano debe apuntar
    al muro creado en la posición correspondiente. Devolvemos el
    índice DENTRO del plan y apply_plan lo resuelve al código real.
    """
    count_level = 1 if any(op == "LEVEL" for op, _ in plan) else 0
    return count_level + 1 + wall_index  # +1 por el propio SPACE


def apply_plan(data: LocalWizardData, ctx: Any) -> Dict[str, Any]:
    """Ejecuta el plan por las fachadas oficiales y devuelve resumen.

    Usa ArchitectureService (CommandBus §76, auditoría §71 y eventos
    §75) exactamente como la CLI, y confirma una sola vez al final:
    si algo falla, el proyecto queda como antes.
    """
    from services.architecture_service import ArchitectureService

    arch = ArchitectureService(ctx)
    plan = build_plan(data)
    wall_codes: List[str] = []
    created: Dict[str, Any] = {"walls": wall_codes, "door": "",
                               "window": "", "level": "", "space": ""}
    pending_vanos: List[Tuple[str, int, Dict[str, Any]]] = []

    for position, (op, params) in enumerate(plan):
        if op == "LEVEL":
            level = arch.create_level(
                name=params["name"], elevation_m=params["elevation_m"],
                height_m=params["height_m"])
            created["level"] = level.code
        elif op == "SPACE":
            space = arch.create_space(**params)
            created["space"] = space.code
        elif op == "WALL":
            wall = arch.create_wall(
                level_ref=params["level_ref"], start=params["start"],
                end=params["end"], thickness_m=params["thickness_m"])
            wall_codes.append(wall.code)
        else:  # DOOR / WINDOW: resolvemos el muro cuando exista
            pending_vanos.append((op, params["wall_ref"], params))

    for op, wall_index, params in pending_vanos:
        wall_code = wall_codes[_real_wall_index(plan, wall_index)]
        kind = "DOOR" if op == "DOOR" else "WINDOW"
        opening = arch.create_opening(
            kind=kind, wall_ref=wall_code,
            width_m=params["width_m"], height_m=params["height_m"],
            offset_m=params["offset_m"],
            sill_height_m=params.get("sill_height_m", 0.0) or 0.0)
        created[kind.lower()] = opening.code

    # INSTALACIONES (v3.8.0): el local no se queda aislado en la
    # arquitectura; queda conectado a las redes del proyecto (luminaria
    # + toma en la «Red eléctrica», y aparatos sanitarios con desagüe
    # si es un local húmedo). Si el proyecto no tiene redes, se crean.
    from services.installations_generator import connect_local
    inst_summary: Dict[str, Any] = {"redes": 0, "equipos": 0, "tramos": 0,
                                    "nombres": []}
    if created.get("space"):
        inst_summary = connect_local(ctx, created["space"],
                                     origin="asistente de local")
        created["warnings"] = inst_summary.get("warnings", [])
    created["instalaciones"] = inst_summary

    ctx.commit()
    created["local_name"] = data.name.strip()
    return created


def _real_wall_index(plan: List[Tuple[str, Dict[str, Any]]],
                     plan_index: int) -> int:
    """Índice del muro (0-3) a partir de su posición en el plan."""
    wall_positions = [i for i, (op, _p) in enumerate(plan) if op == "WALL"]
    if plan_index not in wall_positions:
        return 0
    return wall_positions.index(plan_index)


def step_summary(data: LocalWizardData) -> str:
    """Resumen legible del paso 4 (lo que se va a crear)."""
    lines: List[str] = []
    level = data.new_level_name.strip() if data.new_level \
        else data.level_ref.strip()
    lines.append(f"Local «{data.name.strip()}» "
                 f"(tipo {data.space_type.strip() or 'ROOM'})")
    lines.append(f"· Nivel: {level}"
                 + (" (se crea ahora, cota 0 m por defecto)"
                    if data.new_level else ""))
    lines.append(f"· Medidas: {data.width_m:.2f} m de ancho × "
                 f"{data.depth_m:.2f} m de fondo, esquina en "
                 f"({data.x0_m:.2f}, {data.y0_m:.2f})")
    lines.append(f"· Muros: 4 lados de {data.thickness_m:.2f} m de "
                 "espesor")
    if data.with_door:
        lines.append(f"· Puerta: {data.door_width_m:.2f} × "
                     f"{data.door_height_m:.2f} m en el lado "
                     f"{data.door_side.lower()}")
    else:
        lines.append("· Puerta: no")
    if data.with_window:
        lines.append(f"· Ventana: {data.window_width_m:.2f} × "
                     f"{data.window_height_m:.2f} m (antepecho "
                     f"{data.window_sill_m:.2f} m) en el lado "
                     f"{data.window_side.lower()}")
    else:
        lines.append("· Ventana: no")
    return "\n".join(lines)


def data_from_values(step: int, values: Dict[str, Any],
                     data: LocalWizardData) -> List[str]:
    """Vuelca un dict del formulario en «data» y devuelve errores.

    Separa los errores de conversión (parse_float_es) de los de
    validación: la GUI llama a esto en cada «Siguiente» y muestra la
    lista completa tal cual.
    """
    conversion_errors: List[str] = []
    float_fields = {
        0: {"new_level_elevation_m": "Cota del nivel nuevo"},
        1: {"x0_m": "Posición X", "y0_m": "Posición Y",
            "width_m": "Ancho", "depth_m": "Fondo",
            "thickness_m": "Espesor"},
        2: {"door_width_m": "Ancho de la puerta",
            "door_height_m": "Alto de la puerta",
            "window_width_m": "Ancho de la ventana",
            "window_height_m": "Alto de la ventana",
            "window_sill_m": "Antepecho"},
    }.get(step, {})
    for key, label in float_fields.items():
        if key in values and values[key] not in ("", None):
            try:
                setattr(data, key,
                        parse_float_es(str(values[key]), label))
            except ValueError as exc:
                conversion_errors.append(str(exc))
    if step == 0:
        data.new_level = bool(values.get("new_level"))
        data.level_ref = (values.get("level_ref") or "").strip()
        data.new_level_name = (values.get("new_level_name") or "").strip()
        data.name = (values.get("name") or "").strip()
        data.space_type = (values.get("space_type") or "").strip() \
            or "ROOM"
    elif step == 2:
        data.with_door = bool(values.get("with_door"))
        data.door_side = values.get("door_side") or "Frente"
        data.with_window = bool(values.get("with_window"))
        data.window_side = values.get("window_side") or "Fondo"
    return conversion_errors


def wizard_field_names() -> List[str]:
    """Todos los campos del asistente (para pruebas y ayuda)."""
    return [f.name for f in fields(LocalWizardData)]


__all__ = [
    "WIZARD_STEPS", "DOOR_SIDES", "SIDE_INDEX", "NUEVO_NIVEL",
    "LocalWizardData", "parse_float_es", "side_wall", "validate_step",
    "build_plan", "apply_plan", "step_summary", "data_from_values",
    "wizard_field_names",
]
