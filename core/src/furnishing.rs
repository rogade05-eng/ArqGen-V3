//! Deterministic, deliberately small 2D furnishing templates for the two-strip plan.
//! Coordinates are mirrored per facade; the route is an orthogonal aisle plus a
//! branch reaching the central aisle-width part of the door. This is NOT accessibility or
//! ergonomic/code compliance: heights, appliance services and human motion are
//! outside this model. No candidate survives if even this schematic fit fails.
use crate::model::{Fixture, FixtureSize, Kind, Rect, Room, Rules, Side, EPS};

// A plan-only projection kept free in front of any drawn facade window.
// This is NOT a sill height, an accessibility clearance or daylight evidence.
const WINDOW_PROJECTION_M: f64 = 0.20;

struct Local<'a> {
    room: &'a Room,
}
impl Local<'_> {
    /// u=0 at the exterior face of the clear room; v=0 at its front edge.
    fn rect(&self, u: f64, v: f64, w: f64, h: f64) -> Rect {
        let clear = self.room.usable;
        Rect {
            x: if self.room.side == Side::Left {
                clear.x + u
            } else {
                clear.right() - u - w
            },
            y: clear.y + v,
            w,
            h,
        }
    }
    fn fixture(
        &self,
        kind: &'static str,
        label: &'static str,
        size: FixtureSize,
        u: f64,
        v: f64,
        uses: &[(f64, f64, f64, f64)],
    ) -> Fixture {
        Fixture {
            kind,
            label,
            footprint: self.rect(u, v, size.width, size.depth),
            use_zones: uses
                .iter()
                .map(|&(u, v, w, h)| self.rect(u, v, w, h))
                .collect(),
        }
    }
}

pub struct Fit {
    pub furnishings: Vec<Fixture>,
    pub access_route: Vec<Rect>,
}

/// Build the sole supported arrangement per room kind. The clearance and route
/// geometry are kept separate from the footprint, and never subtracted from
/// `usable_area` (which is the architectural clear rectangle BEFORE furniture).
pub fn design(room: &Room, rules: &Rules) -> Fit {
    let l = Local { room };
    let f = &rules.furnishings;
    let a = f.min_aisle;
    let w = room.usable.w;
    let h = room.usable.h;
    let door_v = room.door.y - room.usable.y;
    let mut items = Vec::new();
    let (spine_u, spine_v, spine_end) = match room.kind {
        Kind::LivingDining => {
            let sofa_u = 0.25;
            let table_u = 0.25;
            let table_v = h - f.dining_table.depth;
            let spine_u = table_u + f.dining_table.width - a / 2.0;
            let spine_right = spine_u + a;
            items.push(l.fixture(
                "sofa",
                "Sofá",
                f.sofa,
                sofa_u,
                0.0,
                &[(
                    sofa_u,
                    f.sofa.depth,
                    (sofa_u + f.sofa.width).max(spine_right) - sofa_u,
                    a,
                )],
            ));
            items.push(l.fixture(
                "dining_table",
                "Mesa",
                f.dining_table,
                table_u,
                table_v,
                &[(
                    table_u,
                    table_v - a,
                    (table_u + f.dining_table.width).max(spine_right) - table_u,
                    a,
                )],
            ));
            (spine_u, f.sofa.depth, table_v)
        }
        Kind::Kitchen => {
            let counter_u = 0.15;
            let fridge_v = h - f.refrigerator.depth;
            let spine_u = f.counter.width - a / 2.0;
            let spine_right = spine_u + a;
            items.push(l.fixture(
                "counter",
                "Encimera",
                f.counter,
                counter_u,
                0.0,
                &[(
                    counter_u,
                    f.counter.depth,
                    (counter_u + f.counter.width).max(spine_right) - counter_u,
                    a,
                )],
            ));
            items.push(l.fixture(
                "refrigerator",
                "Frigorífico",
                f.refrigerator,
                0.0,
                fridge_v,
                &[(
                    f.refrigerator.width,
                    fridge_v,
                    (f.refrigerator.width + a).max(spine_right) - f.refrigerator.width,
                    f.refrigerator.depth,
                )],
            ));
            (spine_u, f.counter.depth, h)
        }
        Kind::Bedroom(_) => {
            let bed_u = 0.25;
            let spine_u = bed_u + f.bed.width;
            items.push(l.fixture(
                "bed",
                "Cama",
                f.bed,
                bed_u,
                0.0,
                &[
                    (spine_u, 0.0, a, f.bed.depth),
                    (bed_u, f.bed.depth, spine_u + a - bed_u, a),
                ],
            ));
            (spine_u, 0.0, h)
        }
        Kind::Bathroom(_) => {
            // A drawn bath opening must not be hidden behind the shower's 2D
            // footprint. When the illustrative window target is positive,
            // leave its narrow facade projection free; reject an otherwise
            // impossible arrangement in verify rather than ignore collision.
            let shower_u = if rules.bathroom.window_ratio > 0.0 {
                WINDOW_PROJECTION_M
            } else {
                0.0
            };
            let spine_u = (shower_u + f.shower.width).max(f.toilet.width);
            let spine_right = spine_u + a;
            let toilet_v = h - f.toilet.depth;
            // Leave the full swing free: the basin sits beyond it, closer to the
            // exterior end, and its use zone reaches the door branch.
            let basin_u = w - room.door.width - rules.swing_clearance - f.basin.width;
            let basin_use_u = basin_u + f.basin.width - f.basin.width.max(a);
            let basin_use_v = f.basin.depth;
            let basin_use_h = (door_v + a / 2.0 - basin_use_v).max(a);
            items.push(l.fixture(
                "shower",
                "Ducha",
                f.shower,
                shower_u,
                0.0,
                &[(
                    shower_u + f.shower.width,
                    0.0,
                    spine_right - shower_u - f.shower.width,
                    f.shower.depth,
                )],
            ));
            items.push(l.fixture(
                "toilet",
                "Inodoro",
                f.toilet,
                0.0,
                toilet_v,
                &[(
                    f.toilet.width,
                    toilet_v,
                    spine_right - f.toilet.width,
                    f.toilet.depth,
                )],
            ));
            items.push(l.fixture(
                "basin",
                "Lavabo",
                f.basin,
                basin_u,
                0.0,
                &[(basin_use_u, basin_use_v, f.basin.width.max(a), basin_use_h)],
            ));
            (spine_u, 0.0, h)
        }
    };
    // The branch overlaps the spine over a full aisle-width square and reaches
    // the central, aisle-width part of the room-door opening.
    Fit {
        furnishings: items,
        access_route: vec![
            l.rect(spine_u, spine_v, a, spine_end - spine_v),
            l.rect(spine_u, door_v - a / 2.0, w - spine_u, a),
        ],
    }
}

