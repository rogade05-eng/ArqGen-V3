use arqgen_core::{
    generate_json,
    json::{self, Value},
};
use std::collections::BTreeSet;

fn request() -> Value {
    let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
    root.insert(
        "rules",
        json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
    )
    .unwrap();
    root
}

fn put(parent: &mut Value, field: &str, value: Value) {
    match parent {
        Value::Object(map) => {
            map.insert(field.into(), value);
        }
        _ => panic!("objeto requerido"),
    }
}
fn child<'a>(parent: &'a mut Value, field: &str) -> &'a mut Value {
    match parent {
        Value::Object(map) => map.get_mut(field).expect(field),
        _ => panic!("objeto requerido"),
    }
}
fn output(value: &Value) -> Value {
    let result = json::parse(&generate_json(&value.stringify())).unwrap();
    check_rejections(&result);
    result
}
fn check_rejections(result: &Value) {
    let summary = result.get("rejection_summary").unwrap().as_array().unwrap();
    if result.get("status").unwrap().as_str() == Some("error") {
        assert!(summary.is_empty());
        return;
    }
    let generated = num(result, "generated");
    let rejected = num(result, "rejected");
    assert!(generated >= 0.0 && rejected <= generated);
    assert_eq!(
        summary.iter().map(|r| num(r, "count")).sum::<f64>(),
        rejected
    );
    let mut previous: Option<(f64, &str)> = None;
    for row in summary {
        let count = num(row, "count");
        let reason = row.get("reason").unwrap().as_str().unwrap();
        assert!(count > 0.0 && count.fract() == 0.0 && !reason.is_empty());
        if let Some((older_count, older_reason)) = previous {
            assert!(older_count > count || (older_count == count && older_reason < reason));
        }
        previous = Some((count, reason));
    }
    if result.get("status").unwrap().as_str() == Some("infeasible") {
        assert_eq!(generated, rejected);
        assert!(result
            .get("alternatives")
            .unwrap()
            .as_array()
            .unwrap()
            .is_empty());
    }
}
fn num(obj: &Value, key: &str) -> f64 {
    obj.get(key).unwrap().as_number().unwrap()
}
fn arr<'a>(obj: &'a Value, key: &str) -> &'a [Value] {
    obj.get(key).unwrap().as_array().unwrap()
}
fn status(obj: &Value) -> &str {
    obj.get("status").unwrap().as_str().unwrap()
}

#[derive(Clone, Copy, Debug)]
struct Box2 {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}
impl Box2 {
    fn from(value: &Value) -> Self {
        Self {
            x: num(value, "x"),
            y: num(value, "y"),
            w: num(value, "width"),
            h: num(value, "depth"),
        }
    }
    fn area(self) -> f64 {
        self.w * self.h
    }
    fn right(self) -> f64 {
        self.x + self.w
    }
    fn bottom(self) -> f64 {
        self.y + self.h
    }
    fn contains(self, other: Self) -> bool {
        other.x >= self.x - 1e-6
            && other.y >= self.y - 1e-6
            && other.right() <= self.right() + 1e-6
            && other.bottom() <= self.bottom() + 1e-6
    }
    fn intersection(self, other: Self) -> f64 {
        (self.right().min(other.right()) - self.x.max(other.x)).max(0.0)
            * (self.bottom().min(other.bottom()) - self.y.max(other.y)).max(0.0)
    }
}
fn close(a: f64, b: f64) {
    assert!((a - b).abs() < 1e-5, "{a} ≠ {b}");
}
fn opening_in_wall(opening: Box2, walls: &[Box2]) {
    close(
        opening.area(),
        walls.iter().map(|wall| opening.intersection(*wall)).sum(),
    );
}

// Check the exported placements with rectangles read back from JSON, rather
// than invoking the template generator or trusting its `furnishing_status`.
fn check_furnishings(room: &Value) {
    let clear = Box2::from(room.get("usable_rect").unwrap());
    let door = room.get("door").unwrap();
    let swing = Box2::from(door.get("swing").unwrap());
    let route: Vec<_> = arr(room, "access_route").iter().map(Box2::from).collect();
    assert_eq!(route.len(), 2);
    let a = route[0].w;
    assert!(a + 1e-6 >= 0.55 && route[1].h + 1e-6 >= a);
    for segment in &route {
        assert!(clear.contains(*segment));
    }
    assert!(route[0].intersection(route[1]) >= a * a - 1e-5);
    assert!(route[1].y >= num(door, "y") - num(door, "width") / 2.0 - 1e-6);
    assert!(route[1].bottom() <= num(door, "y") + num(door, "width") / 2.0 + 1e-6);
    if room.get("side").unwrap().as_str() == Some("left") {
        close(route[1].right(), clear.right());
    } else {
        close(route[1].x, clear.x);
    }
    let fixtures = arr(room, "furnishings");
    let expected = match room.get("type").unwrap().as_str().unwrap() {
        "living_dining" | "kitchen" => 2,
        "bedroom" => 1,
        "bathroom" => 3,
        other => panic!("tipo inesperado {other}"),
    };
    assert_eq!(fixtures.len(), expected);
    assert_eq!(
        room.get("furnishing_status").unwrap().as_str(),
        Some("illustrative_geometric_fit")
    );
    let solids: Vec<_> = fixtures
        .iter()
        .map(|f| Box2::from(f.get("footprint").unwrap()))
        .collect();
    for (index, fixture) in fixtures.iter().enumerate() {
        let solid = solids[index];
        assert!(clear.contains(solid));
        assert!(solid.intersection(swing) < 1e-6);
        assert!(route.iter().all(|r| solid.intersection(*r) < 1e-6));
        for other in solids.iter().skip(index + 1) {
            assert!(solid.intersection(*other) < 1e-6);
        }
        if let Some(window) = room.get("window").filter(|w| **w != Value::Null) {
            let opening = Box2::from(window.get("opening").unwrap());
            let band = Box2 {
                x: if room.get("side").unwrap().as_str() == Some("left") {
                    clear.x
                } else {
                    clear.right() - 0.20
                },
                y: opening.y,
                w: 0.20,
                h: opening.h,
            };
            assert!(solid.intersection(band) < 1e-6);
        }
        let id = fixture.get("id").unwrap().as_str().unwrap();
        assert_eq!(
            id,
            format!(
                "{}-{}",
                room.get("id").unwrap().as_str().unwrap(),
                fixture.get("type").unwrap().as_str().unwrap()
            )
        );
        assert!(!arr(fixture, "use_zones").is_empty());
        for zone in arr(fixture, "use_zones").iter().map(Box2::from) {
            assert!(clear.contains(zone));
            assert!(zone.intersection(swing) < 1e-6);
            assert!(solids.iter().all(|solid| zone.intersection(*solid) < 1e-6));
            assert!(route.iter().any(|r| zone.intersection(*r) >= a * a - 1e-5));
        }
    }
}

// Exhaust is tested from serialized coordinates independently of the Rust
// placement function. Its 2D projection is not evidence of installed airflow.
fn check_bath_exhaust(room: &Value, walls: &[Box2]) -> Option<Box2> {
    let exhaust = room.get("bath_exhaust").unwrap();
    if room.get("type").unwrap().as_str() != Some("bathroom") {
        assert_eq!(*exhaust, Value::Null);
        return None;
    }
    assert_eq!(
        exhaust.get("mode").unwrap().as_str(),
        Some("direct_exterior_exhaust_reservation")
    );
    assert_eq!(
        exhaust.get("geometry_status").unwrap().as_str(),
        Some("outlet_and_route_reserved")
    );
    assert_eq!(
        exhaust.get("airflow_status").unwrap().as_str(),
        Some("not_evaluated")
    );
    let cell = Box2::from(room.get("rect").unwrap());
    let clear = Box2::from(room.get("usable_rect").unwrap());
    let outlet = Box2::from(exhaust.get("outlet").unwrap());
    let route = Box2::from(exhaust.get("route").unwrap());
    let pickup = Box2::from(exhaust.get("pickup").unwrap());
    let swing = Box2::from(room.get("door").unwrap().get("swing").unwrap());
    assert!(cell.contains(outlet) && clear.contains(route) && route.contains(pickup));
    opening_in_wall(outlet, walls);
    close(num(exhaust, "run_length"), clear.w / 2.0);
    close(route.h, pickup.h);
    close(route.y, pickup.y);
    assert!(route.intersection(swing) < 1e-6);
    let fixtures = arr(room, "furnishings");
    for fixture in fixtures {
        assert!(route.intersection(Box2::from(fixture.get("footprint").unwrap())) < 1e-6);
    }
    let shower = fixtures
        .iter()
        .find(|f| f.get("type").unwrap().as_str() == Some("shower"))
        .unwrap();
    let toilet = fixtures
        .iter()
        .find(|f| f.get("type").unwrap().as_str() == Some("toilet"))
        .unwrap();
    let between_start = Box2::from(shower.get("footprint").unwrap()).bottom();
    let between_end = Box2::from(toilet.get("footprint").unwrap()).y;
    assert!(outlet.y >= between_start - 1e-6 && outlet.bottom() <= between_end + 1e-6);
    assert!(route.y >= between_start - 1e-6 && route.bottom() <= between_end + 1e-6);
    if room.get("side").unwrap().as_str() == Some("left") {
        close(outlet.x, cell.x);
        close(outlet.right(), clear.x);
        close(route.x, clear.x);
    } else {
        close(outlet.x, clear.right());
        close(outlet.right(), cell.right());
        close(route.right(), clear.right());
    }
    if let Some(window) = room.get("window").filter(|w| **w != Value::Null) {
        let other = Box2::from(window.get("opening").unwrap());
        let separation = (outlet.y - other.bottom()).max(other.y - outlet.bottom());
        assert!(separation + 1e-6 >= 0.15);
    }
    Some(outlet)
}

// Recompute the nominal scenario solely from exported JSON (not the Rust
// design function). This cannot validate a real installed system or airflow.
fn check_bath_airflow(room: &Value) {
    let value = room.get("bath_airflow").unwrap();
    if room.get("type").unwrap().as_str() != Some("bathroom") {
        assert_eq!(*value, Value::Null);
        assert_eq!(
            room.get("ventilation_status").unwrap().as_str(),
            Some("not_applicable")
        );
        return;
    }
    assert_eq!(
        value.get("status").unwrap().as_str(),
        Some("nominal_precheck_only")
    );
    assert_eq!(
        value.get("delivered_flow_status").unwrap().as_str(),
        Some("not_evaluated")
    );
    assert_eq!(
        room.get("ventilation_status").unwrap().as_str(),
        Some("not_evaluated")
    );
    let volume = num(room, "usable_area") * num(value, "assumed_ceiling_height_m");
    let target = volume * num(value, "target_ach");
    close(num(value, "room_volume_m3"), volume);
    close(num(value, "target_flow_m3h"), target);
    assert!(target <= num(value, "fan_reference_free_air_rating_m3h") + 1e-6);
    let transfer = value.get("transfer").unwrap();
    let transfer_area =
        num(room.get("door").unwrap(), "width") * num(transfer, "assumed_door_undercut_m");
    close(num(transfer, "assumed_free_area_m2"), transfer_area);
    close(
        num(transfer, "velocity_at_target_mps"),
        target / (3600.0 * transfer_area),
    );
    assert!(num(transfer, "velocity_at_target_mps") <= num(transfer, "max_velocity_mps") + 1e-6);
    let duct = value.get("duct").unwrap();
    let exhaust = room.get("bath_exhaust").unwrap();
    let section = num(exhaust.get("route").unwrap(), "depth")
        .min(num(exhaust.get("outlet").unwrap(), "depth"))
        * (num(duct, "assumed_top_m") - num(duct, "assumed_bottom_m"));
    close(
        num(duct, "assumed_width_m"),
        num(exhaust.get("route").unwrap(), "depth")
            .min(num(exhaust.get("outlet").unwrap(), "depth")),
    );
    close(
        num(duct, "assumed_height_m"),
        num(duct, "assumed_top_m") - num(duct, "assumed_bottom_m"),
    );
    close(num(duct, "assumed_section_m2"), section);
    close(
        num(duct, "velocity_at_target_mps"),
        target / (3600.0 * section),
    );
    assert!(num(duct, "velocity_at_target_mps") <= num(duct, "max_velocity_mps") + 1e-6);
    assert!(num(duct, "assumed_bottom_m") + 1e-6 >= num(duct, "min_headroom_m"));
    assert!(num(duct, "assumed_top_m") <= num(value, "assumed_ceiling_height_m") + 1e-6);
}

// Independent round-trip proof of the *hypothetical* pressure calculation.
// No actual fan, measured loss or delivered ventilation is represented.
fn check_bath_pressure(room: &Value) {
    let value = room.get("bath_pressure").unwrap();
    if room.get("type").unwrap().as_str() != Some("bathroom") {
        assert_eq!(*value, Value::Null);
        return;
    }
    assert_eq!(
        value.get("status").unwrap().as_str(),
        Some("hypothetical_pressure_screen_only")
    );
    assert_eq!(
        value.get("delivered_flow_status").unwrap().as_str(),
        Some("not_evaluated")
    );
    let fan = value.get("fan_reference").unwrap();
    let inputs = value.get("assumptions").unwrap();
    let budget = value.get("pressure_budget").unwrap();
    let flow = room.get("bath_airflow").unwrap();
    let duct = flow.get("duct").unwrap();
    let exhaust = room.get("bath_exhaust").unwrap();
    close(num(budget, "target_flow_m3h"), num(flow, "target_flow_m3h"));
    close(
        num(fan, "free_air_flow_m3h"),
        num(flow, "fan_reference_free_air_rating_m3h"),
    );
    assert!(num(fan, "reference_flow_m3h") < num(fan, "free_air_flow_m3h"));
    let length = num(exhaust, "run_length") + num(exhaust.get("outlet").unwrap(), "width");
    close(num(budget, "assumed_straight_length_m"), length);
    let width = num(duct, "assumed_width_m");
    let height = num(duct, "assumed_height_m");
    let diameter = 2.0 * width * height / (width + height);
    close(num(budget, "assumed_hydraulic_diameter_m"), diameter);
    let velocity = num(duct, "velocity_at_target_mps");
    let dynamic = 0.5 * num(inputs, "air_density_kg_m3") * velocity * velocity;
    close(num(budget, "assumed_dynamic_pressure_pa"), dynamic);
    let straight = num(inputs, "darcy_factor") * length / diameter * dynamic;
    let bends = num(inputs, "bend_count") * num(inputs, "bend_k") * dynamic;
    let outlet = num(inputs, "outlet_k") * dynamic;
    close(num(budget, "assumed_straight_loss_pa"), straight);
    close(num(budget, "assumed_bend_loss_pa"), bends);
    close(num(budget, "assumed_outlet_loss_pa"), outlet);
    close(num(budget, "assumed_reserve_pa"), num(inputs, "reserve_pa"));
    let total = straight + bends + outlet + num(inputs, "reserve_pa");
    close(num(budget, "assumed_total_pa"), total);
    assert!(total <= num(fan, "reference_pressure_pa") + 1e-6);
    let linear = num(fan, "free_air_flow_m3h")
        + (num(fan, "reference_flow_m3h") - num(fan, "free_air_flow_m3h")) * total
            / num(fan, "reference_pressure_pa");
    close(num(fan, "assumed_linear_capacity_at_budget_m3h"), linear);
    assert!(linear + 1e-6 >= num(budget, "target_flow_m3h"));
}

