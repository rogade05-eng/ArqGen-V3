use arqgen_core::{
    explore_json, generate_json,
    json::{self, Value},
};

fn brief() -> Value {
    let mut input = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
    input
        .insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
    input
}
fn explore(input: Value, count: u32) -> Value {
    json::parse(&explore_json(
        &json::object(vec![
            ("input", input),
            ("seed_count", json::number(count as f64)),
        ])
        .stringify(),
    ))
    .unwrap()
}
fn number(row: &Value, key: &str) -> usize {
    row.get(key).unwrap().as_number().unwrap() as usize
}
fn rows(row: &Value, key: &str) -> Vec<Value> {
    row.get(key).unwrap().as_array().unwrap().to_vec()
}
fn status(row: &Value) -> &str {
    row.get("status").unwrap().as_str().unwrap()
}

#[test]
fn every_seed_replays_independently_and_pool_counts_all_48_per_seed() {
    let input = brief();
    let batch = explore(input.clone(), 4);
    assert_eq!(status(&batch), "ok");
    assert_eq!(
        batch.get("exploration_method").unwrap().as_str(),
        Some("bounded-seed-sweep-v1")
    );
    assert_eq!(number(&batch, "seed_count"), 4);
    assert_eq!(number(&batch, "generated"), 192);
    assert_eq!(number(&batch, "valid") + number(&batch, "rejected"), 192);
    assert!(number(&batch, "pareto_front_size") > 0);
    assert_eq!(rows(&batch, "objectives").len(), 5);
    assert_eq!(rows(&batch, "seed_runs").len(), 4);
    assert!((1..=3).contains(&rows(&batch, "alternatives").len()));
    assert_eq!(
        explore_json(
            &json::object(vec![
                ("input", input.clone()),
                ("seed_count", json::number(4.0))
            ])
            .stringify()
        ),
        explore_json(
            &json::object(vec![
                ("input", input.clone()),
                ("seed_count", json::number(4.0))
            ])
            .stringify()
        )
    );
    let rejection_sum: usize = rows(&batch, "rejection_summary")
        .iter()
        .map(|row| number(row, "count"))
        .sum();
    assert_eq!(number(&batch, "rejected"), rejection_sum);
    for (offset, run) in rows(&batch, "seed_runs").iter().enumerate() {
        assert_eq!(number(run, "seed"), 42 + offset);
        let mut for_seed = input.clone();
        for_seed
            .insert("seed", json::number((42 + offset) as f64))
            .unwrap();
        let single = json::parse(&generate_json(&for_seed.stringify())).unwrap();
        assert_eq!(run.get("input_hash"), single.get("input_hash"));
        assert_eq!(
            run.get("rejection_summary"),
            single.get("rejection_summary")
        );
        assert_eq!(number(run, "generated"), number(&single, "generated"));
        assert_eq!(number(run, "rejected"), number(&single, "rejected"));
        assert_eq!(status(run), status(&single));
    }
    for entry in rows(&batch, "alternatives") {
        let seed = number(&entry, "seed");
        assert!((42..46).contains(&seed));
        let candidate = entry.get("candidate").unwrap();
        let run = &rows(&batch, "seed_runs")[seed - 42];
        assert!(candidate
            .get("id")
            .unwrap()
            .as_str()
            .unwrap()
            .contains(run.get("input_hash").unwrap().as_str().unwrap()));
        assert!(candidate
            .get("svg")
            .unwrap()
            .as_str()
            .unwrap()
            .contains("NO APTO PARA OBRA"));
        assert_eq!(
            candidate
                .get("bathroom_ventilation_status")
                .unwrap()
                .as_str(),
            Some("not_evaluated")
        );
        assert!(number(candidate, "pareto_layer") <= 48 * 4);
    }
}

#[test]
fn all_rejections_and_precheck_zero_do_not_invent_any_plan() {
    let mut input = brief();
    let site = input.get("site").unwrap().clone();
    let mut site = site;
    site.insert("width", json::number(4.0)).unwrap();
    input.insert("site", site).unwrap();
    let batch = explore(input, 3);
    assert_eq!(status(&batch), "infeasible");
    assert_eq!(number(&batch, "generated"), 0);
    assert_eq!(number(&batch, "pareto_front_size"), 0);
    assert!(rows(&batch, "alternatives").is_empty());
    assert_eq!(rows(&batch, "seed_runs").len(), 3);
    assert!(!rows(&batch, "reasons").is_empty());

    let mut input = brief();
    let mut site = input.get("site").unwrap().clone();
    site.insert(
        "reserved_areas",
        json::list(vec![json::object(vec![
            ("x", json::number(8.5)),
            ("y", json::number(0.5)),
            ("width", json::number(1.0)),
            ("depth", json::number(0.5)),
        ])]),
    )
    .unwrap();
    input.insert("site", site).unwrap();
    let batch = explore(input, 2);
    assert_eq!(status(&batch), "infeasible");
    assert_eq!(number(&batch, "generated"), 96);
    assert_eq!(number(&batch, "rejected"), 96);
    assert_eq!(
        rows(&batch, "rejection_summary")
            .iter()
            .map(|r| number(r, "count"))
            .sum::<usize>(),
        96
    );
    assert!(rows(&batch, "alternatives").is_empty());
}

#[test]
fn seed_wrap_and_invalid_envelopes_fail_closed() {
    let mut input = brief();
    input.insert("seed", json::number(u32::MAX as f64)).unwrap();
    let batch = explore(input.clone(), 3);
    assert_eq!(
        rows(&batch, "seed_runs")
            .iter()
            .map(|r| number(r, "seed"))
            .collect::<Vec<_>>(),
        vec![u32::MAX as usize, 0, 1]
    );
    for count in [0.0, 1.0, 13.0, 2.5, -3.0, 1e30] {
        let bad = json::object(vec![
            ("input", input.clone()),
            ("seed_count", json::number(count)),
        ]);
        assert_eq!(
            status(&json::parse(&explore_json(&bad.stringify())).unwrap()),
            "error"
        );
    }
    let bad = json::object(vec![
        ("input", input.clone()),
        ("seed_count", json::number(2.0)),
        ("extra", json::number(1.0)),
    ]);
    assert_eq!(
        status(&json::parse(&explore_json(&bad.stringify())).unwrap()),
        "error"
    );
    let old = json::object(vec![("request_schema", json::text("arqgen-brief-v7"))]);
    assert_eq!(status(&explore(old, 2)), "error");
}
