//! XLSX nativo en Rust (FASE B) — equivalente funcional de «rust_xlsxwriter»,
//! que no existe como binding Python en PyPI. Genera un .xlsx OOXML mínimo
//! pero profesional con el MISMO formato del exportador openpyxl:
//!   - fila 1 de cabecera: relleno sólido FF2F5496, fuente blanca en negrita,
//!     alineación centrada;
//!   - pane congelado en A2;
//!   - anchos de columna personalizados.
//! El archivo resultante se lee con openpyxl sin cambios (paridad vigilada
//! por tests/test_190_fase_b_rust.py).

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyList};
use std::io::Write;
use zip::CompressionMethod;
use zip::ZipWriter;
use zip::write::SimpleFileOptions;

#[derive(Clone, Debug)]
enum Celda {
    Texto(String),
    Numero(f64),
    Vacia,
}

#[derive(Clone, Debug)]
struct Hoja {
    titulo: String,
    headers: Vec<String>,
    filas: Vec<Vec<Celda>>,
    anchos: Vec<f64>,
}

/// escape de texto XML (texto de celdas y títulos)
fn esc(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 8);
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&apos;"),
            _ => out.push(c),
        }
    }
    out
}

/// índice de columna 0-based -> letras (A, B, ..., Z, AA, AB, ...)
fn letras_col(mut i: usize) -> String {
    let mut buf = Vec::new();
    loop {
        buf.push(b'A' + (i % 26) as u8);
        if i < 26 {
            break;
        }
        i = i / 26 - 1;
    }
    buf.reverse();
    String::from_utf8(buf).unwrap_or_default()
}

fn extraer_celda(v: &Bound<'_, PyAny>) -> PyResult<Celda> {
    if v.is_none() {
        return Ok(Celda::Vacia);
    }
    if v.is_instance_of::<pyo3::types::PyString>() {
        let s: String = v.extract()?;
        // cadena vacía == celda vacía (semántica openpyxl: '' al guardar es None)
        if s.is_empty() {
            return Ok(Celda::Vacia);
        }
        return Ok(Celda::Texto(s));
    }
    // bool antes que número (bool es int en Python)
    if let Ok(b) = v.extract::<bool>() {
        // el exportador nunca pasa bool; por robustez va como texto
        return Ok(Celda::Texto(if b { "True" } else { "False" }.to_string()));
    }
    if let Ok(n) = v.extract::<f64>() {
        return Ok(Celda::Numero(n));
    }
    // último recurso: str() del objeto
    let s: String = v.str()?.to_str()?.to_string();
    Ok(Celda::Texto(s))
}

fn extraer_hojas(hojas: &Bound<'_, PyList>) -> PyResult<Vec<Hoja>> {
    let mut salida = Vec::with_capacity(hojas.len());
    for item in hojas.iter() {
        let d = item.downcast_into::<pyo3::types::PyDict>()?;
        let titulo: String = d.get_item("titulo")?.expect("hoja sin titulo").extract()?;
        let mut headers = Vec::new();
        if let Some(h) = d.get_item("headers")? {
            if !h.is_none() {
                let hl = h.downcast_into::<PyList>()?;
                for x in hl.iter() {
                    headers.push(x.extract::<String>()?);
                }
            }
        }
        let mut filas: Vec<Vec<Celda>> = Vec::new();
        if let Some(f) = d.get_item("filas")? {
            if !f.is_none() {
                let fl = f.downcast_into::<PyList>()?;
                for fila in fl.iter() {
                    let fl2 = fila.downcast_into::<PyList>()?;
                    let mut nf = Vec::with_capacity(fl2.len());
                    for c in fl2.iter() {
                        nf.push(extraer_celda(&c)?);
                    }
                    filas.push(nf);
                }
            }
        }
        let mut anchos = Vec::new();
        if let Some(a) = d.get_item("anchos")? {
            if !a.is_none() {
                let al = a.downcast_into::<PyList>()?;
                for x in al.iter() {
                    anchos.push(x.extract::<f64>()?);
                }
            }
        }
        salida.push(Hoja { titulo, headers, filas, anchos });
    }
    Ok(salida)
}

fn xml_hoja(hoja: &Hoja, congelar_a2: bool) -> String {
    let mut s = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\
         <worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">",
    );
    if congelar_a2 {
        s.push_str(
            "<sheetViews><sheetView workbookViewId=\"0\">\
             <pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/>\
             </sheetView></sheetViews>",
        );
    }
    if !hoja.anchos.is_empty() {
        s.push_str("<cols>");
        for (i, w) in hoja.anchos.iter().enumerate() {
            s.push_str(&format!(
                "<col min=\"{}\" max=\"{}\" width=\"{}\" customWidth=\"1\"/>",
                i + 1,
                i + 1,
                w
            ));
        }
        s.push_str("</cols>");
    }
    s.push_str("<sheetData>");
    // fila 1: cabecera con estilo 1
    if !hoja.headers.is_empty() {
        s.push_str("<row r=\"1\">");
        for (i, h) in hoja.headers.iter().enumerate() {
            s.push_str(&format!(
                "<c r=\"{}1\" s=\"1\" t=\"inlineStr\"><is><t>{}</t></is></c>",
                letras_col(i),
                esc(h)
            ));
        }
        s.push_str("</row>");
    }
    // filas de datos
    for (n_fila, fila) in hoja.filas.iter().enumerate() {
        s.push_str(&format!("<row r=\"{}\">", n_fila + 2));
        for (i, celda) in fila.iter().enumerate() {
            let refc = format!("{}{}", letras_col(i), n_fila + 2);
            match celda {
                Celda::Texto(t) => s.push_str(&format!(
                    "<c r=\"{refc}\" t=\"inlineStr\"><is><t>{}</t></is></c>",
                    esc(t)
                )),
                Celda::Numero(n) => {
                    if n.is_finite() {
                        s.push_str(&format!("<c r=\"{refc}\"><v>{n}</v></c>"));
                    } else {
                        s.push_str(&format!("<c r=\"{refc}\" t=\"inlineStr\"/>"));
                    }
                }
                Celda::Vacia => s.push_str(&format!("<c r=\"{refc}\"/>")),
            }
        }
        s.push_str("</row>");
    }
    s.push_str("</sheetData></worksheet>");
    s
}