fn check_plan_geometry(alt: &Value, site: &Value) {
    let buildable = Box2::from(site.get("buildable").unwrap());
    let corridor = Box2::from(alt.get("corridor").unwrap());
    let rooms = arr(alt, "rooms");
    let walls: Vec<_> = arr(alt, "wall_zones").iter().map(Box2::from).collect();
    let clear_corridor: Vec<_> = arr(alt, "corridor_usable_segments")
        .iter()
        .map(Box2::from)
        .collect();
    assert!(buildable.contains(corridor));
    let gross = corridor.area()
        + rooms
            .iter()
            .map(|room| Box2::from(room.get("rect").unwrap()).area())
            .sum::<f64>();
    let net_rooms = rooms
        .iter()
        .map(|room| Box2::from(room.get("usable_rect").unwrap()).area())
        .sum::<f64>();
    let net_corridor = clear_corridor.iter().map(|seg| seg.area()).sum::<f64>();
    let wall_area = walls.iter().map(|wall| wall.area()).sum::<f64>();
    close(num(alt, "built_area"), gross);
    close(num(alt, "usable_area"), net_rooms + net_corridor);
    close(num(alt, "circulation_usable_area"), net_corridor);
    close(num(alt, "wall_allowance_area"), wall_area);
    close(gross, net_rooms + net_corridor + wall_area);
    assert!(num(alt, "built_area") <= num(site, "max_footprint") + 1e-6);
    assert!(num(alt, "built_area") <= num(site, "max_built_area") + 1e-6);
    for (index, wall) in walls.iter().enumerate() {
        assert!(wall.area() > 0.0 && buildable.contains(*wall));
        for other in walls.iter().skip(index + 1) {
            assert!(wall.intersection(*other) < 1e-6);
        }
    }
    let mut openings = Vec::new();
    let entrance = alt.get("entrance").unwrap();
    let entry = Box2::from(entrance.get("opening").unwrap());
    opening_in_wall(entry, &walls);
    openings.push(entry);
    let main_swing = Box2::from(entrance.get("swing").unwrap());
    close(
        main_swing.area(),
        clear_corridor
            .iter()
            .map(|c| main_swing.intersection(*c))
            .sum(),
    );
    for room in rooms {
        let cell = Box2::from(room.get("rect").unwrap());
        let clear = Box2::from(room.get("usable_rect").unwrap());
        assert!(buildable.contains(cell) && cell.contains(clear));
        close(clear.area(), num(room, "usable_area"));
        close(clear.area(), num(room, "area"));
        close(cell.area(), num(room, "gross_cell_area"));
        check_furnishings(room);
        check_bath_airflow(room);
        check_bath_pressure(room);
        assert!(cell.intersection(corridor) < 1e-6);
        for wall in &walls {
            assert!(clear.intersection(*wall) < 1e-6);
        }
        let door = room.get("door").unwrap();
        let door_opening = Box2::from(door.get("opening").unwrap());
        opening_in_wall(door_opening, &walls);
        openings.push(door_opening);
        assert!(clear.contains(Box2::from(door.get("swing").unwrap())));
        if let Some(outlet) = check_bath_exhaust(room, &walls) {
            openings.push(outlet);
        }
        if room.get("type").unwrap().as_str() == Some("bathroom") {
            assert_eq!(
                room.get("ventilation_status").unwrap().as_str(),
                Some("not_evaluated")
            );
        }
        if let Some(window) = room.get("window").filter(|w| **w != Value::Null) {
            let window_opening = Box2::from(window.get("opening").unwrap());
            opening_in_wall(window_opening, &walls);
            openings.push(window_opening);
        }
    }
    for (i, a) in openings.iter().enumerate() {
        for b in openings.iter().skip(i + 1) {
            assert!(a.intersection(*b) < 1e-6);
        }
    }
    assert_eq!(
        alt.get("bathroom_ventilation_status").unwrap().as_str(),
        Some("not_evaluated")
    );
    assert_eq!(
        alt.get("bathroom_exhaust_status").unwrap().as_str(),
        Some("geometry_reserved_only")
    );
    assert_eq!(
        alt.get("bathroom_airflow_status").unwrap().as_str(),
        Some("nominal_precheck_only")
    );
    assert_eq!(
        alt.get("bathroom_pressure_status").unwrap().as_str(),
        Some("hypothetical_pressure_screen_only")
    );
}

#[test]
fn sample_has_distinct_safe_options_and_explanations() {
    let out = output(&request());
    assert_eq!(status(&out), "ok");
    assert_eq!(
        out.get("engine_version").unwrap().as_str(),
        Some("mvp0.18-rust-0.15.0")
    );
    assert_eq!(out.get("rule_version").unwrap().as_str(), Some("0.8.0"));
    assert!(out
        .get("notice")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("No se evalúan curva real de ventilador"));
    let alternatives = arr(&out, "alternatives");
    assert_eq!(alternatives.len(), 3);
    assert_eq!(num(&out, "generated"), 48.0);
    assert_eq!(
        out.get("regulatory_status").unwrap().as_str(),
        Some("illustrative_not_certified")
    );
    let site = out.get("site").unwrap();
    let options: BTreeSet<_> = alternatives
        .iter()
        .map(|a| a.get("id").unwrap().as_str().unwrap())
        .collect();
    assert_eq!(options.len(), 3);
    for alternative in alternatives {
        assert!(num(alternative, "built_area") <= num(site, "max_footprint") + 1e-7);
        assert!(num(alternative, "built_area") <= num(site, "max_built_area") + 1e-7);
        check_plan_geometry(alternative, site);
        let rooms = arr(alternative, "rooms");
        assert_eq!(rooms.len(), 7);
        assert!(arr(alternative, "decisions").len() >= rooms.len() + 2);
        assert!(alternative
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("NO APTO PARA OBRA"));
        let names: BTreeSet<_> = rooms
            .iter()
            .map(|r| r.get("id").unwrap().as_str().unwrap())
            .collect();
        assert_eq!(names.len(), rooms.len());
        for i in 1..=3 {
            assert!(names.contains(format!("bedroom-{i}").as_str()));
        }
        for i in 1..=2 {
            assert!(names.contains(format!("bathroom-{i}").as_str()));
        }
        let corridor = alternative.get("corridor").unwrap();
        for room in rooms {
            let rect = room.get("rect").unwrap();
            let door = room.get("door").unwrap();
            let shared = if room.get("side").unwrap().as_str() == Some("left") {
                num(rect, "x") + num(rect, "width") - num(corridor, "x")
            } else {
                num(rect, "x") - (num(corridor, "x") + num(corridor, "width"))
            };
            assert!(shared.abs() < 1e-6);
            assert!(num(door, "width") >= 0.7);
            if room.get("type").unwrap().as_str() != Some("bathroom") {
                let window = room.get("window").unwrap();
                assert!(num(window, "width") * num(window, "height") >= num(room, "area") * 0.1);
            }
        }
    }
}

#[test]
fn replay_is_byte_identical_and_rules_are_part_of_input_hash() {
    let input = request();
    let output_one = generate_json(&input.stringify());
    assert_eq!(output_one, generate_json(&input.stringify()));
    let mut changed = input.clone();
    put(child(&mut changed, "rules"), "max_far", Value::Number(0.60));
    let a = output(&input);
    let b = output(&changed);
    assert_ne!(a.get("input_hash"), b.get("input_hash"));
    let mut new_seed = input.clone();
    put(&mut new_seed, "seed", Value::Number(991.0));
    assert_ne!(output(&new_seed).get("input_hash"), a.get("input_hash"));
}

#[test]
fn infeasible_inputs_never_return_partial_plans() {
    let mut tiny = request();
    put(child(&mut tiny, "site"), "width", Value::Number(7.0));
    put(child(&mut tiny, "site"), "depth", Value::Number(9.0));
    let result = output(&tiny);
    assert_eq!(status(&result), "infeasible");
    assert!(arr(&result, "alternatives").is_empty());
    assert!(!arr(&result, "reasons").is_empty());
    assert!(result
        .get("notice")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("no demuestra"));

    let mut low_far = request();
    put(child(&mut low_far, "rules"), "max_far", Value::Number(0.01));
    assert_eq!(status(&output(&low_far)), "infeasible");
}

#[test]
fn far_does_not_infer_zero_floors_from_full_footprint() {
    let mut input = request();
    let s = child(&mut input, "site");
    put(s, "width", Value::Number(10.0));
    put(s, "depth", Value::Number(10.0));
    let p = child(&mut input, "program");
    put(p, "bedrooms", Value::Number(1.0));
    put(p, "bathrooms", Value::Number(1.0));
    put(p, "target_built_area", Value::Number(55.0));
    let rules = child(&mut input, "rules");
    put(rules, "max_far", Value::Number(0.60));
    put(rules, "max_coverage", Value::Number(0.80));
    let setbacks = child(rules, "setbacks");
    for edge in ["front", "rear", "left", "right"] {
        put(setbacks, edge, Value::Number(0.0));
    }
    let result = output(&input);
    assert_eq!(status(&result), "ok", "{result:?}");
    assert_eq!(num(result.get("site").unwrap(), "max_built_area"), 60.0);
    assert!(num(&arr(&result, "alternatives")[0], "built_area") <= 60.0);
}

#[test]
fn invalid_fields_and_fake_regulatory_claims_fail_closed() {
    let mut input = request();
    put(child(&mut input, "site"), "floors", Value::Number(2.0));
    assert_eq!(status(&output(&input)), "error");
    let mut input = request();
    put(
        child(&mut input, "rules"),
        "regulatory_status",
        Value::String("certified".into()),
    );
    assert_eq!(status(&output(&input)), "error");
    let mut input = request();
    put(child(&mut input, "program"), "bedrooms", Value::Number(2.5));
    assert_eq!(status(&output(&input)), "error");
}

