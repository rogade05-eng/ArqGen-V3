use crate::json::{list, number, object, text, Value};

pub const ENGINE_VERSION: &str = "mvp0.18-rust-0.15.0";
pub const REQUEST_SCHEMA: &str = "arqgen-brief-v8";
pub const RESERVATION_PROVENANCE: &str = "user_sketch_unverified";
pub const PLOT_SKETCH_STATUS: &str = "orthogonal_plot_sketch_2d_only";
pub const FRONT_APPROACH_STATUS: &str = "declared_front_trace_sketch_2d_only";
pub const EPS: f64 = 1e-7;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

impl Rect {
    pub fn area(self) -> f64 {
        self.w * self.h
    }
    pub fn right(self) -> f64 {
        self.x + self.w
    }
    pub fn bottom(self) -> f64 {
        self.y + self.h
    }
    pub fn center(self) -> (f64, f64) {
        (self.x + self.w / 2.0, self.y + self.h / 2.0)
    }
    pub fn contains(self, other: Self) -> bool {
        other.x + EPS >= self.x
            && other.y + EPS >= self.y
            && other.right() <= self.right() + EPS
            && other.bottom() <= self.bottom() + EPS
    }
    pub fn overlaps_interior(self, other: Self) -> bool {
        self.x < other.right() - EPS
            && other.x < self.right() - EPS
            && self.y < other.bottom() - EPS
            && other.y < self.bottom() - EPS
    }
    pub fn valid(self) -> bool {
        [self.x, self.y, self.w, self.h]
            .iter()
            .all(|n| n.is_finite())
            && self.w > EPS
            && self.h > EPS
    }
    pub fn approx_eq(self, other: Self) -> bool {
        (self.x - other.x).abs() <= EPS
            && (self.y - other.y).abs() <= EPS
            && (self.w - other.w).abs() <= EPS
            && (self.h - other.h).abs() <= EPS
    }
    pub fn intersection_area(self, other: Self) -> f64 {
        (self.right().min(other.right()) - self.x.max(other.x)).max(0.0)
            * (self.bottom().min(other.bottom()) - self.y.max(other.y)).max(0.0)
    }
    pub fn to_json(self) -> Value {
        object(vec![
            ("x", number(self.x)),
            ("y", number(self.y)),
            ("width", number(self.w)),
            ("depth", number(self.h)),
        ])
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Orientation {
    N,
    E,
    S,
    W,
}

impl Orientation {
    pub fn from_str(value: &str) -> Result<Self, String> {
        match value {
            "N" => Ok(Self::N),
            "E" => Ok(Self::E),
            "S" => Ok(Self::S),
            "W" => Ok(Self::W),
            _ => Err("site.front_orientation debe ser N, E, S o W".into()),
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            Self::N => "N",
            Self::E => "E",
            Self::S => "S",
            Self::W => "W",
        }
    }
    pub fn side_direction(self, side: Side) -> &'static str {
        match (self, side) {
            (Self::N, Side::Left) => "W",
            (Self::N, Side::Right) => "E",
            (Self::E, Side::Left) => "N",
            (Self::E, Side::Right) => "S",
            (Self::S, Side::Left) => "E",
            (Self::S, Side::Right) => "W",
            (Self::W, Side::Left) => "S",
            (Self::W, Side::Right) => "N",
        }
    }
    pub fn arrow_rotation(self) -> u16 {
        match self {
            Self::N => 0,
            Self::E => 270,
            Self::S => 180,
            Self::W => 90,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Side {
    Left,
    Right,
}
impl Side {
    pub fn as_str(self) -> &'static str {
        if self == Side::Left {
            "left"
        } else {
            "right"
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    LivingDining,
    Kitchen,
    Bedroom(u8),
    Bathroom(u8),
}

impl Kind {
    pub fn key(self) -> &'static str {
        match self {
            Self::LivingDining => "living_dining",
            Self::Kitchen => "kitchen",
            Self::Bedroom(_) => "bedroom",
            Self::Bathroom(_) => "bathroom",
        }
    }
    pub fn id(self) -> String {
        match self {
            Self::LivingDining => "living-dining".into(),
            Self::Kitchen => "kitchen".into(),
            Self::Bedroom(i) => format!("bedroom-{i}"),
            Self::Bathroom(i) => format!("bathroom-{i}"),
        }
    }
    pub fn label(self) -> String {
        match self {
            Self::LivingDining => "Sala / comedor".into(),
            Self::Kitchen => "Cocina".into(),
            Self::Bedroom(i) => format!("Dormitorio {i}"),
            Self::Bathroom(i) => format!("Baño {i}"),
        }
    }
    pub fn zone(self) -> &'static str {
        match self {
            Self::LivingDining => "public",
            Self::Kitchen | Self::Bathroom(_) => "service",
            Self::Bedroom(_) => "private",
        }
    }
}

#[derive(Clone, Debug)]
pub struct SpaceRule {
    pub area_min: f64,
    pub area_pref: f64,
    pub area_max: f64,
    pub min_width: f64,
    pub min_depth: f64,
    pub window_ratio: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct FixtureSize {
    pub width: f64,
    pub depth: f64,
}

#[derive(Clone, Debug)]
pub struct FurnishingRules {
    pub min_aisle: f64,
    pub sofa: FixtureSize,
    pub dining_table: FixtureSize,
    pub counter: FixtureSize,
    pub refrigerator: FixtureSize,
    pub bed: FixtureSize,
    pub shower: FixtureSize,
    pub toilet: FixtureSize,
    pub basin: FixtureSize,
}

/// Parameters for a *plan-projection reservation* from each bath to its own
/// exterior wall. They do not specify fan, airflow, height or installed duct.
#[derive(Clone, Copy, Debug)]
pub struct BathExhaustRules {
    pub outlet_span: f64,
    pub route_band: f64,
    pub fixture_gap: f64,
    pub max_run: f64,
}

/// Illustrative *nominal* airflow scenario. The free-air fan rating is an
/// uninstalled reference, not a delivered flow with duct/pressure losses.
#[derive(Clone, Copy, Debug)]
pub struct BathAirflowRules {
    pub assumed_ceiling_height: f64,
    pub target_ach: f64,
    pub fan_free_air_rating: f64,
    pub door_undercut: f64,
    pub max_transfer_velocity: f64,
    pub duct_height: f64,
    pub duct_bottom: f64,
    pub min_headroom: f64,
    pub max_duct_velocity: f64,
}

/// Two unverified fan reference points and *hypothetical* loss coefficients.
/// Neither the points nor the route describe an identified installed system.
#[derive(Clone, Copy, Debug)]
pub struct BathPressureRules {
    pub fan_reference_pressure_pa: f64,
    pub fan_reference_flow_m3h: f64,
    pub assumed_air_density_kg_m3: f64,
    pub assumed_darcy_factor: f64,
    pub assumed_bend_count: u32,
    pub assumed_bend_k: f64,
    pub assumed_outlet_k: f64,
    pub assumed_reserve_pa: f64,
}

#[derive(Clone, Debug)]
pub struct Rules {
    pub id: String,
    pub version: String,
    pub setbacks: Setbacks,
    pub max_coverage: f64,
    pub max_far: f64,
    pub corridor_width: f64,
    pub soft_max_ratio: f64,
    pub main_door: f64,
    pub room_door: f64,
    pub bathroom_door: f64,
    pub exterior_wall: f64,
    pub partition_wall: f64,
    pub corner_clearance: f64,
    pub swing_clearance: f64,
    pub max_egress_distance: f64,
    pub window_height: f64,
    pub living: SpaceRule,
    pub kitchen: SpaceRule,
    pub bedroom: SpaceRule,
    pub bathroom: SpaceRule,
    pub furnishings: FurnishingRules,
    pub bath_exhaust: BathExhaustRules,
    pub bath_airflow: BathAirflowRules,
    pub bath_pressure: BathPressureRules,
}

impl Rules {
    pub fn for_kind(&self, kind: Kind) -> &SpaceRule {
        match kind {
            Kind::LivingDining => &self.living,
            Kind::Kitchen => &self.kitchen,
            Kind::Bedroom(_) => &self.bedroom,
            Kind::Bathroom(_) => &self.bathroom,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Setbacks {
    pub front: f64,
    pub rear: f64,
    pub left: f64,
    pub right: f64,
}
/// One of at most two opposite rear-corner cut-outs of a bounding rectangle.
/// The input is an applicant's 2D sketch, not a survey or a legal setback.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RearSide {
    Left,
    Right,
}
impl RearSide {
    pub fn from_str(side: &str) -> Result<Self, String> {
        match side {
            "left" => Ok(Self::Left),
            "right" => Ok(Self::Right),
            _ => Err("site.plot_outline.rear_notches[].side debe ser left o right".into()),
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Left => "left",
            Self::Right => "right",
        }
    }
}
#[derive(Clone, Copy, Debug)]
pub struct RearNotch {
    pub side: RearSide,
    pub width: f64,
    pub depth: f64,
}
impl RearNotch {
    pub fn to_json(self) -> Value {
        object(vec![
            ("side", text(self.side.as_str())),
            ("width", number(self.width)),
            ("depth", number(self.depth)),
        ])
    }
}

#[derive(Clone, Copy, Debug)]
pub enum FrontTrace {
    Straight,
    Orthogonal { front_x: f64, turn_y: f64 },
}
impl FrontTrace {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Straight => "straight_front_strip",
            Self::Orthogonal { .. } => "orthogonal_front_detour",
        }
    }
    pub fn coordinates(self) -> (Value, Value) {
        match self {
            Self::Straight => (Value::Null, Value::Null),
            Self::Orthogonal { front_x, turn_y } => (number(front_x), number(turn_y)),
        }
    }
}

/// Only the union of these rectangles was checked in the self-reported 2D
/// sketch. No exterior route, ownership, street or accessible travel is proven.
#[derive(Clone, Debug)]
pub struct ApproachSketch {
    pub shape: FrontTrace,
    pub width: f64,
    pub front_x: f64,
    pub door_x: f64,
    pub door_y: f64,
    pub turns: Vec<(f64, f64)>,
    pub segments: Vec<Rect>,
}
impl ApproachSketch {
    pub fn to_json(&self) -> Value {
        object(vec![
            ("shape", text(self.shape.as_str())),
            ("width", number(self.width)),
            (
                "geometry_status",
                text(if self.segments.is_empty() {
                    "door_at_front_boundary_2d_only"
                } else if matches!(self.shape, FrontTrace::Straight) {
                    "strip_clear_of_declared_exclusions_2d_only"
                } else {
                    "orthogonal_detour_clear_of_declared_exclusions_2d_only"
                }),
            ),
            ("segments", list(self.segments.iter().map(|r| r.to_json()))),
            (
                "turns",
                list(
                    self.turns
                        .iter()
                        .map(|&(x, y)| object(vec![("x", number(x)), ("y", number(y))])),
                ),
            ),
            (
                "front_contact",
                object(vec![("x", number(self.front_x)), ("y", number(0.0))]),
            ),
            (
                "door_contact",
                object(vec![("x", number(self.door_x)), ("y", number(self.door_y))]),
            ),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Site {
    pub width: f64,
    pub depth: f64,
    pub front: Orientation,
    /// Applicant-selected 2D trace from the drawn front edge to the entrance.
    /// No road, right of way, accessibility or physical route is proven.
    pub front_trace: FrontTrace,
    pub front_approach_width: f64,
    /// Zero to two rear-corner cut-outs, one per side, of the applicant's
    /// 2D sketch. A central rear strip stays between them (not legal land data).
    pub rear_notches: Vec<RearNotch>,
    /// At most two non-overlapping voluntary rectangles in plot coordinates
    /// (x from the left, y measured back from the front). Not surveyed obstacles,
    /// regulatory setbacks, easements, or evidence about natural light.
    pub reserved_areas: Vec<Rect>,
}
impl Site {
    pub fn bounds(&self) -> Rect {
        Rect {
            x: 0.0,
            y: 0.0,
            w: self.width,
            h: self.depth,
        }
    }
    pub fn notch_rects(&self) -> impl Iterator<Item = Rect> + '_ {
        self.rear_notches.iter().map(|notch| Rect {
            x: if notch.side == RearSide::Left {
                0.0
            } else {
                self.width - notch.width
            },
            y: self.depth - notch.depth,
            w: notch.width,
            h: notch.depth,
        })
    }
    pub fn contains_gross_rect(&self, rect: Rect) -> bool {
        self.bounds().contains(rect)
            && self
                .notch_rects()
                .all(|notch| notch.intersection_area(rect) == 0.0)
    }
    pub fn plot_area(&self) -> f64 {
        self.bounds().area() - self.notch_rects().map(Rect::area).sum::<f64>()
    }
    /// Reconstruct the ONLY submitted front trace for this candidate, bounded
    /// entirely by the front setback. Every band's full width (including both
    /// corners) must avoid excluded 2D areas; a centreline is insufficient.
    /// The gross house begins at front_y; none of these rectangles is built area.
    pub fn front_route(&self, door_x: f64, front_y: f64) -> Result<ApproachSketch, String> {
        let width = self.front_approach_width;
        let half = width / 2.0;
        if !door_x.is_finite()
            || !front_y.is_finite()
            || front_y < -EPS
            || door_x - half < -EPS
            || door_x + half > self.width + EPS
        {
            return Err("El punto de puerta frontal queda fuera de la parcela esquemática.".into());
        }
        let (front_x, turns, segments) = match self.front_trace {
            FrontTrace::Straight => (
                door_x,
                vec![],
                if front_y > EPS {
                    vec![Rect {
                        x: door_x - half,
                        y: 0.0,
                        w: width,
                        h: front_y,
                    }]
                } else {
                    vec![]
                },
            ),
            FrontTrace::Orthogonal { front_x, turn_y } => {
                if (front_x - door_x).abs() < width
                    || turn_y - half < 0.0
                    || turn_y + half > front_y
                {
                    return Err("El rodeo frontal ortogonal no cabe íntegro en el retiro frontal: se requieren dos giros, bandas completas y separación respecto de la puerta.".into());
                }
                (
                    front_x,
                    vec![(front_x, turn_y), (door_x, turn_y)],
                    vec![
                        Rect {
                            x: front_x - half,
                            y: 0.0,
                            w: width,
                            h: turn_y,
                        },
                        Rect {
                            x: front_x.min(door_x),
                            y: turn_y - half,
                            w: (front_x - door_x).abs(),
                            h: width,
                        },
                        Rect {
                            x: door_x - half,
                            y: turn_y,
                            w: width,
                            h: front_y - turn_y,
                        },
                    ],
                )
            }
        };
        for band in &segments {
            if !band.valid()
                || !self.bounds().contains(*band)
                || self
                    .notch_rects()
                    .any(|notch| notch.intersection_area(*band) > 0.0)
            {
                return Err(match self.front_trace {
                    FrontTrace::Straight => "La franja frontal recta sale del croquis de parcela no verificado; no se dibuja acceso exterior.",
                    FrontTrace::Orthogonal { .. } => "El rodeo frontal ortogonal sale del croquis de parcela no verificado; no se dibuja acceso exterior.",
                }.into());
            }
            if self
                .reserved_areas
                .iter()
                .any(|area| area.intersection_area(*band) > 0.0)
            {
                return Err(match self.front_trace {
                    FrontTrace::Straight => "La reserva voluntaria cruza la franja frontal recta del croquis; no se dibuja acceso exterior.",
                    FrontTrace::Orthogonal { .. } => "La reserva voluntaria cruza una banda del rodeo frontal ortogonal del croquis; no se dibuja acceso exterior.",
                }.into());
            }
        }
        Ok(ApproachSketch {
            shape: self.front_trace,
            width,
            front_x,
            door_x,
            door_y: front_y,
            turns,
            segments,
        })
    }
    pub fn approach_json(&self) -> Value {
        let (front_x, turn_y) = self.front_trace.coordinates();
        object(vec![
            ("provenance", text(RESERVATION_PROVENANCE)),
            ("geometry_status", text(FRONT_APPROACH_STATUS)),
            ("shape", text(self.front_trace.as_str())),
            ("width", number(self.front_approach_width)),
            ("front_x", front_x),
            ("turn_y", turn_y),
            ("street_connection_status", text("not_evaluated")),
            ("right_of_way_status", text("not_evaluated")),
            ("accessibility_status", text("not_evaluated")),
        ])
    }
    /// Clockwise vertices in local plot coordinates, no repeated closing point.
    /// A full front edge and at least 1 m of drawn rear strip always remain.
    /// The input order is preserved in the echo/hash, but cannot invert the outline.
    pub fn outline_vertices(&self) -> Vec<(f64, f64)> {
        let w = self.width;
        let d = self.depth;
        let left = self.rear_notches.iter().find(|n| n.side == RearSide::Left);
        let right = self.rear_notches.iter().find(|n| n.side == RearSide::Right);
        let mut vertices = vec![(0.0, 0.0), (w, 0.0)];
        if let Some(n) = right {
            vertices.extend([
                (w, d - n.depth),
                (w - n.width, d - n.depth),
                (w - n.width, d),
            ]);
        } else {
            vertices.push((w, d));
        }
        if let Some(n) = left {
            vertices.extend([(n.width, d), (n.width, d - n.depth), (0.0, d - n.depth)]);
        } else {
            vertices.push((0.0, d));
        }
        vertices
    }
    pub fn plot_json(&self) -> Value {
        object(vec![
            ("provenance", text(RESERVATION_PROVENANCE)),
            ("geometry_status", text(PLOT_SKETCH_STATUS)),
            (
                "shape",
                text(match self.rear_notches.len() {
                    0 => "rectangle",
                    1 => "rear_corner_notch",
                    _ => "rear_both_corners_notched",
                }),
            ),
            (
                "rear_notches",
                list(self.rear_notches.iter().map(|notch| notch.to_json())),
            ),
            (
                "vertices",
                list(
                    self.outline_vertices()
                        .into_iter()
                        .map(|(x, y)| object(vec![("x", number(x)), ("y", number(y))])),
                ),
            ),
        ])
    }
    pub fn reservations_json(&self) -> Value {
        object(vec![
            ("provenance", text(RESERVATION_PROVENANCE)),
            ("geometry_status", text("footprint_exclusion_2d_only")),
            (
                "areas",
                list(self.reserved_areas.iter().map(|area| area.to_json())),
            ),
        ])
    }
}
#[derive(Clone, Debug)]
pub struct Program {
    pub bedrooms: u8,
    pub bathrooms: u8,
    pub target_built_area: f64,
}
/// Self-reported project intake, not professional verification of the site or
/// the edition/scope of any Cuban standard. Even a fully filled form cannot
/// authorize a regulatory claim from the illustrative demo ruleset.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Jurisdiction {
    Unreported,
    Cuba,
    OutsideCuba,
}
impl Jurisdiction {
    fn as_str(self) -> &'static str {
        match self {
            Self::Unreported => "unreported",
            Self::Cuba => "CU",
            Self::OutsideCuba => "outside_CU",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HousingClass {
    Unreported,
    UrbanSocial,
    Other,
}
impl HousingClass {
    fn as_str(self) -> &'static str {
        match self {
            Self::Unreported => "unreported",
            Self::UrbanSocial => "urban_social",
            Self::Other => "other",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AccessibilityNeeds {
    Unreported,
    Declared,
    NoneDeclared,
}
impl AccessibilityNeeds {
    fn as_str(self) -> &'static str {
        match self {
            Self::Unreported => "unreported",
            Self::Declared => "declared",
            Self::NoneDeclared => "none_declared",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ProjectContext {
    pub jurisdiction: Jurisdiction,
    pub housing_class: HousingClass,
    pub occupants: Option<u8>,
    pub accessibility_needs: AccessibilityNeeds,
}
impl ProjectContext {
    fn from_value(value: &Value) -> Result<Self, String> {
        only_keys(
            value,
            &[
                "jurisdiction",
                "housing_class",
                "occupants",
                "accessibility_needs",
                "provenance",
            ],
            "project_context",
        )?;
        if string(value, "provenance", "project_context")? != "self_reported_unverified" {
            return Err("project_context.provenance debe ser self_reported_unverified".into());
        }
        let jurisdiction = match string(value, "jurisdiction", "project_context")?.as_str() {
            "unreported" => Jurisdiction::Unreported,
            "CU" => Jurisdiction::Cuba,
            "outside_CU" => Jurisdiction::OutsideCuba,
            _ => {
                return Err(
                    "project_context.jurisdiction debe ser unreported, CU u outside_CU".into(),
                )
            }
        };
        let housing_class = match string(value, "housing_class", "project_context")?.as_str() {
            "unreported" => HousingClass::Unreported,
            "urban_social" => HousingClass::UrbanSocial,
            "other" => HousingClass::Other,
            _ => {
                return Err(
                    "project_context.housing_class debe ser unreported, urban_social u other"
                        .into(),
                )
            }
        };
        let occupants = match required(value, "occupants", "project_context")? {
            Value::Null => None,
            _ => Some(integer(value, "occupants", "project_context", 1, 20)? as u8),
        };
        let accessibility_needs = match string(value, "accessibility_needs", "project_context")?
            .as_str()
        {
            "unreported" => AccessibilityNeeds::Unreported,
            "declared" => AccessibilityNeeds::Declared,
            "none_declared" => AccessibilityNeeds::NoneDeclared,
            _ => return Err(
                "project_context.accessibility_needs debe ser unreported, declared o none_declared"
                    .into(),
            ),
        };
        Ok(Self {
            jurisdiction,
            housing_class,
            occupants,
            accessibility_needs,
        })
    }

    pub fn to_json(self) -> Value {
        object(vec![
            ("jurisdiction", text(self.jurisdiction.as_str())),
            ("housing_class", text(self.housing_class.as_str())),
            (
                "occupants",
                self.occupants.map_or(Value::Null, |n| number(n as f64)),
            ),
            (
                "accessibility_needs",
                text(self.accessibility_needs.as_str()),
            ),
            ("provenance", text("self_reported_unverified")),
        ])
    }

    pub fn applicability_json(self) -> Value {
        let mut missing = Vec::new();
        if self.jurisdiction == Jurisdiction::Unreported {
            missing.push(text("jurisdiction"));
        }
        if self.housing_class == HousingClass::Unreported {
            missing.push(text("housing_class"));
        }
        if self.occupants.is_none() {
            missing.push(text("occupants"));
        }
        if self.accessibility_needs == AccessibilityNeeds::Unreported {
            missing.push(text("accessibility_needs"));
        }
        let declared_scope = if self.jurisdiction == Jurisdiction::Cuba
            && self.housing_class == HousingClass::UrbanSocial
        {
            "candidate_from_self_report_only"
        } else {
            "undetermined"
        };
        object(vec![
            ("status", text("not_evaluated")),
            ("declared_scope", text(declared_scope)),
            ("missing_context", list(missing)),
            ("source_status", text("no_verified_cuban_ruleset")),
            ("daylight_status", text("not_evaluated")),
            ("ventilation_status", text("not_evaluated")),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Request {
    pub site: Site,
    pub program: Program,
    pub project_context: ProjectContext,
    pub seed: u32,
    pub rules: Rules,
}

fn required<'a>(parent: &'a Value, key: &str, context: &str) -> Result<&'a Value, String> {
    parent
        .get(key)
        .ok_or_else(|| format!("falta {context}.{key}"))
}
fn only_keys(parent: &Value, keys: &[&str], context: &str) -> Result<(), String> {
    match parent {
        Value::Object(map) => {
            for key in map.keys() {
                if !keys.contains(&key.as_str()) {
                    return Err(format!("campo no admitido: {context}.{key}"));
                }
            }
            Ok(())
        }
        _ => Err(format!("{context} debe ser un objeto")),
    }
}
fn num(parent: &Value, key: &str, context: &str, min: f64, max: f64) -> Result<f64, String> {
    let value = required(parent, key, context)?
        .as_number()
        .ok_or_else(|| format!("{context}.{key} debe ser numérico"))?;
    if !value.is_finite() || value < min || value > max {
        return Err(format!("{context}.{key} debe estar entre {min} y {max}"));
    }
    Ok(value)
}
fn integer(parent: &Value, key: &str, context: &str, min: u32, max: u32) -> Result<u32, String> {
    let value = num(parent, key, context, min as f64, max as f64)?;
    if value.fract() != 0.0 {
        return Err(format!("{context}.{key} debe ser entero"));
    }
    Ok(value as u32)
}
fn string(parent: &Value, key: &str, context: &str) -> Result<String, String> {
    let result = required(parent, key, context)?
        .as_str()
        .ok_or_else(|| format!("{context}.{key} debe ser texto"))?;
    if result.is_empty() || result.len() > 80 {
        return Err(format!("{context}.{key}: longitud inválida"));
    }
    Ok(result.to_string())
}

fn space_rule(value: &Value, name: &str) -> Result<SpaceRule, String> {
    let ctx = format!("rules.spaces.{name}");
    only_keys(
        value,
        &[
            "area_min",
            "area_pref",
            "area_max",
            "min_width",
            "min_depth",
            "window_ratio",
        ],
        &ctx,
    )?;
    let rule = SpaceRule {
        area_min: num(value, "area_min", &ctx, 1.0, 200.0)?,
        area_pref: num(value, "area_pref", &ctx, 1.0, 200.0)?,
        area_max: num(value, "area_max", &ctx, 1.0, 200.0)?,
        min_width: num(value, "min_width", &ctx, 0.6, 15.0)?,
        min_depth: num(value, "min_depth", &ctx, 0.6, 15.0)?,
        window_ratio: num(value, "window_ratio", &ctx, 0.0, 0.5)?,
    };
    if rule.area_min > rule.area_pref
        || rule.area_pref > rule.area_max
        || rule.min_width * rule.min_depth > rule.area_max + EPS
    {
        return Err(format!("{ctx}: rangos de área/dimensiones incompatibles"));
    }
    Ok(rule)
}

fn fixture_size(parent: &Value, key: &str) -> Result<FixtureSize, String> {
    let ctx = format!("rules.furnishings.{key}");
    let fixture = required(parent, key, "rules.furnishings")?;
    only_keys(fixture, &["width", "depth"], &ctx)?;
    Ok(FixtureSize {
        width: num(fixture, "width", &ctx, 0.30, 4.0)?,
        depth: num(fixture, "depth", &ctx, 0.30, 4.0)?,
    })
}

fn furnishing_rules(value: &Value) -> Result<FurnishingRules, String> {
    only_keys(
        value,
        &[
            "min_aisle",
            "sofa",
            "dining_table",
            "counter",
            "refrigerator",
            "bed",
            "shower",
            "toilet",
            "basin",
        ],
        "rules.furnishings",
    )?;
    Ok(FurnishingRules {
        min_aisle: num(value, "min_aisle", "rules.furnishings", 0.45, 1.50)?,
        sofa: fixture_size(value, "sofa")?,
        dining_table: fixture_size(value, "dining_table")?,
        counter: fixture_size(value, "counter")?,
        refrigerator: fixture_size(value, "refrigerator")?,
        bed: fixture_size(value, "bed")?,
        shower: fixture_size(value, "shower")?,
        toilet: fixture_size(value, "toilet")?,
        basin: fixture_size(value, "basin")?,
    })
}

fn bath_exhaust_rules(value: &Value) -> Result<BathExhaustRules, String> {
    let ctx = "rules.bath_exhaust";
    only_keys(
        value,
        &["outlet_span", "route_band", "fixture_gap", "max_run"],
        ctx,
    )?;
    Ok(BathExhaustRules {
        outlet_span: num(value, "outlet_span", ctx, 0.10, 0.80)?,
        route_band: num(value, "route_band", ctx, 0.10, 0.60)?,
        fixture_gap: num(value, "fixture_gap", ctx, 0.0, 0.30)?,
        max_run: num(value, "max_run", ctx, 0.25, 8.0)?,
    })
}

fn bath_airflow_rules(value: &Value) -> Result<BathAirflowRules, String> {
    let ctx = "rules.bath_airflow";
    only_keys(
        value,
        &[
            "assumed_ceiling_height",
            "target_ach",
            "fan_free_air_rating",
            "door_undercut",
            "max_transfer_velocity",
            "duct_height",
            "duct_bottom",
            "min_headroom",
            "max_duct_velocity",
        ],
        ctx,
    )?;
    let rules = BathAirflowRules {
        assumed_ceiling_height: num(value, "assumed_ceiling_height", ctx, 2.20, 4.0)?,
        target_ach: num(value, "target_ach", ctx, 0.50, 12.0)?,
        fan_free_air_rating: num(value, "fan_free_air_rating", ctx, 10.0, 500.0)?,
        door_undercut: num(value, "door_undercut", ctx, 0.005, 0.04)?,
        max_transfer_velocity: num(value, "max_transfer_velocity", ctx, 0.20, 3.0)?,
        duct_height: num(value, "duct_height", ctx, 0.10, 0.60)?,
        duct_bottom: num(value, "duct_bottom", ctx, 1.80, 3.60)?,
        min_headroom: num(value, "min_headroom", ctx, 1.80, 2.50)?,
        max_duct_velocity: num(value, "max_duct_velocity", ctx, 0.20, 5.0)?,
    };
    if rules.duct_bottom + EPS < rules.min_headroom
        || rules.duct_bottom + rules.duct_height > rules.assumed_ceiling_height + EPS
    {
        return Err("rules.bath_airflow: la banda vertical supuesta no cabe entre la altura libre y el techo supuesto".into());
    }
    Ok(rules)
}

fn bath_pressure_rules(value: &Value, free_air_flow: f64) -> Result<BathPressureRules, String> {
    let ctx = "rules.bath_pressure";
    only_keys(
        value,
        &[
            "fan_reference_pressure_pa",
            "fan_reference_flow_m3h",
            "assumed_air_density_kg_m3",
            "assumed_darcy_factor",
            "assumed_bend_count",
            "assumed_bend_k",
            "assumed_outlet_k",
            "assumed_reserve_pa",
        ],
        ctx,
    )?;
    let rules = BathPressureRules {
        fan_reference_pressure_pa: num(value, "fan_reference_pressure_pa", ctx, 5.0, 500.0)?,
        fan_reference_flow_m3h: num(value, "fan_reference_flow_m3h", ctx, 1.0, 500.0)?,
        assumed_air_density_kg_m3: num(value, "assumed_air_density_kg_m3", ctx, 0.90, 1.40)?,
        assumed_darcy_factor: num(value, "assumed_darcy_factor", ctx, 0.005, 0.20)?,
        assumed_bend_count: integer(value, "assumed_bend_count", ctx, 0, 12)?,
        assumed_bend_k: num(value, "assumed_bend_k", ctx, 0.0, 5.0)?,
        assumed_outlet_k: num(value, "assumed_outlet_k", ctx, 0.0, 10.0)?,
        assumed_reserve_pa: num(value, "assumed_reserve_pa", ctx, 0.0, 100.0)?,
    };
    if rules.fan_reference_flow_m3h >= free_air_flow {
        return Err("rules.bath_pressure.fan_reference_flow_m3h debe ser inferior a rules.bath_airflow.fan_free_air_rating".into());
    }
    Ok(rules)
}

impl Request {
    pub fn from_value(root: &Value) -> Result<Self, String> {
        only_keys(
            root,
            &[
                "request_schema",
                "site",
                "program",
                "project_context",
                "seed",
                "rules",
            ],
            "entrada",
        )?;
        if string(root, "request_schema", "entrada")? != REQUEST_SCHEMA {
            return Err(format!("entrada.request_schema debe ser {REQUEST_SCHEMA}; los archivos antiguos no se migran automáticamente"));
        }
        let project_context =
            ProjectContext::from_value(required(root, "project_context", "entrada")?)?;
        let site_value = required(root, "site", "entrada")?;
        only_keys(
            site_value,
            &[
                "width",
                "depth",
                "front_orientation",
                "plot_outline",
                "front_approach",
                "reservation_provenance",
                "reserved_areas",
            ],
            "site",
        )?;
        if string(site_value, "reservation_provenance", "site")? != RESERVATION_PROVENANCE {
            return Err(format!("site.reservation_provenance debe ser {RESERVATION_PROVENANCE}; un croquis no certifica titularidad ni derechos"));
        }
        let mut site = Site {
            width: num(site_value, "width", "site", 4.0, 200.0)?,
            depth: num(site_value, "depth", "site", 4.0, 200.0)?,
            front: Orientation::from_str(&string(site_value, "front_orientation", "site")?)?,
            front_trace: FrontTrace::Straight,
            front_approach_width: 0.0,
            rear_notches: Vec::new(),
            reserved_areas: Vec::new(),
        };
        let approach = required(site_value, "front_approach", "site")?;
        only_keys(
            approach,
            &["provenance", "shape", "width", "front_x", "turn_y"],
            "site.front_approach",
        )?;
        if string(approach, "provenance", "site.front_approach")? != RESERVATION_PROVENANCE {
            return Err("site.front_approach: solo un trazado autodeclarado, NO un acceso, servidumbre ni ancho legal verificado".into());
        }
        site.front_approach_width = num(
            approach,
            "width",
            "site.front_approach",
            0.90,
            site.width.min(6.0),
        )?;
        let front_x = required(approach, "front_x", "site.front_approach")?;
        let turn_y = required(approach, "turn_y", "site.front_approach")?;
        site.front_trace = match string(approach, "shape", "site.front_approach")?.as_str() {
            "straight_front_strip" if *front_x == Value::Null && *turn_y == Value::Null => FrontTrace::Straight,
            "orthogonal_front_detour" => {
                let half = site.front_approach_width / 2.0;
                FrontTrace::Orthogonal {
                    front_x: num(approach, "front_x", "site.front_approach", half, site.width - half)?,
                    turn_y: num(approach, "turn_y", "site.front_approach", half, site.depth - half)?,
                }
            }
            _ => return Err("site.front_approach: recta exige front_x/turn_y nulos; rodeo ortogonal exige ambos números finitos dentro del croquis, sin afirmar acceso real".into()),
        };
        let outline = required(site_value, "plot_outline", "site")?;
        only_keys(
            outline,
            &["provenance", "shape", "rear_notches"],
            "site.plot_outline",
        )?;
        if string(outline, "provenance", "site.plot_outline")? != RESERVATION_PROVENANCE {
            return Err("site.plot_outline.provenance debe ser user_sketch_unverified; no se han comprobado los linderos".into());
        }
        let notches = required(outline, "rear_notches", "site.plot_outline")?
            .as_array()
            .ok_or_else(|| "site.plot_outline.rear_notches debe ser un arreglo".to_string())?;
        let shape = string(outline, "shape", "site.plot_outline")?;
        if !matches!(
            (shape.as_str(), notches.len()),
            ("rectangle", 0) | ("rear_corner_notch", 1) | ("rear_both_corners_notched", 2)
        ) {
            return Err("site.plot_outline: rectangle exige 0 recortes, rear_corner_notch 1 y rear_both_corners_notched 2 opuestos".into());
        }
        for (index, value) in notches.iter().enumerate() {
            let context = format!("site.plot_outline.rear_notches[{index}]");
            only_keys(value, &["side", "width", "depth"], &context)?;
            let notch = RearNotch {
                side: RearSide::from_str(&string(value, "side", &context)?)?,
                // A single cut keeps 1 m on the other rear side; two cuts
                // must additionally leave 1 m of central rear strip.
                width: num(value, "width", &context, 1.0, site.width - 1.0)?,
                depth: num(value, "depth", &context, 1.0, site.depth - 1.0)?,
            };
            if site
                .rear_notches
                .iter()
                .any(|other| other.side == notch.side)
            {
                return Err(format!(
                    "{context}: dos recortes de la misma esquina posterior no están admitidos"
                ));
            }
            site.rear_notches.push(notch);
        }
        if site.rear_notches.len() == 2
            && site
                .rear_notches
                .iter()
                .map(|notch| notch.width)
                .sum::<f64>()
                > site.width - 1.0
        {
            return Err("site.plot_outline: los dos recortes posteriores dejan menos de 1 m de franja central dibujada (mínimo ilustrativo, NO retiro legal)".into());
        }
        let areas = required(site_value, "reserved_areas", "site")?
            .as_array()
            .ok_or_else(|| "site.reserved_areas debe ser un arreglo".to_string())?;
        if areas.len() > 2 {
            return Err("site.reserved_areas: este corte admite como máximo dos reservas rectangulares voluntarias".into());
        }
        for (index, value) in areas.iter().enumerate() {
            let context = format!("site.reserved_areas[{index}]");
            only_keys(value, &["x", "y", "width", "depth"], &context)?;
            let area = Rect {
                x: num(value, "x", &context, 0.0, site.width)?,
                y: num(value, "y", &context, 0.0, site.depth)?,
                w: num(value, "width", &context, 0.10, site.width)?,
                h: num(value, "depth", &context, 0.10, site.depth)?,
            };
            // Input boundaries and intersections are exact, not EPS-tolerant:
            // a positive sliver outside the plot or inside the cut-out is not
            // an admissible voluntary sketch. Edge contact is allowed.
            if area.right() > site.width
                || area.bottom() > site.depth
                || site
                    .notch_rects()
                    .any(|notch| notch.intersection_area(area) > 0.0)
            {
                return Err(format!(
                    "{context}: la reserva debe quedar dentro del croquis de parcela, sin invadir el recorte posterior"
                ));
            }
            if let Some(other_index) = site
                .reserved_areas
                .iter()
                .position(|other| other.intersection_area(area) > 0.0)
            {
                return Err(format!(
                    "{context}: las reservas {other_index} y {index} se solapan; no se puede descontar dos veces la misma superficie del croquis"
                ));
            }
            site.reserved_areas.push(area);
        }
        let program = required(root, "program", "entrada")?;
        only_keys(
            program,
            &["bedrooms", "bathrooms", "target_built_area"],
            "program",
        )?;
        let program = Program {
            bedrooms: integer(program, "bedrooms", "program", 1, 4)? as u8,
            bathrooms: integer(program, "bathrooms", "program", 1, 2)? as u8,
            target_built_area: num(program, "target_built_area", "program", 30.0, 500.0)?,
        };
        let seed = integer(root, "seed", "entrada", 0, u32::MAX)?;
        let rules = required(root, "rules", "entrada")?;
        only_keys(
            rules,
            &[
                "id",
                "version",
                "regulatory_status",
                "setbacks",
                "max_coverage",
                "max_far",
                "corridor",
                "doors",
                "walls",
                "openings",
                "max_egress_distance",
                "window_height",
                "spaces",
                "furnishings",
                "bath_exhaust",
                "bath_airflow",
                "bath_pressure",
            ],
            "rules",
        )?;
        let status = string(rules, "regulatory_status", "rules")?;
        if status != "illustrative_not_certified" {
            return Err("rules.regulatory_status debe ser illustrative_not_certified; este prototipo no valida normas".into());
        }
        let setbacks = required(rules, "setbacks", "rules")?;
        only_keys(
            setbacks,
            &["front", "rear", "left", "right"],
            "rules.setbacks",
        )?;
        let setbacks = Setbacks {
            front: num(setbacks, "front", "rules.setbacks", 0.0, 30.0)?,
            rear: num(setbacks, "rear", "rules.setbacks", 0.0, 30.0)?,
            left: num(setbacks, "left", "rules.setbacks", 0.0, 30.0)?,
            right: num(setbacks, "right", "rules.setbacks", 0.0, 30.0)?,
        };
        let corridor = required(rules, "corridor", "rules")?;
        only_keys(corridor, &["min_width", "soft_max_ratio"], "rules.corridor")?;
        let doors = required(rules, "doors", "rules")?;
        only_keys(doors, &["main", "room", "bathroom"], "rules.doors")?;
        let walls = required(rules, "walls", "rules")?;
        only_keys(walls, &["exterior", "partition"], "rules.walls")?;
        let openings = required(rules, "openings", "rules")?;
        only_keys(
            openings,
            &["corner_clearance", "swing_clearance"],
            "rules.openings",
        )?;
        let spaces = required(rules, "spaces", "rules")?;
        only_keys(
            spaces,
            &["living_dining", "kitchen", "bedroom", "bathroom"],
            "rules.spaces",
        )?;
        let bath_airflow = bath_airflow_rules(required(rules, "bath_airflow", "rules")?)?;
        let bath_pressure = bath_pressure_rules(
            required(rules, "bath_pressure", "rules")?,
            bath_airflow.fan_free_air_rating,
        )?;
        let config = Rules {
            id: string(rules, "id", "rules")?,
            version: string(rules, "version", "rules")?,
            setbacks,
            max_coverage: num(rules, "max_coverage", "rules", 0.01, 1.0)?,
            max_far: num(rules, "max_far", "rules", 0.01, 4.0)?,
            corridor_width: num(corridor, "min_width", "rules.corridor", 0.9, 3.0)?,
            soft_max_ratio: num(corridor, "soft_max_ratio", "rules.corridor", 0.01, 0.5)?,
            main_door: num(doors, "main", "rules.doors", 0.7, 2.0)?,
            room_door: num(doors, "room", "rules.doors", 0.6, 2.0)?,
            bathroom_door: num(doors, "bathroom", "rules.doors", 0.6, 2.0)?,
            exterior_wall: num(walls, "exterior", "rules.walls", 0.10, 0.40)?,
            partition_wall: num(walls, "partition", "rules.walls", 0.08, 0.30)?,
            corner_clearance: num(openings, "corner_clearance", "rules.openings", 0.10, 0.40)?,
            swing_clearance: num(openings, "swing_clearance", "rules.openings", 0.05, 0.30)?,
            max_egress_distance: num(rules, "max_egress_distance", "rules", 1.0, 100.0)?,
            window_height: num(rules, "window_height", "rules", 0.5, 2.5)?,
            living: space_rule(
                required(spaces, "living_dining", "rules.spaces")?,
                "living_dining",
            )?,
            kitchen: space_rule(required(spaces, "kitchen", "rules.spaces")?, "kitchen")?,
            bedroom: space_rule(required(spaces, "bedroom", "rules.spaces")?, "bedroom")?,
            bathroom: space_rule(required(spaces, "bathroom", "rules.spaces")?, "bathroom")?,
            furnishings: furnishing_rules(required(rules, "furnishings", "rules")?)?,
            bath_exhaust: bath_exhaust_rules(required(rules, "bath_exhaust", "rules")?)?,
            bath_airflow,
            bath_pressure,
        };
        if config.main_door + 2.0 * config.swing_clearance > config.corridor_width + EPS {
            return Err("rules.doors.main y rules.openings.swing_clearance exceden el ancho libre del corredor".into());
        }
        if site.front_approach_width + EPS < config.main_door {
            return Err("site.front_approach.width debe cubrir al menos el vano principal dibujado; NO acredita accesibilidad".into());
        }
        Ok(Self {
            site,
            program,
            project_context,
            seed,
            rules: config,
        })
    }
}

#[derive(Clone, Debug)]
pub struct Door {
    pub x: f64, // axis of the shared gross-cell boundary
    pub y: f64,
    pub width: f64, // clear passage along the wall
    pub side: &'static str,
    pub opening: Rect, // band across the partition, not inside a clear room
    pub swing: Rect,   // conservative 90-degree sweep bounding box inside the clear room
}

#[derive(Clone, Debug)]
pub struct Entrance {
    pub width: f64,
    pub opening: Rect,
    pub swing: Rect,
}
impl Entrance {
    pub fn to_json(&self) -> Value {
        object(vec![
            ("width", number(self.width)),
            ("opening", self.opening.to_json()),
            ("swing", self.swing.to_json()),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Window {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub direction: &'static str,
    pub opening: Rect, // through the exterior-wall band in plan, not ventilation evidence
}

/// Floor-plan projection only: a reserved pick-up point and continuous band
/// through an exterior-wall outlet. Equipment, section, airflow and discharge
/// conditions are *not* modeled or certified.
#[derive(Clone, Debug)]
pub struct BathExhaust {
    pub outlet: Rect,
    pub route: Rect,
    pub pickup: Rect,
    pub run_length: f64, // from clear facade face to pick-up centre
    pub direction: &'static str,
}
impl BathExhaust {
    pub fn to_json(&self) -> Value {
        object(vec![
            ("mode", text("direct_exterior_exhaust_reservation")),
            ("geometry_status", text("outlet_and_route_reserved")),
            ("airflow_status", text("not_evaluated")),
            ("outlet", self.outlet.to_json()),
            ("route", self.route.to_json()),
            ("pickup", self.pickup.to_json()),
            ("run_length", number(self.run_length)),
            ("direction", text(self.direction)),
        ])
    }
}

/// A deterministic nominal scenario, not delivered airflow or a specified fan.
/// The rule snapshot is retained here for a completely explicit JSON trace.
#[derive(Clone, Debug)]
pub struct BathAirflowPrecheck {
    pub assumptions: BathAirflowRules,
    pub room_volume_m3: f64,
    pub target_flow_m3h: f64,
    pub transfer_area_m2: f64,
    pub transfer_velocity_mps: f64,
    pub duct_width_m: f64,
    pub duct_area_m2: f64,
    pub duct_velocity_mps: f64,
}
impl BathAirflowPrecheck {
    pub fn to_json(&self) -> Value {
        let a = self.assumptions;
        object(vec![
            ("status", text("nominal_precheck_only")),
            ("delivered_flow_status", text("not_evaluated")),
            ("target_ach", number(a.target_ach)),
            ("assumed_ceiling_height_m", number(a.assumed_ceiling_height)),
            ("room_volume_m3", number(self.room_volume_m3)),
            ("target_flow_m3h", number(self.target_flow_m3h)),
            (
                "fan_reference_free_air_rating_m3h",
                number(a.fan_free_air_rating),
            ),
            (
                "transfer",
                object(vec![
                    ("assumed_door_undercut_m", number(a.door_undercut)),
                    ("assumed_free_area_m2", number(self.transfer_area_m2)),
                    ("velocity_at_target_mps", number(self.transfer_velocity_mps)),
                    ("max_velocity_mps", number(a.max_transfer_velocity)),
                ]),
            ),
            (
                "duct",
                object(vec![
                    ("assumed_width_m", number(self.duct_width_m)),
                    ("assumed_height_m", number(a.duct_height)),
                    ("assumed_section_m2", number(self.duct_area_m2)),
                    ("velocity_at_target_mps", number(self.duct_velocity_mps)),
                    ("max_velocity_mps", number(a.max_duct_velocity)),
                    ("assumed_bottom_m", number(a.duct_bottom)),
                    ("assumed_top_m", number(a.duct_bottom + a.duct_height)),
                    ("min_headroom_m", number(a.min_headroom)),
                ]),
            ),
        ])
    }
}

/// Comparison of a *hypothetical* loss budget with a linear interpolation
/// between two unverified reference points. Never a measured operating point.
#[derive(Clone, Debug)]
pub struct BathPressureScreen {
    pub assumptions: BathPressureRules,
    pub free_air_flow_m3h: f64,
    pub target_flow_m3h: f64,
    pub assumed_straight_length_m: f64,
    pub assumed_hydraulic_diameter_m: f64,
    pub assumed_dynamic_pressure_pa: f64,
    pub assumed_straight_loss_pa: f64,
    pub assumed_bend_loss_pa: f64,
    pub assumed_outlet_loss_pa: f64,
    pub assumed_total_pressure_budget_pa: f64,
    pub assumed_linear_reference_capacity_m3h: f64,
}
impl BathPressureScreen {
    pub fn to_json(&self) -> Value {
        let a = self.assumptions;
        object(vec![
            ("status", text("hypothetical_pressure_screen_only")),
            ("delivered_flow_status", text("not_evaluated")),
            (
                "fan_reference",
                object(vec![
                    ("free_air_flow_m3h", number(self.free_air_flow_m3h)),
                    ("reference_pressure_pa", number(a.fan_reference_pressure_pa)),
                    ("reference_flow_m3h", number(a.fan_reference_flow_m3h)),
                    (
                        "assumed_linear_capacity_at_budget_m3h",
                        number(self.assumed_linear_reference_capacity_m3h),
                    ),
                ]),
            ),
            (
                "assumptions",
                object(vec![
                    ("air_density_kg_m3", number(a.assumed_air_density_kg_m3)),
                    ("darcy_factor", number(a.assumed_darcy_factor)),
                    ("bend_count", number(a.assumed_bend_count as f64)),
                    ("bend_k", number(a.assumed_bend_k)),
                    ("outlet_k", number(a.assumed_outlet_k)),
                    ("reserve_pa", number(a.assumed_reserve_pa)),
                ]),
            ),
            (
                "pressure_budget",
                object(vec![
                    ("target_flow_m3h", number(self.target_flow_m3h)),
                    (
                        "assumed_straight_length_m",
                        number(self.assumed_straight_length_m),
                    ),
                    (
                        "assumed_hydraulic_diameter_m",
                        number(self.assumed_hydraulic_diameter_m),
                    ),
                    (
                        "assumed_dynamic_pressure_pa",
                        number(self.assumed_dynamic_pressure_pa),
                    ),
                    (
                        "assumed_straight_loss_pa",
                        number(self.assumed_straight_loss_pa),
                    ),
                    ("assumed_bend_loss_pa", number(self.assumed_bend_loss_pa)),
                    (
                        "assumed_outlet_loss_pa",
                        number(self.assumed_outlet_loss_pa),
                    ),
                    ("assumed_reserve_pa", number(a.assumed_reserve_pa)),
                    (
                        "assumed_total_pa",
                        number(self.assumed_total_pressure_budget_pa),
                    ),
                ]),
            ),
        ])
    }
}

/// Fixed schematic footprint and its required free use zone(s). Neither is a code
/// clearance, ergonomic guarantee, or accessibility certificate.
#[derive(Clone, Debug)]
pub struct Fixture {
    pub kind: &'static str,
    pub label: &'static str,
    pub footprint: Rect,
    pub use_zones: Vec<Rect>,
}
impl Fixture {
    pub fn to_json(&self, room_id: &str) -> Value {
        object(vec![
            ("id", text(&format!("{room_id}-{}", self.kind))),
            ("type", text(self.kind)),
            ("label", text(self.label)),
            ("footprint", self.footprint.to_json()),
            (
                "use_zones",
                list(self.use_zones.iter().map(|r| r.to_json())),
            ),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Room {
    pub kind: Kind,
    pub side: Side,
    pub rect: Rect,   // gross planning cell; cells do not overlap
    pub usable: Rect, // clear interior after exterior/partition wall allowances
    pub door: Door,
    pub window: Option<Window>,
    pub exhaust: Option<BathExhaust>,
    pub airflow: Option<BathAirflowPrecheck>,
    pub pressure: Option<BathPressureScreen>,
    pub furnishings: Vec<Fixture>,
    pub access_route: Vec<Rect>, // contiguous aisle + threshold branch, in useful space
}

impl Room {
    pub fn to_json(&self) -> Value {
        object(vec![
            ("id", text(self.kind.id())),
            ("label", text(self.kind.label())),
            ("type", text(self.kind.key())),
            ("zone", text(self.kind.zone())),
            ("side", text(self.side.as_str())),
            ("rect", self.rect.to_json()),
            ("gross_cell_area", number(self.rect.area())),
            ("usable_rect", self.usable.to_json()),
            ("usable_area", number(self.usable.area())),
            ("area", number(self.usable.area())), // legacy alias; always useful, never gross
            (
                "furnishings",
                list(self.furnishings.iter().map(|f| f.to_json(&self.kind.id()))),
            ),
            (
                "access_route",
                list(self.access_route.iter().map(|r| r.to_json())),
            ),
            ("furnishing_status", text("illustrative_geometric_fit")),
            (
                "bath_exhaust",
                self.exhaust
                    .as_ref()
                    .map_or(Value::Null, BathExhaust::to_json),
            ),
            (
                "bath_airflow",
                self.airflow
                    .as_ref()
                    .map_or(Value::Null, BathAirflowPrecheck::to_json),
            ),
            (
                "bath_pressure",
                self.pressure
                    .as_ref()
                    .map_or(Value::Null, BathPressureScreen::to_json),
            ),
            (
                "ventilation_status",
                text(if matches!(self.kind, Kind::Bathroom(_)) {
                    "not_evaluated"
                } else {
                    "not_applicable"
                }),
            ),
            (
                "door",
                object(vec![
                    ("x", number(self.door.x)),
                    ("y", number(self.door.y)),
                    ("width", number(self.door.width)),
                    ("side", text(self.door.side)),
                    ("opening", self.door.opening.to_json()),
                    ("swing", self.door.swing.to_json()),
                ]),
            ),
            (
                "window",
                match &self.window {
                    Some(w) => object(vec![
                        ("x", number(w.x)),
                        ("y", number(w.y)),
                        ("width", number(w.width)),
                        ("height", number(w.height)),
                        ("direction", text(w.direction)),
                        ("opening", w.opening.to_json()),
                    ]),
                    None => Value::Null,
                },
            ),
            (
                "window_geometry_status",
                text(if self.window.is_some() {
                    "exterior_opening_drawn_only"
                } else {
                    "not_drawn"
                }),
            ),
            ("daylight_status", text("not_evaluated")),
        ])
    }
}

/// Gross cells are disjoint. The clear cells and the wall zones partition their area.
/// Wall zones retain opening footprints in the gross-area balance (not material volume).
#[derive(Clone, Debug)]
pub struct PlanGeometry {
    pub rooms: Vec<Room>,
    pub corridor: Rect,
    pub corridor_usable: Vec<Rect>,
    pub wall_zones: Vec<Rect>,
    pub entrance: Entrance,
    pub built_area: f64,
    pub usable_area: f64,
    pub circulation_usable_area: f64,
    pub wall_allowance_area: f64,
}

#[derive(Clone, Debug)]
pub struct Decision {
    pub entity_id: String,
    pub rule: String,
    pub explanation: String,
}
impl Decision {
    pub fn to_json(&self) -> Value {
        object(vec![
            ("entity_id", text(&self.entity_id)),
            ("rule", text(&self.rule)),
            ("explanation", text(&self.explanation)),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Metrics {
    pub area_fit: f64,
    pub circulation_score: f64,
    pub privacy_score: f64,
    pub service_score: f64,
    pub east_bedroom_score: f64,
    pub circulation_ratio: f64,
    pub longest_egress: f64,
}
impl Metrics {
    pub fn vector(&self) -> [f64; 5] {
        [
            self.area_fit,
            self.circulation_score,
            self.privacy_score,
            self.service_score,
            self.east_bedroom_score,
        ]
    }
    pub fn to_json(&self) -> Value {
        object(vec![
            ("area_fit", number(self.area_fit)),
            ("circulation_score", number(self.circulation_score)),
            ("privacy_score", number(self.privacy_score)),
            ("service_score", number(self.service_score)),
            ("east_bedroom_score", number(self.east_bedroom_score)),
            ("circulation_ratio", number(self.circulation_ratio)),
            ("longest_egress", number(self.longest_egress)),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct Candidate {
    pub id: String,
    pub label: String,
    pub pattern: usize,
    pub mirrored: bool,
    pub compact: bool,
    pub layout: PlanGeometry,
    /// Evaluated against the applicant's sketch only; excluded from built area/FAR.
    pub approach: ApproachSketch,
    pub metrics: Metrics,
    pub pareto_layer: usize,
    pub decisions: Vec<Decision>,
    pub warnings: Vec<String>,
    pub svg: String,
}
impl Candidate {
    pub fn to_json(&self) -> Value {
        let plan = &self.layout;
        object(vec![
            ("id", text(&self.id)),
            ("label", text(&self.label)),
            ("pattern", number(self.pattern as f64)),
            ("mirrored", Value::Bool(self.mirrored)),
            ("compact", Value::Bool(self.compact)),
            ("rooms", list(plan.rooms.iter().map(Room::to_json))),
            ("corridor", plan.corridor.to_json()),
            (
                "corridor_usable_segments",
                list(plan.corridor_usable.iter().map(|r| r.to_json())),
            ),
            (
                "wall_zones",
                list(plan.wall_zones.iter().map(|r| r.to_json())),
            ),
            ("entrance", plan.entrance.to_json()),
            ("front_approach", self.approach.to_json()),
            ("built_area", number(plan.built_area)),
            ("usable_area", number(plan.usable_area)),
            (
                "circulation_usable_area",
                number(plan.circulation_usable_area),
            ),
            ("wall_allowance_area", number(plan.wall_allowance_area)),
            ("bathroom_ventilation_status", text("not_evaluated")),
            ("bathroom_exhaust_status", text("geometry_reserved_only")),
            ("bathroom_airflow_status", text("nominal_precheck_only")),
            (
                "bathroom_pressure_status",
                text("hypothetical_pressure_screen_only"),
            ),
            ("metrics", self.metrics.to_json()),
            ("pareto_layer", number(self.pareto_layer as f64)),
            (
                "decisions",
                list(self.decisions.iter().map(Decision::to_json)),
            ),
            ("warnings", list(self.warnings.iter().map(|s| text(s)))),
            ("svg", text(&self.svg)),
        ])
    }
}

#[derive(Clone, Debug)]
pub struct SiteReport {
    pub plot_area: f64,
    pub buildable: Rect,
    /// Upper bound on area of the demo inset rectangle intersected with the
    /// applicant's sketch, minus the optional 2D voluntary reserve. It does
    /// NOT prove the remainder connected or legally buildable.
    pub unreserved_buildable_area: f64,
    pub max_footprint: f64,
    pub max_built_area: f64,
}
impl SiteReport {
    pub fn to_json(&self) -> Value {
        object(vec![
            ("plot_area", number(self.plot_area)),
            ("buildable", self.buildable.to_json()),
            (
                "unreserved_buildable_area",
                number(self.unreserved_buildable_area),
            ),
            ("max_footprint", number(self.max_footprint)),
            ("max_built_area", number(self.max_built_area)),
        ])
    }
}

/// Full deterministic histogram: every tried-and-rejected variant is counted
/// once, including on successful searches. This is not a normative diagnosis.
pub(crate) fn rejection_summary_json(rejections: &[(String, usize)]) -> Value {
    list(rejections.iter().map(|(reason, count)| {
        object(vec![
            ("reason", text(reason)),
            ("count", number(*count as f64)),
        ])
    }))
}

pub fn success_json(
    hash: &str,
    request: &Request,
    site: &SiteReport,
    alternatives: &[Candidate],
    generated: usize,
    rejected: usize,
    rejections: &[(String, usize)],
) -> Value {
    object(vec![
        ("status", text("ok")), ("engine_version", text(ENGINE_VERSION)),
        ("request_schema", text(REQUEST_SCHEMA)),
        ("input_hash", text(hash)), ("rule_id", text(&request.rules.id)),
        ("rule_version", text(&request.rules.version)), ("regulatory_status", text("illustrative_not_certified")),
        ("project_context", request.project_context.to_json()),
        ("applicability", request.project_context.applicability_json()),
        ("site_plot", request.site.plot_json()),
        ("site_approach", request.site.approach_json()),
        ("site_reservations", request.site.reservations_json()),
        ("site", site.to_json()), ("generated", number(generated as f64)),
        ("rejected", number(rejected as f64)),
        ("rejection_summary", rejection_summary_json(rejections)),
        ("alternatives", list(alternatives.iter().map(Candidate::to_json))),
        ("selection_note", text(if alternatives.len() < 3 {
            "Hay menos de tres soluciones viables y geométricamente distintas; no se han inventado alternativas inválidas."
        } else { "Se presentan tres soluciones viables y geométricamente distintas." })),
        ("notice", text("Esquema conceptual, no certificado ni apto para obra. Extracción de baños: reserva 2D; caudal OBJETIVO y presupuesto de presión SOLO hipotéticos, contrastados con dos puntos nominales interpolados de referencia SIN equipo identificado. Contorno, franja frontal recta y reserva son croquis 2D NO verificados: se evita el recorte en la huella y la franja, y la reserva en ambos. La franja llega al vano dibujado pero NO acredita calle, derecho de paso, acceso exterior real, pendientes, accesibilidad, linderos ni retiros del entrante. Las ventanas son huecos de planta, NO luz natural comprobada. No se evalúan curva real de ventilador, pérdidas de carga reales, caudal entregado, aire de reposición real, conducto instalado, interferencias 3D, descarga segura, ventilación efectiva, accesibilidad, estructura ni normativa.")),
    ])
}

pub fn infeasible_json(
    hash: &str,
    request: &Request,
    reasons: &[String],
    rejections: &[(String, usize)],
    generated: usize,
) -> Value {
    object(vec![
        ("status", text("infeasible")),
        ("engine_version", text(ENGINE_VERSION)),
        ("request_schema", text(REQUEST_SCHEMA)),
        ("input_hash", text(hash)),
        ("project_context", request.project_context.to_json()),
        ("applicability", request.project_context.applicability_json()),
        ("site_plot", request.site.plot_json()),
        ("site_approach", request.site.approach_json()),
        ("site_reservations", request.site.reservations_json()),
        ("generated", number(generated as f64)),
        ("rejected", number(generated as f64)),
        ("rejection_summary", rejection_summary_json(rejections)),
        ("alternatives", list(Vec::<Value>::new())),
        ("reasons", list(reasons.iter().map(|r| text(r)))),
        ("notice", text("No se halló una alternativa válida en los esquemas explorados. El trazado frontal comprueba solo la geometría declarada en un croquis 2D; puede haber otras rutas o soluciones no exploradas. No acredita calle, derechos ni accesibilidad y no demuestra inviabilidad real de la parcela.")),
    ])
}

pub fn error_json(message: &str) -> Value {
    object(vec![
        ("status", text("error")),
        ("engine_version", text(ENGINE_VERSION)),
        ("message", text(message)),
        ("alternatives", list(Vec::<Value>::new())),
        ("rejection_summary", list(Vec::<Value>::new())),
    ])
}
