//! SVG and JSON are projections of the *same validated* gross/clear geometry.
//! Wall bands and openings are schematic plan-level allowances, never working drawings.
use crate::model::{Candidate, Kind, Orientation, Rect, Rules, Side, Site, SiteReport};
use std::fmt::Write;

fn rect(out: &mut String, r: Rect, fill: &str, stroke: &str, dash: &str) {
    decorated_rect(out, r, "", fill, stroke, 0.055, dash, 1.0);
}

fn decorated_rect(
    out: &mut String,
    r: Rect,
    class: &str,
    fill: &str,
    stroke: &str,
    line: f64,
    dash: &str,
    opacity: f64,
) {
    let _ = write!(out, "<rect class=\"{class}\" x=\"{:.3}\" y=\"{:.3}\" width=\"{:.3}\" height=\"{:.3}\" fill=\"{fill}\" stroke=\"{stroke}\" stroke-width=\"{line:.3}\" opacity=\"{opacity:.2}\" {} />",
        r.x, r.y, r.w, r.h, if dash.is_empty() { String::new() } else { format!("stroke-dasharray=\"{dash}\"") });
}

fn escape_xml(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn plot_path(site: &Site) -> String {
    let mut path = String::new();
    for (index, (x, y)) in site.outline_vertices().into_iter().enumerate() {
        let _ = write!(
            path,
            "{} {:.3} {:.3}",
            if index == 0 { "M" } else { " L" },
            x,
            y
        );
    }
    path.push_str(" Z");
    path
}

pub fn render(site: &Site, analysis: &SiteReport, candidate: &Candidate, rules: &Rules) -> String {
    const SCALE: f64 = 37.0;
    let margin = 1.25;
    let upper = 2.1;
    let w = (site.width + margin * 2.0) * SCALE;
    let h = (site.depth + upper + 1.45) * SCALE;
    let plan = &candidate.layout;
    let mut out = String::with_capacity(18000);
    let _ = write!(out, "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {:.0} {:.0}\" role=\"img\" aria-label=\"Esquema conceptual con reserva de extracción, caudal objetivo y presión supuesta, SIN caudal entregado verificado: {}\">", w, h, escape_xml(&candidate.label));
    out.push_str("<rect width=\"100%\" height=\"100%\" fill=\"#fcfbf8\"/>");
    let _ = write!(out, "<text x=\"{:.0}\" y=\"37\" fill=\"#203b38\" font-family=\"Arial,sans-serif\" font-weight=\"700\" font-size=\"19\">ARQ GEN <tspan fill=\"#74938a\">/</tspan> {}</text>", margin * SCALE, escape_xml(&candidate.label));
    let _ = write!(out, "<text x=\"{:.0}\" y=\"61\" fill=\"#69817b\" font-family=\"Arial,sans-serif\" font-size=\"11\">Una planta · {:.1} m² brutos · {:.1} m² útiles · frente {}</text>", margin * SCALE, plan.built_area, plan.usable_area, site.front.as_str());
    let _ = write!(
        out,
        "<g transform=\"translate({:.2},{:.2}) scale({SCALE})\" font-family=\"Arial,sans-serif\">",
        margin * SCALE,
        upper * SCALE
    );
    let outline = plot_path(site);
    // Clip the demo inset to the submitted ortho-outline (4, 6 or 8 vertices).
    // Bbox-based setbacks are NOT setbacks from either interior edge.
    let _ = write!(
        out,
        "<defs><clipPath id=\"site-plot-clip\"><path d=\"{outline}\"/></clipPath></defs>"
    );
    let _ = write!(
        out,
        "<path d=\"{outline}\" fill=\"#f1f2ea\" stroke=\"none\"/>"
    );
    out.push_str("<g clip-path=\"url(#site-plot-clip)\">");
    rect(
        &mut out,
        analysis.buildable,
        "#faf9f4",
        "#aec7bd",
        "0.12 0.12",
    );
    out.push_str("</g>");
    let _ = write!(out, "<path class=\"site-plot-outline\" d=\"{outline}\" fill=\"none\" stroke=\"#879f91\" stroke-width=\"0.055\" stroke-dasharray=\"0.15 0.10\"/>");
    for notch in site.notch_rects() {
        if notch.w >= 2.0 && notch.h >= 1.0 {
            let _ = write!(out, "<text x=\"{:.3}\" y=\"{:.3}\" text-anchor=\"middle\" font-size=\"0.18\" fill=\"#987452\">FUERA DEL CROQUIS</text>", notch.x + notch.w / 2.0, notch.y + notch.h / 2.0);
        }
    }
    // The applicant's voluntary sketch, not a surveyed or legally mandated
    // exclusion. No height, vegetation, path or daylight effect is modeled.
    for (index, area) in site.reserved_areas.iter().enumerate() {
        decorated_rect(
            &mut out,
            *area,
            "site-reserved-area",
            "#f2dcc9",
            "#ae7047",
            0.055,
            "0.13 0.08",
            0.82,
        );
        if area.w >= 1.2 && area.h >= 0.5 {
            let _ = write!(out, "<text x=\"{:.3}\" y=\"{:.3}\" text-anchor=\"middle\" font-size=\"0.18\" fill=\"#87583b\">RESERVA {}</text>", area.x + area.w / 2.0, area.y + area.h / 2.0, index + 1);
        }
    }

    // Draw only the route whose FULL bands passed the Rust sketch check.
    // Turning corners are bands too, not a zero-width centreline. No paved
    // space, street connection, passage right or accessibility is inferred.
    for band in &candidate.approach.segments {
        decorated_rect(
            &mut out,
            *band,
            "front-approach-strip",
            "#dce9e6",
            "#427b71",
            0.055,
            "0.14 0.08",
            0.78,
        );
    }
    if !candidate.approach.segments.is_empty() {
        let first = candidate.approach.segments[0];
        if first.h >= 1.4 && first.w >= 0.9 {
            let _ = write!(out, "<text class=\"front-approach-label\" x=\"{:.3}\" y=\"{:.3}\" text-anchor=\"middle\" font-size=\"0.15\" fill=\"#356b62\">{}</text>",
                first.center().0, first.center().1,
                if candidate.approach.turns.is_empty() { "FRANJA 2D" } else { "RODEO 2D" });
        }
        for &(x, y) in &candidate.approach.turns {
            let _ = write!(out, "<circle class=\"front-approach-turn\" cx=\"{x:.3}\" cy=\"{y:.3}\" r=\"0.08\" fill=\"#427b71\"/>");
        }
    }
    let _ = write!(out, "<circle class=\"front-approach-contact\" cx=\"{:.3}\" cy=\"0\" r=\"0.10\" fill=\"#427b71\"/>", candidate.approach.front_x);

    // The gross footprint is exactly the union of the disjoint clear and wall rectangles.
    for band in &plan.wall_zones {
        rect(&mut out, *band, "#667971", "none", "");
    }
    for slice in &plan.corridor_usable {
        rect(&mut out, *slice, "#e9eee8", "none", "");
    }
    for room in &plan.rooms {
        let color = match room.kind {
            Kind::LivingDining => "#d9e9de",
            Kind::Kitchen => "#dcebe8",
            Kind::Bedroom(_) => "#e8e6da",
            Kind::Bathroom(_) => "#e2e9ee",
        };
        let _ = write!(
            out,
            "<g data-room-id=\"{}\" class=\"plan-room\">",
            room.kind.id()
        );
        decorated_rect(
            &mut out,
            room.usable,
            "room-floor",
            color,
            "#8aa49a",
            0.055,
            "",
            1.0,
        );
        // The footprints, free-use zones and aisle share the exact validated
        // coordinates serialized to JSON. Dashed overlays stay faint in a
        // standalone SVG and can be toggled in the browser's plan view.
        for route in &room.access_route {
            decorated_rect(
                &mut out,
                *route,
                "access-band",
                "none",
                "#4e9886",
                0.035,
                "0.12 0.09",
                0.14,
            );
        }
        for fixture in &room.furnishings {
            for zone in &fixture.use_zones {
                decorated_rect(
                    &mut out,
                    *zone,
                    "use-clearance",
                    "none",
                    "#b58b5b",
                    0.032,
                    "0.10 0.08",
                    0.18,
                );
            }
            decorated_rect(
                &mut out,
                fixture.footprint,
                "fixture",
                "#f6f2e7",
                "#aa9478",
                0.038,
                "",
                0.88,
            );
        }
        if let Some(exhaust) = &room.exhaust {
            // Symbol for a projected reservation, NOT an installed duct or
            // measured airflow. The outlet crosses the exterior-wall band.
            decorated_rect(
                &mut out,
                exhaust.route,
                "exhaust-route",
                "#b8a7c3",
                "#806991",
                0.025,
                "0.09 0.08",
                0.62,
            );
            decorated_rect(
                &mut out,
                exhaust.pickup,
                "exhaust-pickup",
                "#8b71a2",
                "#f8f4fa",
                0.025,
                "",
                0.85,
            );
            decorated_rect(
                &mut out,
                exhaust.outlet,
                "exhaust-outlet",
                "#78568b",
                "#fff8fa",
                0.022,
                "",
                1.0,
            );
        }
        let (cx, cy) = room.usable.center();
        match room.kind {
            Kind::LivingDining => {
                let _ = write!(out, "<text x=\"{cx:.3}\" y=\"{:.3}\" text-anchor=\"middle\" font-size=\"0.29\" font-weight=\"700\" fill=\"#24433c\"><tspan x=\"{cx:.3}\">Sala /</tspan><tspan x=\"{cx:.3}\" dy=\"0.36\">comedor</tspan></text>", cy - 0.28);
            }
            _ => {
                let _ = write!(out, "<text x=\"{cx:.3}\" y=\"{:.3}\" text-anchor=\"middle\" font-size=\"0.28\" font-weight=\"700\" fill=\"#24433c\">{}</text>", cy - 0.12, escape_xml(&room.kind.label()));
            }
        }
        let _ = write!(out, "<text x=\"{cx:.3}\" y=\"{:.3}\" text-anchor=\"middle\" font-size=\"0.21\" fill=\"#58746b\">{:.1} m² útiles</text>", cy + 0.43, room.usable.area());
        out.push_str("</g>");
    }
    // The verified apertures cross the wall bands. Arcs indicate empty-room sweep only.
    for room in &plan.rooms {
        let d = &room.door;
        rect(&mut out, d.opening, "#fcfbf8", "none", "");
        let (hinge, end, sweep) = if room.side == Side::Left {
            (room.usable.right(), room.usable.right() - d.width, 1)
        } else {
            (room.usable.x, room.usable.x + d.width, 0)
        };
        let hinge_y = d.y - d.width / 2.0;
        let _ = write!(out, "<path d=\"M {hinge:.3} {:.3} A {:.3} {:.3} 0 0 {sweep} {end:.3} {hinge_y:.3}\" fill=\"none\" stroke=\"#ad8b66\" stroke-width=\"0.024\"/><path d=\"M {hinge:.3} {hinge_y:.3} L {end:.3} {hinge_y:.3}\" fill=\"none\" stroke=\"#9c7955\" stroke-width=\"0.035\"/>", d.y + d.width / 2.0, d.width, d.width);
        if let Some(window) = &room.window {
            rect(&mut out, window.opening, "#77b7bb", "#fbfdfb", "");
        }
    }
    let entry = &plan.entrance;
    rect(&mut out, entry.opening, "#fcfbf8", "none", "");
    let hinge_x = entry.opening.x;
    let hinge_y = entry.swing.y;
    let _ = write!(out, "<path d=\"M {:.3} {hinge_y:.3} A {:.3} {:.3} 0 0 1 {hinge_x:.3} {:.3}\" fill=\"none\" stroke=\"#ad8b66\" stroke-width=\"0.025\"/><path d=\"M {hinge_x:.3} {hinge_y:.3} v {:.3}\" fill=\"none\" stroke=\"#9c7955\" stroke-width=\"0.035\"/>", entry.opening.right(), entry.width, entry.width, hinge_y + entry.width, entry.width);
    let (cx, cy) = plan.corridor.center();
    let _ = write!(out, "<text transform=\"translate({cx:.3},{cy:.3}) rotate(90)\" text-anchor=\"middle\" font-size=\"0.20\" letter-spacing=\"0.05\" fill=\"#59776c\">PASILLO · {:.2} m libres mín.</text>", rules.corridor_width);
    let entrance_x = entry.opening.x + entry.width / 2.0;
    let _ = write!(out, "<path d=\"M {:.3} {:.3} v -0.70\" stroke=\"#ad7452\" stroke-width=\"0.055\" fill=\"none\"/><path d=\"M {:.3} {:.3} l -0.17 0.20 m 0.17 -0.20 l 0.17 0.20\" stroke=\"#ad7452\" stroke-width=\"0.055\" fill=\"none\"/>", entrance_x, plan.corridor.y - 0.2, entrance_x, plan.corridor.y - 0.9);
    let _ = write!(out, "<text x=\"{:.3}\" y=\"-0.48\" text-anchor=\"middle\" fill=\"#7c9586\" font-size=\"0.20\" letter-spacing=\"0.08\">FRENTE DIBUJADO</text><text x=\"{:.3}\" y=\"{:.3}\" text-anchor=\"middle\" fill=\"#a3b4a7\" font-size=\"0.18\">FONDO</text>", site.width / 2.0, site.width / 2.0, site.depth + 0.40);
    let nx = site.width - 0.80;
    let ny = 0.98;
    let _ = write!(out, "<g transform=\"translate({nx:.3},{ny:.3}) rotate({})\"><path d=\"M 0 -0.38 L -0.15 0.24 L 0 0.12 L 0.15 0.24 Z\" fill=\"#276559\"/></g>", site.front.arrow_rotation());
    let (label_x, label_y) = match site.front {
        Orientation::N => (nx, ny - 0.49),
        Orientation::E => (nx - 0.53, ny + 0.10),
        Orientation::S => (nx, ny + 0.70),
        Orientation::W => (nx + 0.53, ny + 0.10),
    };
    let _ = write!(out, "<text x=\"{label_x:.3}\" y=\"{label_y:.3}\" text-anchor=\"middle\" fill=\"#276559\" font-size=\"0.28\" font-weight=\"700\">N</text>");
    out.push_str("</g>");
    let trace_name = if candidate.approach.turns.is_empty() {
        "FRANJA FRONTAL"
    } else {
        "RODEO FRONTAL"
    };
    let footer = if site.rear_notches.len() == 2 {
        format!("DOS RECORTES{} NO VERIFICADOS · RETIROS DE ENTRANTES NO EVALUADOS · {trace_name} ≠ ACCESO REAL",
            match site.reserved_areas.len() { 0 => "", 1 => " Y RESERVA", _ => " Y RESERVAS" })
    } else if site.rear_notches.len() == 1 && !site.reserved_areas.is_empty() {
        format!("CROQUIS EN L Y {} NO VERIFICADOS · RETIROS DEL ENTRANTE NO EVALUADOS · {trace_name} ≠ ACCESO REAL",
            if site.reserved_areas.len() == 1 { "RESERVA" } else { "RESERVAS" })
    } else if site.rear_notches.len() == 1 {
        format!("PARCELA EN L NO VERIFICADA · RETIROS DEL ENTRANTE NO EVALUADOS · {trace_name} ≠ ACCESO REAL")
    } else if site.reserved_areas.is_empty() {
        format!("{trace_name} 2D ≠ ACCESO REAL · VENTANAS DIBUJADAS ≠ LUZ NATURAL COMPROBADA")
    } else {
        format!(
            "{}: CROQUIS 2D NO VERIFICADO · {trace_name} ≠ ACCESO REAL · VENTANAS ≠ LUZ",
            if site.reserved_areas.len() == 1 {
                "RESERVA VOLUNTARIA"
            } else {
                "RESERVAS VOLUNTARIAS"
            }
        )
    };
    let _ = write!(out, "<text x=\"{:.0}\" y=\"{:.0}\" fill=\"#7c9189\" font-family=\"Arial,sans-serif\" font-size=\"10\">{footer}</text>", margin * SCALE, h - 35.0);
    let _ = write!(out, "<text x=\"{:.0}\" y=\"{:.0}\" fill=\"#7c9189\" font-family=\"Arial,sans-serif\" font-size=\"10\">EXTRACCIÓN RESERVADA · PRESIÓN SUPUESTA · CAUDAL ENTREGADO NO EVALUADO · NO APTO PARA OBRA</text>", margin * SCALE, h - 19.0);
    out.push_str("</svg>");
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn xml_escapes_special_characters() {
        assert_eq!(escape_xml("x<&\"'"), "x&lt;&amp;&quot;&apos;");
    }
}