#[test]
fn cli_does_not_write_svg_for_an_infeasible_brief() {
    use std::{fs, process::Command};
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    let brief = std::env::temp_dir().join(format!("arqgen-brief-{}.json", std::process::id()));
    let svg = std::env::temp_dir().join(format!("arqgen-invalid-{}.svg", std::process::id()));
    let _ = fs::remove_file(&svg);
    let mut brief_input = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
    put(child(&mut brief_input, "site"), "width", Value::Number(7.0));
    put(child(&mut brief_input, "site"), "depth", Value::Number(9.0));
    fs::write(&brief, brief_input.stringify()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(&brief)
        .arg("--rules")
        .arg(root.join("knowledge/generic-house.json"))
        .arg("--svg")
        .arg(&svg)
        .output()
        .unwrap();
    let _ = fs::remove_file(&brief);
    assert!(!output.status.success());
    assert_eq!(
        status(&json::parse(std::str::from_utf8(&output.stdout).unwrap()).unwrap()),
        "infeasible"
    );
    assert!(
        !svg.exists(),
        "nunca se exporta SVG si no hay propuesta válida"
    );
}

#[test]
fn cli_never_exports_a_plan_when_bath_exhaust_has_no_viable_route() {
    use std::{fs, process::Command};
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    let rules_file =
        std::env::temp_dir().join(format!("arqgen-exhaust-rules-{}.json", std::process::id()));
    let svg_file =
        std::env::temp_dir().join(format!("arqgen-exhaust-invalid-{}.svg", std::process::id()));
    let _ = fs::remove_file(&svg_file);
    let mut rules = json::parse(include_str!("../../knowledge/generic-house.json")).unwrap();
    put(
        child(&mut rules, "bath_exhaust"),
        "route_band",
        Value::Number(0.40),
    );
    fs::write(&rules_file, rules.stringify()).unwrap();
    let result = Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(root.join("examples/rectangular.json"))
        .arg("--rules")
        .arg(&rules_file)
        .arg("--svg")
        .arg(&svg_file)
        .output()
        .unwrap();
    let _ = fs::remove_file(&rules_file);
    assert!(!result.status.success());
    let parsed = json::parse(std::str::from_utf8(&result.stdout).unwrap()).unwrap();
    assert_eq!(status(&parsed), "infeasible");
    assert!(arr(&parsed, "alternatives").is_empty());
    assert!(
        !svg_file.exists(),
        "no debe escribirse un SVG para una extracción inviable"
    );
}

#[test]
fn cardinal_orientation_changes_window_directions_and_keeps_static_export() {
    for (front, expected_left, expected_right) in [
        ("N", "W", "E"),
        ("E", "N", "S"),
        ("S", "E", "W"),
        ("W", "S", "N"),
    ] {
        let mut input = request();
        put(
            child(&mut input, "site"),
            "front_orientation",
            Value::String(front.into()),
        );
        let result = output(&input);
        assert_eq!(status(&result), "ok");
        for alt in arr(&result, "alternatives") {
            let svg = alt.get("svg").unwrap().as_str().unwrap();
            assert!(
                !svg.contains("tabindex="),
                "el SVG exportado no es interactivo"
            );
            assert!(
                svg.contains(">N</text>"),
                "la etiqueta norte está fuera del grupo rotado"
            );
            for room in arr(alt, "rooms") {
                if let Some(window) = room.get("window") {
                    if window != &Value::Null {
                        let expected = if room.get("side").unwrap().as_str() == Some("left") {
                            expected_left
                        } else {
                            expected_right
                        };
                        assert_eq!(window.get("direction").unwrap().as_str(), Some(expected));
                    }
                }
                if let Some(exhaust) = room.get("bath_exhaust").filter(|e| **e != Value::Null) {
                    let expected = if room.get("side").unwrap().as_str() == Some("left") {
                        expected_left
                    } else {
                        expected_right
                    };
                    assert_eq!(exhaust.get("direction").unwrap().as_str(), Some(expected));
                }
            }
        }
    }
}

#[test]
fn matrix_covers_program_sizes_or_reports_explicit_infeasibility() {
    for beds in 1..=4 {
        for baths in 1..=2 {
            for width in [12.0, 18.0, 26.0] {
                for depth in [14.0, 22.0] {
                    let mut req = request();
                    put(child(&mut req, "site"), "width", Value::Number(width));
                    put(child(&mut req, "site"), "depth", Value::Number(depth));
                    put(
                        child(&mut req, "program"),
                        "bedrooms",
                        Value::Number(beds as f64),
                    );
                    put(
                        child(&mut req, "program"),
                        "bathrooms",
                        Value::Number(baths as f64),
                    );
                    let result = output(&req);
                    assert!(matches!(status(&result), "ok" | "infeasible"));
                    if status(&result) == "ok" {
                        for alt in arr(&result, "alternatives") {
                            assert_eq!(arr(alt, "rooms").len(), 2 + beds + baths);
                            check_plan_geometry(alt, result.get("site").unwrap());
                            assert!(
                                num(alt, "built_area")
                                    <= num(result.get("site").unwrap(), "max_footprint") + 1e-7
                            );
                        }
                    } else {
                        assert!(arr(&result, "alternatives").is_empty());
                        assert!(!arr(&result, "reasons").is_empty());
                    }
                }
            }
        }
    }
}

#[test]
fn a_thick_partition_never_reduces_the_declared_clear_corridor() {
    let mut input = request();
    let walls = child(child(&mut input, "rules"), "walls");
    put(walls, "exterior", Value::Number(0.10));
    put(walls, "partition", Value::Number(0.30));
    let out = output(&input);
    assert_eq!(status(&out), "ok", "{out:?}");
    for alt in arr(&out, "alternatives") {
        check_plan_geometry(alt, out.get("site").unwrap());
        for segment in arr(alt, "corridor_usable_segments") {
            assert!(num(segment, "width") + 1e-7 >= 1.10);
        }
    }
}

#[test]
fn varied_wall_thicknesses_programs_and_sites_keep_area_identity() {
    for index in 0..64_u32 {
        let mut input = request();
        let front = ["N", "E", "S", "W"][index as usize % 4];
        let site = child(&mut input, "site");
        put(site, "width", Value::Number(9.0 + (index % 12) as f64));
        put(site, "depth", Value::Number(12.0 + (index % 14) as f64));
        put(site, "front_orientation", Value::String(front.into()));
        let program = child(&mut input, "program");
        put(program, "bedrooms", Value::Number(1.0 + (index % 4) as f64));
        put(
            program,
            "bathrooms",
            Value::Number(1.0 + (index % 2) as f64),
        );
        let walls = child(child(&mut input, "rules"), "walls");
        put(
            walls,
            "exterior",
            Value::Number(0.10 + (index % 5) as f64 * 0.06),
        );
        put(
            walls,
            "partition",
            Value::Number(0.08 + (index % 4) as f64 * 0.05),
        );
        put(&mut input, "seed", Value::Number(index as f64));
        let result = output(&input);
        assert!(
            matches!(status(&result), "ok" | "infeasible"),
            "index {index}: {result:?}"
        );
        if status(&result) == "ok" {
            for alt in arr(&result, "alternatives") {
                check_plan_geometry(alt, result.get("site").unwrap());
            }
        } else {
            assert!(arr(&result, "alternatives").is_empty());
            assert!(!arr(&result, "reasons").is_empty());
        }
    }
}

#[test]
fn changed_furniture_dimensions_and_aisles_always_produce_verified_fit_or_no_plan() {
    for index in 0..48_u32 {
        let mut input = request();
        let furniture = child(child(&mut input, "rules"), "furnishings");
        let aisle = 0.55 + (index % 4) as f64 * 0.05;
        put(furniture, "min_aisle", Value::Number(aisle));
        put(
            child(furniture, "bed"),
            "width",
            Value::Number(1.20 + (index % 6) as f64 * 0.24),
        );
        put(
            child(furniture, "shower"),
            "width",
            Value::Number(0.75 + (index % 3) as f64 * 0.10),
        );
        put(
            child(furniture, "sofa"),
            "width",
            Value::Number(1.60 + (index % 4) as f64 * 0.25),
        );
        put(&mut input, "seed", Value::Number(index as f64));
        let result = output(&input);
        assert!(
            matches!(status(&result), "ok" | "infeasible"),
            "index {index}: {result:?}"
        );
        if status(&result) == "ok" {
            for alt in arr(&result, "alternatives") {
                check_plan_geometry(alt, result.get("site").unwrap());
                for room in arr(alt, "rooms") {
                    close(num(&arr(room, "access_route")[0], "width"), aisle);
                }
            }
        } else {
            assert!(arr(&result, "alternatives").is_empty());
            assert!(!arr(&result, "reasons").is_empty());
        }
    }
}

#[test]
fn varied_exhaust_rules_are_proven_in_plan_or_report_infeasible() {
    for index in 0..48_u32 {
        let mut input = request();
        let config = child(child(&mut input, "rules"), "bath_exhaust");
        let outlet = 0.10 + (index % 4) as f64 * 0.04;
        let band = 0.10 + (index % 5) as f64 * 0.03;
        let fixture_gap = (index % 3) as f64 * 0.01;
        let max_run = 1.30 + (index % 4) as f64 * 0.40;
        put(config, "outlet_span", Value::Number(outlet));
        put(config, "route_band", Value::Number(band));
        put(config, "fixture_gap", Value::Number(fixture_gap));
        put(config, "max_run", Value::Number(max_run));
        put(&mut input, "seed", Value::Number(index as f64));
        let result = output(&input);
        assert!(
            matches!(status(&result), "ok" | "infeasible"),
            "index {index}: {result:?}"
        );
        if status(&result) == "ok" {
            for alt in arr(&result, "alternatives") {
                check_plan_geometry(alt, result.get("site").unwrap());
                for room in arr(alt, "rooms") {
                    if let Some(exhaust) = room.get("bath_exhaust").filter(|e| **e != Value::Null) {
                        close(num(exhaust.get("outlet").unwrap(), "depth"), outlet);
                        close(num(exhaust.get("route").unwrap(), "depth"), band);
                        assert!(num(exhaust, "run_length") <= max_run + 1e-6);
                    }
                }
            }
        } else {
            assert!(arr(&result, "alternatives").is_empty());
            assert!(!arr(&result, "reasons").is_empty());
        }
    }
}

#[test]
fn impossible_or_malformed_bath_exhaust_fails_closed() {
    let baseline = output(&request());
    assert_eq!(status(&baseline), "ok");
    let mut too_wide = request();
    put(
        child(child(&mut too_wide, "rules"), "bath_exhaust"),
        "route_band",
        Value::Number(0.40),
    );
    let result = output(&too_wide);
    assert_eq!(status(&result), "infeasible", "{result:?}");
    assert!(arr(&result, "alternatives").is_empty());
    assert!(arr(&result, "reasons")
        .iter()
        .any(|reason| reason.as_str().unwrap().contains("extracción")));
    assert_ne!(baseline.get("input_hash"), result.get("input_hash"));

    let mut too_long = request();
    put(
        child(child(&mut too_long, "rules"), "bath_exhaust"),
        "max_run",
        Value::Number(0.50),
    );
    let result = output(&too_long);
    assert_eq!(status(&result), "infeasible");
    assert!(arr(&result, "alternatives").is_empty());

    // The new bathroom template places a small opening off the exhaust
    // outlet instead of superposing them on the same segment of facade.
    let mut small = request();
    put(
        child(child(child(&mut small, "rules"), "spaces"), "bathroom"),
        "window_ratio",
        Value::Number(0.01),
    );
    let result = output(&small);
    assert_eq!(status(&result), "ok");
    for alt in arr(&result, "alternatives") {
        for room in arr(alt, "rooms")
            .iter()
            .filter(|room| room.get("type").unwrap().as_str() == Some("bathroom"))
        {
            assert!(room.get("window").unwrap() != &Value::Null);
        }
    }

    // A target that cannot fit anywhere on this facade cannot silently
    // degrade into a windowless bath or a superposed opening.
    let mut conflict = request();
    put(
        child(child(child(&mut conflict, "rules"), "spaces"), "bathroom"),
        "window_ratio",
        Value::Number(0.50),
    );
    let result = output(&conflict);
    assert_eq!(status(&result), "infeasible");
    assert!(arr(&result, "alternatives").is_empty());
    assert!(arr(&result, "reasons")
        .iter()
        .any(|reason| reason.as_str().unwrap().contains("ventana")));

    let mut missing = request();
    if let Value::Object(rules) = child(&mut missing, "rules") {
        rules.remove("bath_exhaust");
    }
    let result = output(&missing);
    assert_eq!(status(&result), "error");
    assert!(arr(&result, "alternatives").is_empty());
    let mut unknown = request();
    put(
        child(child(&mut unknown, "rules"), "bath_exhaust"),
        "certified_airflow",
        Value::Bool(true),
    );
    assert_eq!(status(&output(&unknown)), "error");
}

#[test]
fn impossible_or_malformed_furnishings_fail_closed_and_change_the_hash() {
    let baseline = output(&request());
    let mut huge_bed = request();
    put(
        child(child(&mut huge_bed, "rules"), "furnishings"),
        "bed",
        json::parse(r#"{"width":4.0,"depth":1.90}"#).unwrap(),
    );
    let result = output(&huge_bed);
    assert_eq!(status(&result), "infeasible");
    assert!(arr(&result, "alternatives").is_empty());
    assert!(arr(&result, "reasons").iter().any(|reason| {
        reason
            .as_str()
            .unwrap()
            .contains("equipamiento ilustrativo inviable")
    }));
    assert_ne!(baseline.get("input_hash"), result.get("input_hash"));

    let mut wide_aisle = request();
    put(
        child(child(&mut wide_aisle, "rules"), "furnishings"),
        "min_aisle",
        Value::Number(1.50),
    );
    let result = output(&wide_aisle);
    assert_eq!(status(&result), "infeasible");
    assert!(arr(&result, "alternatives").is_empty());

    let mut missing = request();
    if let Value::Object(rules) = child(&mut missing, "rules") {
        rules.remove("furnishings");
    }
    let result = output(&missing);
    assert_eq!(status(&result), "error");
    assert!(arr(&result, "alternatives").is_empty());
    let mut unknown = request();
    put(
        child(child(child(&mut unknown, "rules"), "furnishings"), "basin"),
        "accessible",
        Value::Bool(true),
    );
    assert_eq!(status(&output(&unknown)), "error");
}

#[test]
fn impossible_sweeps_windows_and_unknown_wall_rules_fail_closed() {
    let mut wide_door = request();
    put(
        child(child(&mut wide_door, "rules"), "doors"),
        "bathroom",
        Value::Number(2.0),
    );
    let out = output(&wide_door);
    assert_eq!(status(&out), "infeasible");
    assert!(arr(&out, "alternatives").is_empty());
    assert!(arr(&out, "reasons")
        .iter()
        .any(|r| r.as_str().unwrap().contains("Puerta")));

    let mut no_window = request();
    put(
        child(
            child(child(&mut no_window, "rules"), "spaces"),
            "living_dining",
        ),
        "window_ratio",
        Value::Number(0.5),
    );
    let out = output(&no_window);
    assert_eq!(status(&out), "infeasible");
    assert!(arr(&out, "alternatives").is_empty());

    let mut bad_wall = request();
    put(
        child(child(&mut bad_wall, "rules"), "walls"),
        "exterior",
        Value::Number(0.0),
    );
    assert_eq!(status(&output(&bad_wall)), "error");
    let mut bad_clearance = request();
    put(
        child(child(&mut bad_clearance, "rules"), "openings"),
        "swing_clearance",
        Value::Number(0.2),
    );
    assert_eq!(status(&output(&bad_clearance)), "error");
    let mut missing_wall = request();
    if let Value::Object(map) = child(&mut missing_wall, "rules") {
        map.remove("walls");
    }
    assert_eq!(status(&output(&missing_wall)), "error");
}

#[test]
fn bath_airflow_rules_fail_closed_and_hash_is_versioned() {
    let baseline = output(&request());
    assert_eq!(status(&baseline), "ok");
    let mut missing = request();
    if let Value::Object(rules) = child(&mut missing, "rules") {
        rules.remove("bath_airflow");
    }
    let result = output(&missing);
    assert_eq!(status(&result), "error");
    assert!(arr(&result, "alternatives").is_empty());
    for (key, value) in [
        ("target_ach", Value::Number(0.0)),
        ("fan_free_air_rating", Value::Number(-1.0)),
        ("door_undercut", Value::Number(0.0)),
        ("max_transfer_velocity", Value::String("1.6".into())),
        ("duct_height", Value::Number(0.0)),
        ("max_duct_velocity", Value::Number(f64::INFINITY)),
    ] {
        let mut input = request();
        put(
            child(child(&mut input, "rules"), "bath_airflow"),
            key,
            value,
        );
        assert_eq!(status(&output(&input)), "error", "campo {key}");
    }
    let mut unknown = request();
    put(
        child(child(&mut unknown, "rules"), "bath_airflow"),
        "certified_delivered_flow",
        Value::Bool(true),
    );
    assert_eq!(status(&output(&unknown)), "error");
    for (key, value) in [
        ("assumed_ceiling_height", 2.30), // 2.30 + 0.16 > 2.30
        ("duct_bottom", 2.50),            // 2.50 + 0.16 > 2.60
        ("min_headroom", 2.40),           // 2.30 < 2.40
    ] {
        let mut input = request();
        put(
            child(child(&mut input, "rules"), "bath_airflow"),
            key,
            Value::Number(value),
        );
        let result = output(&input);
        assert_eq!(status(&result), "error", "campo {key}");
        assert!(arr(&result, "alternatives").is_empty());
    }
    let mut changed = request();
    put(
        child(child(&mut changed, "rules"), "bath_airflow"),
        "target_ach",
        Value::Number(3.0),
    );
    let result = output(&changed);
    assert_eq!(status(&result), "ok");
    assert_ne!(baseline.get("input_hash"), result.get("input_hash"));
    for alt in arr(&result, "alternatives") {
        check_plan_geometry(alt, result.get("site").unwrap());
        for room in arr(alt, "rooms") {
            if room.get("type").unwrap().as_str() == Some("bathroom") {
                close(num(room.get("bath_airflow").unwrap(), "target_ach"), 3.0);
            }
        }
    }
}

#[test]
fn nominal_fan_transfer_and_duct_bounds_reject_all_impossible_candidates() {
    for (key, value, reason) in [
        ("fan_free_air_rating", 10.0, "aire libre"),
        ("door_undercut", 0.005, "holgura de puerta"),
        ("max_transfer_velocity", 0.20, "holgura de puerta"),
        ("max_duct_velocity", 0.20, "sección idealizada"),
    ] {
        let mut input = request();
        put(
            child(child(&mut input, "rules"), "bath_airflow"),
            key,
            Value::Number(value),
        );
        if key == "fan_free_air_rating" {
            put(
                child(child(&mut input, "rules"), "bath_pressure"),
                "fan_reference_flow_m3h",
                Value::Number(5.0),
            );
        }
        let result = output(&input);
        assert_eq!(status(&result), "infeasible", "campo {key}: {result:?}");
        assert!(arr(&result, "alternatives").is_empty());
        assert!(arr(&result, "reasons")
            .iter()
            .any(|message| message.as_str().unwrap().contains(reason)));
    }
}

#[test]
fn varied_airflow_scenarios_are_verified_or_marked_infeasible() {
    for index in 0..32_u32 {
        let mut input = request();
        let rules = child(child(&mut input, "rules"), "bath_airflow");
        put(rules, "target_ach", Value::Number(2.0 + (index % 6) as f64));
        put(
            rules,
            "fan_free_air_rating",
            Value::Number(35.0 + (index % 5) as f64 * 25.0),
        );
        put(
            rules,
            "door_undercut",
            Value::Number(0.012 + (index % 4) as f64 * 0.006),
        );
        put(
            rules,
            "duct_height",
            Value::Number(0.10 + (index % 4) as f64 * 0.02),
        );
        put(
            rules,
            "max_duct_velocity",
            Value::Number(0.5 + (index % 4) as f64 * 0.5),
        );
        // Keep the second reference point below every varied free-air rating.
        put(
            child(child(&mut input, "rules"), "bath_pressure"),
            "fan_reference_flow_m3h",
            Value::Number(10.0),
        );
        put(&mut input, "seed", Value::Number(index as f64));
        let result = output(&input);
        assert!(matches!(status(&result), "ok" | "infeasible"), "{result:?}");
        if status(&result) == "ok" {
            for alt in arr(&result, "alternatives") {
                check_plan_geometry(alt, result.get("site").unwrap());
            }
        } else {
            assert!(arr(&result, "alternatives").is_empty());
            assert!(!arr(&result, "reasons").is_empty());
        }
    }
}

#[test]
fn cli_never_exports_a_plan_when_nominal_airflow_bounds_fail() {
    use std::{fs, process::Command};
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    let rules_file =
        std::env::temp_dir().join(format!("arqgen-airflow-rules-{}.json", std::process::id()));
    let svg_file =
        std::env::temp_dir().join(format!("arqgen-airflow-invalid-{}.svg", std::process::id()));
    let _ = fs::remove_file(&svg_file);
    let mut rules = json::parse(include_str!("../../knowledge/generic-house.json")).unwrap();
    put(
        child(&mut rules, "bath_airflow"),
        "fan_free_air_rating",
        Value::Number(10.0),
    );
    put(
        child(&mut rules, "bath_pressure"),
        "fan_reference_flow_m3h",
        Value::Number(5.0),
    );
    fs::write(&rules_file, rules.stringify()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(root.join("examples/rectangular.json"))
        .arg("--rules")
        .arg(&rules_file)
        .arg("--svg")
        .arg(&svg_file)
        .output()
        .unwrap();
    let _ = fs::remove_file(&rules_file);
    assert!(!output.status.success());
    let parsed = json::parse(std::str::from_utf8(&output.stdout).unwrap()).unwrap();
    assert_eq!(status(&parsed), "infeasible");
    assert!(arr(&parsed, "alternatives").is_empty());
    assert!(
        !svg_file.exists(),
        "nunca se exporta SVG con caudal objetivo inviable"
    );
}

#[test]
fn pressure_rules_are_strict_and_change_the_input_hash() {
    let baseline = output(&request());
    assert_eq!(status(&baseline), "ok");
    let mut missing = request();
    if let Value::Object(rules) = child(&mut missing, "rules") {
        rules.remove("bath_pressure");
    }
    let result = output(&missing);
    assert_eq!(status(&result), "error");
    assert!(arr(&result, "alternatives").is_empty());
    for (key, value) in [
        ("fan_reference_pressure_pa", Value::Number(0.0)),
        ("fan_reference_flow_m3h", Value::Number(-1.0)),
        ("assumed_air_density_kg_m3", Value::Number(0.0)),
        ("assumed_darcy_factor", Value::Number(0.0)),
        ("assumed_bend_count", Value::Number(2.5)),
        ("assumed_bend_k", Value::Number(-0.1)),
        ("assumed_outlet_k", Value::String("2".into())),
        ("assumed_reserve_pa", Value::Number(f64::INFINITY)),
    ] {
        let mut input = request();
        put(
            child(child(&mut input, "rules"), "bath_pressure"),
            key,
            value,
        );
        let result = output(&input);
        assert_eq!(status(&result), "error", "campo {key}: {result:?}");
        assert!(arr(&result, "alternatives").is_empty());
    }
    for (key, value) in [
        ("fan_reference_flow_m3h", 120.0),
        ("fan_reference_flow_m3h", 150.0),
    ] {
        let mut input = request();
        put(
            child(child(&mut input, "rules"), "bath_pressure"),
            key,
            Value::Number(value),
        );
        let result = output(&input);
        assert_eq!(status(&result), "error");
        assert!(result
            .get("message")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("fan_free_air_rating"));
    }
    let mut unknown = request();
    put(
        child(child(&mut unknown, "rules"), "bath_pressure"),
        "verified_curve",
        Value::Bool(true),
    );
    assert_eq!(status(&output(&unknown)), "error");
    let mut changed = request();
    put(
        child(child(&mut changed, "rules"), "bath_pressure"),
        "assumed_reserve_pa",
        Value::Number(21.0),
    );
    let result = output(&changed);
    assert_eq!(status(&result), "ok");
    assert_ne!(baseline.get("input_hash"), result.get("input_hash"));
    for alt in arr(&result, "alternatives") {
        check_plan_geometry(alt, result.get("site").unwrap());
    }
}

#[test]
fn pressure_outside_reference_span_or_below_target_never_exports_alternatives() {
    let baseline = output(&request());
    for (key, value, pressure_point, reason) in [
        ("fan_reference_pressure_pa", 10.0, None, "no se extrapola"),
        ("assumed_reserve_pa", 100.0, None, "no se extrapola"),
        ("fan_reference_flow_m3h", 1.0, Some(25.0), "objetivo supera"),
    ] {
        let mut input = request();
        put(
            child(child(&mut input, "rules"), "bath_pressure"),
            key,
            Value::Number(value),
        );
        if let Some(p) = pressure_point {
            put(
                child(child(&mut input, "rules"), "bath_pressure"),
                "fan_reference_pressure_pa",
                Value::Number(p),
            );
        }
        let result = output(&input);
        assert_eq!(status(&result), "infeasible", "campo {key}: {result:?}");
        assert!(arr(&result, "alternatives").is_empty());
        assert_ne!(baseline.get("input_hash"), result.get("input_hash"));
        assert!(arr(&result, "reasons")
            .iter()
            .any(|r| r.as_str().unwrap().contains(reason)));
    }
}

#[test]
fn varied_pressure_scenarios_are_verified_or_reported_infeasible() {
    for index in 0..40_u32 {
        let mut input = request();
        let pressure = child(child(&mut input, "rules"), "bath_pressure");
        put(
            pressure,
            "fan_reference_pressure_pa",
            Value::Number(18.0 + (index % 8) as f64 * 8.0),
        );
        put(
            pressure,
            "fan_reference_flow_m3h",
            Value::Number(20.0 + (index % 6) as f64 * 12.0),
        );
        put(
            pressure,
            "assumed_darcy_factor",
            Value::Number(0.02 + (index % 5) as f64 * 0.02),
        );
        put(
            pressure,
            "assumed_bend_count",
            Value::Number((index % 5) as f64),
        );
        put(
            pressure,
            "assumed_reserve_pa",
            Value::Number(8.0 + (index % 6) as f64 * 6.0),
        );
        put(&mut input, "seed", Value::Number(index as f64));
        let result = output(&input);
        assert!(matches!(status(&result), "ok" | "infeasible"), "{result:?}");
        if status(&result) == "ok" {
            for alt in arr(&result, "alternatives") {
                check_plan_geometry(alt, result.get("site").unwrap());
            }
        } else {
            assert!(arr(&result, "alternatives").is_empty());
            assert!(!arr(&result, "reasons").is_empty());
        }
    }
}

#[test]
fn cli_never_writes_svg_when_pressure_screen_is_infeasible() {
    use std::{fs, process::Command};
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    let rules_file =
        std::env::temp_dir().join(format!("arqgen-pressure-rules-{}.json", std::process::id()));
    let svg_file = std::env::temp_dir().join(format!(
        "arqgen-pressure-invalid-{}.svg",
        std::process::id()
    ));
    let _ = fs::remove_file(&svg_file);
    let mut rules = json::parse(include_str!("../../knowledge/generic-house.json")).unwrap();
    put(
        child(&mut rules, "bath_pressure"),
        "fan_reference_pressure_pa",
        Value::Number(10.0),
    );
    fs::write(&rules_file, rules.stringify()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(root.join("examples/rectangular.json"))
        .arg("--rules")
        .arg(&rules_file)
        .arg("--svg")
        .arg(&svg_file)
        .output()
        .unwrap();
    let _ = fs::remove_file(&rules_file);
    assert!(!output.status.success());
    let parsed = json::parse(std::str::from_utf8(&output.stdout).unwrap()).unwrap();
    assert_eq!(status(&parsed), "infeasible");
    assert!(arr(&parsed, "alternatives").is_empty());
    assert!(!svg_file.exists());
}

#[test]
fn pressure_screen_filters_some_variants_before_selection_without_partial_plans() {
    let mut input = request();
    put(
        child(child(&mut input, "rules"), "bath_pressure"),
        "fan_reference_flow_m3h",
        Value::Number(20.0),
    );
    let first = generate_json(&input.stringify());
    assert_eq!(first, generate_json(&input.stringify()));
    let result = json::parse(&first).unwrap();
    check_rejections(&result);
    assert_eq!(status(&result), "ok");
    assert_eq!(num(&result, "generated"), 48.0);
    assert_eq!(num(&result, "rejected"), 12.0);
    assert!(arr(&result, "rejection_summary").iter().any(|r| r
        .get("reason")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("presión")));
    assert!(!arr(&result, "alternatives").is_empty());
    for alt in arr(&result, "alternatives") {
        check_plan_geometry(alt, result.get("site").unwrap());
    }
}

#[test]
fn self_reported_context_is_versioned_hashed_and_never_certifies_applicability() {
    let baseline_input = request();
    let baseline = output(&baseline_input);
    assert_eq!(status(&baseline), "ok");
    assert_eq!(
        baseline.get("request_schema").unwrap().as_str(),
        Some("arqgen-brief-v8")
    );
    assert_eq!(
        baseline.get("project_context"),
        baseline_input.get("project_context")
    );
    let applicability = baseline.get("applicability").unwrap();
    assert_eq!(status(applicability), "not_evaluated");
    assert_eq!(
        applicability.get("declared_scope").unwrap().as_str(),
        Some("undetermined")
    );
    assert_eq!(arr(applicability, "missing_context").len(), 4);
    assert_eq!(
        applicability.get("source_status").unwrap().as_str(),
        Some("no_verified_cuban_ruleset")
    );

    let mut reported = request();
    let context = child(&mut reported, "project_context");
    put(context, "jurisdiction", Value::String("CU".into()));
    put(
        context,
        "housing_class",
        Value::String("urban_social".into()),
    );
    put(context, "occupants", Value::Number(4.0));
    put(
        context,
        "accessibility_needs",
        Value::String("declared".into()),
    );
    let result = output(&reported);
    assert_eq!(status(&result), "ok");
    assert_eq!(
        result.get("project_context"),
        reported.get("project_context")
    );
    assert_ne!(result.get("input_hash"), baseline.get("input_hash"));
    assert_eq!(num(&result, "generated"), num(&baseline, "generated"));
    assert_eq!(num(&result, "rejected"), num(&baseline, "rejected"));
    let applicability = result.get("applicability").unwrap();
    assert_eq!(status(applicability), "not_evaluated");
    assert_eq!(
        applicability.get("declared_scope").unwrap().as_str(),
        Some("candidate_from_self_report_only")
    );
    assert!(arr(applicability, "missing_context").is_empty());
    for key in ["daylight_status", "ventilation_status"] {
        assert_eq!(
            applicability.get(key).unwrap().as_str(),
            Some("not_evaluated")
        );
    }
    assert_eq!(
        result.get("regulatory_status").unwrap().as_str(),
        Some("illustrative_not_certified")
    );
    assert_eq!(
        generate_json(&reported.stringify()),
        generate_json(&reported.stringify())
    );

    for (key, value) in [
        ("jurisdiction", Value::String("outside_CU".into())),
        ("housing_class", Value::String("other".into())),
        ("occupants", Value::Number(3.0)),
        ("accessibility_needs", Value::String("none_declared".into())),
    ] {
        let mut changed = baseline_input.clone();
        put(child(&mut changed, "project_context"), key, value);
        let changed_result = output(&changed);
        assert_eq!(status(&changed_result), "ok");
        assert_ne!(
            changed_result.get("input_hash"),
            baseline.get("input_hash"),
            "{key}"
        );
        assert_eq!(
            changed_result
                .get("applicability")
                .unwrap()
                .get("declared_scope")
                .unwrap()
                .as_str(),
            Some("undetermined")
        );
    }

    let mut blocked = reported.clone();
    put(
        child(child(&mut blocked, "rules"), "bath_pressure"),
        "fan_reference_pressure_pa",
        Value::Number(10.0),
    );
    let impossible = output(&blocked);
    assert_eq!(status(&impossible), "infeasible");
    assert_eq!(
        impossible.get("project_context"),
        reported.get("project_context")
    );
    assert_eq!(
        status(impossible.get("applicability").unwrap()),
        "not_evaluated"
    );
    assert!(arr(&impossible, "alternatives").is_empty());
}

#[test]
fn legacy_briefs_and_forged_or_malformed_context_fail_closed() {
    let mut old = request();
    if let Value::Object(map) = &mut old {
        map.remove("request_schema");
    }
    let error = output(&old);
    assert_eq!(status(&error), "error");
    assert!(error
        .get("message")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("request_schema"));
    assert!(error.get("applicability").is_none());

    for (key, invalid) in [
        ("jurisdiction", Value::String("Cu".into())),
        ("housing_class", Value::String("NC 598 verified".into())),
        ("occupants", Value::Number(0.0)),
        ("occupants", Value::Number(21.0)),
        ("occupants", Value::Number(1.5)),
        ("occupants", Value::String("4".into())),
        ("accessibility_needs", Value::String("exempt".into())),
        ("provenance", Value::String("official_verified".into())),
    ] {
        let mut input = request();
        put(child(&mut input, "project_context"), key, invalid);
        assert_eq!(status(&output(&input)), "error", "{key}");
    }
    let mut input = request();
    put(
        child(&mut input, "project_context"),
        "applicability",
        Value::String("complies".into()),
    );
    assert_eq!(status(&output(&input)), "error");
    let mut input = request();
    put(
        &mut input,
        "request_schema",
        Value::String("arqgen-brief-v1".into()),
    );
    assert_eq!(status(&output(&input)), "error");
    let mut input = request();
    if let Value::Object(map) = &mut input {
        map.remove("project_context");
    }
    assert_eq!(status(&output(&input)), "error");
}

#[test]
fn illustrative_bath_windows_have_facade_piers_and_never_prove_daylight() {
    let input = request();
    let output = output(&input);
    assert_eq!(status(&output), "ok");
    assert_eq!(
        output
            .get("applicability")
            .unwrap()
            .get("daylight_status")
            .unwrap()
            .as_str(),
        Some("not_evaluated")
    );
    assert_eq!(output.get("rule_version").unwrap().as_str(), Some("0.8.0"));
    assert_eq!(arr(&output, "alternatives").len(), 3);
    for candidate in arr(&output, "alternatives") {
        assert!(candidate
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("VENTANAS DIBUJADAS ≠ LUZ NATURAL COMPROBADA"));
        assert!(arr(candidate, "warnings")
            .iter()
            .any(|w| w.as_str().unwrap().contains("No es umbral NC 598")));
        for bath in arr(candidate, "rooms")
            .iter()
            .filter(|r| r.get("type").unwrap().as_str() == Some("bathroom"))
        {
            assert_eq!(
                bath.get("window_geometry_status").unwrap().as_str(),
                Some("exterior_opening_drawn_only")
            );
            assert_eq!(
                bath.get("daylight_status").unwrap().as_str(),
                Some("not_evaluated")
            );
            assert_eq!(
                bath.get("ventilation_status").unwrap().as_str(),
                Some("not_evaluated")
            );
            let window = bath.get("window").unwrap();
            let opening = window.get("opening").unwrap();
            let outlet = bath.get("bath_exhaust").unwrap().get("outlet").unwrap();
            let usable = bath.get("usable_rect").unwrap();
            assert!(
                num(window, "width") * num(window, "height") + 1e-7
                    >= num(usable, "width") * num(usable, "depth") * 0.05
            );
            assert!(num(opening, "width") > 0.0 && num(opening, "depth") > 0.0);
            assert!(
                num(window, "y") < num(outlet, "y"),
                "primer vano de fachada antes de la salida"
            );
            assert!(num(outlet, "y") - (num(opening, "y") + num(opening, "depth")) + 1e-7 >= 0.15);
            let shower = arr(bath, "furnishings")
                .iter()
                .find(|f| f.get("type").unwrap().as_str() == Some("shower"))
                .unwrap();
            let shower_footprint = shower.get("footprint").unwrap();
            let exterior_clear_face = if bath.get("side").unwrap().as_str() == Some("left") {
                num(usable, "x")
            } else {
                num(usable, "x") + num(usable, "width")
            };
            let distance = if bath.get("side").unwrap().as_str() == Some("left") {
                num(shower_footprint, "x") - exterior_clear_face
            } else {
                exterior_clear_face - num(shower_footprint, "x") - num(shower_footprint, "width")
            };
            assert!(
                distance + 1e-7 >= 0.20,
                "franja de ventana 2D libre de ducha"
            );
        }
    }
}

#[test]
fn impossible_window_target_is_not_hidden_by_a_windowless_fallback() {
    let mut input = request();
    put(
        child(child(child(&mut input, "rules"), "spaces"), "bathroom"),
        "window_ratio",
        Value::Number(0.5),
    );
    let result = output(&input);
    assert_eq!(status(&result), "infeasible");
    assert!(arr(&result, "alternatives").is_empty());
    assert!(arr(&result, "reasons")
        .iter()
        .any(|why| why.as_str().unwrap().contains("ventana")));
    assert_eq!(
        result
            .get("applicability")
            .unwrap()
            .get("daylight_status")
            .unwrap()
            .as_str(),
        Some("not_evaluated")
    );
    let mut no_window = request();
    put(
        child(child(child(&mut no_window, "rules"), "spaces"), "bathroom"),
        "window_ratio",
        Value::Number(0.0),
    );
    let legacy_mode = output(&no_window);
    assert_eq!(status(&legacy_mode), "ok");
    assert_ne!(
        legacy_mode.get("input_hash"),
        output(&request()).get("input_hash")
    );
    for candidate in arr(&legacy_mode, "alternatives") {
        for bath in arr(candidate, "rooms")
            .iter()
            .filter(|r| r.get("type").unwrap().as_str() == Some("bathroom"))
        {
            assert_eq!(bath.get("window").unwrap(), &Value::Null);
            assert_eq!(
                bath.get("window_geometry_status").unwrap().as_str(),
                Some("not_drawn")
            );
            assert_eq!(
                bath.get("daylight_status").unwrap().as_str(),
                Some("not_evaluated")
            );
        }
    }
}

fn reserve_site(input: &mut Value, x: f64, y: f64, width: f64, depth: f64) {
    let area = json::parse(&format!(
        "{{\"x\":{x},\"y\":{y},\"width\":{width},\"depth\":{depth}}}"
    ))
    .unwrap();
    put(
        child(input, "site"),
        "reserved_areas",
        Value::Array(vec![area]),
    );
}

fn add_reserve(input: &mut Value, x: f64, y: f64, width: f64, depth: f64) {
    let area = json::parse(&format!(
        "{{\"x\":{x},\"y\":{y},\"width\":{width},\"depth\":{depth}}}"
    ))
    .unwrap();
    if let Value::Array(areas) = child(child(input, "site"), "reserved_areas") {
        areas.push(area);
    } else {
        panic!("lista de reservas requerida");
    }
}

fn cut_rear_corner(input: &mut Value, side: &str, width: f64, depth: f64) {
    let shape = json::parse(&format!("{{\"provenance\":\"user_sketch_unverified\",\"shape\":\"rear_corner_notch\",\"rear_notches\":[{{\"side\":\"{side}\",\"width\":{width},\"depth\":{depth}}}]}}"))
        .unwrap();
    put(child(input, "site"), "plot_outline", shape);
}
fn cut_opposite_rear_corner(input: &mut Value, side: &str, width: f64, depth: f64) {
    let notch = json::parse(&format!(
        "{{\"side\":\"{side}\",\"width\":{width},\"depth\":{depth}}}"
    ))
    .unwrap();
    let plot = child(child(input, "site"), "plot_outline");
    put(
        plot,
        "shape",
        Value::String("rear_both_corners_notched".into()),
    );
    if let Value::Array(notches) = child(plot, "rear_notches") {
        notches.push(notch);
    } else {
        panic!("lista de recortes requerida");
    }
}

#[test]
fn voluntary_site_reservation_filters_gross_footprints_without_claiming_legal_validity() {
    let baseline = output(&request());
    let mut input = request();
    reserve_site(&mut input, 4.5, 12.0, 2.0, 2.0);
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    assert_ne!(result.get("input_hash"), baseline.get("input_hash"));
    assert_eq!(num(&result, "generated"), 48.0);
    assert!(num(&result, "rejected") > 0.0 && num(&result, "rejected") < 48.0);
    assert_eq!(arr(&result, "alternatives").len(), 3);
    assert!(arr(&result, "rejection_summary").iter().any(|row| row
        .get("reason")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("reserva voluntaria")));
    let provenance = result.get("site_reservations").unwrap();
    assert_eq!(
        provenance.get("provenance").unwrap().as_str(),
        Some("user_sketch_unverified")
    );
    assert_eq!(
        provenance.get("geometry_status").unwrap().as_str(),
        Some("footprint_exclusion_2d_only")
    );
    let reserve = Box2::from(&arr(provenance, "areas")[0]);
    let site = result.get("site").unwrap();
    let buildable = Box2::from(site.get("buildable").unwrap());
    close(
        num(site, "unreserved_buildable_area"),
        buildable.area() - buildable.intersection(reserve),
    );
    close(num(site, "max_footprint"), num(site, "plot_area") * 0.55);
    for alt in arr(&result, "alternatives") {
        assert!(reserve.intersection(Box2::from(alt.get("corridor").unwrap())) < 1e-6);
        for room in arr(alt, "rooms") {
            assert!(
                reserve.intersection(Box2::from(room.get("rect").unwrap())) < 1e-6,
                "huella bruta no invade zona declarada"
            );
        }
        assert!(alt
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("class=\"site-reserved-area\""));
        assert!(arr(alt, "warnings").iter().any(|v| v
            .as_str()
            .unwrap()
            .contains("titularidad y linderos NO están verificados")));
        assert!(arr(alt, "decisions").iter().any(|v| v
            .get("rule")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("site.reserved_areas@user_sketch_unverified")));
    }
    let output_again = output(&input);
    assert_eq!(output_again, result);
    assert_eq!(
        status(result.get("applicability").unwrap()),
        "not_evaluated"
    );
    // A declaration wholly in the setback is still recorded, but does not
    // consume buildable area and cannot silently change the demo FAR/coverage.
    let mut outside = request();
    reserve_site(&mut outside, 0.0, 0.0, 1.0, 1.0);
    let non_blocking = output(&outside);
    assert_eq!(status(&non_blocking), "ok");
    assert_eq!(num(&non_blocking, "rejected"), 0.0);
    let available = non_blocking.get("site").unwrap();
    close(
        num(available, "unreserved_buildable_area"),
        Box2::from(available.get("buildable").unwrap()).area(),
    );
}

#[test]
fn two_disjoint_voluntary_zones_are_both_exported_and_subtracted_without_double_counting() {
    let mut input = request();
    reserve_site(&mut input, 4.5, 12.0, 2.0, 2.0);
    add_reserve(&mut input, 14.0, 16.0, 1.0, 2.0);
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    let site = result.get("site").unwrap();
    let buildable = Box2::from(site.get("buildable").unwrap());
    let zones: Vec<_> = arr(result.get("site_reservations").unwrap(), "areas")
        .iter()
        .map(Box2::from)
        .collect();
    assert_eq!(zones.len(), 2);
    assert_eq!(zones[0].intersection(zones[1]), 0.0);
    close(
        num(site, "unreserved_buildable_area"),
        buildable.area()
            - zones
                .iter()
                .map(|z| buildable.intersection(*z))
                .sum::<f64>(),
    );
    for alt in arr(&result, "alternatives") {
        for zone in &zones {
            assert_eq!(
                zone.intersection(Box2::from(alt.get("corridor").unwrap())),
                0.0
            );
            for room in arr(alt, "rooms") {
                assert_eq!(
                    zone.intersection(Box2::from(room.get("rect").unwrap())),
                    0.0
                );
            }
        }
        let svg = alt.get("svg").unwrap().as_str().unwrap();
        assert_eq!(svg.matches("class=\"site-reserved-area\"").count(), 2);
        assert_eq!(
            arr(alt, "decisions")
                .iter()
                .filter(|v| v.get("rule").unwrap().as_str()
                    == Some("site.reserved_areas@user_sketch_unverified"))
                .count(),
            2
        );
    }
    let mut swapped = input.clone();
    if let Value::Array(areas) = child(child(&mut swapped, "site"), "reserved_areas") {
        areas.reverse();
    }
    let reversed = output(&swapped);
    assert_eq!(status(&reversed), "ok");
    close(
        num(reversed.get("site").unwrap(), "unreserved_buildable_area"),
        num(site, "unreserved_buildable_area"),
    );
    assert_ne!(result.get("input_hash"), reversed.get("input_hash"));
}

#[test]
fn a_second_zone_also_blocks_the_selected_front_trace_and_cannot_create_a_partial_plan() {
    let mut input = request();
    reserve_site(&mut input, 0.0, 0.0, 1.0, 1.0);
    add_reserve(&mut input, 8.5, 0.5, 1.0, 0.5);
    let blocked = output(&input);
    assert_eq!(status(&blocked), "infeasible");
    assert_eq!(num(&blocked, "generated"), 48.0);
    assert!(arr(&blocked, "alternatives").is_empty());
    assert!(arr(&blocked, "rejection_summary").iter().any(|v| v
        .get("reason")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("franja frontal recta")));
    set_declared_detour(&mut input, 11.5, 1.6, 3.0);
    let detour = output(&input);
    assert_eq!(status(&detour), "ok");
    assert_eq!(num(&detour, "rejected"), 0.0);
    for alt in arr(&detour, "alternatives") {
        assert_eq!(arr(alt.get("front_approach").unwrap(), "segments").len(), 3);
        let zones = arr(detour.get("site_reservations").unwrap(), "areas");
        for band in arr(alt.get("front_approach").unwrap(), "segments") {
            let band = Box2::from(band);
            for zone in zones {
                assert_eq!(band.intersection(Box2::from(zone)), 0.0);
            }
        }
    }
    let mut gross_block = request();
    reserve_site(&mut gross_block, 0.0, 0.0, 1.0, 1.0);
    add_reserve(&mut gross_block, 8.0, 3.0, 2.0, 3.0);
    let rejected = output(&gross_block);
    assert_eq!(status(&rejected), "infeasible");
    assert_eq!(num(&rejected, "rejected"), 48.0);
    assert!(arr(&rejected, "alternatives").is_empty());
}

#[test]
fn overlapping_or_outside_zone_is_invalid_even_for_a_tiny_positive_sliver() {
    let mut input = request();
    reserve_site(&mut input, 4.5, 12.0, 2.0, 2.0);
    add_reserve(&mut input, 6.5, 12.0, 1.0, 1.0); // exact contact
    assert_ne!(status(&output(&input)), "error");
    let mut overlap = input.clone();
    if let Value::Array(areas) = child(child(&mut overlap, "site"), "reserved_areas") {
        put(&mut areas[1], "x", Value::Number(6.5 - 1e-8));
    }
    let error = output(&overlap);
    assert_eq!(status(&error), "error");
    assert!(error.get("site_reservations").is_none());
    assert!(arr(&error, "alternatives").is_empty());
    let mut outside = input.clone();
    if let Value::Array(areas) = child(child(&mut outside, "site"), "reserved_areas") {
        put(&mut areas[1], "x", Value::Number(17.0 + 1e-8));
    }
    assert_eq!(status(&output(&outside)), "error");
    let mut too_many = input.clone();
    add_reserve(&mut too_many, 0.0, 0.0, 1.0, 1.0);
    assert_eq!(status(&output(&too_many)), "error");
    // The cut-out remains OUTSIDE the croquis, including with two zones.
    cut_rear_corner(&mut input, "left", 4.0, 10.0);
    let l = output(&input);
    assert_ne!(status(&l), "error");
    let mut cut = input;
    if let Value::Array(areas) = child(child(&mut cut, "site"), "reserved_areas") {
        put(&mut areas[1], "x", Value::Number(3.99999999));
    }
    assert_eq!(status(&output(&cut)), "error");
}

#[test]
fn blocked_reservation_fails_closed_without_partial_plans_or_fabricated_sources() {
    let mut blocked = request();
    reserve_site(&mut blocked, 8.0, 3.0, 2.0, 3.0); // cuts the fixed front corridor
    let result = output(&blocked);
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "generated"), 48.0);
    assert!(arr(&result, "alternatives").is_empty());
    assert_eq!(num(&result, "rejected"), 48.0);
    assert!(arr(&result, "reasons")
        .iter()
        .any(|v| v.as_str().unwrap().contains("reserva voluntaria")));
    assert_eq!(
        arr(result.get("site_reservations").unwrap(), "areas").len(),
        1
    );
    assert_eq!(
        status(result.get("applicability").unwrap()),
        "not_evaluated"
    );

    let mut full = request();
    reserve_site(&mut full, 2.0, 3.0, 14.0, 17.0);
    let result = output(&full);
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "generated"), 0.0);
    assert!(arr(&result, "reasons")
        .iter()
        .any(|v| v.as_str().unwrap().contains("croquis reservado")));

    let brief =
        std::env::temp_dir().join(format!("arqgen-reserved-brief-{}.json", std::process::id()));
    let rules =
        std::env::temp_dir().join(format!("arqgen-reserved-rules-{}.json", std::process::id()));
    let svg = std::env::temp_dir().join(format!("arqgen-reserved-fail-{}.svg", std::process::id()));
    let _ = std::fs::remove_file(&svg);
    let mut cli_input = blocked.clone();
    let cli_rules = if let Value::Object(root) = &mut cli_input {
        root.remove("rules").unwrap()
    } else {
        unreachable!()
    };
    std::fs::write(&brief, cli_input.stringify()).unwrap();
    std::fs::write(&rules, cli_rules.stringify()).unwrap();
    let cli = std::process::Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(&brief)
        .arg("--rules")
        .arg(&rules)
        .arg("--svg")
        .arg(&svg)
        .output()
        .unwrap();
    assert!(!cli.status.success());
    let echoed = json::parse(std::str::from_utf8(&cli.stdout).unwrap()).unwrap();
    assert_eq!(status(&echoed), "infeasible");
    assert!(!svg.exists(), "CLI no puede exportar un plano inválido");
    std::fs::remove_file(brief).unwrap();
    std::fs::remove_file(rules).unwrap();
}

