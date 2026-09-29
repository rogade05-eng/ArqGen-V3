//! Bathroom exhaust *reservation* in plan. A projected pick-up/route meets a
//! lateral facade outlet; no fan, section, duct installation, airflow rate,
//! pressure loss, discharge suitability or code compliance is represented.
use crate::model::{BathExhaust, Kind, Orientation, Rect, Room, Rules, Side, EPS};

fn fail(room: &Room, detail: &str) -> String {
    format!(
        "{}: reserva de extracción inviable ({detail}).",
        room.kind.label()
    )
}

/// The fixed template uses the free transverse slot between the shower and
/// toilet. This keeps its plan projection off their footprints. Use zones and
/// the pedestrian aisle MAY cross this *hypothetical overhead* reservation;
/// their vertical compatibility is deliberately not asserted.
pub fn design(
    room: &Room,
    front: Orientation,
    rules: &Rules,
) -> Result<Option<BathExhaust>, String> {
    if !matches!(room.kind, Kind::Bathroom(_)) {
        return Ok(None);
    }
    let shower = room
        .furnishings
        .iter()
        .find(|item| item.kind == "shower")
        .ok_or_else(|| fail(room, "falta la ducha"))?;
    let toilet = room
        .furnishings
        .iter()
        .find(|item| item.kind == "toilet")
        .ok_or_else(|| fail(room, "falta el inodoro"))?;
    let config = rules.bath_exhaust;
    let start = shower.footprint.bottom() + config.fixture_gap;
    let end = toilet.footprint.y - config.fixture_gap;
    if !start.is_finite()
        || !end.is_finite()
        || end - start + EPS < config.route_band.max(config.outlet_span)
    {
        return Err(fail(
            room,
            "no hay franja libre entre ducha e inodoro para el paso y la salida",
        ));
    }
    let center_y = (start + end) / 2.0;
    let clear = room.usable;
    let run_length = clear.w / 2.0;
    if !run_length.is_finite() || run_length > config.max_run + EPS {
        return Err(fail(
            room,
            "el recorrido en planta hasta fachada supera el máximo ilustrativo",
        ));
    }
    let band = config.route_band;
    let route = Rect {
        x: if room.side == Side::Left {
            clear.x
        } else {
            clear.right() - run_length - band / 2.0
        },
        y: center_y - band / 2.0,
        w: run_length + band / 2.0,
        h: band,
    };
    let pickup = Rect {
        x: if room.side == Side::Left {
            clear.x + run_length - band / 2.0
        } else {
            clear.right() - run_length - band / 2.0
        },
        y: route.y,
        w: band,
        h: band,
    };
    let outlet = Rect {
        x: if room.side == Side::Left {
            room.rect.x
        } else {
            room.rect.right() - rules.exterior_wall
        },
        y: center_y - config.outlet_span / 2.0,
        w: rules.exterior_wall,
        h: config.outlet_span,
    };
    Ok(Some(BathExhaust {
        outlet,
        route,
        pickup,
        run_length,
        direction: front.side_direction(room.side),
    }))
}

/// Recompute the reservation from the *current* validated room and rules and
/// check its contact, clear footprint, opening jambs and noncollision. Engine
/// validation additionally checks the outlet against ALL other wall openings.
pub fn verify(room: &Room, front: Orientation, rules: &Rules) -> Result<(), String> {
    let expected = design(room, front, rules)?;
    let (Some(actual), Some(expected)) = (&room.exhaust, expected) else {
        return if room.exhaust.is_none() && !matches!(room.kind, Kind::Bathroom(_)) {
            Ok(())
        } else {
            Err(fail(room, "falta una salida en baño o sobra en otro local"))
        };
    };
    if !actual.outlet.approx_eq(expected.outlet)
        || !actual.route.approx_eq(expected.route)
        || !actual.pickup.approx_eq(expected.pickup)
        || !actual.run_length.is_finite()
        || (actual.run_length - expected.run_length).abs() > EPS
        || actual.direction != expected.direction
    {
        return Err(fail(
            room,
            "la salida o el trazado no coincide con las reglas",
        ));
    }
    let clear = room.usable;
    if !actual.route.valid()
        || !actual.pickup.valid()
        || !actual.outlet.valid()
        || !clear.contains(actual.route)
        || !actual.route.contains(actual.pickup)
        || !room.rect.contains(actual.outlet)
        || actual.route.overlaps_interior(room.door.swing)
        || room
            .furnishings
            .iter()
            .any(|fixture| actual.route.overlaps_interior(fixture.footprint))
        || actual.outlet.y < clear.y + rules.corner_clearance - EPS
        || actual.outlet.bottom() > clear.bottom() - rules.corner_clearance + EPS
        || (if room.side == Side::Left {
            actual.outlet.right() - actual.route.x
        } else {
            actual.route.right() - actual.outlet.x
        })
        .abs()
            > EPS
    {
        return Err(fail(
            room,
            "la banda no conecta al muro exterior o invade un sólido o una esquina",
        ));
    }
    if let Some(window) = &room.window {
        // Both openings cross the same facade. Leave a continuous wall pier
        // between them, not just zero intersection area.
        let separation = (actual.outlet.y - window.opening.bottom())
            .max(window.opening.y - actual.outlet.bottom());
        if separation + EPS < rules.corner_clearance {
            return Err(fail(room, "la salida exterior interfiere con una ventana"));
        }
    }
    Ok(())
}
