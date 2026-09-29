//! Deterministic, single-level schematic house generator.
//! All candidates are validated before evaluation/selection. The bounded
//! multi-seed explorer reuses this same scan; no web-side geometry or scoring.
use crate::airflow;
use crate::exhaust;
use crate::furnishing;
use crate::geometry;
use crate::json::{self, list, number, object, text, Value};
use crate::model::*;
use crate::pressure;
use crate::svg;
use std::collections::{BTreeMap, BTreeSet};

pub fn generate_json(input: &str) -> String {
    let result = (|| {
        let value = json::parse(input)?;
        let request = Request::from_value(&value)?;
        let canonical = value.stringify();
        let hash = stable_hash(&format!("{ENGINE_VERSION}:{canonical}"));
        Ok::<Value, String>(generate(&request, &hash))
    })();
    match result {
        Ok(output) => output.stringify(),
        Err(message) => error_json(&message).stringify(),
    }
}

pub const EXPLORATION_METHOD: &str = "bounded-seed-sweep-v1";
pub const MAX_EXPLORE_SEEDS: u32 = 12;

/// Separate endpoint; the brief-v8 schema and the single-run output stay
/// byte-for-byte compatible with earlier archives. Each seed searches ALL 48
/// validated variants, not merely the three shown by `arq_generate`.
pub fn explore_json(input: &str) -> String {
    let result = (|| -> Result<Value, String> {
        let envelope = json::parse(input)?;
        let Value::Object(fields) = &envelope else {
            return Err("La exploración requiere {input, seed_count}.".into());
        };
        if fields.len() != 2 || !fields.contains_key("input") || !fields.contains_key("seed_count")
        {
            return Err("La exploración solo admite input y seed_count.".into());
        }
        let count = fields["seed_count"]
            .as_number()
            .filter(|n| {
                n.is_finite() && *n == n.trunc() && (2.0..=MAX_EXPLORE_SEEDS as f64).contains(n)
            })
            .ok_or_else(|| format!("seed_count debe ser entero entre 2 y {MAX_EXPLORE_SEEDS}."))?
            as u32;
        explore(&fields["input"], count)
    })();
    match result {
        Ok(output) => {
            let encoded = output.stringify();
            if encoded.len() > 2_000_000 {
                error_json(
                    "La respuesta de la exploración supera 2 MB; reduce el encargo o el lote.",
                )
                .stringify()
            } else {
                encoded
            }
        }
        Err(message) => error_json(&message).stringify(),
    }
}

fn explore(input: &Value, count: u32) -> Result<Value, String> {
    let mut request = Request::from_value(input)?;
    let start_seed = request.seed;
    let site = site_report(&request);
    let mut seed_input = input.clone();
    let mut all = Vec::<Candidate>::new();
    let mut provenance = BTreeMap::<String, u32>::new();
    let mut outcomes = Vec::new();
    let mut totals = BTreeMap::<String, usize>::new();
    let mut total_generated = 0;
    let mut total_rejected = 0;
    let mut first_reasons = Vec::new();
    for offset in 0..count {
        let seed = start_seed.wrapping_add(offset);
        request.seed = seed;
        seed_input.insert("seed", number(seed as f64))?;
        let hash = stable_hash(&format!("{ENGINE_VERSION}:{}", seed_input.stringify()));
        let scan = match &site {
            Ok(site) => scan(&request, &hash, site),
            Err(reasons) => Scan::early(reasons.clone()),
        };
        let rejected = scan.rejected();
        let reasons = if scan.candidates.is_empty() {
            scan.reasons()
        } else {
            Vec::new()
        };
        if offset == 0 {
            first_reasons = reasons.clone();
        }
        total_generated += scan.generated;
        total_rejected += rejected;
        for (reason, amount) in &scan.rejections {
            *totals.entry(reason.clone()).or_default() += amount;
        }
        outcomes.push(object(vec![
            ("seed", number(seed as f64)),
            ("input_hash", text(&hash)),
            (
                "status",
                text(if scan.candidates.is_empty() {
                    "infeasible"
                } else {
                    "ok"
                }),
            ),
            ("generated", number(scan.generated as f64)),
            ("rejected", number(rejected as f64)),
            (
                "rejection_summary",
                rejection_summary_json(&scan.rejections),
            ),
            ("reasons", list(reasons.iter().map(text))),
        ]));
        for candidate in scan.candidates {
            if provenance.insert(candidate.id.clone(), seed).is_some() {
                return Err("Colisión de identidades en el lote; no se puede atribuir una propuesta a su semilla.".into());
            }
            all.push(candidate);
        }
    }
    let mut rejections: Vec<_> = totals.into_iter().collect();
    rejections.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    debug_assert_eq!(total_generated - total_rejected, all.len());
    let viable = all.len();
    let mut front_size = 0;
    let mut chosen = Vec::new();
    if viable > 0 {
        // Across seeds use a mathematically strict partial order. The old
        // epsilon-tolerant single-run ranking is preserved byte-for-byte for
        // existing v8 archives, but its tolerance need not be transitive.
        compute_pareto_layers_exact(&mut all);
        front_size = all.iter().filter(|c| c.pareto_layer == 0).count();
        chosen = choose_diverse(all, 3);
        let site = site.as_ref().expect("validated candidates require a site");
        for candidate in &mut chosen {
            candidate.svg = svg::render(&request.site, site, candidate, &request.rules);
        }
    }
    Ok(object(vec![
        ("status", text(if viable > 0 { "ok" } else { "infeasible" })),
        ("engine_version", text(ENGINE_VERSION)),
        ("request_schema", text(REQUEST_SCHEMA)),
        ("exploration_method", text(EXPLORATION_METHOD)),
        ("base_seed", number(start_seed as f64)),
        ("seed_count", number(count as f64)),
        ("generated", number(total_generated as f64)),
        ("rejected", number(total_rejected as f64)),
        ("valid", number(viable as f64)),
        ("pareto_front_size", number(front_size as f64)),
        ("objectives", list(["area_fit", "circulation_score", "privacy_score", "service_score", "east_bedroom_score"].into_iter().map(text))),
        ("seed_runs", list(outcomes)),
        ("rejection_summary", rejection_summary_json(&rejections)),
        ("reasons", list(first_reasons.iter().map(text))),
        ("alternatives", list(chosen.iter().map(|candidate| object(vec![
            ("seed", number(*provenance.get(&candidate.id).expect("every chosen candidate has a seed") as f64)),
            ("candidate", candidate.to_json()),
        ])))),
        ("notice", text("Exploración ACOTADA de semillas consecutivas (incluye vuelta de u32). Pareto calculado en Rust sobre las cinco métricas heurísticas de TODAS las variantes validadas de este lote; se muestran hasta tres organizaciones separadas geométricamente. No es óptimo global ni prueba de inexistencia de otras soluciones. Contorno y acceso son croquis, no linderos o derechos verificados. Reglas demo sin validez legal; luz natural, ventilación efectiva, caudal entregado y aptitud para obra NO evaluados.")),
    ]))
}