#[test]
fn reservation_requires_valid_unverified_plot_coordinates_and_new_schema() {
    let baseline = request();
    let mut old = baseline.clone();
    put(
        &mut old,
        "request_schema",
        Value::String("arqgen-brief-v2".into()),
    );
    assert_eq!(status(&output(&old)), "error");
    let mut missing = baseline.clone();
    if let Value::Object(site) = child(&mut missing, "site") {
        site.remove("reserved_areas");
    }
    assert_eq!(status(&output(&missing)), "error");
    let mut missing = baseline.clone();
    if let Value::Object(site) = child(&mut missing, "site") {
        site.remove("reservation_provenance");
    }
    assert_eq!(status(&output(&missing)), "error");
    for fake in ["verified_legal", "official_cadastral_source", "unknown"] {
        let mut forged = baseline.clone();
        put(
            child(&mut forged, "site"),
            "reservation_provenance",
            Value::String(fake.into()),
        );
        assert_eq!(status(&output(&forged)), "error");
    }
    let mut many = baseline.clone();
    reserve_site(&mut many, 0.0, 0.0, 1.0, 1.0);
    if let Value::Array(areas) = child(child(&mut many, "site"), "reserved_areas") {
        let duplicate = areas[0].clone();
        areas.push(duplicate);
    }
    assert_eq!(status(&output(&many)), "error");
    for (x, y, w, h) in [
        (17.9, 3.0, 1.0, 1.0),
        (-0.5, 0.0, 1.0, 1.0),
        (1.0, 1.0, 0.0, 1.0),
        (2.0, 21.8, 2.0, 1.0),
        (1.0, 1.0, 0.05, 1.0),
    ] {
        let mut bad = baseline.clone();
        reserve_site(&mut bad, x, y, w, h);
        let rejected = output(&bad);
        assert_eq!(status(&rejected), "error", "{x},{y} {w}×{h}");
        assert!(arr(&rejected, "alternatives").is_empty());
        assert!(rejected.get("site_reservations").is_none());
    }
    let mut extra = baseline.clone();
    reserve_site(&mut extra, 1.0, 2.0, 2.0, 2.0);
    if let Value::Array(areas) = child(child(&mut extra, "site"), "reserved_areas") {
        put(
            &mut areas[0],
            "legal_status",
            Value::String("complies".into()),
        );
    }
    assert_eq!(status(&output(&extra)), "error");
}

