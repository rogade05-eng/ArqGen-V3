//! Hypothetical pressure-budget *screen*, not a fan performance calculation.
//! Inputs are demo assumptions: no catalogue fan curve, installed duct, real
//! fittings/lengths or measured loss/flow is known. The second fan point is
//! unverified and interpolation is restricted to the two supplied points.
use crate::model::{BathPressureScreen, Kind, Room, Rules, EPS};

fn fail(room: &Room, detail: &str) -> String {
    format!(
        "{}: escenario hipotético de presión inviable ({detail}).",
        room.kind.label()
    )
}

/// At the *target* flow only: build a simplified Darcy-Weisbach + lumped-K
/// budget from the existing 2D run to facade, a hypothetical rectangular
/// section and a wall crossing. No operating point or delivered flow is solved.
pub fn design(room: &Room, rules: &Rules) -> Result<Option<BathPressureScreen>, String> {
    if !matches!(room.kind, Kind::Bathroom(_)) {
        return Ok(None);
    }
    let exhaust = room
        .exhaust
        .as_ref()
        .ok_or_else(|| fail(room, "falta la reserva 2D"))?;
    let flow = room
        .airflow
        .as_ref()
        .ok_or_else(|| fail(room, "falta el objetivo nominal de caudal"))?;
    let a = rules.bath_pressure;
    let free_air = rules.bath_airflow.fan_free_air_rating;
    if ![
        a.fan_reference_pressure_pa,
        a.fan_reference_flow_m3h,
        a.assumed_air_density_kg_m3,
        a.assumed_darcy_factor,
        free_air,
    ]
    .iter()
    .all(|n| n.is_finite() && *n > 0.0)
        || ![a.assumed_bend_k, a.assumed_outlet_k, a.assumed_reserve_pa]
            .iter()
            .all(|n| n.is_finite() && *n >= 0.0)
        || a.fan_reference_flow_m3h >= free_air
    {
        return Err(fail(
            room,
            "los dos puntos de referencia o los supuestos son incoherentes",
        ));
    }
    let width = flow.duct_width_m;
    let height = flow.assumptions.duct_height;
    let velocity = flow.duct_velocity_mps;
    let length = exhaust.run_length + rules.exterior_wall;
    let hydraulic_diameter = 2.0 * width * height / (width + height);
    if ![
        width,
        height,
        velocity,
        length,
        hydraulic_diameter,
        flow.target_flow_m3h,
    ]
    .iter()
    .all(|n| n.is_finite() && *n > EPS)
    {
        return Err(fail(
            room,
            "tramo, sección o caudal objetivo supuesto inválido",
        ));
    }
    let dynamic_pressure = 0.5 * a.assumed_air_density_kg_m3 * velocity * velocity;
    let straight_loss = a.assumed_darcy_factor * length / hydraulic_diameter * dynamic_pressure;
    let bend_loss = a.assumed_bend_count as f64 * a.assumed_bend_k * dynamic_pressure;
    let outlet_loss = a.assumed_outlet_k * dynamic_pressure;
    let budget = straight_loss + bend_loss + outlet_loss + a.assumed_reserve_pa;
    if ![
        dynamic_pressure,
        straight_loss,
        bend_loss,
        outlet_loss,
        budget,
    ]
    .iter()
    .all(|n| n.is_finite() && *n >= 0.0)
    {
        return Err(fail(room, "presupuesto de presión supuesto inválido"));
    }
    if budget > a.fan_reference_pressure_pa {
        return Err(fail(
            room,
            "el presupuesto supuesto excede el tramo de referencia; no se extrapola",
        ));
    }
    // Linear *reference* capacity at the assumed budget, NOT a delivered or
    // predicted operating flow. Both points and all losses are hypothetical.
    let reference_capacity =
        free_air + (a.fan_reference_flow_m3h - free_air) * budget / a.fan_reference_pressure_pa;
    if !reference_capacity.is_finite() || reference_capacity + EPS < flow.target_flow_m3h {
        return Err(fail(
            room,
            "el objetivo supera la capacidad de referencia interpolada bajo estos supuestos",
        ));
    }
    Ok(Some(BathPressureScreen {
        assumptions: a,
        free_air_flow_m3h: free_air,
        target_flow_m3h: flow.target_flow_m3h,
        assumed_straight_length_m: length,
        assumed_hydraulic_diameter_m: hydraulic_diameter,
        assumed_dynamic_pressure_pa: dynamic_pressure,
        assumed_straight_loss_pa: straight_loss,
        assumed_bend_loss_pa: bend_loss,
        assumed_outlet_loss_pa: outlet_loss,
        assumed_total_pressure_budget_pa: budget,
        assumed_linear_reference_capacity_m3h: reference_capacity,
    }))
}

/// Recompute after geometry, outlet and airflow validation; reject stale rule
/// snapshots, mutated intermediate values or pressure data on non-bath rooms.
pub fn verify(room: &Room, rules: &Rules) -> Result<(), String> {
    let expected = design(room, rules)?;
    let (Some(actual), Some(expected)) = (&room.pressure, expected) else {
        return if room.pressure.is_none() && !matches!(room.kind, Kind::Bathroom(_)) {
            Ok(())
        } else {
            Err(fail(
                room,
                "falta el cálculo en un baño o sobra en otro local",
            ))
        };
    };
    let a = actual.assumptions;
    let b = expected.assumptions;
    let numbers = [
        (a.fan_reference_pressure_pa, b.fan_reference_pressure_pa),
        (a.fan_reference_flow_m3h, b.fan_reference_flow_m3h),
        (a.assumed_air_density_kg_m3, b.assumed_air_density_kg_m3),
        (a.assumed_darcy_factor, b.assumed_darcy_factor),
        (a.assumed_bend_k, b.assumed_bend_k),
        (a.assumed_outlet_k, b.assumed_outlet_k),
        (a.assumed_reserve_pa, b.assumed_reserve_pa),
        (actual.free_air_flow_m3h, expected.free_air_flow_m3h),
        (actual.target_flow_m3h, expected.target_flow_m3h),
        (
            actual.assumed_straight_length_m,
            expected.assumed_straight_length_m,
        ),
        (
            actual.assumed_hydraulic_diameter_m,
            expected.assumed_hydraulic_diameter_m,
        ),
        (
            actual.assumed_dynamic_pressure_pa,
            expected.assumed_dynamic_pressure_pa,
        ),
        (
            actual.assumed_straight_loss_pa,
            expected.assumed_straight_loss_pa,
        ),
        (actual.assumed_bend_loss_pa, expected.assumed_bend_loss_pa),
        (
            actual.assumed_outlet_loss_pa,
            expected.assumed_outlet_loss_pa,
        ),
        (
            actual.assumed_total_pressure_budget_pa,
            expected.assumed_total_pressure_budget_pa,
        ),
        (
            actual.assumed_linear_reference_capacity_m3h,
            expected.assumed_linear_reference_capacity_m3h,
        ),
    ];
    if a.assumed_bend_count != b.assumed_bend_count
        || numbers
            .iter()
            .any(|(current, expected)| !current.is_finite() || (*current - *expected).abs() > EPS)
    {
        return Err(fail(
            room,
            "cálculo o hipótesis no coincide con las reglas y el objetivo",
        ));
    }
    Ok(())
}