fn stable_hash(value: &str) -> String {
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in value.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

fn site_report(request: &Request) -> Result<SiteReport, Vec<String>> {
    let site = &request.site;
    let rules = &request.rules;
    let setbacks = rules.setbacks;
    let width = site.width - setbacks.left - setbacks.right;
    let depth = site.depth - setbacks.front - setbacks.rear;
    if width <= EPS || depth <= EPS {
        return Err(vec![
            "Los retiros consumen la parcela: no queda superficie edificable.".into(),
        ]);
    }
    let plot_area = site.plot_area();
    let buildable = Rect {
        x: setbacks.left,
        y: setbacks.front,
        w: width,
        h: depth,
    };
    let min_side_width = rules
        .living
        .min_width
        .max(rules.kitchen.min_width)
        .max(rules.bedroom.min_width)
        .max(rules.bathroom.min_width);
    let min_building_width = geometry::gross_corridor_width(rules)
        + 2.0 * (min_side_width + rules.exterior_wall + rules.partition_wall / 2.0);
    if buildable.w + EPS < min_building_width {
        return Err(vec![format!("Ancho edificable {:.2} m: se requieren al menos {:.2} m para dos franjas de locales y un corredor.", buildable.w, min_building_width)]);
    }
    // The opposite rear cut-outs are outside the applicant's drawn parcel;
    // voluntary zones lie inside it. Parsing rejects shared area, including
    // positive slivers, so each intersection with the demo inset is counted
    // exactly once. Setbacks remain bbox-based, NOT internal-edge or legal.
    let unreserved_buildable_area = buildable.area()
        - site
            .notch_rects()
            .map(|notch| notch.intersection_area(buildable))
            .sum::<f64>()
        - site
            .reserved_areas
            .iter()
            .map(|area| area.intersection_area(buildable))
            .sum::<f64>();
    if unreserved_buildable_area <= EPS {
        return Err(vec![
            if site.rear_notches.len() == 1 && site.reserved_areas.is_empty() {
                "El recorte posterior del croquis consume toda la envolvente ilustrativa.".into()
            } else if site.rear_notches.len() == 1 {
                "El recorte posterior y la reserva consumen toda la envolvente ilustrativa.".into()
            } else if site.rear_notches.len() == 2 && site.reserved_areas.is_empty() {
                "Los dos recortes posteriores consumen toda la envolvente ilustrativa.".into()
            } else if site.rear_notches.len() == 2 {
                "Los dos recortes posteriores y las reservas declaradas consumen toda la envolvente ilustrativa.".into()
            } else {
                "El croquis reservado consume toda la envolvente edificable ilustrativa.".into()
            },
        ]);
    }
    let max_footprint = unreserved_buildable_area.min(plot_area * rules.max_coverage);
    let max_built_area = plot_area * rules.max_far;
    let min_program_area = rules.living.area_min
        + rules.kitchen.area_min
        + request.program.bedrooms as f64 * rules.bedroom.area_min
        + request.program.bathrooms as f64 * rules.bathroom.area_min;
    // A conservative lower bound: avoid rejecting a feasible plan before layout.
    let minimum = min_program_area
        + rules.corridor_width
            * rules
                .living
                .min_depth
                .max(rules.kitchen.min_depth)
                .max(rules.bedroom.min_depth)
                .max(rules.bathroom.min_depth);
    if max_footprint + EPS < minimum || max_built_area + EPS < minimum {
        return Err(vec![format!("La ocupación/FAR{} permite como máximo {:.1} / {:.1} m² de huella/área construida; el programa requiere al menos {:.1} m² incluyendo circulación estimada.",
            if site.rear_notches.len() == 1 { " tras recortar la esquina posterior del croquis" }
            else if site.rear_notches.len() == 2 { " tras recortar ambas esquinas posteriores del croquis" }
            else if site.reserved_areas.is_empty() { "" }
            else if site.reserved_areas.len() == 1 { " tras la reserva voluntaria de parcela" }
            else { " tras las dos reservas voluntarias de parcela" },
            max_footprint, max_built_area, minimum)]);
    }
    Ok(SiteReport {
        plot_area,
        buildable,
        unreserved_buildable_area,
        max_footprint,
        max_built_area,
    })
}

// Keep the validated pool so the same 48-variant scan can power both the
// single-run view and the bounded cross-seed Pareto search.
struct Scan {
    candidates: Vec<Candidate>,
    generated: usize,
    rejections: Vec<(String, usize)>,
    early_reasons: Vec<String>,
}
impl Scan {
    fn early(reasons: Vec<String>) -> Self {
        Self {
            candidates: Vec::new(),
            generated: 0,
            rejections: Vec::new(),
            early_reasons: reasons,
        }
    }
    fn rejected(&self) -> usize {
        self.generated - self.candidates.len()
    }
    fn reasons(&self) -> Vec<String> {
        if !self.early_reasons.is_empty() {
            return self.early_reasons.clone();
        }
        self.rejections
            .iter()
            .take(4)
            .map(|(reason, count)| format!("{reason} ({count} variantes)"))
            .collect()
    }
}

pub fn generate(request: &Request, hash: &str) -> Value {
    let site = match site_report(request) {
        Ok(site) => site,
        Err(reasons) => return infeasible_json(hash, request, &reasons, &[], 0),
    };
    let mut scan = scan(request, hash, &site);
    if scan.candidates.is_empty() {
        return infeasible_json(
            hash,
            request,
            &scan.reasons(),
            &scan.rejections,
            scan.generated,
        );
    }
    let invalid = scan.rejected();
    compute_pareto_layers(&mut scan.candidates);
    let mut chosen = choose_diverse(scan.candidates, 3);
    for candidate in &mut chosen {
        candidate.svg = svg::render(&request.site, &site, candidate, &request.rules);
    }
    success_json(
        hash,
        request,
        &site,
        &chosen,
        scan.generated,
        invalid,
        &scan.rejections,
    )
}

fn scan(request: &Request, hash: &str, site: &SiteReport) -> Scan {
    let mut candidates = Vec::new();
    let mut rejected = BTreeMap::<String, usize>::new();
    let mut generated = 0_usize;
    let min_side = request
        .rules
        .living
        .min_width
        .max(request.rules.kitchen.min_width)
        .max(request.rules.bedroom.min_width)
        .max(request.rules.bathroom.min_width);
    let width_min = geometry::gross_corridor_width(&request.rules)
        + 2.0 * (min_side + request.rules.exterior_wall + request.rules.partition_wall / 2.0);
    let width_max = site.buildable.w.min(11.5).min(
        geometry::gross_corridor_width(&request.rules)
            + 2.0
                * (request.rules.bathroom.area_max / request.rules.bathroom.min_depth
                    + request.rules.exterior_wall
                    + request.rules.partition_wall / 2.0),
    );
    if width_max + EPS < width_min {
        return Scan::early(vec![
            "El ancho disponible no admite los mínimos del programa y los baños.".into(),
        ]);
    }
    let mut rng = XorShift::new(request.seed);
    // The same variant enumeration and RNG call sequence produce the same geometry and order.
    for width_slot in 0..4 {
        let jitter = (rng.next_f64() - 0.5) * 0.12;
        let fraction = (0.08 + width_slot as f64 * 0.26 + jitter).clamp(0.0, 1.0);
        let width = width_min + (width_max - width_min) * fraction;
        for compact in [false, true] {
            for pattern in 0..3 {
                for mirrored in [false, true] {
                    let index = generated;
                    generated += 1;
                    match construct(
                        request, site, hash, index, width, pattern, mirrored, compact,
                    ) {
                        Ok(candidate) => candidates.push(candidate),
                        Err(why) => {
                            *rejected.entry(why).or_default() += 1;
                        }
                    }
                }
            }
        }
    }
    let mut rejections: Vec<_> = rejected.into_iter().collect();
    rejections.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    debug_assert_eq!(
        generated - candidates.len(),
        rejections.iter().map(|(_, count)| count).sum()
    );
    Scan {
        candidates,
        generated,
        rejections,
        early_reasons: Vec::new(),
    }
}

fn construct(
    request: &Request,
    site: &SiteReport,
    hash: &str,
    index: usize,
    width: f64,
    pattern: usize,
    mirrored: bool,
    compact: bool,
) -> Result<Candidate, String> {
    let rules = &request.rules;
    let gross_corridor = geometry::gross_corridor_width(rules);
    let side_width = (width - gross_corridor) / 2.0;
    let (mut left, mut right) =
        allocation(request.program.bedrooms, request.program.bathrooms, pattern);
    if mirrored {
        std::mem::swap(&mut left, &mut right);
    }

    let left_depths = depths_for(&left, side_width, rules, compact)?;
    let right_depths = depths_for(&right, side_width, rules, compact)?;
    let left_depth: f64 = left_depths.iter().sum();
    let right_depth: f64 = right_depths.iter().sum();
    let total_depth = left_depth.max(right_depth);
    if total_depth > site.buildable.h + EPS {
        return Err(format!(
            "El programa requiere {:.1} m de fondo bruto y el sitio ofrece {:.1} m.",
            total_depth, site.buildable.h
        ));
    }
    // The access is fixed at the centre of the FRONT parcel edge.
    let x = (request.site.width - width) / 2.0;
    if x < site.buildable.x - EPS || x + width > site.buildable.right() + EPS {
        return Err(
            "El acceso frontal centrado no permite esta anchura bajo los retiros laterales.".into(),
        );
    }
    let y = site.buildable.y;
    let corridor = Rect {
        x: x + side_width,
        y,
        w: gross_corridor,
        h: total_depth,
    };
    let mut rooms = Vec::new();
    fill_side(
        &mut rooms,
        &left,
        &left_depths,
        Side::Left,
        x,
        y,
        side_width,
        request,
    )?;
    fill_side(
        &mut rooms,
        &right,
        &right_depths,
        Side::Right,
        corridor.right(),
        y,
        side_width,
        request,
    )?;
    rooms.sort_by(|a, b| a.kind.id().cmp(&b.kind.id()));
    let layout = geometry::assemble(rooms, corridor, rules)?;
    let approach = validate_candidate(request, site, &layout)?;

    let metrics = metrics(request, &layout);
    let mut warnings = Vec::new();
    if metrics.circulation_ratio > rules.soft_max_ratio + EPS {
        warnings.push(format!(
            "La circulación útil ({:.1} %) supera el objetivo heurístico ({:.0} %).",
            metrics.circulation_ratio * 100.0,
            rules.soft_max_ratio * 100.0
        ));
    }
    if metrics.area_fit < 0.90 {
        warnings.push(format!(
            "Huella/área construida bruta {:.1} m²: el objetivo orientativo es {:.1} m².",
            layout.built_area, request.program.target_built_area
        ));
    }
    warnings.push(format!("Equipamiento esquemático con franja libre de {:.2} m. Baños: reserva 2D, caudal OBJETIVO y presupuesto de presión SOLO HIPOTÉTICOS; dos puntos de referencia interpolados SIN ventilador identificado. No son pérdidas reales ni caudal entregado. No se verifican curva de fabricante, conducto instalado, holgura real, interferencias 3D, descarga segura, ventilación efectiva, accesibilidad ni normativa.", rules.furnishings.min_aisle));
    if rules.bathroom.window_ratio > 0.0 {
        warnings.push(format!("Baños: vano dibujado con objetivo geométrico ILUSTRATIVO de {:.0} % del área útil, separado en planta de la salida de extracción. No es umbral NC 598; antepecho, acristalamiento, obstrucciones exteriores, iluminación natural efectiva y constructibilidad NO EVALUADOS.", rules.bathroom.window_ratio * 100.0));
    }
    if !request.site.reserved_areas.is_empty() {
        warnings.push(format!("{} {} {} SOLO en la huella bruta y el trazado frontal 2D. Su croquis, titularidad y linderos NO están verificados; no se comprueban accesos exteriores, vegetación, servicios ni efectos sobre luz y ventilación.",
            request.site.reserved_areas.len(),
            if request.site.reserved_areas.len() == 1 { "reserva voluntaria" } else { "reservas voluntarias" },
            if request.site.reserved_areas.len() == 1 { "evitada" } else { "evitadas" }));
    }
    if !request.site.rear_notches.is_empty() {
        warnings.push(format!("{} es un croquis autodeclarado, NO un levantamiento de linderos. Retiros demo solo desde la caja envolvente; no se evalúan retiros de los entrantes, acceso vial, luz, ventilación ni capacidad legal.",
            if request.site.rear_notches.len() == 1 { "La parcela en L" } else { "El contorno con dos recortes posteriores" }));
    }
    warnings.push(format!("Trazado frontal {} de {:.2} m: solo se comprobaron sus bandas completas 2D frente a los recortes y zonas reservadas declarados hasta la puerta. NO acredita calle, derecho de paso, cota, pavimento, obstáculos reales, itinerario accesible ni acceso exterior efectivo.",
        if matches!(approach.shape, FrontTrace::Straight) { "recto" } else { "con dos giros declarados" }, approach.width));

    let id = format!("cand-{hash}-{index:02}");
    let mut decisions = vec![Decision {
        entity_id: id.clone(),
        rule: format!("{}@{}", rules.id, rules.version),
        explanation: format!("Organización {} {}, dimensionado {}. Pasillo reservado antes de los locales: {:.2} m brutos y al menos {:.2} m libres tras muros.",
            pattern + 1, if mirrored { "reflejada" } else { "directa" },
            if compact { "mínimo" } else { "preferido" }, corridor.w, rules.corridor_width),
    }];
    decisions.push(Decision {
        entity_id: id.clone(),
        rule: "site.front_approach@user_sketch_unverified".into(),
        explanation: format!("Se comprobaron SOLO en 2D las bandas completas de un trazado frontal {} de {:.2} m, desde el punto del borde x={:.2}, y=0 hasta la puerta x={:.2}, y={:.2} m, sin invadir el recorte ni la reserva declarados. {} NO se han comprobado vía pública, derechos de paso, pendiente, pavimento, barreras, accesibilidad ni continuidad real.",
            if let FrontTrace::Orthogonal { turn_y, .. } = approach.shape {
                format!("ortogonal con dos giros a y={turn_y:.2} m")
            } else { "recto".into() },
            approach.width, approach.front_x, approach.door_x, approach.door_y,
            if approach.segments.is_empty() { "La puerta toca el borde frontal del croquis; no existe franja exterior en este supuesto." } else { "No es un itinerario construido." }),
    });
    for (index, notch) in request.site.rear_notches.iter().enumerate() {
        decisions.push(Decision {
            entity_id: id.clone(),
            rule: "site.plot_outline@user_sketch_unverified".into(),
            explanation: format!("Huella fuera del recorte posterior {} del croquis {}: {:.2} × {:.2} m; área dibujada {:.2} m² para límites demo de ocupación/FAR. NO acredita linderos ni retiros de los entrantes.",
                if notch.side == RearSide::Left { "izquierdo" } else { "derecho" },
                if request.site.rear_notches.len() == 1 { "en L" } else if index == 0 { "con dos esquinas recortadas (1/2)" } else { "con dos esquinas recortadas (2/2)" },
                notch.width, notch.depth, request.site.plot_area()),
        });
    }
    for (index, area) in request.site.reserved_areas.iter().enumerate() {
        decisions.push(Decision {
            entity_id: id.clone(),
            rule: "site.reserved_areas@user_sketch_unverified".into(),
            explanation: format!("Se evitó el solape de la huella y el trazado frontal 2D con la reserva voluntaria {}: x={:.2}, y={:.2}, ancho={:.2}, fondo={:.2} m; croquis declarado SIN levantamiento, ámbito legal ni acceso exterior verificados.", index + 1, area.x, area.y, area.w, area.h),
        });
    }
    for room in &layout.rooms {
        let source = rules.for_kind(room.kind);
        decisions.push(Decision {
            entity_id: room.kind.id(),
            rule: format!("{}.spaces.{}", rules.id, room.kind.key()),
            explanation: format!("{} en zona {}; {:.1} m² útiles (celda bruta {:.1} m²), rango ilustrativo {:.1}–{:.1} m². Puerta {:.2} m; {} objetos con huellas, zonas de uso y ruta de {:.2} m libres frente al barrido. {}",
                room.kind.label(), room.kind.zone(), room.usable.area(), room.rect.area(),
                source.area_min, source.area_max, room.door.width, room.furnishings.len(),
                rules.furnishings.min_aisle,
                if let Some(window) = &room.window {
                    format!("Ventana al {} con superficie {:.2} m² (vano 2D; luz natural y ventilación NO evaluadas).", window.direction, window.width * window.height)
                } else { "Baño sin ventana; iluminación natural no evaluada.".into() }),
        });
        if let Some(exhaust) = &room.exhaust {
            decisions.push(Decision {
                entity_id: room.kind.id(),
                rule: format!("{}.bath_exhaust", rules.id),
                explanation: format!("Reserva de extracción hacia fachada {}: salida en muro exterior y franja en planta hasta punto interior ({:.2} m; máximo ilustrativo {:.2} m). No representa un conducto instalado; sin caudal entregado ni ventilación efectiva verificados.",
                    exhaust.direction, exhaust.run_length, rules.bath_exhaust.max_run),
            });
        }
        if let Some(flow) = &room.airflow {
            let a = flow.assumptions;
            decisions.push(Decision {
                entity_id: room.kind.id(),
                rule: format!("{}.bath_airflow@{}", rules.id, rules.version),
                explanation: format!("Predimensionado NOMINAL: {:.2} m² útiles × {:.2} m de altura SUPUESTA × {:.1} renovaciones/h OBJETIVO = {:.1} m³/h objetivo (volumen {:.1} m³). Comparación con {:.1} m³/h de referencia de ventilador EN AIRE LIBRE, no caudal entregado. Reposición supuesta por puerta: {:.2} m × {:.3} m de holgura = {:.4} m²; {:.2} m/s ≤ {:.2} m/s. Sección rectangular IDEALIZADA: menor de franja y salida ({:.2} m) × {:.2} m de alto = {:.4} m²; {:.2} m/s ≤ {:.2} m/s. Base a {:.2} m ≥ gálibo supuesto {:.2} m; coronación {:.2} m ≤ techo supuesto {:.2} m. No se verifican pérdidas REALES de presión, umbral real, obstáculos en altura, conducto instalado, descarga segura ni ventilación efectiva.",
                    room.usable.area(), a.assumed_ceiling_height, a.target_ach,
                    flow.target_flow_m3h, flow.room_volume_m3, a.fan_free_air_rating,
                    room.door.width, a.door_undercut, flow.transfer_area_m2,
                    flow.transfer_velocity_mps, a.max_transfer_velocity,
                    flow.duct_width_m, a.duct_height, flow.duct_area_m2, flow.duct_velocity_mps,
                    a.max_duct_velocity, a.duct_bottom, a.min_headroom,
                    a.duct_bottom + a.duct_height, a.assumed_ceiling_height),
            });
        }
        if let Some(screen) = &room.pressure {
            let a = screen.assumptions;
            decisions.push(Decision {
                entity_id: room.kind.id(),
                rule: format!("{}.bath_pressure@{}", rules.id, rules.version),
                explanation: format!("Escenario de presión SOLO HIPOTÉTICO a Q objetivo {:.1} m³/h: recorrido 2D hasta fachada + muro = {:.2} m supuestos; diámetro hidráulico ideal {:.3} m; presión dinámica supuesta {:.2} Pa (densidad {:.2} kg/m³). Recto: {:.2} Pa con factor Darcy {:.3}; {} codos con K {:.2}: {:.2} Pa; salida con K {:.2}: {:.2} Pa; reserva {:.1} Pa; TOTAL {:.2} Pa ≤ referencia {:.1} Pa. DOS PUNTOS NOMINALES SIN EQUIPO IDENTIFICADO: 0 Pa / {:.1} m³/h EN AIRE LIBRE y {:.1} Pa / {:.1} m³/h. Capacidad de REFERENCIA lineal al presupuesto {:.1} m³/h ≥ objetivo; NO representa caudal entregado, curva de fabricante ni pérdidas medidas. No extrapola. No se ha verificado conducto instalado, aire de reposición real, descarga ni ventilación efectiva.",
                    screen.target_flow_m3h, screen.assumed_straight_length_m,
                    screen.assumed_hydraulic_diameter_m, screen.assumed_dynamic_pressure_pa,
                    a.assumed_air_density_kg_m3, screen.assumed_straight_loss_pa,
                    a.assumed_darcy_factor, a.assumed_bend_count, a.assumed_bend_k,
                    screen.assumed_bend_loss_pa, a.assumed_outlet_k, screen.assumed_outlet_loss_pa,
                    a.assumed_reserve_pa, screen.assumed_total_pressure_budget_pa,
                    a.fan_reference_pressure_pa, screen.free_air_flow_m3h,
                    a.fan_reference_pressure_pa, a.fan_reference_flow_m3h,
                    screen.assumed_linear_reference_capacity_m3h),
            });
        }
    }
    decisions.push(Decision {
        entity_id: id.clone(),
        rule: "mvp0.6.feasibility".into(),
        explanation: format!("Validación geométrica, predimensionado nominal y presupuesto hipotético de presión en baños, NO ventilación:  {} locales equipados y un pasillo; huella bruta {:.1} m² ≤ {:.1} m²; área útil {:.1} m² + reserva de muros/vanos {:.1} m²; distancia Manhattan orientativa hasta esquinas (sin considerar muebles) {:.1} m, no evacuación reglamentaria.",
            layout.rooms.len(), layout.built_area, site.max_footprint, layout.usable_area,
            layout.wall_allowance_area, metrics.longest_egress),
    });
    let label = match pattern {
        0 => "Franja de servicios",
        1 => "Habitaciones alternas",
        _ => "Núcleo privado",
    };
    let candidate = Candidate {
        id,
        label: format!(
            "{}{}{}",
            label,
            if mirrored { " · invertida" } else { "" },
            if compact { " · compacta" } else { "" }
        ),
        pattern,
        mirrored,
        compact,
        approach,
        layout,
        metrics,
        pareto_layer: 0,
        decisions,
        warnings,
        svg: String::new(),
    };
    Ok(candidate)
}

fn allocation(beds: u8, baths: u8, pattern: usize) -> (Vec<Kind>, Vec<Kind>) {
    let mut left = vec![Kind::LivingDining];
    let mut right = vec![Kind::Kitchen];
    match pattern {
        0 => {
            if baths >= 1 {
                right.push(Kind::Bathroom(1));
            }
            for i in 1..=beds {
                if i <= 2 {
                    left.push(Kind::Bedroom(i));
                } else {
                    right.push(Kind::Bedroom(i));
                }
            }
            if baths >= 2 {
                right.push(Kind::Bathroom(2));
            }
        }
        1 => {
            for i in 1..=beds {
                if i % 2 == 0 {
                    left.push(Kind::Bedroom(i));
                } else {
                    right.push(Kind::Bedroom(i));
                }
                if i == 1 && baths >= 1 {
                    right.push(Kind::Bathroom(1));
                }
            }
            if baths >= 2 {
                left.push(Kind::Bathroom(2));
            }
        }
        _ => {
            if baths >= 1 {
                left.push(Kind::Bathroom(1));
            }
            for i in 1..=beds {
                if i % 2 == 1 {
                    left.push(Kind::Bedroom(i));
                } else {
                    right.push(Kind::Bedroom(i));
                }
            }
            if baths >= 2 {
                right.push(Kind::Bathroom(2));
            }
        }
    }
    (left, right)
}

fn depths_for(
    kinds: &[Kind],
    gross_width: f64,
    rules: &Rules,
    compact: bool,
) -> Result<Vec<f64>, String> {
    let clear_width = gross_width - rules.exterior_wall - rules.partition_wall / 2.0;
    let mut depths = Vec::new();
    for (index, kind) in kinds.iter().enumerate() {
        let space = rules.for_kind(*kind);
        if clear_width + EPS < space.min_width {
            return Err(format!(
                "{} no alcanza el ancho útil mínimo de {:.2} m.",
                kind.label(),
                space.min_width
            ));
        }
        let target = if compact {
            space.area_min
        } else {
            space.area_pref
        };
        let clear_depth = (target / clear_width).max(space.min_depth);
        if clear_depth * clear_width > space.area_max + EPS {
            return Err(format!(
                "{} excedería el área útil máxima de {:.1} m².",
                kind.label(),
                space.area_max
            ));
        }
        let top = if index == 0 {
            rules.exterior_wall
        } else {
            rules.partition_wall / 2.0
        };
        let bottom = if index + 1 == kinds.len() {
            rules.exterior_wall
        } else {
            rules.partition_wall / 2.0
        };
        depths.push(clear_depth + top + bottom);
    }
    Ok(depths)
}

/// A drawn opening is geometry in a wall band, NOT proof of daylight: sill,
/// glazing, opposite buildings, elevations and illuminance are unknown. The
/// bathroom template reserves a separate exterior-wall pier for its exhaust.
/// If neither slot fits the illustrative opening, reject the variant rather
/// than quietly falling back to a windowless bath.
fn design_window(room: &Room, front: Orientation, rules: &Rules) -> Result<Option<Window>, String> {
    let rule = rules.for_kind(room.kind);
    if rule.window_ratio <= 0.0 {
        return Ok(None);
    }
    let clear = room.usable;
    let width = clear.area() * rule.window_ratio / rules.window_height * 1.01;
    let jamb = rules.corner_clearance;
    if !width.is_finite() || width > clear.h * 0.70 + EPS || width + 2.0 * jamb > clear.h + EPS {
        return Err(format!(
            "{} no admite una ventana exterior con jambas libres suficientes.",
            room.kind.label()
        ));
    }
    let y = if matches!(room.kind, Kind::Bathroom(_)) {
        // Recompute the outlet from the current room instead of trusting a
        // cached snapshot; validation below independently verifies both.
        let outlet = exhaust::design(room, front, rules)?
            .ok_or_else(|| format!("{} sin reserva de extracción.", room.kind.label()))?
            .outlet;
        let slots = [
            (clear.y + jamb, outlet.y - jamb),
            (outlet.bottom() + jamb, clear.bottom() - jamb),
        ];
        let (start, end) = slots
            .into_iter()
            .find(|(start, end)| end - start + EPS >= width)
            .ok_or_else(|| {
                format!(
                    "{}: no cabe ventana de fachada separada de la salida de extracción.",
                    room.kind.label()
                )
            })?;
        (start + end) / 2.0
    } else {
        clear.center().1
    };
    if y - width / 2.0 < clear.y + jamb - EPS || y + width / 2.0 > clear.bottom() - jamb + EPS {
        return Err(format!(
            "{}: ventana exterior sin jambas suficientes.",
            room.kind.label()
        ));
    }
    Ok(Some(Window {
        x: if room.side == Side::Left {
            room.rect.x
        } else {
            room.rect.right()
        },
        y,
        width,
        height: rules.window_height,
        direction: front.side_direction(room.side),
        opening: Rect {
            x: if room.side == Side::Left {
                room.rect.x
            } else {
                room.rect.right() - rules.exterior_wall
            },
            y: y - width / 2.0,
            w: rules.exterior_wall,
            h: width,
        },
    }))
}

fn fill_side(
    output: &mut Vec<Room>,
    kinds: &[Kind],
    depths: &[f64],
    side: Side,
    x: f64,
    start_y: f64,
    width: f64,
    request: &Request,
) -> Result<(), String> {
    let rules = &request.rules;
    let mut y = start_y;
    for (index, (kind, depth)) in kinds.iter().zip(depths).enumerate() {
        let rect = Rect {
            x,
            y,
            w: width,
            h: *depth,
        };
        let usable = geometry::clear_room(rect, side, index == 0, index + 1 == kinds.len(), rules);
        if !usable.valid() {
            return Err(format!(
                "{} no tiene espacio libre después de descontar muros.",
                kind.label()
            ));
        }
        let door_width = if matches!(kind, Kind::Bathroom(_)) {
            rules.bathroom_door
        } else {
            rules.room_door
        };
        let door_y = usable.center().1;
        let partition_half = rules.partition_wall / 2.0;
        let opening = Rect {
            x: if side == Side::Left {
                rect.right() - partition_half
            } else {
                rect.x - partition_half
            },
            y: door_y - door_width / 2.0,
            w: rules.partition_wall,
            h: door_width,
        };
        let door = Door {
            x: if side == Side::Left {
                rect.right()
            } else {
                rect.x
            },
            y: door_y,
            width: door_width,
            side: if side == Side::Left { "right" } else { "left" },
            opening,
            swing: Rect {
                x: if side == Side::Left {
                    usable.right() - door_width
                } else {
                    usable.x
                },
                y: door_y - door_width / 2.0,
                w: door_width,
                h: door_width,
            },
        };
        let mut room = Room {
            kind: *kind,
            side,
            rect,
            usable,
            door,
            window: None,
            exhaust: None,
            airflow: None,
            pressure: None,
            furnishings: Vec::new(),
            access_route: Vec::new(),
        };
        let fit = furnishing::design(&room, rules);
        room.furnishings = fit.furnishings;
        room.access_route = fit.access_route;
        room.exhaust = exhaust::design(&room, request.site.front, rules)?;
        room.window = design_window(&room, request.site.front, rules)?;
        room.airflow = airflow::design(&room, rules)?;
        room.pressure = pressure::design(&room, rules)?;
        output.push(room);
        y += depth;
    }
    Ok(())
}

fn path_to_farthest_corner(room: &Room, plan: &PlanGeometry, rules: &Rules) -> f64 {
    // Conservative Manhattan path from the entrance to the farthest clear corner.
    // Not a statutory egress/accessible-travel calculation.
    let corridor_axis = plan.corridor.x + plan.corridor.w / 2.0;
    room.door.y - plan.entrance.swing.y
        + (corridor_axis - room.door.x).abs()
        + rules.partition_wall / 2.0
        + room.usable.w
        + room.usable.h / 2.0
}

fn validate_candidate(
    request: &Request,
    site: &SiteReport,
    plan: &PlanGeometry,
) -> Result<ApproachSketch, String> {
    let rules = &request.rules;
    let corridor = plan.corridor;
    let rooms = &plan.rooms;
    if !plan.built_area.is_finite()
        || plan.built_area > site.max_footprint + EPS
        || plan.built_area > site.max_built_area + EPS
    {
        return Err("La huella bruta supera la ocupación máxima o el FAR del sitio.".into());
    }
    if !corridor.valid()
        || !site.buildable.contains(corridor)
        || (corridor.w - geometry::gross_corridor_width(rules)).abs() > EPS
    {
        return Err("El corredor bruto con muros no cabe en la envolvente.".into());
    }
    if rooms.len() != 2 + request.program.bedrooms as usize + request.program.bathrooms as usize {
        return Err("El candidato no contiene todas las instancias del programa.".into());
    }
    // This candidate's front door is centred on its corridor (rechecked against
    // the derived entrance below). Only the applicant's chosen 2D trace is
    // tested. Check all full-width bands before gross cells so a blocked route
    // has an explicit reason; no street, passage right or accessibility is proved.
    let approach = request.site.front_route(corridor.center().0, corridor.y)?;
    // Independent gross-footprint recheck: both cut-outs are OUTSIDE the
    // drawn parcel, whereas voluntary zones are INSIDE it. None is a legal
    // setback, and no positive intrusion by a gross cell is accepted.
    for notch in request.site.notch_rects() {
        if corridor.intersection_area(notch) > 0.0 {
            return Err("El corredor invade el recorte posterior fuera del croquis de parcela no verificado.".into());
        }
        if let Some(room) = rooms
            .iter()
            .find(|room| room.rect.intersection_area(notch) > 0.0)
        {
            return Err(format!(
                "{} invade el recorte posterior fuera del croquis de parcela no verificado.",
                room.kind.label()
            ));
        }
    }
    for area in &request.site.reserved_areas {
        if corridor.intersection_area(*area) > 0.0 {
            return Err(
                "El corredor invade la reserva voluntaria de parcela del croquis no verificado."
                    .into(),
            );
        }
        if let Some(room) = rooms
            .iter()
            .find(|room| room.rect.intersection_area(*area) > 0.0)
        {
            return Err(format!(
                "{} invade la reserva voluntaria de parcela del croquis no verificado.",
                room.kind.label()
            ));
        }
    }
    let mut ids = BTreeSet::new();
    let mut gross_sum = corridor.area();
    let mut openings = vec![plan.entrance.opening];
    for (index, room) in rooms.iter().enumerate() {
        if !ids.insert(room.kind.id()) {
            return Err("ID de local duplicado.".into());
        }
        let rect = room.rect;
        let clear = room.usable;
        let rule = rules.for_kind(room.kind);
        if !rect.valid()
            || !clear.valid()
            || !site.buildable.contains(rect)
            || !rect.contains(clear)
            || corridor.overlaps_interior(rect)
            || rooms
                .iter()
                .skip(index + 1)
                .any(|other| rect.overlaps_interior(other.rect))
        {
            return Err(
                "Local o su superficie útil fuera de la envolvente, inválido o superpuesto.".into(),
            );
        }
        let first = !rooms
            .iter()
            .any(|other| other.side == room.side && (other.rect.bottom() - rect.y).abs() <= EPS);
        let last = !rooms
            .iter()
            .any(|other| other.side == room.side && (other.rect.y - rect.bottom()).abs() <= EPS);
        if !clear.approx_eq(geometry::clear_room(rect, room.side, first, last, rules)) {
            return Err(format!(
                "Espesor de muro incorrecto en {}.",
                room.kind.label()
            ));
        }
        if clear.w + EPS < rule.min_width
            || clear.h + EPS < rule.min_depth
            || clear.area() + EPS < rule.area_min
            || clear.area() > rule.area_max + EPS
        {
            return Err(format!(
                "{} incumple áreas/dimensiones útiles mínimas o máximas.",
                room.kind.label()
            ));
        }
        let shared = if room.side == Side::Left {
            (rect.right() - corridor.x).abs()
        } else {
            (rect.x - corridor.right()).abs()
        };
        let expected_x = if room.side == Side::Left {
            rect.right()
        } else {
            rect.x
        };
        let expected_side = if room.side == Side::Left {
            "right"
        } else {
            "left"
        };
        let door = &room.door;
        let min_door = if matches!(room.kind, Kind::Bathroom(_)) {
            rules.bathroom_door
        } else {
            rules.room_door
        };
        let half = rules.partition_wall / 2.0;
        let expected_opening = Rect {
            x: if room.side == Side::Left {
                rect.right() - half
            } else {
                rect.x - half
            },
            y: door.y - door.width / 2.0,
            w: rules.partition_wall,
            h: door.width,
        };
        let expected_swing = Rect {
            x: if room.side == Side::Left {
                clear.right() - door.width
            } else {
                clear.x
            },
            y: door.y - door.width / 2.0,
            w: door.width,
            h: door.width,
        };
        if shared > EPS
            || !door.x.is_finite()
            || !door.y.is_finite()
            || !door.width.is_finite()
            || (door.x - expected_x).abs() > EPS
            || door.side != expected_side
            || (door.y - clear.center().1).abs() > EPS
            || door.width + EPS < min_door
            || (door.width - min_door).abs() > EPS
            || !door.opening.approx_eq(expected_opening)
            || !door.swing.approx_eq(expected_swing)
            || !clear.contains(door.swing)
            || clear.w - door.width + EPS < rules.swing_clearance
            || door.swing.y < clear.y + rules.corner_clearance - EPS
            || door.swing.bottom() > clear.bottom() - rules.corner_clearance + EPS
        {
            return Err(format!(
                "Puerta o barrido sin holgura geométrica en {}.",
                room.kind.label()
            ));
        }
        // Its entire threshold must reach the clear corridor, even across a stepped side.
        let reach = plan
            .corridor_usable
            .iter()
            .filter(|slice| {
                if room.side == Side::Left {
                    (slice.x - door.opening.right()).abs() <= EPS
                } else {
                    (slice.right() - door.opening.x).abs() <= EPS
                }
            })
            .map(|slice| {
                (slice.bottom().min(door.opening.bottom()) - slice.y.max(door.opening.y)).max(0.0)
            })
            .sum::<f64>();
        if reach + EPS < door.width {
            return Err(format!(
                "{} no abre sobre todo el ancho de su puerta hacia el corredor.",
                room.kind.label()
            ));
        }
        openings.push(door.opening);
        let expected_window = design_window(room, request.site.front, rules)?;
        match (&room.window, expected_window) {
            (Some(window), Some(expected)) => {
                if !window.x.is_finite()
                    || !window.y.is_finite()
                    || !window.width.is_finite()
                    || !window.height.is_finite()
                    || (window.x - expected.x).abs() > EPS
                    || (window.y - expected.y).abs() > EPS
                    || (window.width - expected.width).abs() > EPS
                    || (window.height - expected.height).abs() > EPS
                    || window.width * window.height + EPS < clear.area() * rule.window_ratio
                    || window.direction != expected.direction
                    || !window.opening.approx_eq(expected.opening)
                {
                    return Err(format!(
                        "Ventana insuficiente, sin jambas o no exterior en {}.",
                        room.kind.label()
                    ));
                }
                openings.push(window.opening);
            }
            (None, None) => {}
            _ => {
                return Err(format!(
                    "{} sin ventana prevista por el ruleset ilustrativo o con ventana no prevista.",
                    room.kind.label()
                ))
            }
        }
        furnishing::verify(room, rules)?;
        exhaust::verify(room, request.site.front, rules)?;
        airflow::verify(room, rules)?;
        pressure::verify(room, rules)?;
        if let Some(exhaust) = &room.exhaust {
            openings.push(exhaust.outlet);
        }
        let path = path_to_farthest_corner(room, plan, rules);
        if !path.is_finite() || path > rules.max_egress_distance + EPS {
            return Err(format!(
                "{} supera el recorrido orientativo máximo ({:.1} m).",
                room.kind.label(),
                rules.max_egress_distance
            ));
        }
        gross_sum += rect.area();
    }
    let mut expected = BTreeSet::from([Kind::LivingDining.id(), Kind::Kitchen.id()]);
    for i in 1..=request.program.bedrooms {
        expected.insert(Kind::Bedroom(i).id());
    }
    for i in 1..=request.program.bathrooms {
        expected.insert(Kind::Bathroom(i).id());
    }
    if ids != expected {
        return Err("El candidato sustituye u omite una instancia del programa.".into());
    }

    // Recompute the clear corridor and wall partition rather than trusting cached output.
    let derived = geometry::assemble(rooms.clone(), corridor, rules)?;
    if plan.corridor_usable.len() != derived.corridor_usable.len()
        || !plan
            .corridor_usable
            .iter()
            .zip(&derived.corridor_usable)
            .all(|(a, b)| a.approx_eq(*b))
        || plan.wall_zones.len() != derived.wall_zones.len()
        || !plan
            .wall_zones
            .iter()
            .zip(&derived.wall_zones)
            .all(|(a, b)| a.approx_eq(*b))
        || (plan.built_area - gross_sum).abs() > 1e-5
        || (plan.usable_area - derived.usable_area).abs() > 1e-5
        || (plan.circulation_usable_area - derived.circulation_usable_area).abs() > 1e-5
        || (plan.wall_allowance_area - derived.wall_allowance_area).abs() > 1e-5
        || (plan.built_area - plan.usable_area - plan.wall_allowance_area).abs() > 1e-5
    {
        return Err(
            "Balance bruto/útil/reserva de muros o franjas del pasillo inconsistente.".into(),
        );
    }
    if plan
        .corridor_usable
        .iter()
        .any(|r| !r.valid() || !corridor.contains(*r) || r.w + EPS < rules.corridor_width)
    {
        return Err("Ancho libre de pasillo insuficiente tras el espesor de muro.".into());
    }
    let e = &plan.entrance;
    if !e.opening.approx_eq(derived.entrance.opening)
        || !e.swing.approx_eq(derived.entrance.swing)
        || (e.width - rules.main_door).abs() > EPS
        || !geometry::covered_by(e.opening, &plan.wall_zones)
        || !geometry::covered_by(
            Rect {
                x: e.swing.x - rules.swing_clearance,
                y: e.swing.y,
                w: e.swing.w + 2.0 * rules.swing_clearance,
                h: e.swing.h + rules.swing_clearance,
            },
            &plan.corridor_usable,
        )
    {
        return Err("Acceso principal o barrido no cabe dentro del corredor libre.".into());
    }
    let free: Vec<_> = rooms
        .iter()
        .map(|r| r.usable)
        .chain(plan.corridor_usable.iter().copied())
        .collect();
    for (i, wall) in plan.wall_zones.iter().enumerate() {
        if !wall.valid()
            || !site.buildable.contains(*wall)
            || !request.site.contains_gross_rect(*wall)
            || free.iter().any(|r| wall.overlaps_interior(*r))
            || plan
                .wall_zones
                .iter()
                .skip(i + 1)
                .any(|other| wall.overlaps_interior(*other))
        {
            return Err(
                "Franjas de muro solapadas, fuera de huella o invadiendo área útil.".into(),
            );
        }
    }
    for (i, opening) in openings.iter().enumerate() {
        if !geometry::covered_by(*opening, &plan.wall_zones)
            || openings
                .iter()
                .skip(i + 1)
                .any(|other| opening.overlaps_interior(*other))
        {
            return Err("Vanos superpuestos o que no atraviesan una franja de muro.".into());
        }
    }
    Ok(approach)
}

fn metrics(request: &Request, plan: &PlanGeometry) -> Metrics {
    let rooms = &plan.rooms;
    let ratio = plan.circulation_usable_area / plan.usable_area;
    let area_fit = (1.0
        - (plan.built_area - request.program.target_built_area).abs()
            / request.program.target_built_area)
        .max(0.0);
    let circulation_score = if ratio <= request.rules.soft_max_ratio {
        1.0
    } else {
        (1.0 - (ratio - request.rules.soft_max_ratio) * 4.0).max(0.0)
    };
    let beds: Vec<_> = rooms
        .iter()
        .filter(|r| matches!(r.kind, Kind::Bedroom(_)))
        .collect();
    let privacy_score = beds
        .iter()
        .map(|room| ((room.usable.center().1 - plan.corridor.y) / plan.corridor.h).clamp(0.0, 1.0))
        .sum::<f64>()
        / beds.len() as f64;
    let east_bedroom_score = beds
        .iter()
        .filter(|room| room.window.as_ref().is_some_and(|w| w.direction == "E"))
        .count() as f64
        / beds.len() as f64;
    let kitchen = rooms
        .iter()
        .find(|room| room.kind == Kind::Kitchen)
        .unwrap(); // validated count
    let bathroom = rooms
        .iter()
        .find(|room| room.kind == Kind::Bathroom(1))
        .unwrap();
    let (kx, ky) = kitchen.usable.center();
    let (bx, by) = bathroom.usable.center();
    let service_score = (1.0 - ((kx - bx).abs() + (ky - by).abs()) / 15.0).clamp(0.0, 1.0);
    let longest_egress = rooms
        .iter()
        .map(|r| path_to_farthest_corner(r, plan, &request.rules))
        .fold(0.0, f64::max);
    Metrics {
        area_fit,
        circulation_score,
        privacy_score,
        service_score,
        east_bedroom_score,
        circulation_ratio: ratio,
        longest_egress,
    }
}

fn dominates(a: &Metrics, b: &Metrics) -> bool {
    let av = a.vector();
    let bv = b.vector();
    av.iter().zip(bv.iter()).all(|(x, y)| x + EPS >= *y)
        && av.iter().zip(bv.iter()).any(|(x, y)| *x > *y + EPS)
}

fn dominates_exact(a: &Metrics, b: &Metrics) -> bool {
    let av = a.vector();
    let bv = b.vector();
    av.iter().zip(bv.iter()).all(|(x, y)| x >= y) && av.iter().zip(bv.iter()).any(|(x, y)| x > y)
}

fn compute_pareto_layers(candidates: &mut [Candidate]) {
    compute_layers(candidates, dominates); // preserve v8 single-run ranking
}
fn compute_pareto_layers_exact(candidates: &mut [Candidate]) {
    compute_layers(candidates, dominates_exact); // strict cross-seed partial order
}
fn compute_layers(candidates: &mut [Candidate], relation: fn(&Metrics, &Metrics) -> bool) {
    let mut remaining: Vec<usize> = (0..candidates.len()).collect();
    let mut layer = 0;
    while !remaining.is_empty() {
        let front: Vec<usize> = remaining
            .iter()
            .copied()
            .filter(|&i| {
                !remaining
                    .iter()
                    .any(|&j| i != j && relation(&candidates[j].metrics, &candidates[i].metrics))
            })
            .collect();
        // The strict relation always has a front. The historical epsilon
        // relation is kept only for single-run compatibility.
        if front.is_empty() {
            break;
        }
        for &i in &front {
            candidates[i].pareto_layer = layer;
        }
        remaining.retain(|i| !front.contains(i));
        layer += 1;
    }
}

fn layout_distance(a: &Candidate, b: &Candidate) -> f64 {
    let mut sum = (a.layout.corridor.w - b.layout.corridor.w).abs();
    for room in &a.layout.rooms {
        if let Some(other) = b.layout.rooms.iter().find(|r| r.kind == room.kind) {
            let (ax, ay) = room.rect.center();
            let (bx, by) = other.rect.center();
            sum += (ax - bx).abs() + (ay - by).abs();
        }
    }
    sum / a.layout.rooms.len() as f64
}

fn choose_diverse(mut candidates: Vec<Candidate>, count: usize) -> Vec<Candidate> {
    candidates.sort_by(|a, b| {
        a.pareto_layer
            .cmp(&b.pareto_layer)
            .then_with(|| b.metrics.area_fit.total_cmp(&a.metrics.area_fit))
            .then_with(|| a.id.cmp(&b.id))
    });
    let mut chosen: Vec<Candidate> = Vec::new();
    if !candidates.is_empty() {
        chosen.push(candidates.remove(0));
    }
    while chosen.len() < count {
        let mut best: Option<(usize, usize, bool, f64)> = None;
        for (i, candidate) in candidates.iter().enumerate() {
            let distance = chosen
                .iter()
                .map(|s| layout_distance(s, candidate))
                .fold(f64::INFINITY, f64::min);
            if distance < 0.75 {
                continue;
            }
            let new_pattern = !chosen.iter().any(|s| s.pattern == candidate.pattern);
            match best {
                None => best = Some((i, candidate.pareto_layer, new_pattern, distance)),
                Some((_, old_layer, old_pattern, old_distance)) => {
                    if candidate.pareto_layer < old_layer
                        || (candidate.pareto_layer == old_layer && new_pattern && !old_pattern)
                        || (candidate.pareto_layer == old_layer
                            && new_pattern == old_pattern
                            && distance > old_distance + EPS)
                    {
                        best = Some((i, candidate.pareto_layer, new_pattern, distance));
                    }
                }
            }
        }
        match best {
            Some((index, _, _, _)) => chosen.push(candidates.remove(index)),
            None => break,
        }
    }
    chosen
}

struct XorShift(u32);
impl XorShift {
    fn new(seed: u32) -> Self {
        Self(if seed == 0 { 0x6d2b79f5 } else { seed })
    }
    fn next_f64(&mut self) -> f64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        self.0 = x;
        x as f64 / u32::MAX as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pareto_is_partial_order() {
        let a = Metrics {
            area_fit: 0.8,
            circulation_score: 1.0,
            privacy_score: 0.7,
            service_score: 0.8,
            east_bedroom_score: 1.0,
            circulation_ratio: 0.12,
            longest_egress: 10.0,
        };
        let mut b = a.clone();
        b.area_fit = 0.7;
        assert!(dominates(&a, &b));
        assert!(!dominates(&b, &a));
        b.service_score = 0.9;
        assert!(!dominates(&a, &b));
    }

    #[test]
    fn strict_batch_front_contains_exactly_the_nondominated_validated_pool() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let mut request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let mut candidates = Vec::new();
        for seed in 42..45 {
            request.seed = seed;
            let scanned = scan(&request, &format!("test-{seed}"), &site);
            assert_eq!(scanned.generated, 48);
            candidates.extend(scanned.candidates);
        }
        compute_pareto_layers_exact(&mut candidates);
        let front = candidates.iter().filter(|a| a.pareto_layer == 0).count();
        assert!(front > 0);
        for a in &candidates {
            let dominated = candidates
                .iter()
                .any(|b| a.id != b.id && dominates_exact(&b.metrics, &a.metrics));
            assert_eq!(a.pareto_layer == 0, !dominated);
            if a.pareto_layer > 0 {
                assert!(candidates
                    .iter()
                    .any(|b| b.pareto_layer < a.pareto_layer
                        && dominates_exact(&b.metrics, &a.metrics)));
            }
        }
        assert_eq!(
            front,
            explore(&root, 3)
                .unwrap()
                .get("pareto_front_size")
                .unwrap()
                .as_number()
                .unwrap() as usize
        );
    }

    #[test]
    fn rejects_corrupt_door_and_window_after_layout() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        let rules = json::parse(include_str!("../../knowledge/generic-house.json")).unwrap();
        root.insert("rules", rules).unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let mut candidate = construct(&request, &site, "test", 0, 9.0, 0, false, false).unwrap();
        let original = candidate.layout.rooms[0].door.x;
        candidate.layout.rooms[0].door.x += 0.5;
        assert!(validate_candidate(&request, &site, &candidate.layout).is_err());
        candidate.layout.rooms[0].door.x = original;
        let room = candidate
            .layout
            .rooms
            .iter_mut()
            .find(|room| room.window.is_some())
            .unwrap();
        room.window.as_mut().unwrap().direction = "N";
        assert!(validate_candidate(&request, &site, &candidate.layout).is_err());
    }

    #[test]
    fn a_new_user_reservation_invalidates_a_previously_generated_footprint() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let mut request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let layout = construct(&request, &site, "reservation-test", 0, 9.0, 0, false, false)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &layout).is_ok());
        request.site.reserved_areas.push(Rect {
            x: layout.corridor.center().0 - 0.25,
            y: layout.corridor.y + 0.2,
            w: 0.5,
            h: 0.5,
        });
        let site_with_reservation = site_report(&request).unwrap();
        assert!(
            validate_candidate(&request, &site_with_reservation, &layout)
                .unwrap_err()
                .contains("corredor invade la reserva")
        );
        request.site.reserved_areas[0] = Rect {
            x: layout.rooms[0].usable.center().0 - 0.25,
            y: layout.rooms[0].usable.center().1 - 0.25,
            w: 0.5,
            h: 0.5,
        };
        let site_with_reservation = site_report(&request).unwrap();
        assert!(
            validate_candidate(&request, &site_with_reservation, &layout)
                .unwrap_err()
                .contains("invade la reserva")
        );
    }

    #[test]
    fn a_new_rear_plot_cutout_invalidates_an_existing_gross_footprint() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let mut request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let layout = construct(&request, &site, "plot-cutout-test", 0, 9.0, 0, false, false)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &layout).is_ok());
        request.site.rear_notches.push(RearNotch {
            side: RearSide::Left,
            width: 6.0,
            depth: 10.0,
        });
        let changed_site = site_report(&request).unwrap();
        let rejection = validate_candidate(&request, &changed_site, &layout).unwrap_err();
        assert!(rejection.contains("recorte posterior"), "{rejection}");
    }

    #[test]
    fn a_second_rear_cutout_cannot_intrude_even_a_tiny_amount_into_gross_cells() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let mut request = Request::from_value(&root).unwrap();
        let plain = site_report(&request).unwrap();
        let layout = construct(&request, &plain, "two-cuts", 0, 9.0, 0, false, false)
            .unwrap()
            .layout;
        request.site.rear_notches.push(RearNotch {
            side: RearSide::Left,
            width: 1.0,
            depth: 1.0,
        });
        request.site.rear_notches.push(RearNotch {
            side: RearSide::Right,
            width: request.site.width - layout.corridor.right() + 0.1,
            depth: request.site.depth - layout.corridor.bottom(),
        });
        let tangent = site_report(&request).unwrap();
        assert!(validate_candidate(&request, &tangent, &layout).is_ok());
        request.site.rear_notches[1].depth += 1e-8;
        let intruding = site_report(&request).unwrap();
        let reason = validate_candidate(&request, &intruding, &layout).unwrap_err();
        assert!(reason.contains("recorte posterior"), "{reason}");
    }

    #[test]
    fn bathroom_window_outlet_and_shower_are_revalidated_after_layout() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let original = construct(&request, &site, "bath-window-test", 0, 9.0, 0, false, false)
            .unwrap()
            .layout;
        let bath_index = original
            .rooms
            .iter()
            .position(|r| matches!(r.kind, Kind::Bathroom(_)))
            .unwrap();
        assert!(validate_candidate(&request, &site, &original).is_ok());

        let mut missing = original.clone();
        missing.rooms[bath_index].window = None;
        assert!(validate_candidate(&request, &site, &missing).is_err());

        let mut shifted = original.clone();
        shifted.rooms[bath_index].window.as_mut().unwrap().y += 0.20;
        assert!(validate_candidate(&request, &site, &shifted).is_err());

        let mut overlap = original.clone();
        let outlet_y = overlap.rooms[bath_index].exhaust.as_ref().unwrap().outlet.y;
        let window = overlap.rooms[bath_index].window.as_mut().unwrap();
        window.opening.y = outlet_y;
        window.y = outlet_y + window.width / 2.0;
        assert!(validate_candidate(&request, &site, &overlap).is_err());

        let mut obstructed = original.clone();
        let side = obstructed.rooms[bath_index].side;
        let shower = obstructed.rooms[bath_index]
            .furnishings
            .iter_mut()
            .find(|fixture| fixture.kind == "shower")
            .unwrap();
        shower.footprint.x += if side == Side::Left { -0.10 } else { 0.10 };
        assert!(validate_candidate(&request, &site, &obstructed).is_err());

        // If a different arrangement puts the outlet near the front jamb,
        // the deterministic design selects the rear facade slot instead.
        let mut alternative = original.rooms[bath_index].clone();
        let top = alternative.usable.y;
        alternative
            .furnishings
            .iter_mut()
            .find(|f| f.kind == "shower")
            .unwrap()
            .footprint
            .h = 0.40;
        alternative
            .furnishings
            .iter_mut()
            .find(|f| f.kind == "toilet")
            .unwrap()
            .footprint
            .y = top + 0.80;
        let outlet = exhaust::design(&alternative, request.site.front, &request.rules)
            .unwrap()
            .unwrap()
            .outlet;
        let window = design_window(&alternative, request.site.front, &request.rules)
            .unwrap()
            .unwrap();
        assert!(window.opening.y > outlet.bottom() + request.rules.corner_clearance - EPS);
    }

    #[test]
    fn altered_wall_balance_and_swing_never_pass_validation() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let baseline = construct(&request, &site, "wall-test", 0, 9.0, 0, false, true)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &baseline).is_ok());
        let mut changed = baseline.clone();
        changed.wall_zones[0].x += 0.10;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.usable_area += 0.10;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.corridor_usable[0].w -= 0.10;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[0].door.swing.x -= 0.50;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[0].door.opening.y += 0.50;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.entrance.swing.y += 0.50;
        assert!(validate_candidate(&request, &site, &changed).is_err());
    }

    #[test]
    fn changed_fixture_clearance_route_and_rule_snapshot_are_rejected() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let baseline = construct(&request, &site, "fixture-test", 0, 9.0, 0, true, true)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &baseline).is_ok());
        let mut changed = baseline.clone();
        changed.rooms[0].furnishings[0].footprint.x += 0.10;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[0].furnishings[0].use_zones[0].y += 0.10;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[0].access_route[1].h -= 0.10;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[0].furnishings.pop();
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed_rules = request.clone();
        changed_rules.rules.furnishings.bed.width += 0.05;
        assert!(validate_candidate(&changed_rules, &site, &baseline).is_err());
    }

    #[test]
    fn mutated_nominal_airflow_intermediates_and_rule_snapshots_are_rejected() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let baseline = construct(&request, &site, "airflow-test", 0, 9.0, 2, true, false)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &baseline).is_ok());
        let bath_index = baseline
            .rooms
            .iter()
            .position(|room| matches!(room.kind, Kind::Bathroom(_)))
            .unwrap();
        for field in 0..16 {
            let mut changed = baseline.clone();
            let flow = changed.rooms[bath_index].airflow.as_mut().unwrap();
            match field {
                0 => flow.room_volume_m3 += 0.1,
                1 => flow.target_flow_m3h += 0.1,
                2 => flow.transfer_area_m2 += 0.01,
                3 => flow.transfer_velocity_mps += 0.1,
                4 => flow.duct_width_m += 0.01,
                5 => flow.duct_area_m2 += 0.01,
                6 => flow.duct_velocity_mps = f64::NAN,
                7 => flow.assumptions.target_ach += 0.1,
                8 => flow.assumptions.assumed_ceiling_height += 0.1,
                9 => flow.assumptions.fan_free_air_rating += 0.1,
                10 => flow.assumptions.door_undercut += 0.001,
                11 => flow.assumptions.max_transfer_velocity += 0.1,
                12 => flow.assumptions.duct_height += 0.01,
                13 => flow.assumptions.duct_bottom += 0.01,
                14 => flow.assumptions.min_headroom += 0.01,
                15 => flow.assumptions.max_duct_velocity += 0.1,
                _ => unreachable!(),
            }
            assert!(
                validate_candidate(&request, &site, &changed).is_err(),
                "alteración no detectada: {field}"
            );
        }
        let mut changed = baseline.clone();
        changed.rooms[bath_index].airflow = None;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        let other_index = baseline
            .rooms
            .iter()
            .position(|room| !matches!(room.kind, Kind::Bathroom(_)))
            .unwrap();
        changed.rooms[other_index].airflow = baseline.rooms[bath_index].airflow.clone();
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed_rules = request.clone();
        changed_rules.rules.bath_airflow.target_ach += 0.1;
        assert!(validate_candidate(&changed_rules, &site, &baseline).is_err());
        let mut changed_rules = request.clone();
        changed_rules.rules.bath_airflow.duct_bottom += 0.01;
        assert!(validate_candidate(&changed_rules, &site, &baseline).is_err());
    }

    #[test]
    fn pressure_snapshots_and_intermediates_cannot_be_changed_after_validation() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let baseline = construct(&request, &site, "pressure-test", 0, 9.0, 2, true, false)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &baseline).is_ok());
        let bath_index = baseline
            .rooms
            .iter()
            .position(|room| matches!(room.kind, Kind::Bathroom(_)))
            .unwrap();
        for field in 0..18 {
            let mut changed = baseline.clone();
            let screen = changed.rooms[bath_index].pressure.as_mut().unwrap();
            match field {
                0 => screen.assumptions.fan_reference_pressure_pa += 0.1,
                1 => screen.assumptions.fan_reference_flow_m3h += 0.1,
                2 => screen.assumptions.assumed_air_density_kg_m3 += 0.01,
                3 => screen.assumptions.assumed_darcy_factor += 0.01,
                4 => screen.assumptions.assumed_bend_count += 1,
                5 => screen.assumptions.assumed_bend_k += 0.1,
                6 => screen.assumptions.assumed_outlet_k += 0.1,
                7 => screen.assumptions.assumed_reserve_pa += 0.1,
                8 => screen.free_air_flow_m3h += 0.1,
                9 => screen.target_flow_m3h += 0.1,
                10 => screen.assumed_straight_length_m += 0.1,
                11 => screen.assumed_hydraulic_diameter_m += 0.01,
                12 => screen.assumed_dynamic_pressure_pa += 0.1,
                13 => screen.assumed_straight_loss_pa += 0.1,
                14 => screen.assumed_bend_loss_pa += 0.1,
                15 => screen.assumed_outlet_loss_pa += 0.1,
                16 => screen.assumed_total_pressure_budget_pa = f64::NAN,
                17 => screen.assumed_linear_reference_capacity_m3h += 0.1,
                _ => unreachable!(),
            }
            assert!(
                validate_candidate(&request, &site, &changed).is_err(),
                "alteración de presión no detectada: {field}"
            );
        }
        let mut changed = baseline.clone();
        changed.rooms[bath_index].pressure = None;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        let other_index = baseline
            .rooms
            .iter()
            .position(|room| !matches!(room.kind, Kind::Bathroom(_)))
            .unwrap();
        changed.rooms[other_index].pressure = baseline.rooms[bath_index].pressure.clone();
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed_rules = request.clone();
        changed_rules.rules.bath_pressure.assumed_reserve_pa += 1.0;
        assert!(validate_candidate(&changed_rules, &site, &baseline).is_err());
        let mut changed_rules = request.clone();
        changed_rules.rules.bath_pressure.assumed_bend_count += 1;
        assert!(validate_candidate(&changed_rules, &site, &baseline).is_err());
    }

    #[test]
    fn altered_exhaust_outlet_pickup_route_and_rule_snapshot_are_rejected() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let baseline = construct(&request, &site, "exhaust-test", 0, 9.0, 2, true, false)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &baseline).is_ok());
        let bath_index = baseline
            .rooms
            .iter()
            .position(|room| matches!(room.kind, Kind::Bathroom(_)))
            .unwrap();
        let mut changed = baseline.clone();
        changed.rooms[bath_index].exhaust.as_mut().unwrap().outlet.x += 0.05;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[bath_index].exhaust.as_mut().unwrap().route.w -= 0.05;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[bath_index].exhaust.as_mut().unwrap().pickup.y += 0.05;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[bath_index]
            .exhaust
            .as_mut()
            .unwrap()
            .run_length += 0.05;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[bath_index]
            .exhaust
            .as_mut()
            .unwrap()
            .run_length = f64::NAN;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[bath_index]
            .exhaust
            .as_mut()
            .unwrap()
            .direction = "N";
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed = baseline.clone();
        changed.rooms[bath_index].exhaust = None;
        assert!(validate_candidate(&request, &site, &changed).is_err());
        let mut changed_rules = request.clone();
        changed_rules.rules.bath_exhaust.outlet_span += 0.03;
        assert!(validate_candidate(&changed_rules, &site, &baseline).is_err());
    }

    #[test]
    fn second_zone_tangent_to_gross_corridor_allows_contact_but_not_a_tiny_intrusion() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let mut request = Request::from_value(&root).unwrap();
        let baseline_site = site_report(&request).unwrap();
        let layout = construct(
            &request,
            &baseline_site,
            "second-zone",
            0,
            9.0,
            0,
            false,
            false,
        )
        .unwrap()
        .layout;
        request.site.reserved_areas.push(Rect {
            x: 0.0,
            y: 0.0,
            w: 1.0,
            h: 1.0,
        });
        request.site.reserved_areas.push(Rect {
            x: layout.corridor.x,
            y: layout.corridor.y - 1.0,
            w: 0.1,
            h: 1.0,
        });
        let touching = site_report(&request).unwrap();
        assert!(validate_candidate(&request, &touching, &layout).is_ok());
        request.site.reserved_areas[1].h += 1e-8;
        let changed_site = site_report(&request).unwrap();
        let rejection = validate_candidate(&request, &changed_site, &layout).unwrap_err();
        assert!(
            rejection.contains("corredor invade la reserva"),
            "{rejection}"
        );
    }

    #[test]
    fn a_front_reservation_invalidates_an_existing_plan_without_touching_its_footprint() {
        let mut root = json::parse(include_str!("../../examples/rectangular.json")).unwrap();
        root.insert(
            "rules",
            json::parse(include_str!("../../knowledge/generic-house.json")).unwrap(),
        )
        .unwrap();
        let mut request = Request::from_value(&root).unwrap();
        let site = site_report(&request).unwrap();
        let layout = construct(&request, &site, "approach-test", 0, 9.0, 0, false, false)
            .unwrap()
            .layout;
        assert!(validate_candidate(&request, &site, &layout).is_ok());
        request.site.reserved_areas.push(Rect {
            x: layout.corridor.center().0 - 0.25,
            y: 1.0,
            w: 0.5,
            h: 1.0,
        });
        let changed_site = site_report(&request).unwrap();
        assert!(
            (changed_site.unreserved_buildable_area - site.unreserved_buildable_area).abs() < EPS
        );
        let err = validate_candidate(&request, &changed_site, &layout).unwrap_err();
        assert!(err.contains("franja frontal recta"), "{err}");
    }
}
