//! Bounded multi-seed scan from the exact same Rust core as the browser worker.
use arqgen_core::{explore_json, json};
use std::{env, fs, process};

fn usage() -> ! {
    eprintln!("Uso: arqgen-explore ENCARGO.json --rules knowledge/generic-house.json --count 2..12\n\
               Emite un lote conceptual JSON (semillas consecutivas); NO es un óptimo global ni norma.");
    process::exit(2);
}

fn main() {
    let mut args = env::args().skip(1);
    let input_path = args.next().unwrap_or_else(|| usage());
    if input_path.starts_with('-') {
        usage();
    }
    let mut rules_path = None;
    let mut count = None;
    while let Some(flag) = args.next() {
        match flag.as_str() {
            "--rules" => rules_path = Some(args.next().unwrap_or_else(|| usage())),
            "--count" => count = Some(args.next().unwrap_or_else(|| usage())),
            _ => usage(),
        }
    }
    let rules_path = rules_path.unwrap_or_else(|| usage());
    let count: u32 = count
        .unwrap_or_else(|| usage())
        .parse()
        .unwrap_or_else(|_| usage());
    if !(2..=12).contains(&count) {
        usage();
    }
    let result = (|| -> Result<(), String> {
        let input = fs::read_to_string(&input_path).map_err(|e| format!("{input_path}: {e}"))?;
        let rules = fs::read_to_string(&rules_path).map_err(|e| format!("{rules_path}: {e}"))?;
        let mut root = json::parse(&input)?;
        if root.get("rules").is_some() {
            return Err(
                "El encargo no debe incluir rules: usa solo --rules para fijar el snapshot.".into(),
            );
        }
        root.insert("rules", json::parse(&rules)?)?;
        let envelope = json::object(vec![
            ("input", root),
            ("seed_count", json::number(count as f64)),
        ]);
        let output = explore_json(&envelope.stringify());
        let parsed = json::parse_response(&output)?; // separate 2 MB output cap
        match parsed.get("status").and_then(json::Value::as_str) {
            Some("ok" | "infeasible") => {
                println!("{output}");
                Ok(())
            }
            _ => Err(parsed
                .get("message")
                .and_then(json::Value::as_str)
                .unwrap_or("Error de entrada")
                .to_string()),
        }
    })();
    if let Err(error) = result {
        eprintln!("ARQ GEN: {error}");
        process::exit(1);
    }
}