#[test]
fn rear_corner_plot_sketch_changes_area_far_and_filters_only_outside_gross_cells() {
    let ordinary = output(&request());
    let ordinary_site = ordinary.get("site").unwrap();
    close(num(ordinary_site, "plot_area"), 396.0);
    let plain = ordinary.get("site_plot").unwrap();
    assert_eq!(plain.get("shape").unwrap().as_str(), Some("rectangle"));
    assert_eq!(arr(plain, "vertices").len(), 4);
    assert!(arr(plain, "rear_notches").is_empty());

    for side in ["left", "right"] {
        let mut input = request();
        cut_rear_corner(&mut input, side, 4.0, 10.0);
        let result = output(&input);
        assert_eq!(status(&result), "ok", "{side}");
        assert_ne!(result.get("input_hash"), ordinary.get("input_hash"));
        assert_eq!(num(&result, "generated"), 48.0);
        assert_eq!(num(&result, "rejected"), 9.0);
        assert_eq!(arr(&result, "alternatives").len(), 3);
        assert!(arr(&result, "rejection_summary").iter().any(|row| row
            .get("reason")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("recorte posterior")));
        let plot = result.get("site_plot").unwrap();
        assert_eq!(
            plot.get("shape").unwrap().as_str(),
            Some("rear_corner_notch")
        );
        assert_eq!(
            plot.get("provenance").unwrap().as_str(),
            Some("user_sketch_unverified")
        );
        assert_eq!(
            plot.get("geometry_status").unwrap().as_str(),
            Some("orthogonal_plot_sketch_2d_only")
        );
        assert_eq!(arr(plot, "vertices").len(), 6);
        let notch_meta = &arr(plot, "rear_notches")[0];
        assert_eq!(notch_meta.get("side").unwrap().as_str(), Some(side));
        close(num(notch_meta, "width"), 4.0);
        close(num(notch_meta, "depth"), 10.0);
        if side == "left" {
            close(num(&arr(plot, "vertices")[3], "x"), 4.0);
            close(num(&arr(plot, "vertices")[4], "y"), 12.0);
        } else {
            close(num(&arr(plot, "vertices")[2], "y"), 12.0);
            close(num(&arr(plot, "vertices")[3], "x"), 14.0);
        }
        let site = result.get("site").unwrap();
        close(num(site, "plot_area"), 356.0);
        close(num(site, "unreserved_buildable_area"), 222.0); // 238 - 2 x 8
        close(
            num(site, "max_built_area"),
            356.0 * num(input.get("rules").unwrap(), "max_far"),
        );
        assert!(num(site, "max_built_area") < num(ordinary_site, "max_built_area"));
        let notch = if side == "left" {
            Box2 {
                x: 0.0,
                y: 12.0,
                w: 4.0,
                h: 10.0,
            }
        } else {
            Box2 {
                x: 14.0,
                y: 12.0,
                w: 4.0,
                h: 10.0,
            }
        };
        for alt in arr(&result, "alternatives") {
            assert!(notch.intersection(Box2::from(alt.get("corridor").unwrap())) < 1e-6);
            for room in arr(alt, "rooms") {
                assert!(notch.intersection(Box2::from(room.get("rect").unwrap())) < 1e-6);
            }
            for band in arr(alt, "wall_zones") {
                assert!(notch.intersection(Box2::from(band)) < 1e-6);
            }
            let svg = alt.get("svg").unwrap().as_str().unwrap();
            assert!(svg.contains("class=\"site-plot-outline\""));
            assert!(svg.contains("clip-path=\"url(#site-plot-clip)\""));
            assert!(svg.contains("FUERA DEL CROQUIS"));
            assert!(svg.contains("PARCELA EN L NO VERIFICADA"));
            assert!(arr(alt, "decisions")
                .iter()
                .any(|row| row.get("rule").unwrap().as_str()
                    == Some("site.plot_outline@user_sketch_unverified")));
            assert!(arr(alt, "warnings").iter().any(|row| row
                .as_str()
                .unwrap()
                .contains("Retiros demo solo desde la caja")));
        }
        assert_eq!(output(&input), result);
        assert_eq!(
            result
                .get("applicability")
                .unwrap()
                .get("status")
                .unwrap()
                .as_str(),
            Some("not_evaluated")
        );
    }
}

