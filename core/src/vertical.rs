//! Opt-in native, single-level vertical declaration. This is NOT an elevation,
//! section, roof model, second storey, or code-compliance check. The source of
//! each plan opening is a freshly replayed, validated v8 Rust candidate.
use crate::engine::generate_json;
use crate::json::{self, list, number, object, text, Value};
use std::collections::{BTreeMap, BTreeSet};

pub const REQUEST_FORMAT: &str = "arqgen-declared-vertical-request-v1";
pub const MODEL_FORMAT: &str = "arqgen-declared-vertical-model-v1";
const TYPOLOGY: &str = "single_family_house";
const DATUM: &str = "assumed_local_datum_not_surveyed";
const PROVENANCE: &str = "illustrative_assumption_not_measured";

struct Declaration {
    floor_z_m: f64,
    wall_top_z_m: f64,
    entry_head_above_floor_m: f64,
    window_sill_above_floor_m: BTreeMap<String, f64>,
}

fn exact_object<'a>(
    value: &'a Value,
    keys: &[&str],
    context: &str,
) -> Result<&'a BTreeMap<String, Value>, String> {
    let Value::Object(fields) = value else {
        return Err(format!("{context} debe ser un objeto JSON."));
    };
    if fields.len() != keys.len() || keys.iter().any(|key| !fields.contains_key(*key)) {
        return Err(format!(
            "{context}: campos ausentes o desconocidos; se admiten solo {}.",
            keys.join(", ")
        ));
    }
    Ok(fields)
}

fn required_string<'a>(fields: &'a BTreeMap<String, Value>, key: &str) -> Result<&'a str, String> {
    fields
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("{key} debe ser una cadena."))
}

fn required_number(fields: &BTreeMap<String, Value>, key: &str) -> Result<f64, String> {
    fields
        .get(key)
        .and_then(Value::as_number)
        .filter(|value| value.is_finite())
        .ok_or_else(|| format!("{key} debe ser un número finito."))
}

impl Declaration {
    fn parse(value: &Value) -> Result<Self, String> {
        let fields = exact_object(
            value,
            &[
                "datum",
                "height_provenance",
                "floor_z_m",
                "wall_top_z_m",
                "entry_head_above_floor_m",
                "window_sill_above_floor_m",
            ],
            "declared_vertical",
        )?;
        if required_string(fields, "datum")? != DATUM {
            return Err("datum debe declarar una referencia local supuesta, no levantada.".into());
        }
        if required_string(fields, "height_provenance")? != PROVENANCE {
            return Err(
                "height_provenance debe declarar una hipótesis ilustrativa no medida.".into(),
            );
        }
        let floor_z_m = required_number(fields, "floor_z_m")?;
        let wall_top_z_m = required_number(fields, "wall_top_z_m")?;
        let entry_head_above_floor_m = required_number(fields, "entry_head_above_floor_m")?;
        // Data-safety bounds, NOT regulatory dimensions. The 1 µm lower bound
        // prevents a positive but sub-serialization-height opening from
        // becoming a zero-height door after numeric normalization.
        if !(-1000.0..=1000.0).contains(&floor_z_m)
            || wall_top_z_m - floor_z_m < 0.000_001
            || wall_top_z_m - floor_z_m > 100.0
            || entry_head_above_floor_m < 0.000_001
            || entry_head_above_floor_m > wall_top_z_m - floor_z_m
        {
            return Err("Cotas incoherentes: piso local en ±1000 m; muro entre 0,000001 y 100 m de alto; cabeza del acceso dentro del muro y ≥0,000001 m (precisión de datos, NO norma).".into());
        }
        let Value::Object(sills) = &fields["window_sill_above_floor_m"] else {
            return Err("window_sill_above_floor_m debe ser un mapa de local a alféizar.".into());
        };
        if sills.len() > 32 {
            return Err("Demasiados alféizares declarados para una sola planta.".into());
        }
        let mut window_sill_above_floor_m = BTreeMap::new();
        for (room_id, value) in sills {
            let sill = value
                .as_number()
                .filter(|n| n.is_finite() && *n >= 0.0)
                .ok_or_else(|| {
                    format!("Alféizar inválido en {room_id}: debe ser un número ≥ 0.")
                })?;
            if sill > wall_top_z_m - floor_z_m {
                return Err(format!(
                    "Alféizar de {room_id} por encima de la coronación declarada."
                ));
            }
            window_sill_above_floor_m.insert(room_id.clone(), sill);
        }
        Ok(Self {
            floor_z_m,
            wall_top_z_m,
            entry_head_above_floor_m,
            window_sill_above_floor_m,
        })
    }
}

