#![cfg(feature = "declared-vertical-v1")]
use arqgen_core::{
    declared_vertical_json, generate_json,
    json::{self, Value},
};

fn fixture() -> Value {
    json::parse(include_str!(
        "../../examples/declared-vertical-v1-request.json"
    ))
    .unwrap()
}
fn run(input: &Value) -> Value {
    json::parse(&declared_vertical_json(&input.stringify())).unwrap()
}
fn get<'a>(value: &'a Value, key: &str) -> &'a Value {
    value.get(key).unwrap_or_else(|| panic!("falta {key}"))
}
fn s(value: &Value) -> &str {
    value.as_str().unwrap()
}
fn n(value: &Value) -> f64 {
    value.as_number().unwrap()
}
fn put(value: &mut Value, field: &str, data: Value) {
    value.insert(field, data).unwrap();
}
fn child<'a>(value: &'a mut Value, field: &str) -> &'a mut Value {
    match value {
        Value::Object(fields) => fields.get_mut(field).unwrap(),
        _ => panic!("objeto requerido"),
    }
}
fn error(result: &Value) -> &str {
    assert_eq!(s(get(result, "status")), "error");
    assert_eq!(
        s(get(result, "format")),
        "arqgen-declared-vertical-model-v1"
    );
    assert!(get(result, "levels").as_array().unwrap().is_empty());
    assert!(result.get("source").is_none());
    assert!(result.get("model_hash").is_none());
    s(get(result, "message"))
}

#[test]
fn example_replays_v8_and_never_creates_unverified_elevations_or_openings() {
    let input = fixture();
    let model = run(&input);
    assert_eq!(s(get(&model, "status")), "ok");
    assert_eq!(
        model.stringify(),
        include_str!("../../examples/declared-vertical-v1-model.json").trim()
    );
    assert_eq!(s(get(&model, "model_hash")), "70e9ade2b226f678");
    assert_eq!(
        s(get(&model, "height_provenance")),
        "illustrative_assumption_not_measured"
    );
    assert!(s(get(&model, "notice")).contains("NO APTO PARA OBRA"));
    for field in ["roof", "vertical_connections", "sections", "facades"] {
        assert_eq!(
            get(&model, field),
            &Value::Null,
            "{field} must remain unmodelled"
        );
    }
    let source = get(&model, "source");
    let v8 = json::parse(&generate_json(&get(&input, "input").stringify())).unwrap();
    assert_eq!(s(get(source, "input_hash")), s(get(&v8, "input_hash")));
    assert_eq!(
        s(get(source, "engine_version")),
        s(get(&v8, "engine_version"))
    );
    let candidate = get(&v8, "alternatives")
        .as_array()
        .unwrap()
        .iter()
        .find(|row| s(get(row, "id")) == s(get(source, "candidate_id")))
        .unwrap();
    let levels = get(&model, "levels").as_array().unwrap();
    assert_eq!(levels.len(), 1);
    let level = &levels[0];
    assert_eq!(s(get(level, "level_id")), "L0");
    assert_eq!(n(get(level, "floor_z_m")), 0.0);
    assert_eq!(n(get(level, "wall_top_z_m")), 3.1);
    let openings = get(level, "openings").as_array().unwrap();
    let rooms = get(candidate, "rooms").as_array().unwrap();
    let windows: Vec<_> = rooms
        .iter()
        .filter(|r| r.get("window") != Some(&Value::Null) && r.get("window").is_some())
        .collect();
    assert_eq!(openings.len(), windows.len() + 1);
    assert_eq!(
        get(&openings[0], "plan_opening_v8"),
        get(get(candidate, "entrance"), "opening")
    );
    assert_eq!(n(get(&openings[0], "bottom_z_m")), 0.0);
    assert_eq!(n(get(&openings[0], "top_z_m")), 2.15);
    for opening in openings.iter().skip(1) {
        let room = windows
            .iter()
            .find(|r| s(get(r, "id")) == s(get(opening, "room_id")))
            .unwrap();
        assert_eq!(s(get(opening, "kind")), "window");
        assert_eq!(
            get(opening, "plan_opening_v8"),
            get(get(room, "window"), "opening")
        );
        assert!(
            (n(get(opening, "top_z_m"))
                - n(get(opening, "bottom_z_m"))
                - n(get(get(room, "window"), "height")))
            .abs()
                < 1e-8
        );
        assert!(n(get(opening, "top_z_m")) <= n(get(level, "wall_top_z_m")));
    }
}

