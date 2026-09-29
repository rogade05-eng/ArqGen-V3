use arqgen_core::{generate_json, json};
use std::{env, fs, process};

fn usage() -> ! {
    eprintln!(
        "Uso: arqgen ENCARGO.json --rules knowledge/generic-house.json [--svg ruta.svg]\n\
              Emite propuestas JSON por stdout; solo exporta SVG de una alternativa viable.\n\
              Las reglas genéricas de ejemplo NO certifican cumplimiento normativo."
    );
    process::exit(2);
}

fn main() {
    let mut args = env::args().skip(1);
    let input_path = args.next().unwrap_or_else(|| usage());
    if input_path.starts_with('-') {
        usage();
    }
    let mut rules_path = None;
    let mut svg_path = None;
    while let Some(flag) = args.next() {
        match flag.as_str() {
            "--rules" => rules_path = Some(args.next().unwrap_or_else(|| usage())),
            "--svg" => svg_path = Some(args.next().unwrap_or_else(|| usage())),
            _ => usage(),
        }
    }
    let rules_path = rules_path.unwrap_or_else(|| usage());
    let result = (|| -> Result<(), String> {
        let input = fs::read_to_string(&input_path).map_err(|e| format!("{input_path}: {e}"))?;
        let rules = fs::read_to_string(&rules_path).map_err(|e| format!("{rules_path}: {e}"))?;
        let mut root = json::parse(&input)?;
        if root.get("rules").is_some() {
            return Err(
                "El encargo no debe incluir rules: usa únicamente --rules para fijar el snapshot."
                    .into(),
            );
        }
        root.insert("rules", json::parse(&rules)?)?;
        let output = generate_json(&root.stringify());
        let parsed = json::parse(&output)?;
        println!("{output}");
        match parsed.get("status").and_then(json::Value::as_str) {
            Some("ok") => {
                if let Some(path) = svg_path {
                    let first = parsed
                        .get("alternatives")
                        .and_then(json::Value::as_array)
                        .and_then(|alternatives| alternatives.first())
                        .and_then(|candidate| candidate.get("svg"))
                        .and_then(json::Value::as_str)
                        .ok_or("No hay SVG para exportar")?;
                    fs::write(&path, first).map_err(|e| format!("{path}: {e}"))?;
                    eprintln!("Esquema conceptual SVG escrito en {path}");
                }
                Ok(())
            }
            Some("infeasible") => Err(
                "No se halló una solución válida en los esquemas explorados; no se exportó SVG."
                    .into(),
            ),
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