fn fail(room: &Room, detail: &str) -> String {
    format!(
        "{}: equipamiento ilustrativo inviable ({detail}).",
        room.kind.label()
    )
}

/// Called *again* on every candidate before ranking/selection/export. Rebuild
/// the expected placements from the rule snapshot, compare them with the
/// candidate, then independently check free space, sweep and route connectivity.
pub fn verify(room: &Room, rules: &Rules) -> Result<(), String> {
    let expected = design(room, rules);
    if room.furnishings.len() != expected.furnishings.len()
        || room.access_route.len() != expected.access_route.len()
        || !room
            .access_route
            .iter()
            .zip(&expected.access_route)
            .all(|(a, b)| a.approx_eq(*b))
        || !room
            .furnishings
            .iter()
            .zip(&expected.furnishings)
            .all(|(a, b)| {
                a.kind == b.kind
                    && a.label == b.label
                    && a.footprint.approx_eq(b.footprint)
                    && a.use_zones.len() == b.use_zones.len()
                    && a.use_zones
                        .iter()
                        .zip(&b.use_zones)
                        .all(|(a, b)| a.approx_eq(*b))
            })
    {
        return Err(fail(
            room,
            "la disposición no coincide con el ruleset versionado",
        ));
    }
    let a = rules.furnishings.min_aisle;
    let [spine, branch] = room.access_route.as_slice() else {
        return Err(fail(room, "falta la ruta desde la puerta"));
    };
    if !spine.valid()
        || !branch.valid()
        || spine.w + EPS < a
        || branch.h + EPS < a
        || !room.usable.contains(*spine)
        || !room.usable.contains(*branch)
        || spine.intersection_area(*branch) + EPS < a * a
        || branch.y + EPS < room.door.y - room.door.width / 2.0
        || branch.bottom() > room.door.y + room.door.width / 2.0 + EPS
        || (if room.side == Side::Left {
            (branch.right() - room.usable.right()).abs()
        } else {
            (branch.x - room.usable.x).abs()
        }) > EPS
    {
        return Err(fail(
            room,
            "no existe una ruta libre continua del ancho indicado hasta el umbral",
        ));
    }

    // Project a short access band inward from any modeled facade opening.
    // This does not assert that the opening provides legal light/ventilation.
    let window_band = room.window.as_ref().map(|window| Rect {
        x: if room.side == Side::Left {
            room.usable.x
        } else {
            room.usable.right() - WINDOW_PROJECTION_M
        },
        y: window.opening.y,
        w: WINDOW_PROJECTION_M,
        h: window.opening.h,
    });
    for (index, item) in room.furnishings.iter().enumerate() {
        let footprint = item.footprint;
        if !footprint.valid()
            || !room.usable.contains(footprint)
            || footprint.overlaps_interior(room.door.swing)
            || window_band.is_some_and(|band| footprint.overlaps_interior(band))
            || room
                .access_route
                .iter()
                .any(|route| footprint.overlaps_interior(*route))
            || room
                .furnishings
                .iter()
                .skip(index + 1)
                .any(|other| footprint.overlaps_interior(other.footprint))
        {
            return Err(fail(
                room,
                "una huella ocupa un muro, ventana, barrido, recorrido u otra huella",
            ));
        }
        if item.use_zones.is_empty() {
            return Err(fail(room, "un objeto carece de espacio libre de uso"));
        }
        for zone in &item.use_zones {
            if !zone.valid()
                || !room.usable.contains(*zone)
                || zone.overlaps_interior(room.door.swing)
                || room
                    .furnishings
                    .iter()
                    .any(|other| zone.overlaps_interior(other.footprint))
                || room
                    .access_route
                    .iter()
                    .all(|route| zone.intersection_area(*route) + EPS < a * a)
            {
                return Err(fail(
                    room,
                    "una zona de uso colisiona o no enlaza con el recorrido libre",
                ));
            }
        }
    }
    Ok(())
}