#[test]
fn changes_are_domain_separated_replayable_and_not_claimed_as_v8_changes() {
    let input = fixture();
    let original = run(&input);
    assert_eq!(run(&input), original);
    let mut modified = input.clone();
    let sills = child(
        child(&mut modified, "declared_vertical"),
        "window_sill_above_floor_m",
    );
    put(sills, "bedroom-1", json::number(1.15));
    let alternative = run(&modified);
    assert_eq!(s(get(&alternative, "status")), "ok");
    assert_ne!(
        get(&alternative, "model_hash"),
        get(&original, "model_hash")
    );
    assert_eq!(
        get(get(&alternative, "source"), "input_hash"),
        get(get(&original, "source"), "input_hash")
    );
    assert_eq!(
        get(&alternative, "levels").as_array().unwrap()[0]
            .get("openings")
            .unwrap()
            .as_array()
            .unwrap()
            .len(),
        8
    );
    let mut different_candidate = input;
    // Even a plausible ID with the correct input hash must be PUBLISHED by v8.
    put(
        &mut different_candidate,
        "candidate_id",
        json::text("cand-ab3376d8fef08f3b-9999"),
    );
    assert!(error(&run(&different_candidate)).contains("candidate_id"));
}

#[test]
fn a_second_published_candidate_is_replayed_instead_of_reusing_the_first() {
    let mut input = fixture();
    let generated = json::parse(&generate_json(&get(&input, "input").stringify())).unwrap();
    let other = &get(&generated, "alternatives").as_array().unwrap()[1];
    let other_id = s(get(other, "id")).to_owned();
    put(&mut input, "candidate_id", json::text(&other_id));
    let mut sills = Value::Object(Default::default());
    for room in get(other, "rooms").as_array().unwrap() {
        if room.get("window").is_some() && room.get("window") != Some(&Value::Null) {
            put(&mut sills, s(get(room, "id")), json::number(0.9));
        }
    }
    put(
        child(&mut input, "declared_vertical"),
        "window_sill_above_floor_m",
        sills,
    );
    let model = run(&input);
    assert_eq!(s(get(&model, "status")), "ok");
    assert_eq!(s(get(get(&model, "source"), "candidate_id")), other_id);
    assert_ne!(
        get(&model, "model_hash"),
        get(&run(&fixture()), "model_hash")
    );
    let openings = get(&model, "levels").as_array().unwrap()[0]
        .get("openings")
        .unwrap()
        .as_array()
        .unwrap()
        .to_vec();
    assert_eq!(
        openings[0].get("plan_opening_v8"),
        get(other, "entrance").get("opening")
    );
}

#[test]
fn altered_or_missing_ids_and_unverified_typologies_fail_atomically() {
    let mut bad = fixture();
    put(&mut bad, "candidate_id", json::text("cand-forged"));
    assert!(error(&run(&bad)).contains("candidate_id"));
    for typology in ["hospital", "hotel", "multifamily_house"] {
        let mut bad = fixture();
        put(&mut bad, "typology", json::text(typology));
        assert!(error(&run(&bad)).contains("hospitales y hoteles"));
    }
    let mut bad = fixture();
    put(
        &mut bad,
        "format",
        json::text("arqgen-declared-vertical-request-v2"),
    );
    assert!(error(&run(&bad)).contains("format"));
    let mut bad = fixture();
    put(&mut bad, "generation", json::text("injected"));
    assert!(error(&run(&bad)).contains("campos"));
    let mut bad = fixture();
    put(
        child(&mut bad, "input"),
        "request_schema",
        json::text("arqgen-brief-v7"),
    );
    assert!(error(&run(&bad)).contains("v8"));
    let mut bad = fixture();
    put(
        child(child(&mut bad, "input"), "site"),
        "width",
        json::number(4.0),
    );
    assert!(error(&run(&bad)).contains("v8"));
}