fn source_field<'a>(value: &'a Value, key: &str) -> Result<&'a Value, String> {
    value
        .get(key)
        .ok_or_else(|| format!("Inconsistencia del núcleo v8: falta {key}."))
}

fn source_number(value: &Value, key: &str) -> Result<f64, String> {
    source_field(value, key)?
        .as_number()
        .filter(|n| n.is_finite())
        .ok_or_else(|| format!("Inconsistencia del núcleo v8: {key} no es un número."))
}

fn source_text<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    source_field(value, key)?
        .as_str()
        .ok_or_else(|| format!("Inconsistencia del núcleo v8: {key} no es una cadena."))
}

fn source_array<'a>(value: &'a Value, key: &str) -> Result<&'a [Value], String> {
    source_field(value, key)?
        .as_array()
        .ok_or_else(|| format!("Inconsistencia del núcleo v8: {key} no es una lista."))
}

// Suppress sub-nanometre IEEE-754 addition noise in serialized sums. This is
// numerical formatting, NOT geometric, construction, or surveying precision.
fn summed_z_m(value: f64) -> Value {
    number((value * 1_000_000_000.0).round() / 1_000_000_000.0)
}

fn opening_from_v8(window: &Value) -> Result<Value, String> {
    let opening = source_field(window, "opening")?;
    // This is the original bounded, independently validated PLAN rectangle.
    // It is not an inferred facade plane, vertical section, or surveyed opening.
    if !matches!(opening, Value::Object(_)) {
        return Err("Inconsistencia del núcleo v8: vano de planta inválido.".into());
    }
    for field in ["x", "y", "width", "depth"] {
        let n = source_number(opening, field)?;
        if !n.is_finite() || (field == "width" || field == "depth") && n <= 0.0 {
            return Err("Inconsistencia del núcleo v8: rectángulo de planta inválido.".into());
        }
    }
    Ok(opening.clone())
}

