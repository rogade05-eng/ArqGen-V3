//! ARQ GEN — acelerador Rust (FASE B, v3.49.0)
//!
//! Puerto 1:1 de las funciones calientes de `domain/encaje.py` (encaje al
//! polígono del «Desde dibujo»): `_seccion_en` se invoca O(niveles^2 x 7)
//! veces dentro de `rectangulo_inscrito` y era el cuello de botella real
//! con contornos de muchos vértices.
//!
//! REGLAS DE PARIDAD (vigiadas por tests/test_190_fase_b_rust.py):
//! - mismo orden de operaciones y de iteración que el Python original;
//! - `redondea4` replica `round(x, 4)` de Python (half-to-even);
//! - el sort de contenedores usa el área YA REDONDEADA, igual que el
//!   original, y es estable (empates conservan el orden de creación);
//! - `max` de intervalos toma el PRIMERO máximo, como `max(key=...)`.
//!
//! El acelerador es OPT-IN: el motor Python por defecto no cambia ni un
//! resultado; se activa con ARQ_GEN_ACELERADOR=rust o usar_rust=True.
//!
//! Convención de nombres: el núcleo nativo vive en `*_nucleo`; las
//! funciones `#[pyfunction]` expuestas a Python llevan el nombre público.

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

const TOL: f64 = 1e-7;

/// round(x, 4) de Python: half-to-even sobre el valor del double.
fn redondea4(x: f64) -> f64 {
    let m = x * 1e4;
    let f = m.floor();
    let diff = m - f;
    let r = if (diff - 0.5).abs() < 1e-10 {
        // midpoint decimal exacto: round-half-even (round(2.5)=2, round(3.5)=4)
        if (f % 2.0).abs() < 1e-10 { f } else { f + 1.0 }
    } else {
        m.round() // half-away-from-zero, como el resto de casos de Python
    };
    r / 1e4
}

fn sort_floats(v: &mut [f64]) {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
}

// ---------------------------------------------------------------------------
// núcleo geométrico (réplica de domain/encaje.py)
// ---------------------------------------------------------------------------

/// `_es_ortogonal`: todas las aristas paralelas a los ejes.
fn es_ortogonal_nucleo(poligono: &[(f64, f64)], tol: f64) -> bool {
    let n = poligono.len();
    for i in 0..n {
        let (x0, y0) = poligono[i];
        let (x1, y1) = poligono[(i + 1) % n];
        if (x1 - x0).abs() > tol && (y1 - y0).abs() > tol {
            return false;
        }
    }
    true
}

/// `_seccion_en`: intervalos x del interior del polígono en la horizontal y
/// (cruces de aristas, ordenados y emparejados).
fn seccion_en_nucleo(poligono: &[(f64, f64)], y: f64) -> Vec<(f64, f64)> {
    let mut cruces: Vec<f64> = Vec::new();
    let n = poligono.len();
    for i in 0..n {
        let (x0, y0) = poligono[i];
        let (x1, y1) = poligono[(i + 1) % n];
        if (y0 <= y && y < y1) || (y1 <= y && y < y0) {
            let t = if (y1 - y0).abs() > TOL { (y - y0) / (y1 - y0) } else { 0.0 };
            cruces.push(x0 + t * (x1 - x0));
        }
    }
    sort_floats(&mut cruces);
    (0..cruces.len().saturating_sub(1))
        .step_by(2)
        .map(|i| (cruces[i], cruces[i + 1]))
        .collect()
}

fn mismos_intervalos(a: &[(f64, f64)], b: &[(f64, f64)], tol: f64) -> bool {
    if a.len() != b.len() {
        return false;
    }
    a.iter()
        .zip(b.iter())
        .all(|(p, q)| (p.0 - q.0).abs() <= tol && (p.1 - q.1).abs() <= tol)
}

/// Contenedor rectangular axis-alineado (lo que en Python es el dict
/// {x0, y0, x1, y1, ancho, fondo, area}).
#[derive(Clone, Copy, Debug)]
struct Contenedor {
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
}