#[test]
fn declared_heights_must_cover_exactly_the_generated_v8_windows() {
    let mut bad = fixture();
    let sills = child(
        child(&mut bad, "declared_vertical"),
        "window_sill_above_floor_m",
    );
    match sills {
        Value::Object(fields) => {
            fields.remove("bathroom-1");
        }
        _ => panic!(),
    }
    assert!(error(&run(&bad)).contains("bathroom-1"));
    let mut bad = fixture();
    let sills = child(
        child(&mut bad, "declared_vertical"),
        "window_sill_above_floor_m",
    );
    put(sills, "invented-stair-window", json::number(1.0));
    assert!(error(&run(&bad)).contains("invented-stair-window"));
    let mut bad = fixture();
    let sills = child(
        child(&mut bad, "declared_vertical"),
        "window_sill_above_floor_m",
    );
    put(sills, "bathroom-1", json::number(2.0));
    assert!(error(&run(&bad)).contains("sobresale"));
    let mut bad = fixture();
    let sills = child(
        child(&mut bad, "declared_vertical"),
        "window_sill_above_floor_m",
    );
    put(sills, "kitchen", json::number(-0.1));
    assert!(error(&run(&bad)).contains("Alféizar"));
}

#[test]
fn local_datum_provenance_bounds_and_invalid_json_are_never_trusted() {
    let mut bad = fixture();
    put(
        child(&mut bad, "declared_vertical"),
        "datum",
        json::text("surveyed_and_certified"),
    );
    assert!(error(&run(&bad)).contains("datum"));
    let mut bad = fixture();
    put(
        child(&mut bad, "declared_vertical"),
        "height_provenance",
        json::text("measured"),
    );
    assert!(error(&run(&bad)).contains("height_provenance"));
    for (key, value) in [
        ("floor_z_m", json::number(1001.0)),
        ("floor_z_m", json::text("0")),
        ("wall_top_z_m", json::number(-1.0)),
        ("wall_top_z_m", json::number(0.000_000_000_1)),
        ("entry_head_above_floor_m", json::number(0.0)),
        ("entry_head_above_floor_m", json::number(0.000_000_000_1)),
        ("entry_head_above_floor_m", json::number(3.2)),
    ] {
        let mut bad = fixture();
        put(child(&mut bad, "declared_vertical"), key, value);
        error(&run(&bad));
    }
    let mut bad = fixture();
    put(
        child(&mut bad, "declared_vertical"),
        "unverified_roof",
        json::number(4.0),
    );
    assert!(error(&run(&bad)).contains("campos"));
    let duplicate = "{\"format\":\"x\",\"format\":\"y\"}";
    assert!(error(&json::parse(&declared_vertical_json(duplicate)).unwrap()).contains("duplic"));
    assert!(
        error(&json::parse(&declared_vertical_json("{\"format\":1e999}")).unwrap())
            .contains("finito")
    );
}

#[test]
fn native_cli_exports_only_a_complete_model_and_exits_nonzero_on_error() {
    use std::{fs, process::Command};
    let executable = std::env::var("CARGO_BIN_EXE_arqgen-vertical")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| {
            std::env::current_exe()
                .unwrap()
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .join(format!("arqgen-vertical{}", std::env::consts::EXE_SUFFIX))
        });
    let example = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../examples/declared-vertical-v1-request.json"
    );
    let good = Command::new(&executable).arg(example).output().unwrap();
    assert!(good.status.success());
    assert!(good.stderr.is_empty());
    assert_eq!(
        String::from_utf8(good.stdout).unwrap().trim(),
        include_str!("../../examples/declared-vertical-v1-model.json").trim()
    );

    let mut bad = fixture();
    put(&mut bad, "candidate_id", json::text("forged"));
    let tmp = std::env::temp_dir().join(format!("arqgen-vertical-bad-{}.json", std::process::id()));
    fs::write(&tmp, bad.stringify()).unwrap();
    let rejected = Command::new(executable).arg(&tmp).output().unwrap();
    fs::remove_file(&tmp).unwrap();
    assert_eq!(rejected.status.code(), Some(1));
    assert!(rejected.stdout.is_empty(), "No exportar modelos parciales");
    assert!(String::from_utf8(rejected.stderr)
        .unwrap()
        .contains("candidate_id"));
}
