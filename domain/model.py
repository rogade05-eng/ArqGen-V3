"""Domain entities of the unique semantic model (spec sections 7, 20).

Project → Site → Building → Level → Zone → Space → Wall → Door/Window/Opening.
One wall is ONE wall: every discipline reads the same object (spec 111).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.entities.base import Entity, EntityStatus
from core.errors import DomainError
from core.geometry.engine import area as geom_area
from core.geometry.primitives import Point, Polygon


@dataclass
class Project(Entity):
    ENTITY_TYPE = "PROJECT"
    name: str = ""
    client: str = ""
    address: str = ""
    description: str = ""
    units_length: str = "m"
    ruleset_code: str = ""
    currency: str = "CUP"

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.name:
            raise DomainError(
                message="El proyecto requiere un nombre",
                code="ARQ-DOM-002",
            )


@dataclass
class Site(Entity):
    ENTITY_TYPE = "SITE"
    name: str = ""
    area_m2: float = 0.0
    boundary: Optional[List[Tuple[float, float]]] = None


@dataclass
class Building(Entity):
    ENTITY_TYPE = "BUILDING"
    site_id: Optional[str] = None
    name: str = ""
    floors: int = 1
    description: str = ""


@dataclass
class Level(Entity):
    ENTITY_TYPE = "LEVEL"
    building_id: Optional[str] = None
    name: str = ""
    elevation_m: float = 0.0
    height_m: float = 3.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.height_m <= 0:
            raise DomainError(
                message=f"La altura del nivel '{self.name}' debe ser positiva",
                code="ARQ-DOM-003",
                context={"height_m": self.height_m},
            )


@dataclass
class Zone(Entity):
    """Zones: PUBLIC / PRIVATE / SERVICE / TECHNICAL / CIRCULATION / EMERGENCY / EXTERIOR (spec 17)."""

    ENTITY_TYPE = "ZONE"
    name: str = ""
    kind: str = "SERVICE"
    allowed_kinds: Tuple[str, ...] = (
        "PUBLIC", "PRIVATE", "SERVICE", "TECHNICAL",
        "CIRCULATION", "EMERGENCY", "EXTERIOR",
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind not in self.allowed_kinds:
            raise DomainError(
                message=f"Tipo de zona inválido: {self.kind}",
                code="ARQ-DOM-004",
                context={"kind": self.kind, "allowed": list(self.allowed_kinds)},
            )


@dataclass
class Space(Entity):
    ENTITY_TYPE = "SPACE"
    level_id: str = ""
    zone_id: Optional[str] = None
    name: str = ""
    space_type: str = "ROOM"          # key into Space DNA
    boundary: List[Tuple[float, float]] = field(default_factory=list)  # meters

    def polygon(self) -> Polygon:
        return Polygon([Point(x, y) for x, y in self.boundary])

    def area_m2(self) -> float:
        if len(self.boundary) < 3:
            return 0.0
        return geom_area(self.polygon())

    def perimeter_m(self) -> float:
        if len(self.boundary) < 3:
            return 0.0
        return sum(s.length for s in self.polygon().segments())


RELATIONSHIP_KINDS: Tuple[str, ...] = (
    "adjacent_to",
    "accessible_from",
    "requires_access",
    "visually_related_to",
    "acoustically_separated_from",
    "service_related_to",
)


@dataclass
class SpaceRelationship(Entity):
    """Relationships are logical entities too (spec section 8)."""

    ENTITY_TYPE = "SPACE_RELATIONSHIP"
    from_space_id: str = ""
    to_space_id: str = ""
    kind: str = "adjacent_to"
    source: str = "manual"  # geometry | knowledge | manual

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind not in RELATIONSHIP_KINDS:
            raise DomainError(
                message=f"Tipo de relación inválido: {self.kind}",
                code="ARQ-DOM-005",
                context={"kind": self.kind, "allowed": list(RELATIONSHIP_KINDS)},
            )


@dataclass
class Wall(Entity):
    ENTITY_TYPE = "WALL"
    level_id: str = ""
    start: Tuple[float, float] = (0.0, 0.0)
    end: Tuple[float, float] = (1.0, 0.0)
    thickness_m: float = 0.2
    height_m: float = 3.0
    base_offset_m: float = 0.0
    material_id: Optional[str] = None
    structural: bool = False

    @property
    def length_m(self) -> float:
        return Point(*self.start).distance_to(Point(*self.end))


@dataclass
class Opening(Entity):
    """Base for Door / Window / generic Opening cut into a wall."""

    ENTITY_TYPE = "OPENING"
    level_id: str = ""
    wall_id: str = ""
    kind: str = "OPENING"            # DOOR | WINDOW | OPENING
    width_m: float = 0.9
    height_m: float = 2.1
    offset_m: float = 0.0            # distance along wall from start
    sill_height_m: float = 0.0       # for windows
    swing: str = "LEFT"              # doors
    material_id: Optional[str] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind not in ("DOOR", "WINDOW", "OPENING"):
            raise DomainError(
                message=f"Tipo de vano inválido: {self.kind}",
                code="ARQ-DOM-006",
                context={"kind": self.kind},
            )
        if self.width_m <= 0 or self.height_m <= 0:
            raise DomainError(
                message="Las dimensiones del vano deben ser positivas",
                code="ARQ-DOM-007",
                context={"width_m": self.width_m, "height_m": self.height_m},
            )

    @property
    def area_m2(self) -> float:
        return self.width_m * self.height_m


@dataclass
class Door(Opening):
    ENTITY_TYPE = "DOOR"
    kind: str = "DOOR"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.kind = "DOOR"


@dataclass
class Window(Opening):
    ENTITY_TYPE = "WINDOW"
    kind: str = "WINDOW"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.kind = "WINDOW"
        if self.sill_height_m < 0:
            raise DomainError(
                message="La altura de antepecho no puede ser negativa",
                code="ARQ-DOM-008",
            )


@dataclass
class Furniture(Entity):
    """Pieza de mobiliario colocada DENTRO de un local (v3.15.0).

    «kind» es la clave del catálogo de domain/mobiliario.py; la posición
    (x, y) es el CENTRO de la pieza en metros y el rectángulo se orienta
    con rotation_deg (antihorario). Es una entidad de arquitectura más:
    auditoría, undo persistente, códigos ARQ-FURNITURE-nnn y QTO.
    """

    ENTITY_TYPE = "FURNITURE"
    level_id: str = ""
    space_id: str = ""
    kind: str = "MOB"
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    width_m: float = 1.0
    depth_m: float = 0.5
    height_m: float = 0.75

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.width_m <= 0 or self.depth_m <= 0 or self.height_m <= 0:
            raise DomainError(
                message="Las dimensiones del mobiliario deben ser positivas",
                code="ARQ-DOM-090",
                context={"width_m": self.width_m, "depth_m": self.depth_m,
                         "height_m": self.height_m},
            )


@dataclass
class Roof(Entity):
    """Cubierta de la edificación sobre el nivel superior (v3.15.0).

    ``tipologia`` ∈ plana_transitable / plana_no_transitable / un_agua /
    dos_aguas / cuatro_aguas; ``material`` es la clave del catálogo de
    domain/cubiertas.py. La geometría viaja en ``footprint`` (contorno
    del ALERO, con vuelo) y ``ridge`` (cumbrera, None en plana); la
    pendiente es en % y ``altura_cumbrera_m`` sobre el nivel.
    """

    ENTITY_TYPE = "ROOF"
    level_id: str = ""
    tipologia: str = "plana_no_transitable"
    material: str = "losa_impermeabilizada"
    estructura: str = "hormigon"
    pendiente_pct: float = 2.0
    alero_m: float = 0.6
    altura_cumbrera_m: float = 0.0
    footprint: List[Tuple[float, float]] = field(default_factory=list)
    ridge: Optional[Tuple[Tuple[float, float], Tuple[float, float]]] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.pendiente_pct < 0 or self.pendiente_pct > 100:
            raise DomainError(
                message="La pendiente de la cubierta debe estar entre 0 y 100 %",
                code="ARQ-DOM-091",
                context={"pendiente_pct": self.pendiente_pct},
            )


@dataclass
class Ramp(Entity):
    """Rampa accesible resolviendo un desnivel (v3.15.0).

    ``corners`` son los 4 vértices de la huella en planta (los 2 del
    pie a cota baja, los 2 de arriba a cota alta); ``desnivel_m`` es la
    altura salvada y ``slope_pct`` la pendiente (longitud horizontal =
    length_m). Normativa CTE DB-SUA1 en domain/accesibilidad.py.
    """

    ENTITY_TYPE = "RAMP"
    level_id: str = ""
    space_id: str = ""
    corners: List[Tuple[float, float]] = field(default_factory=list)
    width_m: float = 1.20
    length_m: float = 1.50
    desnivel_m: float = 0.15
    slope_pct: float = 10.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.width_m <= 0 or self.length_m <= 0 or self.desnivel_m < 0:
            raise DomainError(
                message="Dimensiones de rampa inválidas",
                code="ARQ-DOM-092",
                context={"width_m": self.width_m, "length_m": self.length_m,
                         "desnivel_m": self.desnivel_m},
            )


@dataclass
class Handrail(Entity):
    """Barandilla o pasamanos sobre un tramo (v3.15.0).

    ``points`` es la polilínea en planta; ``kind`` ∈ barandilla /
    barandilla_rampa / barra_apoyo. Con ``altura_secundaria_m`` > 0 se
    pinta el doble pasamanos (0.65 + 0.95 m en rampas, DB-SUA1).
    """

    ENTITY_TYPE = "HANDRAIL"
    level_id: str = ""
    space_id: str = ""
    kind: str = "barandilla"
    points: List[Tuple[float, float]] = field(default_factory=list)
    altura_m: float = 0.90
    altura_secundaria_m: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.altura_m <= 0 or self.altura_secundaria_m < 0:
            raise DomainError(
                message="Las alturas de la barandilla deben ser positivas",
                code="ARQ-DOM-093",
                context={"altura_m": self.altura_m},
            )


@dataclass
class Elevator(Entity):
    """Hueco de ascensor con cabina según Neufert (v3.18.0).

    ``tipo`` es la clave del catálogo de domain/ascensores.py
    (pasajeros/hospital/montacargas/panoramico); ``width_m`` y
    ``depth_m`` son las dimensiones del HUECO en planta (ancho ×
    fondo), ``(x, y)`` el centro del hueco y ``rotation_deg`` el giro
    en planta. La puerta mira hacia ``puerta_lado`` (N/S/E/O, en la
    metadata) y el foso, el recorrido superior y la velocidad viajan
    en metadata como datos de referencia del libro.
    """

    ENTITY_TYPE = "ELEVATOR"
    level_id: str = ""
    tipo: str = "pasajeros"
    capacidad_kg: int = 630
    personas: int = 8
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    width_m: float = 1.80
    depth_m: float = 2.05
    puerta_m: float = 0.80

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.width_m <= 0 or self.depth_m <= 0 or self.capacidad_kg <= 0:
            raise DomainError(
                message="Las dimensiones y la capacidad del ascensor "
                        "deben ser positivas",
                code="ARQ-DOM-094",
                context={"width_m": self.width_m, "depth_m": self.depth_m,
                         "capacidad_kg": self.capacidad_kg},
            )


@dataclass
class Parasol(Entity):
    """Parasol (brise-soleil) sobre una fachada del edificio (v3.18.0).

    ``side`` ∈ N/S/E/O según la orientación del recinto (S = el lado
    de y mínima); ``tipo`` ∈ horizontal/vertical/mixto/lamas_moviles
    (catálogo de domain/fachadas.py); ``length_m`` es el largo de la
    fachada cubierta y ``(x, y)`` el centro de la línea de fachada.
    Las láamas se reparten entre ``altura_inicio_m`` y ``altura_fin_m``
    cada ``separacion_m`` (horizontales) o a lo largo de la fachada
    (verticales); ``n_lamas`` queda calculado al generar.
    """

    ENTITY_TYPE = "PARASOL"
    level_id: str = ""
    side: str = "S"
    tipo: str = "horizontal"
    material: str = "aluminio"
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    length_m: float = 1.0
    profundidad_m: float = 0.50
    separacion_m: float = 0.60
    n_lamas: int = 0
    altura_inicio_m: float = 0.0
    altura_fin_m: float = 3.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.length_m <= 0 or self.profundidad_m <= 0 \
                or self.separacion_m <= 0 or self.n_lamas < 0:
            raise DomainError(
                message="Dimensiones de parasol inválidas",
                code="ARQ-DOM-095",
                context={"length_m": self.length_m,
                         "profundidad_m": self.profundidad_m,
                         "separacion_m": self.separacion_m},
            )


@dataclass
class Stair(Entity):
    """Escalera por tipología según Neufert (v3.19.0).

    ``tipo`` es la clave del catálogo de domain/escaleras.py (recta,
    en L, en U/doble piso y caracol); ``(x, y)`` es el centro del
    recinto que ocupa y ``desnivel_m`` la altura a salvar. La
    contrahuella y la huella respetan la fórmula de Blondel
    (2·h + p = 0.60-0.64 m); la GEOMETRÍA generada (contorno,
    huellas de cada peldaño y mesetas, ya rotadas en planta) viaja
    en metadata para que el lienzo 2D y la vista 3D la dibujen
    sin repetir el cálculo.
    """

    ENTITY_TYPE = "STAIR"
    level_id: str = ""
    space_id: str = ""
    tipo: str = "recta"
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    width_m: float = 1.10
    desnivel_m: float = 3.0
    contrahuella_m: float = 0.17
    huella_m: float = 0.29

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.width_m <= 0 or self.desnivel_m <= 0 \
                or self.contrahuella_m <= 0 or self.huella_m <= 0:
            raise DomainError(
                message="Las dimensiones de la escalera deben ser "
                        "positivas",
                code="ARQ-DOM-097",
                context={"width_m": self.width_m,
                         "desnivel_m": self.desnivel_m,
                         "contrahuella_m": self.contrahuella_m,
                         "huella_m": self.huella_m},
            )


@dataclass
class FacadeSkin(Entity):
    """Piel exterior (doble piel / celosía / malla...) del edificio
    (v3.18.0).

    ``tipo`` es la clave del catálogo de domain/fachadas.py (doble
    piel de vidrio, celosía, malla metálica, baguettes de terracota,
    panel perforado, jardín vertical, GRC, policarbonato); el plano
    de la piel corre PARALELO a la fachada ``side`` separado de ella
    ``separacion_m`` (la cámara ventilada) y cubre ``length_m`` de
    fachada por ``altura_m`` de alto, desde su nivel de base.
    """

    ENTITY_TYPE = "SKIN"
    level_id: str = ""
    side: str = "S"
    tipo: str = "doble_piel_vidrio"
    material: str = "vidrio"
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    length_m: float = 1.0
    altura_m: float = 3.0
    separacion_m: float = 0.60

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.length_m <= 0 or self.altura_m <= 0 \
                or self.separacion_m <= 0:
            raise DomainError(
                message="Dimensiones de piel exterior inválidas",
                code="ARQ-DOM-096",
                context={"length_m": self.length_m,
                         "altura_m": self.altura_m,
                         "separacion_m": self.separacion_m},
            )


__all__ = [
    "Project", "Site", "Building", "Level", "Zone", "Space",
    "SpaceRelationship", "RELATIONSHIP_KINDS", "Wall", "Opening",
    "Door", "Window", "Furniture", "Roof", "Ramp", "Handrail",
    "Stair", "Elevator", "Parasol", "FacadeSkin",
]
