//! Illustrative bathroom airflow precheck. These bounds only compare a target
//! flow to a FREE-AIR rating and idealized transfer / duct areas. Neither a fan
//! curve nor pressure losses, real make-up air, a 3D duct, discharge or code
//! compliance is assessed. Passing is NOT evidence of delivered ventilation.
use crate::model::{BathAirflowPrecheck, Kind, Room, Rules, EPS};

fn fail(room: &Room, detail: &str) -> String {
    format!(
        "{}: predimensionado nominal de extracción inviable ({detail}).",
        room.kind.label()
    )
}

/// Recompute exclusively from validated clear room/door geometry, the reserved
/// plan route/outlet and the versioned assumptions supplied in `rules`.
pub fn design(room: &Room, rules: &Rules) -> Result<Option<BathAirflowPrecheck>, String> {
    if !matches!(room.kind, Kind::Bathroom(_)) {
        return Ok(None);
    }
    let exhaust = room
        .exhaust
        .as_ref()
        .ok_or_else(|| fail(room, "no hay reserva de extracción en planta"))?;
    let a = rules.bath_airflow;
    if ![
        a.assumed_ceiling_height,
        a.target_ach,
        a.fan_free_air_rating,
        a.door_undercut,
        a.max_transfer_velocity,
        a.duct_height,
        a.duct_bottom,
        a.min_headroom,
        a.max_duct_velocity,
    ]
    .iter()
    .all(|n| n.is_finite() && *n > 0.0)
        || a.duct_bottom + EPS < a.min_headroom
        || a.duct_bottom + a.duct_height > a.assumed_ceiling_height + EPS
    {
        return Err(fail(
            room,
            "la envolvente vertical supuesta no cabe o tiene parámetros inválidos",
        ));
    }
    let volume = room.usable.area() * a.assumed_ceiling_height;
    let flow = volume * a.target_ach;
    let transfer_area = room.door.width * a.door_undercut;
    // An ideal rectangular cross section; not a circular-equivalent diameter,
    // installed duct or proof of clearance through the wall/fixtures in 3D.
    let duct_width = exhaust.route.h.min(exhaust.outlet.h);
    let duct_area = duct_width * a.duct_height;
    if ![volume, flow, transfer_area, duct_width, duct_area]
        .iter()
        .all(|n| n.is_finite() && *n > EPS)
    {
        return Err(fail(
            room,
            "volumen, holgura o sección supuestos nulos o inválidos",
        ));
    }
    let transfer_velocity = flow / (3600.0 * transfer_area);
    let duct_velocity = flow / (3600.0 * duct_area);
    if !transfer_velocity.is_finite() || !duct_velocity.is_finite() {
        return Err(fail(room, "velocidades supuestas inválidas"));
    }
    if flow > a.fan_free_air_rating + EPS {
        return Err(fail(
            room,
            "el caudal objetivo supera la referencia nominal del ventilador en aire libre",
        ));
    }
    if transfer_velocity > a.max_transfer_velocity + EPS {
        return Err(fail(
            room,
            "la velocidad supuesta por la holgura de puerta supera el límite ilustrativo",
        ));
    }
    if duct_velocity > a.max_duct_velocity + EPS {
        return Err(fail(
            room,
            "la velocidad supuesta en la sección idealizada supera el límite ilustrativo",
        ));
    }
    Ok(Some(BathAirflowPrecheck {
        assumptions: a,
        room_volume_m3: volume,
        target_flow_m3h: flow,
        transfer_area_m2: transfer_area,
        transfer_velocity_mps: transfer_velocity,
        duct_width_m: duct_width,
        duct_area_m2: duct_area,
        duct_velocity_mps: duct_velocity,
    }))
}

/// Detect stale rule snapshots and tampered intermediates, even when a mutated
/// field would not otherwise cause a bound failure. Non-bath rooms must have no
/// attached airflow precheck.
pub fn verify(room: &Room, rules: &Rules) -> Result<(), String> {
    let expected = design(room, rules)?;
    let (Some(actual), Some(expected)) = (&room.airflow, expected) else {
        return if room.airflow.is_none() && !matches!(room.kind, Kind::Bathroom(_)) {
            Ok(())
        } else {
            Err(fail(
                room,
                "falta un cálculo para el baño o sobra en otro local",
            ))
        };
    };
    let a = actual.assumptions;
    let b = expected.assumptions;
    let pairs = [
        (a.assumed_ceiling_height, b.assumed_ceiling_height),
        (a.target_ach, b.target_ach),
        (a.fan_free_air_rating, b.fan_free_air_rating),
        (a.door_undercut, b.door_undercut),
        (a.max_transfer_velocity, b.max_transfer_velocity),
        (a.duct_height, b.duct_height),
        (a.duct_bottom, b.duct_bottom),
        (a.min_headroom, b.min_headroom),
        (a.max_duct_velocity, b.max_duct_velocity),
        (actual.room_volume_m3, expected.room_volume_m3),
        (actual.target_flow_m3h, expected.target_flow_m3h),
        (actual.transfer_area_m2, expected.transfer_area_m2),
        (actual.transfer_velocity_mps, expected.transfer_velocity_mps),
        (actual.duct_width_m, expected.duct_width_m),
        (actual.duct_area_m2, expected.duct_area_m2),
        (actual.duct_velocity_mps, expected.duct_velocity_mps),
    ];
    if pairs
        .iter()
        .any(|(actual, expected)| !actual.is_finite() || (*actual - *expected).abs() > EPS)
    {
        return Err(fail(
            room,
            "cálculo o hipótesis no coincide con la geometría y las reglas",
        ));
    }
    Ok(())
}