impl Contenedor {
    fn a_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        let ancho = self.x1 - self.x0;
        let fondo = self.y1 - self.y0;
        d.set_item("x0", self.x0)?;
        d.set_item("y0", self.y0)?;
        d.set_item("x1", self.x1)?;
        d.set_item("y1", self.y1)?;
        d.set_item("ancho", redondea4(ancho))?;
        d.set_item("fondo", redondea4(fondo))?;
        d.set_item("area", redondea4(ancho * fondo))?;
        Ok(d)
    }

    /// Clave de orden: área YA REDONDEADA (igual que el original Python).
    fn clave_orden(&self) -> f64 {
        redondea4((self.x1 - self.x0) * (self.y1 - self.y0))
    }
}

#[derive(Clone, Copy, Debug)]
struct Franja {
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    seccion: [(f64, f64); 1], // en el original ortogonal la sección es un solo intervalo
}

/// `contenedores_ortogonales`: descomposición exacta del polígono ortogonal
/// en rectángulos (franjas de barrido fusionadas), descontado el margen.
fn contenedores_ortogonales_nucleo(
    poligono: &[(f64, f64)],
    margen: f64,
    min_lado: f64,
) -> Vec<Contenedor> {
    let mut ys: Vec<f64> = poligono.iter().map(|p| p.1).collect();
    sort_floats(&mut ys);
    ys.dedup();

    let mut crudos: Vec<Franja> = Vec::new();
    for par in ys.windows(2) {
        let (y0, y1) = (par[0], par[1]);
        if y1 - y0 <= TOL {
            continue;
        }
        for (x0, x1) in seccion_en_nucleo(poligono, (y0 + y1) / 2.0) {
            if x1 - x0 > TOL {
                crudos.push(Franja { x0, y0, x1, y1, seccion: [(x0, x1)] });
            }
        }
    }

    // fusiona franjas contiguas en y con la misma sección x
    let mut salida: Vec<Franja> = Vec::new();
    for f in crudos {
        if let Some(ant) = salida.last_mut() {
            if (ant.y1 - f.y0).abs() <= TOL
                && mismos_intervalos(&ant.seccion, &f.seccion, 1e-6)
            {
                ant.y1 = f.y1;
                continue;
            }
        }
        salida.push(f);
    }

    let mut res: Vec<Contenedor> = Vec::new();
    for f in &salida {
        let c = Contenedor {
            x0: f.x0 + margen,
            y0: f.y0 + margen,
            x1: f.x1 - margen,
            y1: f.y1 - margen,
        };
        if c.x1 - c.x0 >= min_lado && c.y1 - c.y0 >= min_lado {
            res.push(c);
        }
    }
    // sort estable por -area (área redondeada, como en Python)
    res.sort_by(|a, b| {
        b.clave_orden()
            .partial_cmp(&a.clave_orden())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    res
}

/// `_niveles_refinados`: cotas y candidatas para bandas (vértices + fracciones).
fn niveles_refinados(poligono: &[(f64, f64)]) -> Vec<f64> {
    let mut ys: Vec<f64> = poligono.iter().map(|p| p.1).collect();
    sort_floats(&mut ys);
    ys.dedup();

    let mut niveles: Vec<f64> = ys.clone();
    for par in ys.windows(2) {
        let (y0, y1) = (par[0], par[1]);
        let h = y1 - y0;
        for f in [0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 0.75] {
            niveles.push(y0 + f * h);
        }
    }
    sort_floats(&mut niveles);
    // dedup estilo set de Python (igualdad exacta de doubles consecutivos)
    let mut finos: Vec<f64> = Vec::with_capacity(niveles.len());
    for v in niveles {
        if finos.last().copied() != Some(v) {
            finos.push(v);
        }
    }
    // capo determinista por si el contorno trae decenas de vértices
    while finos.len() > 48 {
        finos = finos.into_iter().step_by(2).collect();
    }
    finos
}

/// `rectangulo_inscrito`: mayor rectángulo axis-alineado inscrito en un
/// polígono simple (candidatos: pares de cotas refinadas).
fn rectangulo_inscrito_nucleo(poligono: &[(f64, f64)], margen: f64) -> Option<Contenedor> {
    let ys = niveles_refinados(poligono);
    if ys.len() < 2 {
        return None;
    }
    let mut mejor: Option<(Contenedor, f64)> = None; // (contenedor, area redondeada)
    for i in 0..ys.len() - 1 {
        for j in i + 1..ys.len() {
            let (yb, yt) = (ys[i], ys[j]);
            let h = yt - yb;
            if h <= TOL {
                continue;
            }
            let mut inter: Vec<(f64, f64)> = Vec::new();
            let mut bandas_rotas = false;
            for (k, t) in [0.0, 0.02, 0.25, 0.5, 0.75, 0.98, 1.0].iter().enumerate() {
                let sec = seccion_en_nucleo(poligono, yb + t * h);
                if sec.is_empty() {
                    inter.clear();
                    bandas_rotas = true;
                    break;
                }
                if k == 0 {
                    inter = sec;
                } else {
                    let mut nueva: Vec<(f64, f64)> = Vec::new();
                    for (a0, a1) in &inter {
                        for (b0, b1) in &sec {
                            let x0 = a0.max(*b0);
                            let x1 = (*a1).min(*b1);
                            if x1 - x0 > TOL {
                                nueva.push((x0, x1));
                            }
                        }
                    }
                    inter = nueva;
                    if inter.is_empty() {
                        bandas_rotas = true;
                        break;
                    }
                }
            }
            if bandas_rotas || inter.is_empty() {
                continue;
            }
            // max(key=lambda p: p[1]-p[0]) de Python: el PRIMERO máximo
            let mut mejor_par = inter[0];
            let mut ancho_max = inter[0].1 - inter[0].0;
            for p in &inter[1..] {
                let w = p.1 - p.0;
                if w > ancho_max {
                    ancho_max = w;
                    mejor_par = *p;
                }
            }
            let (x0, x1) = mejor_par;
            let area = (x1 - x0) * h;
            let supera = match &mejor {
                None => true,
                // la comparación usa el área REDONDEADA guardada (como Python)
                Some((_, area_mejor)) => area > *area_mejor,
            };
            if supera {
                mejor = Some((
                    Contenedor { x0, y0: yb, x1, y1: yt },
                    redondea4(area),
                ));
            }
        }
    }
    let (c, _) = mejor?;
    let m = margen.max(0.0);
    let x0 = c.x0 + m;
    let x1 = c.x1 - m;
    let y0 = c.y0 + m;
    let y1 = c.y1 - m;
    if x1 - x0 <= 0.5 || y1 - y0 <= 0.5 {
        return None;
    }
    Some(Contenedor { x0, y0, x1, y1 })
}

/// `comparten_banda`: dos contenedores axis-alineados comparten arista de
/// longitud suficiente.
#[allow(clippy::too_many_arguments)]
fn comparten_banda_nucleo(
    ax0: f64, ay0: f64, ax1: f64, ay1: f64,
    bx0: f64, by0: f64, bx1: f64, by1: f64,
    min_len: f64, tol: f64,
) -> bool {
    let solape_y = ay1.min(by1) - ay0.max(by0);
    let solape_x = ax1.min(bx1) - ax0.max(bx0);
    if ((ax1 - bx0).abs() <= tol || (ax0 - bx1).abs() <= tol) && solape_y >= min_len {
        return true;
    }
    if ((ay1 - by0).abs() <= tol || (ay0 - by1).abs() <= tol) && solape_x >= min_len {
        return true;
    }
    false
}

/// `_area`: área shoelace con el mismo orden de iteración (paridad bit a bit).
fn area_poligono_nucleo(poligono: &[(f64, f64)]) -> f64 {
    let mut s = 0.0;
    let n = poligono.len();
    for i in 0..n {
        let (x0, y0) = poligono[i];
        let (x1, y1) = poligono[(i + 1) % n];
        s += x0 * y1 - x1 * y0;
    }
    s.abs() / 2.0
}

// ---------------------------------------------------------------------------
// bindings PyO3
// ---------------------------------------------------------------------------

fn extraer_f(d: &Bound<'_, PyDict>, clave: &str) -> PyResult<f64> {
    match d.get_item(clave)? {
        Some(v) => v.extract::<f64>(),
        None => Err(PyKeyError::new_err(format!(
            "contenedor sin la clave requerida '{clave}'"
        ))),
    }
}

#[pyfunction]
#[pyo3(signature = (poligono, tol=None))]
fn es_ortogonal(poligono: Vec<(f64, f64)>, tol: Option<f64>) -> bool {
    es_ortogonal_nucleo(&poligono, tol.unwrap_or(1e-6))
}

#[pyfunction]
fn seccion_en(poligono: Vec<(f64, f64)>, y: f64) -> Vec<(f64, f64)> {
    seccion_en_nucleo(&poligono, y)
}

#[pyfunction]
#[pyo3(signature = (poligono, margen=0.0, min_lado=1.0))]
fn contenedores_ortogonales(
    py: Python<'_>,
    poligono: Vec<(f64, f64)>,
    margen: f64,
    min_lado: f64,
) -> PyResult<Vec<Bound<'_, PyDict>>> {
    let res = contenedores_ortogonales_nucleo(&poligono, margen, min_lado);
    res.iter().map(|c| c.a_dict(py)).collect()
}

#[pyfunction]
#[pyo3(signature = (poligono, margen=0.0))]
fn rectangulo_inscrito(
    py: Python<'_>,
    poligono: Vec<(f64, f64)>,
    margen: f64,
) -> PyResult<Option<Bound<'_, PyDict>>> {
    Ok(match rectangulo_inscrito_nucleo(&poligono, margen) {
        Some(c) => Some(c.a_dict(py)?),
        None => None,
    })
}