#[test]
fn two_opposite_rear_cuts_recompute_polygon_area_inset_far_and_exclude_gross_cells() {
    let ordinary = output(&request());
    let mut input = request();
    cut_rear_corner(&mut input, "left", 4.0, 10.0);
    cut_opposite_rear_corner(&mut input, "right", 3.0, 10.0);
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    assert_ne!(result.get("input_hash"), ordinary.get("input_hash"));
    let site = result.get("site").unwrap();
    close(num(site, "plot_area"), 326.0); // 18*22 - 4*10 - 3*10
    close(num(site, "unreserved_buildable_area"), 214.0); // 238 - 2*8 - 1*8
    close(
        num(site, "max_built_area"),
        326.0 * num(input.get("rules").unwrap(), "max_far"),
    );
    let plot = result.get("site_plot").unwrap();
    assert_eq!(
        plot.get("shape").unwrap().as_str(),
        Some("rear_both_corners_notched")
    );
    assert_eq!(arr(plot, "rear_notches").len(), 2);
    assert_eq!(
        arr(plot, "rear_notches"),
        arr(
            child(&mut input, "site").get("plot_outline").unwrap(),
            "rear_notches"
        )
    );
    let vertices: Vec<_> = arr(plot, "vertices")
        .iter()
        .map(|point| (num(point, "x"), num(point, "y")))
        .collect();
    assert_eq!(
        vertices,
        [
            (0.0, 0.0),
            (18.0, 0.0),
            (18.0, 12.0),
            (15.0, 12.0),
            (15.0, 22.0),
            (4.0, 22.0),
            (4.0, 12.0),
            (0.0, 12.0)
        ]
    );
    let polygon_area = vertices
        .iter()
        .enumerate()
        .map(|(i, &(x, y))| {
            let (nx, ny) = vertices[(i + 1) % vertices.len()];
            x * ny - nx * y
        })
        .sum::<f64>()
        / 2.0;
    close(polygon_area, 326.0);
    let cuts = [
        Box2 {
            x: 0.0,
            y: 12.0,
            w: 4.0,
            h: 10.0,
        },
        Box2 {
            x: 15.0,
            y: 12.0,
            w: 3.0,
            h: 10.0,
        },
    ];
    for alt in arr(&result, "alternatives") {
        for cut in cuts {
            assert_eq!(
                cut.intersection(Box2::from(alt.get("corridor").unwrap())),
                0.0
            );
            for room in arr(alt, "rooms") {
                assert_eq!(cut.intersection(Box2::from(room.get("rect").unwrap())), 0.0);
            }
            for wall in arr(alt, "wall_zones") {
                assert_eq!(cut.intersection(Box2::from(wall)), 0.0);
            }
        }
        let svg = alt.get("svg").unwrap().as_str().unwrap();
        assert_eq!(svg.matches("FUERA DEL CROQUIS").count(), 2);
        assert!(svg.contains("DOS RECORTES"));
        assert_eq!(
            arr(alt, "decisions")
                .iter()
                .filter(|row| row.get("rule").unwrap().as_str()
                    == Some("site.plot_outline@user_sketch_unverified"))
                .count(),
            2
        );
        assert!(arr(alt, "warnings")
            .iter()
            .any(|note| note.as_str().unwrap().contains("dos recortes posteriores")));
    }
    let mut reordered = request();
    cut_rear_corner(&mut reordered, "right", 3.0, 10.0);
    cut_opposite_rear_corner(&mut reordered, "left", 4.0, 10.0);
    let reverse = output(&reordered);
    assert_eq!(status(&reverse), "ok");
    assert_ne!(reverse.get("input_hash"), result.get("input_hash"));
    assert_eq!(
        arr(reverse.get("site_plot").unwrap(), "vertices"),
        arr(plot, "vertices")
    );
    close(num(reverse.get("site").unwrap(), "plot_area"), 326.0);
}

#[test]
fn second_rear_cut_blocks_or_touches_voluntary_zone_and_front_band_without_partial_plan() {
    let mut input = request();
    cut_rear_corner(&mut input, "left", 4.0, 10.0);
    cut_opposite_rear_corner(&mut input, "right", 3.0, 10.0);
    reserve_site(&mut input, 14.0, 16.0, 1.0, 2.0); // exact contact at x=15
    assert_ne!(status(&output(&input)), "error");
    if let Value::Array(areas) = child(child(&mut input, "site"), "reserved_areas") {
        put(&mut areas[0], "width", Value::Number(1.000_000_01));
    }
    let invalid = output(&input);
    assert_eq!(status(&invalid), "error");
    assert!(invalid.get("site_plot").is_none());
    let mut blocked = request();
    cut_rear_corner(&mut blocked, "left", 1.0, 1.0);
    cut_opposite_rear_corner(&mut blocked, "right", 10.2, 21.0);
    let result = output(&blocked);
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "generated"), 48.0);
    assert_eq!(num(&result, "rejected"), 48.0);
    assert!(arr(&result, "alternatives").is_empty());
    assert!(arr(&result, "rejection_summary").iter().any(|row| row
        .get("reason")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("franja frontal recta")));
    assert_eq!(arr(result.get("site_plot").unwrap(), "vertices").len(), 8);
    assert!(result.get("site").is_none());
}

#[test]
fn both_rear_cuts_and_both_voluntary_zones_are_disjoint_and_accounted_once() {
    let mut input = request();
    cut_rear_corner(&mut input, "left", 4.0, 10.0);
    cut_opposite_rear_corner(&mut input, "right", 3.0, 10.0);
    reserve_site(&mut input, 4.5, 12.0, 2.0, 2.0);
    add_reserve(&mut input, 14.0, 16.0, 1.0, 2.0); // exact contact with right cut
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    close(num(result.get("site").unwrap(), "plot_area"), 326.0);
    close(
        num(result.get("site").unwrap(), "unreserved_buildable_area"),
        208.0,
    );
    assert_eq!(
        arr(result.get("site_plot").unwrap(), "rear_notches").len(),
        2
    );
    assert_eq!(
        arr(result.get("site_reservations").unwrap(), "areas").len(),
        2
    );
    assert_eq!(num(&result, "generated"), 48.0);
    assert_eq!(num(&result, "rejected"), 40.0);
    assert_eq!(arr(&result, "alternatives").len(), 3);
    let zones = [
        Box2 {
            x: 4.5,
            y: 12.0,
            w: 2.0,
            h: 2.0,
        },
        Box2 {
            x: 14.0,
            y: 16.0,
            w: 1.0,
            h: 2.0,
        },
    ];
    for alt in arr(&result, "alternatives") {
        for zone in zones {
            assert_eq!(
                zone.intersection(Box2::from(alt.get("corridor").unwrap())),
                0.0
            );
            for room in arr(alt, "rooms") {
                assert_eq!(
                    zone.intersection(Box2::from(room.get("rect").unwrap())),
                    0.0
                );
            }
            for band in arr(alt.get("front_approach").unwrap(), "segments") {
                assert_eq!(zone.intersection(Box2::from(band)), 0.0);
            }
        }
        assert_eq!(
            arr(alt, "decisions")
                .iter()
                .filter(|decision| decision.get("rule").unwrap().as_str()
                    == Some("site.reserved_areas@user_sketch_unverified"))
                .count(),
            2
        );
    }
}

#[test]
fn posterior_cutout_and_voluntary_reservation_subtract_disjoint_intersections() {
    let mut input = request();
    cut_rear_corner(&mut input, "left", 4.0, 10.0);
    reserve_site(&mut input, 4.5, 12.0, 2.0, 2.0);
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    close(num(result.get("site").unwrap(), "plot_area"), 356.0);
    close(
        num(result.get("site").unwrap(), "unreserved_buildable_area"),
        218.0,
    );
    assert_eq!(
        arr(result.get("site_reservations").unwrap(), "areas").len(),
        1
    );
    assert!(arr(&result, "alternatives").iter().all(|alt| {
        let decisions = arr(alt, "decisions");
        decisions.iter().any(|row| {
            row.get("rule").unwrap().as_str() == Some("site.plot_outline@user_sketch_unverified")
        }) && decisions.iter().any(|row| {
            row.get("rule").unwrap().as_str() == Some("site.reserved_areas@user_sketch_unverified")
        })
    }));
    let mut touching = request();
    cut_rear_corner(&mut touching, "left", 4.0, 10.0);
    reserve_site(&mut touching, 4.0, 18.0, 2.0, 2.0); // shared border, no intersection
    assert_ne!(status(&output(&touching)), "error");
    let mut overlapping = request();
    cut_rear_corner(&mut overlapping, "left", 4.0, 10.0);
    reserve_site(&mut overlapping, 3.999_999_99, 18.0, 2.0, 2.0); // even sub-EPS overlap is rejected
    let invalid = output(&overlapping);
    assert_eq!(status(&invalid), "error");
    assert!(invalid.get("site_plot").is_none());
}

#[test]
fn cutout_fails_closed_when_candidates_or_inset_are_consumed() {
    let mut candidates_blocked = request();
    cut_rear_corner(&mut candidates_blocked, "right", 7.0, 12.0);
    let result = output(&candidates_blocked);
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "generated"), 48.0);
    assert_eq!(num(&result, "rejected"), 48.0);
    assert!(arr(&result, "alternatives").is_empty());
    assert_eq!(arr(result.get("site_plot").unwrap(), "vertices").len(), 6);
    assert!(arr(&result, "reasons")
        .iter()
        .any(|r| r.as_str().unwrap().contains("recorte posterior")));
    assert_eq!(
        result
            .get("applicability")
            .unwrap()
            .get("status")
            .unwrap()
            .as_str(),
        Some("not_evaluated")
    );

    let mut inset_consumed = request();
    cut_rear_corner(&mut inset_consumed, "left", 17.0, 21.0);
    let result = output(&inset_consumed);
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "generated"), 0.0);
    assert!(arr(&result, "rejection_summary").is_empty());
    assert!(arr(&result, "reasons")
        .iter()
        .any(|r| r.as_str().unwrap().contains("recorte posterior")));
}