const STYLES_XML: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF2F5496"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
<dxfs count="0"/>
</styleSheet>"#;

fn xml_workbook(titulos: &[String]) -> String {
    let mut s = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\
         <workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" \
         xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>",
    );
    for (i, t) in titulos.iter().enumerate() {
        s.push_str(&format!(
            "<sheet name=\"{}\" sheetId=\"{}\" r:id=\"rId{}\"/>",
            esc(t),
            i + 1,
            i + 1
        ));
    }
    s.push_str("</sheets></workbook>");
    s
}

fn xml_workbook_rels(n: usize) -> String {
    let mut s = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\
         <Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">",
    );
    for i in 0..n {
        s.push_str(&format!(
            "<Relationship Id=\"rId{}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet{}.xml\"/>",
            i + 1,
            i + 1
        ));
    }
    s.push_str(&format!(
        "<Relationship Id=\"rId{}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>",
        n + 1
    ));
    s.push_str("</Relationships>");
    s
}

fn xml_content_types(n: usize) -> String {
    let mut s = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\
         <Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">\
         <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>\
         <Default Extension=\"xml\" ContentType=\"application/xml\"/>\
         <Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>\
         <Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>",
    );
    for i in 0..n {
        s.push_str(&format!(
            "<Override PartName=\"/xl/worksheets/sheet{}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>",
            i + 1
        ));
    }
    s.push_str("</Types>");
    s
}

/// Título de hoja seguro: <=31 caracteres, sin []:*?/\ (regla de Excel).
fn titulo_seguro(t: &str) -> String {
    let limpio: String = t
        .chars()
        .filter(|c| !matches!(c, '[' | ']' | ':' | '*' | '?' | '/' | '\\'))
        .take(31)
        .collect();
    if limpio.is_empty() {
        "Hoja".to_string()
    } else {
        limpio
    }
}

fn escribir_xlsx(ruta: &str, hojas: &[Hoja]) -> std::io::Result<usize> {
    if let Some(padre) = std::path::Path::new(ruta).parent() {
        if !padre.as_os_str().is_empty() {
            std::fs::create_dir_all(padre)?;
        }
    }
    let file = std::fs::File::create(ruta)?;
    let mut zw = ZipWriter::new(std::io::BufWriter::new(file));
    let opts = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);

    let mut celdas = 0usize;

    zw.start_file("[Content_Types].xml", opts)?;
    zw.write_all(xml_content_types(hojas.len()).as_bytes())?;

    zw.start_file("_rels/.rels", opts)?;
    zw.write_all(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\
         <Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\
         <Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>\
         </Relationships>"
            .as_bytes(),
    )?;

    zw.start_file("xl/workbook.xml", opts)?;
    zw.write_all(xml_workbook(&hojas.iter().map(|h| h.titulo.clone()).collect::<Vec<_>>())
        .as_bytes())?;

    zw.start_file("xl/_rels/workbook.xml.rels", opts)?;
    zw.write_all(xml_workbook_rels(hojas.len()).as_bytes())?;

    zw.start_file("xl/styles.xml", opts)?;
    zw.write_all(STYLES_XML.as_bytes())?;

    for (i, hoja) in hojas.iter().enumerate() {
        zw.start_file(format!("xl/worksheets/sheet{}.xml", i + 1), opts)?;
        zw.write_all(xml_hoja(hoja, true).as_bytes())?;
        celdas += hoja.headers.len() + hoja.filas.iter().map(|f| f.len()).sum::<usize>();
    }

    zw.finish()?;
    Ok(celdas)
}

/// Entrada pública del binding (llamada desde lib.rs; el #[pyfunction]
/// vive allí para evitar la colisión del módulo interno del macro).
pub fn xlsx_escribir_py(py: Python<'_>, ruta: &str, hojas: &Bound<'_, PyList>) -> PyResult<usize> {
    let datos = extraer_hojas(hojas)?;
    let mut limpias: Vec<Hoja> = datos
        .into_iter()
        .map(|mut h| {
            h.titulo = titulo_seguro(&h.titulo);
            h
        })
        .collect();
    if limpias.is_empty() {
        limpias.push(Hoja {
            titulo: "Hoja".to_string(),
            headers: vec![],
            filas: vec![],
            anchos: vec![],
        });
    }
    let ruta = ruta.to_string();
    let n = py
        .allow_threads(move || escribir_xlsx(&ruta, &limpias))
        .map_err(|e| {
            pyo3::exceptions::PyIOError::new_err(format!("No se pudo escribir el XLSX: {e}"))
        })?;
    Ok(n)
}