#[pyfunction]
#[pyo3(signature = (a, b, min_len=1.0, tol=1e-6))]
fn comparten_banda(
    a: &Bound<'_, PyDict>,
    b: &Bound<'_, PyDict>,
    min_len: f64,
    tol: f64,
) -> PyResult<bool> {
    Ok(comparten_banda_nucleo(
        extraer_f(a, "x0")?, extraer_f(a, "y0")?,
        extraer_f(a, "x1")?, extraer_f(a, "y1")?,
        extraer_f(b, "x0")?, extraer_f(b, "y0")?,
        extraer_f(b, "x1")?, extraer_f(b, "y1")?,
        min_len, tol,
    ))
}

#[pyfunction]
fn area_poligono(poligono: Vec<(f64, f64)>) -> f64 {
    area_poligono_nucleo(&poligono)
}

/// Versión del acelerador (para selftest y diagnóstico).
#[pyfunction]
fn version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

mod xlsx;

#[pyfunction]
fn xlsx_escribir(py: Python<'_>, ruta: &str, hojas: &Bound<'_, PyList>) -> PyResult<usize> {
    xlsx::xlsx_escribir_py(py, ruta, hojas)
}

#[pymodule]
fn arqgen_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(es_ortogonal, m)?)?;
    m.add_function(wrap_pyfunction!(seccion_en, m)?)?;
    m.add_function(wrap_pyfunction!(contenedores_ortogonales, m)?)?;
    m.add_function(wrap_pyfunction!(rectangulo_inscrito, m)?)?;
    m.add_function(wrap_pyfunction!(comparten_banda, m)?)?;
    m.add_function(wrap_pyfunction!(area_poligono, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(xlsx_escribir, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