#[test]
fn bounded_two_cut_matrix_never_returns_a_gross_cell_or_trace_outside_the_sketch() {
    for left_width in [1.0, 4.0, 7.0] {
        for right_width in [1.0, 3.0, 7.0] {
            for (left_depth, right_depth) in [(1.0, 1.0), (10.0, 14.0), (21.0, 10.0)] {
                let mut input = request();
                cut_rear_corner(&mut input, "left", left_width, left_depth);
                cut_opposite_rear_corner(&mut input, "right", right_width, right_depth);
                let result = output(&input);
                assert_ne!(status(&result), "error");
                assert_eq!(arr(result.get("site_plot").unwrap(), "vertices").len(), 8);
                let cuts = [
                    Box2 {
                        x: 0.0,
                        y: 22.0 - left_depth,
                        w: left_width,
                        h: left_depth,
                    },
                    Box2 {
                        x: 18.0 - right_width,
                        y: 22.0 - right_depth,
                        w: right_width,
                        h: right_depth,
                    },
                ];
                if status(&result) == "ok" {
                    let site = result.get("site").unwrap();
                    close(
                        num(site, "plot_area"),
                        396.0 - left_width * left_depth - right_width * right_depth,
                    );
                    let inset = Box2 {
                        x: 2.0,
                        y: 3.0,
                        w: 14.0,
                        h: 17.0,
                    };
                    close(
                        num(site, "unreserved_buildable_area"),
                        inset.area() - cuts.iter().map(|cut| cut.intersection(inset)).sum::<f64>(),
                    );
                    for alt in arr(&result, "alternatives") {
                        for cut in cuts {
                            for gross in std::iter::once(alt.get("corridor").unwrap()).chain(
                                arr(alt, "rooms")
                                    .iter()
                                    .map(|room| room.get("rect").unwrap()),
                            ) {
                                assert_eq!(cut.intersection(Box2::from(gross)), 0.0);
                            }
                            for band in arr(alt.get("front_approach").unwrap(), "segments") {
                                assert_eq!(cut.intersection(Box2::from(band)), 0.0);
                            }
                        }
                    }
                } else {
                    assert_eq!(status(&result), "infeasible");
                    assert!(arr(&result, "alternatives").is_empty());
                    assert!(result.get("site").is_none());
                }
            }
        }
    }
}

#[test]
fn plot_outline_rejects_unverified_or_ambiguous_shapes_and_legacy_requests() {
    let baseline = request();
    for schema in [
        "arqgen-brief-v1",
        "arqgen-brief-v2",
        "arqgen-brief-v3",
        "arqgen-brief-v4",
        "arqgen-brief-v5",
        "arqgen-brief-v6",
        "arqgen-brief-v7",
    ] {
        let mut old = baseline.clone();
        put(&mut old, "request_schema", Value::String(schema.into()));
        assert_eq!(status(&output(&old)), "error", "{schema}");
    }
    let mut missing = baseline.clone();
    if let Value::Object(site) = child(&mut missing, "site") {
        site.remove("plot_outline");
    }
    assert_eq!(status(&output(&missing)), "error");
    let mut forged = baseline.clone();
    put(
        child(child(&mut forged, "site"), "plot_outline"),
        "provenance",
        Value::String("official_survey".into()),
    );
    assert_eq!(status(&output(&forged)), "error");
    for bad in [
        r#"{"shape":"rectangle","rear_notches":[{"side":"left","width":2,"depth":2}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_both_corners_notched","rear_notches":[{"side":"left","width":2,"depth":2}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"freehand","rear_notches":[],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[{"side":"back","width":2,"depth":2}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[{"side":"left","width":0.2,"depth":2}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[{"side":"right","width":18,"depth":2}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[{"side":"left","width":2,"depth":22}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[{"side":"left","width":2,"depth":2,"rights":"verified"}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_corner_notch","rear_notches":[{"side":"left","width":2,"depth":2}],"provenance":"user_sketch_unverified","regulatory_status":"verified"}"#,
        r#"{"shape":"rectangle","rear_notch":null,"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_both_corners_notched","rear_notches":[{"side":"left","width":4,"depth":10},{"side":"left","width":3,"depth":9}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_both_corners_notched","rear_notches":[{"side":"left","width":10,"depth":10},{"side":"right","width":8,"depth":9}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_both_corners_notched","rear_notches":[{"side":"left","width":10.00000001,"depth":10},{"side":"right","width":7,"depth":9}],"provenance":"user_sketch_unverified"}"#,
        r#"{"shape":"rear_both_corners_notched","rear_notches":[{"side":"left","width":4,"depth":10},{"side":"right","width":3,"depth":9},{"side":"left","width":1,"depth":2}],"provenance":"user_sketch_unverified"}"#,
    ] {
        let mut input = baseline.clone();
        put(
            child(&mut input, "site"),
            "plot_outline",
            json::parse(bad).unwrap(),
        );
        let error = output(&input);
        assert_eq!(status(&error), "error", "{bad}");
        assert!(arr(&error, "alternatives").is_empty());
        assert!(error.get("site_plot").is_none());
    }
}

#[test]
fn cli_never_writes_svg_for_a_house_over_the_applicants_rear_cutout() {
    let brief = std::env::temp_dir().join(format!("arqgen-L-brief-{}.json", std::process::id()));
    let rules = std::env::temp_dir().join(format!("arqgen-L-rules-{}.json", std::process::id()));
    let svg = std::env::temp_dir().join(format!("arqgen-L-invalid-{}.svg", std::process::id()));
    let _ = std::fs::remove_file(&svg);
    let mut input = request();
    cut_rear_corner(&mut input, "left", 7.0, 12.0);
    let actual_rules = if let Value::Object(root) = &mut input {
        root.remove("rules").unwrap()
    } else {
        unreachable!()
    };
    std::fs::write(&brief, input.stringify()).unwrap();
    std::fs::write(&rules, actual_rules.stringify()).unwrap();
    let run = std::process::Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(&brief)
        .arg("--rules")
        .arg(&rules)
        .arg("--svg")
        .arg(&svg)
        .output()
        .unwrap();
    assert!(!run.status.success());
    let echoed = json::parse(std::str::from_utf8(&run.stdout).unwrap()).unwrap();
    assert_eq!(status(&echoed), "infeasible");
    assert_eq!(num(&echoed, "generated"), 48.0);
    assert!(
        !svg.exists(),
        "Nunca debe escribirse un SVG sobre el recorte del croquis"
    );
    std::fs::remove_file(brief).unwrap();
    std::fs::remove_file(rules).unwrap();
}

#[test]
fn cli_never_exports_svg_when_the_second_rear_cut_blocks_the_only_front_trace() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap();
    let brief = std::env::temp_dir().join(format!("arqgen-U-brief-{}.json", std::process::id()));
    let svg = std::env::temp_dir().join(format!("arqgen-U-invalid-{}.svg", std::process::id()));
    let _ = std::fs::remove_file(&svg);
    let mut input = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
    cut_rear_corner(&mut input, "left", 1.0, 1.0);
    cut_opposite_rear_corner(&mut input, "right", 10.2, 21.0);
    std::fs::write(&brief, input.stringify()).unwrap();
    let run = std::process::Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(&brief)
        .arg("--rules")
        .arg(root.join("knowledge/generic-house.json"))
        .arg("--svg")
        .arg(&svg)
        .output()
        .unwrap();
    std::fs::remove_file(brief).unwrap();
    assert!(!run.status.success());
    let result = json::parse(std::str::from_utf8(&run.stdout).unwrap()).unwrap();
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "rejected"), 48.0);
    assert_eq!(arr(result.get("site_plot").unwrap(), "vertices").len(), 8);
    assert!(
        !svg.exists(),
        "No se debe exportar un plano con la franja bloqueada"
    );
}

#[test]
fn matrix_of_schematic_l_plots_is_bounded_and_never_fabricates_a_plan() {
    for side in ["left", "right"] {
        for width in [1.5, 4.0, 6.5] {
            for depth in [1.0, 7.5, 14.0] {
                let mut input = request();
                cut_rear_corner(&mut input, side, width, depth);
                if width > 4.0 {
                    reserve_site(&mut input, 8.0, 4.0, 1.0, 2.0);
                }
                let result = output(&input);
                assert_ne!(status(&result), "error", "{side} {width} x {depth}");
                assert_eq!(num(&result, "generated"), 48.0);
                assert_eq!(
                    status(result.get("applicability").unwrap()),
                    "not_evaluated"
                );
                assert_eq!(arr(result.get("site_plot").unwrap(), "vertices").len(), 6);
                let notch = Box2 {
                    x: if side == "left" { 0.0 } else { 18.0 - width },
                    y: 22.0 - depth,
                    w: width,
                    h: depth,
                };
                if status(&result) == "ok" {
                    let site = result.get("site").unwrap();
                    let inset = Box2::from(site.get("buildable").unwrap());
                    close(num(site, "plot_area"), 396.0 - width * depth);
                    close(
                        num(site, "unreserved_buildable_area"),
                        inset.area()
                            - inset.intersection(notch)
                            - if width > 4.0 { 2.0 } else { 0.0 },
                    );
                    for alt in arr(&result, "alternatives") {
                        assert!(
                            notch.intersection(Box2::from(alt.get("corridor").unwrap())) < 1e-6
                        );
                        for room in arr(alt, "rooms") {
                            assert!(
                                notch.intersection(Box2::from(room.get("rect").unwrap())) < 1e-6
                            );
                        }
                        for wall in arr(alt, "wall_zones") {
                            assert!(notch.intersection(Box2::from(wall)) < 1e-6);
                        }
                    }
                } else {
                    assert_eq!(status(&result), "infeasible");
                    assert!(arr(&result, "alternatives").is_empty());
                }
            }
        }
    }
}

#[test]
fn straight_front_approach_reaches_the_door_without_claiming_accessibility() {
    let input = request();
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    assert_eq!(num(&result, "rejected"), 0.0);
    let echo = result.get("site_approach").unwrap();
    assert_eq!(
        echo.get("provenance").unwrap().as_str(),
        Some("user_sketch_unverified")
    );
    assert_eq!(
        echo.get("geometry_status").unwrap().as_str(),
        Some("declared_front_trace_sketch_2d_only")
    );
    close(num(echo, "width"), 1.2);
    assert_eq!(
        echo.get("shape").unwrap().as_str(),
        Some("straight_front_strip")
    );
    assert!(matches!(echo.get("front_x"), Some(Value::Null)));
    assert!(matches!(echo.get("turn_y"), Some(Value::Null)));
    for field in [
        "street_connection_status",
        "right_of_way_status",
        "accessibility_status",
    ] {
        assert_eq!(echo.get(field).unwrap().as_str(), Some("not_evaluated"));
    }
    for alt in arr(&result, "alternatives") {
        let approach = alt.get("front_approach").unwrap();
        assert_eq!(
            approach.get("geometry_status").unwrap().as_str(),
            Some("strip_clear_of_declared_exclusions_2d_only")
        );
        assert_eq!(
            approach.get("shape").unwrap().as_str(),
            Some("straight_front_strip")
        );
        assert!(arr(approach, "turns").is_empty());
        assert_eq!(arr(approach, "segments").len(), 1);
        let band = Box2::from(&arr(approach, "segments")[0]);
        close(band.x, 8.4);
        close(band.y, 0.0);
        close(band.w, 1.2);
        close(band.h, 3.0);
        let entrance = alt.get("entrance").unwrap().get("opening").unwrap();
        close(
            num(approach.get("front_contact").unwrap(), "x"),
            num(entrance, "x") + num(entrance, "width") / 2.0,
        );
        close(num(approach.get("front_contact").unwrap(), "y"), 0.0);
        close(
            num(approach.get("door_contact").unwrap(), "y"),
            num(entrance, "y"),
        );
        assert!(alt
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("class=\"front-approach-strip\""));
        assert!(alt
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("FRANJA FRONTAL 2D ≠ ACCESO REAL"));
        assert!(arr(alt, "decisions")
            .iter()
            .any(|row| row.get("rule").unwrap().as_str()
                == Some("site.front_approach@user_sketch_unverified")));
        assert!(arr(alt, "warnings")
            .iter()
            .any(|row| row.as_str().unwrap().contains("NO acredita calle")));
        assert_eq!(
            alt.get("bathroom_ventilation_status").unwrap().as_str(),
            Some("not_evaluated")
        );
    }
    assert_eq!(
        status(result.get("applicability").unwrap()),
        "not_evaluated"
    );
}

#[test]
fn reserved_front_strip_is_rejected_even_when_all_gross_cells_still_fit() {
    let mut blocked = request();
    reserve_site(&mut blocked, 8.5, 1.0, 1.0, 1.0);
    let result = output(&blocked);
    assert_eq!(status(&result), "infeasible");
    assert_eq!(num(&result, "generated"), 48.0);
    assert_eq!(num(&result, "rejected"), 48.0);
    assert_eq!(arr(&result, "rejection_summary").len(), 1);
    assert!(arr(&result, "reasons")[0]
        .as_str()
        .unwrap()
        .contains("franja frontal recta"));
    assert!(arr(&result, "alternatives").is_empty());
    assert!(result.get("site_approach").is_some());
    assert!(result.get("site").is_none());
    // The same reserved area never crosses the house's gross cells: its y=1..2
    // is fully within the 3 m front setback. Only the approach gate changed.
    let mut touching = request();
    reserve_site(&mut touching, 9.6, 1.0, 1.0, 1.0);
    assert_eq!(
        status(&output(&touching)),
        "ok",
        "a shared edge is not an overlap"
    );
    reserve_site(&mut touching, 9.599_999_99, 1.0, 1.0, 1.0);
    assert_eq!(
        status(&output(&touching)),
        "infeasible",
        "even a sub-EPS crossing is excluded"
    );
    let mut widened = request();
    reserve_site(&mut widened, 7.0, 1.0, 1.1, 1.0);
    assert_eq!(status(&output(&widened)), "ok");
    put(
        child(child(&mut widened, "site"), "front_approach"),
        "width",
        Value::Number(4.0),
    );
    let wide = output(&widened);
    assert_eq!(status(&wide), "infeasible");
    assert_ne!(wide.get("input_hash"), output(&request()).get("input_hash"));
}

#[test]
fn rear_cutout_can_block_the_front_trace_and_zero_setback_has_no_exterior_band() {
    let mut notch = request();
    cut_rear_corner(&mut notch, "left", 10.2, 21.0); // at y=1 the notch crosses x=8.4..9.6
    let blocked = output(&notch);
    assert_eq!(status(&blocked), "infeasible");
    assert!(arr(&blocked, "rejection_summary").iter().any(|row| row
        .get("reason")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("franja frontal recta sale del croquis")));
    assert!(arr(&blocked, "alternatives").is_empty());
    let mut zero = request();
    put(
        child(child(&mut zero, "rules"), "setbacks"),
        "front",
        Value::Number(0.0),
    );
    let result = output(&zero);
    assert_eq!(status(&result), "ok");
    for alt in arr(&result, "alternatives") {
        let approach = alt.get("front_approach").unwrap();
        assert_eq!(
            approach.get("geometry_status").unwrap().as_str(),
            Some("door_at_front_boundary_2d_only")
        );
        assert!(arr(approach, "segments").is_empty());
        assert!(arr(approach, "turns").is_empty());
        close(num(approach.get("door_contact").unwrap(), "y"), 0.0);
        assert!(alt
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("class=\"front-approach-contact\""));
    }
}

