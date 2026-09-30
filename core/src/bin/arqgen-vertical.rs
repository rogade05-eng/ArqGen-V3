//! Opt-in native preview of declared Z coordinates, NOT construction plans.
use arqgen_core::{declared_vertical_json, json};
use std::{env, fs, process};

fn main() {
    let mut args = env::args().skip(1);
    let Some(path) = args.next() else {
        eprintln!("Uso: arqgen-vertical SOLICITUD.json\nVista previa nativa de cotas Z declaradas; NO APTO PARA OBRA.");
        process::exit(2);
    };
    if path.starts_with('-') || args.next().is_some() {
        eprintln!("Uso: arqgen-vertical SOLICITUD.json");
        process::exit(2);
    }
    let result = (|| -> Result<String, String> {
        let input = fs::read_to_string(&path).map_err(|error| format!("{path}: {error}"))?;
        let output = declared_vertical_json(&input);
        let response = json::parse_response(&output)?;
        if response.get("status").and_then(json::Value::as_str) != Some("ok") {
            return Err(response
                .get("message")
                .and_then(json::Value::as_str)
                .unwrap_or("No se generó el modelo vertical.")
                .to_string());
        }
        Ok(output)
    })();
    match result {
        Ok(output) => println!("{output}"),
        Err(message) => {
            eprintln!("ARQ GEN: {message}");
            process::exit(1);
        }
    }
}