/// Re-run the exact v8 source brief, resolve ONLY a returned candidate ID,
/// and place its existing 2D openings between explicitly declared Z bounds.
/// On error there are no partial levels or speculative openings.
pub fn declared_vertical_json(input: &str) -> String {
    let result = (|| -> Result<Value, String> {
        let envelope = json::parse(input)?; // strict: 256 KiB, bounded depth, no duplicate keys
        let fields = exact_object(
            &envelope,
            &[
                "format",
                "typology",
                "input",
                "candidate_id",
                "declared_vertical",
            ],
            "solicitud vertical",
        )?;
        if required_string(fields, "format")? != REQUEST_FORMAT {
            return Err(format!("format debe ser {REQUEST_FORMAT}."));
        }
        if required_string(fields, "typology")? != TYPOLOGY {
            return Err("Solo se admite vivienda unifamiliar v8 en esta vista previa; hospitales y hoteles NO tienen programa ni geometría generada.".into());
        }
        let candidate_id = required_string(fields, "candidate_id")?;
        if candidate_id.is_empty() || candidate_id.len() > 128 {
            return Err("candidate_id inválido.".into());
        }
        let declared = Declaration::parse(&fields["declared_vertical"])?;
        let generation = json::parse_response(&generate_json(&fields["input"].stringify()))?;
        match generation.get("status").and_then(Value::as_str) {
            Some("ok") => {}
            Some("infeasible") => {
                return Err(
                    "La corrida v8 es inviable: no hay planta a la que vincular las cotas.".into(),
                )
            }
            _ => {
                return Err(format!(
                    "No se pudo reproducir la corrida v8: {}",
                    generation
                        .get("message")
                        .and_then(Value::as_str)
                        .unwrap_or("entrada inválida")
                ))
            }
        }
        let candidate = source_array(&generation, "alternatives")?
            .iter()
            .find(|item| item.get("id").and_then(Value::as_str) == Some(candidate_id))
            .ok_or_else(|| {
                "candidate_id no corresponde a una alternativa publicada por este encargo v8."
                    .to_string()
            })?;
        let rooms = source_array(candidate, "rooms")?;
        let mut expected_sills = BTreeSet::new();
        for room in rooms {
            if room.get("window").is_some() && room.get("window") != Some(&Value::Null) {
                expected_sills.insert(source_text(room, "id")?.to_string());
            }
        }
        let provided_sills: BTreeSet<String> =
            declared.window_sill_above_floor_m.keys().cloned().collect();
        if expected_sills != provided_sills {
            let missing: Vec<_> = expected_sills
                .difference(&provided_sills)
                .cloned()
                .collect();
            let extra: Vec<_> = provided_sills
                .difference(&expected_sills)
                .cloned()
                .collect();
            return Err(format!("Alféizares deben corresponder exactamente a las ventanas v8; faltan: {missing:?}; sobran: {extra:?}."));
        }

        let entry = source_field(candidate, "entrance")?;
        let entry_opening = opening_from_v8(entry)?;
        let mut openings = vec![object(vec![
            ("id", text("main-entry")),
            ("kind", text("entrance")),
            ("room_id", Value::Null),
            ("plan_opening_v8", entry_opening),
            ("bottom_z_m", number(declared.floor_z_m)),
            (
                "top_z_m",
                summed_z_m(declared.floor_z_m + declared.entry_head_above_floor_m),
            ),
            ("height_source", text("explicit_illustrative_assumption")),
        ])];
        for room in rooms {
            let Some(window) = room.get("window").filter(|value| *value != &Value::Null) else {
                continue;
            };
            let room_id = source_text(room, "id")?;
            let sill = declared.window_sill_above_floor_m[room_id];
            let nominal_height = source_number(window, "height")?;
            if nominal_height <= 0.0
                || sill + nominal_height > declared.wall_top_z_m - declared.floor_z_m + 1e-9
            {
                return Err(format!("La ventana de {room_id} sobresale del muro declarado; revisa altura nominal v8 y alféizar."));
            }
            let plan_opening = opening_from_v8(window)?;
            openings.push(object(vec![
                ("id", text(format!("window-{room_id}"))),
                ("kind", text("window")),
                ("room_id", text(room_id)),
                ("plan_opening_v8", plan_opening),
                ("bottom_z_m", summed_z_m(declared.floor_z_m + sill)),
                (
                    "top_z_m",
                    summed_z_m(declared.floor_z_m + sill + nominal_height),
                ),
                ("height_source", text("v8_demo_nominal_window_height")),
            ]));
        }

        let input_hash = source_text(&generation, "input_hash")?;
        let engine_version = source_text(&generation, "engine_version")?;
        let identity = stable_identity(&format!("{MODEL_FORMAT}:{}", envelope.stringify()));
        Ok(object(vec![
            ("status", text("ok")),
            ("format", text(MODEL_FORMAT)),
            ("model_hash", text(identity)),
            ("hash_method", text("fnv1a64_canonical_json_noncryptographic")),
            ("typology", text(TYPOLOGY)),
            ("source", object(vec![
                ("request_schema", text("arqgen-brief-v8")),
                ("engine_version", text(engine_version)),
                ("input_hash", text(input_hash)),
                ("candidate_id", text(candidate_id)),
            ])),
            ("datum", text(DATUM)),
            ("height_provenance", text(PROVENANCE)),
            ("levels", list(vec![object(vec![
                ("level_id", text("L0")),
                ("floor_z_m", number(declared.floor_z_m)),
                ("wall_top_z_m", number(declared.wall_top_z_m)),
                ("room_ids", list(rooms.iter().map(|r| source_text(r, "id").map(text)).collect::<Result<Vec<_>,_>>()?)),
                ("openings", list(openings)),
            ])])),
            ("roof", Value::Null),
            ("vertical_connections", Value::Null),
            ("sections", Value::Null),
            ("facades", Value::Null),
            ("notice", text("NO APTO PARA OBRA. Solo planta L0 de vivienda y cotas Z hipotéticas; no hay levantamiento, terreno, forjados, estructura, cubierta, escaleras, plantas adicionales, alzados, secciones ni comprobación normativa. Los rectángulos de huecos son de la planta v8, no geometría de fachada verificada. La altura nominal de las ventanas proviene del ejemplo v8; los alféizares, acceso, piso y coronación son hipótesis explícitas, no medidas.")),
        ]))
    })();
    match result {
        Ok(value) => value.stringify(),
        Err(message) => object(vec![
            ("status", text("error")),
            ("format", text(MODEL_FORMAT)),
            ("message", text(message)),
            ("levels", list(Vec::<Value>::new())),
        ])
        .stringify(),
    }
}

fn stable_identity(value: &str) -> String {
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in value.bytes() {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}