#[test]
fn frontal_band_is_strictly_autodeclared_and_never_accepted_as_a_legal_route() {
    let baseline = request();
    let mut no_band = baseline.clone();
    if let Value::Object(site) = child(&mut no_band, "site") {
        site.remove("front_approach");
    }
    assert_eq!(status(&output(&no_band)), "error");
    for (field, value) in [
        ("provenance", Value::String("verified_right_of_way".into())),
        ("shape", Value::String("certified_road".into())),
        ("width", Value::Number(0.1)),
        ("width", Value::Number(20.0)),
        ("width", Value::String("1.2".into())),
    ] {
        let mut bad = baseline.clone();
        put(
            child(child(&mut bad, "site"), "front_approach"),
            field,
            value,
        );
        let result = output(&bad);
        assert_eq!(status(&result), "error");
        assert!(result.get("site_approach").is_none());
    }
    let mut extra = baseline.clone();
    put(
        child(child(&mut extra, "site"), "front_approach"),
        "legal",
        Value::Bool(true),
    );
    assert_eq!(status(&output(&extra)), "error");
    let mut narrow = baseline.clone();
    put(
        child(child(&mut narrow, "site"), "front_approach"),
        "width",
        Value::Number(0.9),
    );
    let result = output(&narrow);
    assert_eq!(status(&result), "ok");
    put(
        child(child(&mut narrow, "rules"), "doors"),
        "main",
        Value::Number(0.95),
    );
    assert_eq!(
        status(&output(&narrow)),
        "error",
        "the band must span the modelled door"
    );
}

#[test]
fn cli_never_writes_svg_when_only_the_declared_front_band_is_blocked() {
    let brief =
        std::env::temp_dir().join(format!("arqgen-front-brief-{}.json", std::process::id()));
    let rules =
        std::env::temp_dir().join(format!("arqgen-front-rules-{}.json", std::process::id()));
    let svg = std::env::temp_dir().join(format!("arqgen-front-invalid-{}.svg", std::process::id()));
    let _ = std::fs::remove_file(&svg);
    let mut input = request();
    reserve_site(&mut input, 8.5, 1.0, 1.0, 1.0);
    let rules_input = if let Value::Object(root) = &mut input {
        root.remove("rules").unwrap()
    } else {
        unreachable!()
    };
    std::fs::write(&brief, input.stringify()).unwrap();
    std::fs::write(&rules, rules_input.stringify()).unwrap();
    let run = std::process::Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(&brief)
        .arg("--rules")
        .arg(&rules)
        .arg("--svg")
        .arg(&svg)
        .output()
        .unwrap();
    assert!(!run.status.success());
    let echoed = json::parse(std::str::from_utf8(&run.stdout).unwrap()).unwrap();
    assert_eq!(status(&echoed), "infeasible");
    assert_eq!(num(&echoed, "generated"), 48.0);
    assert!(!svg.exists());
    std::fs::remove_file(brief).unwrap();
    std::fs::remove_file(rules).unwrap();
}

fn set_declared_detour(input: &mut Value, front_x: f64, turn_y: f64, front_setback: f64) {
    put(
        child(child(input, "rules"), "setbacks"),
        "front",
        Value::Number(front_setback),
    );
    let trace = child(child(input, "site"), "front_approach");
    put(
        trace,
        "shape",
        Value::String("orthogonal_front_detour".into()),
    );
    put(trace, "front_x", Value::Number(front_x));
    put(trace, "turn_y", Value::Number(turn_y));
}

#[test]
fn declared_two_turn_sketch_can_avoid_a_front_reservation_without_proving_access() {
    let mut straight = request();
    put(
        child(child(&mut straight, "rules"), "setbacks"),
        "front",
        Value::Number(5.0),
    );
    let unobstructed = output(&straight);
    reserve_site(&mut straight, 8.5, 1.0, 1.0, 1.0);
    assert_eq!(status(&output(&straight)), "infeasible");
    let mut detour = straight.clone();
    set_declared_detour(&mut detour, 11.5, 3.0, 5.0);
    let context = child(&mut detour, "project_context");
    put(context, "jurisdiction", Value::String("CU".into()));
    put(
        context,
        "housing_class",
        Value::String("urban_social".into()),
    );
    let result = output(&detour);
    assert_eq!(status(&result), "ok");
    assert_eq!(num(&result, "generated"), 48.0);
    assert_eq!(num(&result, "rejected"), 2.0); // two designs too deep; neither is faked
    assert_ne!(
        result.get("input_hash"),
        output(&straight).get("input_hash")
    );
    assert_eq!(
        status(result.get("applicability").unwrap()),
        "not_evaluated"
    );
    close(
        num(result.get("site").unwrap(), "max_built_area"),
        num(unobstructed.get("site").unwrap(), "max_built_area"),
    );
    close(
        num(result.get("site").unwrap(), "unreserved_buildable_area"),
        num(
            unobstructed.get("site").unwrap(),
            "unreserved_buildable_area",
        ),
    );
    let echo = result.get("site_approach").unwrap();
    assert_eq!(
        echo.get("shape").unwrap().as_str(),
        Some("orthogonal_front_detour")
    );
    assert_eq!(
        echo.get("geometry_status").unwrap().as_str(),
        Some("declared_front_trace_sketch_2d_only")
    );
    close(num(echo, "front_x"), 11.5);
    close(num(echo, "turn_y"), 3.0);
    for field in [
        "street_connection_status",
        "right_of_way_status",
        "accessibility_status",
    ] {
        assert_eq!(echo.get(field).unwrap().as_str(), Some("not_evaluated"));
    }
    for alt in arr(&result, "alternatives") {
        let a = alt.get("front_approach").unwrap();
        assert_eq!(
            a.get("shape").unwrap().as_str(),
            Some("orthogonal_front_detour")
        );
        assert_eq!(
            a.get("geometry_status").unwrap().as_str(),
            Some("orthogonal_detour_clear_of_declared_exclusions_2d_only")
        );
        close(num(a, "width"), 1.2);
        close(num(a.get("front_contact").unwrap(), "x"), 11.5);
        close(
            num(a.get("door_contact").unwrap(), "x"),
            num(alt.get("entrance").unwrap().get("opening").unwrap(), "x")
                + num(
                    alt.get("entrance").unwrap().get("opening").unwrap(),
                    "width",
                ) / 2.0,
        );
        close(num(a.get("door_contact").unwrap(), "y"), 5.0);
        let segments: Vec<_> = arr(a, "segments").iter().map(Box2::from).collect();
        assert_eq!(segments.len(), 3);
        let turns = arr(a, "turns");
        assert_eq!(turns.len(), 2);
        close(num(&turns[0], "x"), 11.5);
        close(num(&turns[0], "y"), 3.0);
        close(
            num(&turns[1], "x"),
            num(a.get("door_contact").unwrap(), "x"),
        );
        close(num(&turns[1], "y"), 3.0);
        let plot = Box2 {
            x: 0.0,
            y: 0.0,
            w: 18.0,
            h: 5.0,
        };
        let reserve = Box2 {
            x: 8.5,
            y: 1.0,
            w: 1.0,
            h: 1.0,
        };
        for band in &segments {
            assert!(plot.contains(*band));
            assert_eq!(band.intersection(reserve), 0.0);
        }
        assert!(segments[0].intersection(segments[1]) > 0.0);
        assert!(segments[1].intersection(segments[2]) > 0.0);
        let svg = alt.get("svg").unwrap().as_str().unwrap();
        assert_eq!(svg.matches("class=\"front-approach-strip\"").count(), 3);
        assert_eq!(svg.matches("class=\"front-approach-turn\"").count(), 2);
        assert!(svg.contains("RODEO FRONTAL ≠ ACCESO REAL"));
        assert!(arr(alt, "warnings")
            .iter()
            .any(|w| w.as_str().unwrap().contains("NO acredita calle")));
    }
}

#[test]
fn both_corners_and_all_three_bands_must_fit_or_the_sketch_has_no_plan() {
    let mut start = request();
    set_declared_detour(&mut start, 11.5, 3.0, 5.0);
    // No clearance behind a 1 m-deep obstacle within the default 3 m setback.
    let mut short = start.clone();
    put(
        child(child(&mut short, "rules"), "setbacks"),
        "front",
        Value::Number(3.0),
    );
    reserve_site(&mut short, 8.5, 1.0, 1.0, 1.0);
    assert_eq!(status(&output(&short)), "infeasible");
    // A band crosses the reservation although the centreline can miss it.
    for (x, y, w, h) in [
        (11.0, 1.0, 0.25, 0.5), // entering vertical leg
        (10.0, 3.2, 0.3, 0.2),  // horizontal band's edge, not its centreline y=3
        (8.6, 4.0, 0.5, 0.4),   // door vertical leg
    ] {
        let mut blocked = start.clone();
        reserve_site(&mut blocked, x, y, w, h);
        let rejected = output(&blocked);
        assert_eq!(status(&rejected), "infeasible", "{x}, {y}");
        assert_eq!(num(&rejected, "generated"), 48.0);
        assert!(arr(&rejected, "rejection_summary").iter().any(|row| row
            .get("reason")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("banda del rodeo frontal")));
        assert!(arr(&rejected, "alternatives").is_empty());
    }
    let mut tangent = start.clone();
    reserve_site(&mut tangent, 8.5, 1.0, 1.0, 1.0);
    put(
        child(child(&mut tangent, "site"), "front_approach"),
        "turn_y",
        Value::Number(2.6),
    );
    assert_eq!(
        status(&output(&tangent)),
        "ok",
        "shared band/reserve edge allowed"
    );
    put(
        child(child(&mut tangent, "site"), "front_approach"),
        "turn_y",
        Value::Number(2.599_999_99),
    );
    assert_eq!(
        status(&output(&tangent)),
        "infeasible",
        "sub-EPS invasion is not ignored"
    );
    let mut notch = start.clone();
    cut_rear_corner(&mut notch, "right", 7.0, 21.0); // at y=1, x>=11 is outside the L sketch
    let excluded = output(&notch);
    assert_eq!(status(&excluded), "infeasible");
    assert!(arr(&excluded, "rejection_summary").iter().any(|row| row
        .get("reason")
        .unwrap()
        .as_str()
        .unwrap()
        .contains("rodeo frontal ortogonal sale del croquis")));
    let mut zero = start.clone();
    put(
        child(child(&mut zero, "rules"), "setbacks"),
        "front",
        Value::Number(0.0),
    );
    assert_eq!(
        status(&output(&zero)),
        "infeasible",
        "detour cannot draw a zero-height route"
    );
    let mut no_bends = start;
    put(
        child(child(&mut no_bends, "site"), "front_approach"),
        "front_x",
        Value::Number(9.0),
    );
    assert_eq!(
        status(&output(&no_bends)),
        "infeasible",
        "a redundant detour is not a real turn"
    );
}

#[test]
fn malformed_detours_are_errors_without_a_fabricated_verified_trace() {
    let baseline = request();
    let mut malformed = Vec::new();
    let mut null_bend = baseline.clone();
    put(
        child(child(&mut null_bend, "site"), "front_approach"),
        "turn_y",
        Value::Number(1.0),
    );
    malformed.push(null_bend);
    let mut missing = baseline.clone();
    if let Value::Object(approach) = child(child(&mut missing, "site"), "front_approach") {
        approach.remove("front_x");
    }
    malformed.push(missing);
    let mut missing_turn = baseline.clone();
    set_declared_detour(&mut missing_turn, 11.5, 3.0, 5.0);
    put(
        child(child(&mut missing_turn, "site"), "front_approach"),
        "turn_y",
        Value::Null,
    );
    malformed.push(missing_turn);
    for (field, bad_value) in [
        ("front_x", Value::Number(0.1)),
        ("front_x", Value::Number(18.0)),
        ("turn_y", Value::Number(0.2)),
        ("turn_y", Value::Number(22.0)),
        ("turn_y", Value::String("3".into())),
        ("provenance", Value::String("verified_public_road".into())),
    ] {
        let mut bad = baseline.clone();
        set_declared_detour(&mut bad, 11.5, 3.0, 5.0);
        put(
            child(child(&mut bad, "site"), "front_approach"),
            field,
            bad_value,
        );
        malformed.push(bad);
    }
    let mut extra = baseline.clone();
    put(
        child(child(&mut extra, "site"), "front_approach"),
        "permission",
        Value::Bool(true),
    );
    malformed.push(extra);
    let mut old = baseline;
    put(
        &mut old,
        "request_schema",
        Value::String("arqgen-brief-v6".into()),
    );
    malformed.push(old);
    for bad in malformed {
        let result = output(&bad);
        assert_eq!(status(&result), "error");
        assert!(result.get("site_approach").is_none());
        assert!(arr(&result, "alternatives").is_empty());
    }
}

#[test]
fn cli_does_not_write_an_svg_when_the_declared_two_turn_trace_is_blocked() {
    let brief =
        std::env::temp_dir().join(format!("arqgen-detour-brief-{}.json", std::process::id()));
    let rules =
        std::env::temp_dir().join(format!("arqgen-detour-rules-{}.json", std::process::id()));
    let svg =
        std::env::temp_dir().join(format!("arqgen-detour-blocked-{}.svg", std::process::id()));
    let _ = std::fs::remove_file(&svg);
    let mut input = request();
    set_declared_detour(&mut input, 11.5, 3.0, 5.0);
    reserve_site(&mut input, 10.0, 2.8, 0.3, 0.3);
    let rules_input = if let Value::Object(root) = &mut input {
        root.remove("rules").unwrap()
    } else {
        unreachable!()
    };
    std::fs::write(&brief, input.stringify()).unwrap();
    std::fs::write(&rules, rules_input.stringify()).unwrap();
    let cli = std::process::Command::new(env!("CARGO_BIN_EXE_arqgen"))
        .arg(&brief)
        .arg("--rules")
        .arg(&rules)
        .arg("--svg")
        .arg(&svg)
        .output()
        .unwrap();
    assert!(!cli.status.success());
    let answer = json::parse(std::str::from_utf8(&cli.stdout).unwrap()).unwrap();
    assert_eq!(status(&answer), "infeasible");
    assert_eq!(num(&answer, "generated"), 48.0);
    assert!(!svg.exists());
    std::fs::remove_file(brief).unwrap();
    std::fs::remove_file(rules).unwrap();
}

#[test]
fn the_declared_two_turn_trace_can_go_left_as_well_as_right() {
    let mut input = request();
    reserve_site(&mut input, 8.5, 0.5, 1.0, 0.5);
    set_declared_detour(&mut input, 6.5, 1.6, 3.0);
    let result = output(&input);
    assert_eq!(status(&result), "ok");
    assert_eq!(num(&result, "rejected"), 0.0);
    for alt in arr(&result, "alternatives") {
        let route = alt.get("front_approach").unwrap();
        let segments = arr(route, "segments");
        let first = Box2::from(&segments[0]);
        let middle = Box2::from(&segments[1]);
        let last = Box2::from(&segments[2]);
        close(first.x, 5.9);
        close(first.h, 1.6);
        close(middle.x, 6.5);
        close(middle.w, 2.5);
        close(last.x, 8.4);
        close(last.bottom(), 3.0);
        assert!(first.intersection(middle) > 0.0);
        assert!(middle.intersection(last) > 0.0);
        close(num(route.get("front_contact").unwrap(), "x"), 6.5);
        close(num(&arr(route, "turns")[0], "x"), 6.5);
        close(num(&arr(route, "turns")[1], "x"), 9.0);
    }
}
