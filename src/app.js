// ============================================================================
//  ARQ GEN — Tauri Fase C: UI web completa (vanilla JS, sin build)
//  Todo pasa por el canal JSON-RPC: invoke('rpc', {method, params})
//  Vistas: inicio · programa · contorno · forma · resultado · exportar ·
//  proyecto. El estado de formulario vive en localStorage; los ANÁLISIS
//  completos viven en la sesión LRU del sidecar (el cliente solo guarda id).
// ============================================================================

"use strict";

// ------------------------------------------------------------- utilidades ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const CONTORNOS_PRESET = {
  rect: [[0, 0], [24, 0], [24, 12], [0, 12]],
  l: [[0, 0], [18, 0], [18, 8], [8, 8], [8, 14], [0, 14]],
  t: [[0, 0], [24, 0], [24, 8], [14, 8], [14, 16], [10, 16], [10, 8], [0, 8]],
  u: [[0, 0], [20, 0], [20, 14], [16, 14], [16, 4], [4, 4], [4, 14], [0, 14]],
};

// Paleta de flujos del motor (la misma del render matplotlib)
const PALETA = {
  publico: "#a8c8e4",
  limpio: "#a8dfc0",
  restringido: "#f2e2a0",
  sucio: "#eba8a0",
  exterior: "#d5d8dc",
  libre: "#cfe3f5",
};
const COLOR_PASILLO = "#c9c9c9";
const COLOR_ESCALERA = "#9aa5b1";
const COLOR_PATIO = "#b6d7a8";
const COLOR_FONDO = "#f8f9fa";

const ALA_PRESET = [
  { contorno: [[0, 0], [18, 0], [18, 12], [0, 12]], rol: "ala norte" },
  { contorno: [[0, 0], [16, 0], [16, 10], [0, 10]], rol: "ala sur" },
];

// Estado de la UI (sin análisis: solo parámetros y preferencias)
const CLAVE_ESTADO = "arqgen_ui_v1";
let ESTADO = {
  modoPrograma: "texto",
  quickTexto: "dormitorio, bano, cocina, sala, patio",
  fichas: [
    { space_type: "ENTRANCE", cantidad: 1 },
    { space_type: "OFFICE", cantidad: 4 },
    { space_type: "LAVATORY", cantidad: 2 },
  ],
  nombre: "Edificio ARQ GEN",
  contorno: JSON.stringify(CONTORNOS_PRESET.rect),
  modoForma: "simple",
  simple: { ajuste: "ideal", chaflanes: true, patio: false },
  radial: { radio_ext: 14, radio_nucleo: 3, corredor_m: 1.6, sectores: 8, niveles: 1 },
  y: { radio_nucleo: 7, largo_ala: 16, ancho_ala: 11, n_alas: 3,
       corredor_m: 1.5, cabecera_m: 0, largos: "", niveles: 1 },
  x: { largo_barra: 64, ancho_barra: 14, corredor_m: 2, cabecera_m: 0,
       angulo: 45, niveles: 1 },
  zonas: JSON.parse(JSON.stringify(ALA_PRESET)),
  rejilla: { columnas: 3, filas: 2, pasillo_m: 1.6 },
  exportar: { carpeta: "", base: "proyecto_arqgen", formatos: ["IFC", "DXF", "XLSX"],
              muros: true, con_proyecto: true, mobiliario: "auto" },
};

let CATALOGO = [];       // [{code, nombre, area_min,...}] del RPC catalogo
let RESULTADO = null;    // resumen del análisis activo (con id de sesión)
let PIEZA_ACTIVA = 0;    // índice del tab activo (nivel o ala·nivel)

function guardarEstado() {
  try { localStorage.setItem(CLAVE_ESTADO, JSON.stringify(ESTADO)); }
  catch (_) { /* almacenamiento lleno o no disponible: se ignora */ }
}
function cargarEstado() {
  try {
    const crudo = localStorage.getItem(CLAVE_ESTADO);
    if (crudo) ESTADO = Object.assign(ESTADO, JSON.parse(crudo));
  } catch (_) { /* estado corrupto: se parte del defecto */ }
}

// ------------------------------------------------------------ canal RPC ---
function llamar(metodo, params) {
  if (!window.__TAURI__) {
    return Promise.reject("Sin Tauri: esta UI habla con el motor por el " +
      "shell de escritorio. Para ensayar el canal a mano: " +
      "python main.py rpc");
  }
  return window.__TAURI__.core.invoke("rpc", { method: metodo, params });
}

function decorarError(e) {
  // El shell propaga el objeto error JSON-RPC serializado
  try {
    const o = JSON.parse(String(e));
    if (o && o.message) {
      let msg = "Error " + (o.code || "") + ": " + o.message;
      const data = o.data || {};
      if (data.codigo) msg += " [" + data.codigo + "]";
      if (data.accion) msg += " — " + data.accion;
      return msg;
    }
  } catch (_) { /* texto plano */ }
  return String(e);
}

function mostrarError(msg) {
  const pie = $("#pie-error");
  pie.textContent = msg;
  pie.classList.remove("oculto");
}
function limpiarError() {
  $("#pie-error").textContent = "";
  $("#pie-error").classList.add("oculto");
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function num(x, dec) {
  if (x == null || isNaN(Number(x))) return "—";
  return Number(x).toFixed(dec == null ? 2 : dec);
}

// --------------------------------------------------------- navegación ---
function irVista(nombre) {
  $$(".nav-btn").forEach((b) =>
    b.classList.toggle("activo", b.dataset.vista === nombre));
  $$(".vista").forEach((v) =>
    v.classList.toggle("activa", v.id === "vista-" + nombre));
  if (nombre === "resultado") renderResultado();
  if (nombre === "exportar") renderExportarVista();
  limpiarError();
}
$$(".nav-btn").forEach((b) =>
  b.addEventListener("click", () => irVista(b.dataset.vista)));
document.addEventListener("click", (ev) => {
  const ir = ev.target.closest("[data-ir]");
  if (ir) irVista(ir.dataset.ir);
});

// --------------------------------------------------------------- inicio ---
async function comprobarMotor() {
  const chip = $("#estado");
  try {
    const p = await llamar("ping", {});
    chip.textContent = "Motor v" + p.app_version + " conectado";
    chip.className = "chip ok";
  } catch (e) {
    chip.textContent = "Motor NO disponible";
    chip.className = "chip fallo";
    mostrarError(decorarError(e));
    return;
  }
  try {
    const v = await llamar("version", {});
    $("#ini-version").textContent = "v" + v.app_version;
    $("#ini-python").textContent = v.python;
    $("#ini-acelerador").textContent =
      v.modo_acelerador === "rust" ? "Rust (FASE B activa)" : "Python puro";
    const chipA = $("#chip-acelerador");
    chipA.textContent = v.modo_acelerador === "rust"
      ? "acelerador Rust" : "acelerador: python";
    chipA.className = "chip " + (v.modo_acelerador === "rust" ? "info" : "");
    chipA.classList.remove("oculto");
  } catch (_) { /* la versión ampliada es best effort */ }
  try {
    const ruta = await window.__TAURI__.core.invoke("motor_ruta");
    $("#ini-ruta").textContent = ruta;
  } catch (e) {
    $("#ini-ruta").textContent = String(e);
  }
}

// ------------------------------------------------------------- programa ---
function programaModoActual() {
  const sel = document.querySelector('input[name="modo-programa"]:checked');
  return sel ? sel.value : "texto";
}

function initPrograma() {
  const radios = $$('input[name="modo-programa"]');
  radios.forEach((r) => r.addEventListener("change", () => {
    ESTADO.modoPrograma = programaModoActual();
    $("#bloque-texto").classList.toggle("oculto", ESTADO.modoPrograma !== "texto");
    $("#bloque-fichas").classList.toggle("oculto", ESTADO.modoPrograma !== "fichas");
    guardarEstado();
  }));

  $("#quick-texto").addEventListener("input", () => {
    ESTADO.quickTexto = $("#quick-texto").value; guardarEstado();
  });
  $("#nombre-prog").addEventListener("input", () => {
    ESTADO.nombre = $("#nombre-prog").value; guardarEstado();
  });
  $("#btn-ficha").addEventListener("click", () => {
    ESTADO.fichas.push({ space_type: "OFFICE", cantidad: 1 });
    renderFichas(); guardarEstado();
  });
}

function renderPrograma() {
  $$('input[name="modo-programa"]').forEach((r) => {
    r.checked = r.value === ESTADO.modoPrograma;
  });
  $("#bloque-texto").classList.toggle("oculto", ESTADO.modoPrograma !== "texto");
  $("#bloque-fichas").classList.toggle("oculto", ESTADO.modoPrograma !== "fichas");
  $("#quick-texto").value = ESTADO.quickTexto;
  $("#nombre-prog").value = ESTADO.nombre;
  renderFichas();
}

function renderFichas() {
  const cuerpo = $("#tabla-fichas tbody");
  cuerpo.innerHTML = "";
  ESTADO.fichas.forEach((f, i) => {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td");
    const input = document.createElement("input");
    input.setAttribute("list", "catalogo-datalist");
    input.className = "mono";
    input.value = f.space_type;
    input.addEventListener("change", () => {
      ESTADO.fichas[i].space_type = input.value.trim().toUpperCase();
      guardarEstado();
    });
    td1.appendChild(input);
    const td2 = document.createElement("td");
    const qty = document.createElement("input");
    qty.type = "number"; qty.min = "1"; qty.max = "999"; qty.value = f.cantidad;
    qty.addEventListener("change", () => {
      ESTADO.fichas[i].cantidad = Math.max(1, parseInt(qty.value || "1", 10));
      guardarEstado();
    });
    td2.appendChild(qty);
    const td3 = document.createElement("td");
    const borrar = document.createElement("button");
    borrar.className = "borrar"; borrar.textContent = "Quitar";
    borrar.addEventListener("click", () => {
      ESTADO.fichas.splice(i, 1); renderFichas(); guardarEstado();
    });
    td3.appendChild(borrar);
    tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3);
    cuerpo.appendChild(tr);
  });
  // datalist del catálogo
  let dl = $("#catalogo-datalist");
  if (!dl) {
    dl = document.createElement("datalist");
    dl.id = "catalogo-datalist";
    document.body.appendChild(dl);
  }
  dl.innerHTML = CATALOGO.map((t) =>
    '<option value="' + esc(t.code) + '">' + esc(t.nombre) + "</option>").join("");
}

async function cargarCatalogo() {
  try {
    const r = await llamar("catalogo", {});
    CATALOGO = r.tipos || [];
    $("#cuenta-catalogo").textContent = CATALOGO.length + " usos";
    renderFichas();
  } catch (e) {
    $("#cuenta-catalogo").textContent = "catálogo no disponible";
  }
}

// ------------------------------------------------------------- contorno ---
function contornoActual() {
  try {
    const lista = JSON.parse(ESTADO.contorno);
    if (!Array.isArray(lista) || lista.length < 3 ||
        lista.some((p) => !Array.isArray(p) || p.length < 2)) return null;
    return lista.map((p) => [Number(p[0]), Number(p[1])]);
  } catch (_) { return null; }
}

function initContorno() {
  $$("#preset-contornos .ficha-preset").forEach((b) =>
    b.addEventListener("click", () => {
      ESTADO.contorno = JSON.stringify(CONTORNOS_PRESET[b.dataset.preset]);
      renderContorno(); guardarEstado();
    }));
  $("#json-contorno").addEventListener("input", () => {
    ESTADO.contorno = $("#json-contorno").value;
    renderContorno(); guardarEstado();
  });
}

function areaPoligono(pol) {
  let s = 0;
  for (let i = 0; i < pol.length; i++) {
    const a = pol[i], b = pol[(i + 1) % pol.length];
    s += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(s) / 2;
}
function bboxDe(poligonos) {
  const pts = poligonos.reduce((acc, pol) => acc.concat(pol), []);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return {
    x0: Math.min(...xs), y0: Math.min(...ys),
    x1: Math.max(...xs), y1: Math.max(...ys),
  };
}

function renderContorno() {
  const ta = $("#json-contorno");
  if (document.activeElement !== ta) ta.value = ESTADO.contorno;
  const cont = contornoActual();
  const aviso = $("#aviso-contorno");
  const medidas = $("#medidas-contorno");
  if (!cont) {
    aviso.textContent = "Contorno ilegible: se necesita una lista de " +
      "al menos 3 vértices [[x,y],…].";
    aviso.classList.remove("oculto");
    medidas.innerHTML = "";
    dibujarSVG($("#prev-contorno"), { poligonos: [] });
    return;
  }
  aviso.classList.add("oculto");
  const bb = bboxDe([cont]);
  medidas.innerHTML =
    par("Vértices", cont.length) +
    par("Ancho × fondo", num(bb.x1 - bb.x0, 2) + " × " + num(bb.y1 - bb.y0, 2) + " m") +
    par("Área bruta", num(areaPoligono(cont), 2) + " m²");
  dibujarSVG($("#prev-contorno"), {
    poligonos: [[{ puntos: cont, color: COLOR_FONDO, borde: "#2c3e50",
                   ancho: 2 }]],
  });
}
function par(k, v) {
  return '<div class="par"><span>' + esc(k) + "</span><b>" + esc(v) + "</b></div>";
}

// --------------------------------------------------------- SVG genérico ---
const NS_SVG = "http://www.w3.org/2000/svg";

function dibujarSVG(svg, { poligonos, fondo, etiquetaMinPx }) {
  // poligonos: [[{puntos, color, borde, ancho, etiqueta, sub}], ...] capas
  svg.innerHTML = "";
  const capas = poligonos || [];
  const todos = capas.reduce((acc, cap) =>
    acc.concat(cap.map((p) => p.puntos)), []);
  if (fondo) todos.push(fondo);
  if (!todos.length) return;
  const bb = bboxDe(todos);
  const W = 1000, H = 500, margen = 26;
  const dx = Math.max(bb.x1 - bb.x0, 1e-6), dy = Math.max(bb.y1 - bb.y0, 1e-6);
  const escala = Math.min((W - 2 * margen) / dx, (H - 2 * margen) / dy);
  const ox = margen + ((W - 2 * margen) - dx * escala) / 2;
  const oy = margen + ((H - 2 * margen) - dy * escala) / 2;
  const X = (x) => ox + (x - bb.x0) * escala;
  const Y = (y) => oy + (bb.y1 - y) * escala;
  const pts = (pol) => pol.map((p) => X(p[0]) + "," + Y(p[1])).join(" ");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);

  if (fondo && fondo.length >= 3) {
    const el = document.createElementNS(NS_SVG, "polygon");
    el.setAttribute("points", pts(fondo));
    el.setAttribute("fill", "#eef2f7");
    el.setAttribute("stroke", "#2c3e50");
    el.setAttribute("stroke-width", "2.5");
    el.setAttribute("stroke-dasharray", "none");
    svg.appendChild(el);
  }
  for (const capa of capas) {
    for (const p of capa) {
      if (!p.puntos || p.puntos.length < 3) continue;
      const el = document.createElementNS(NS_SVG, "polygon");
      el.setAttribute("points", pts(p.puntos));
      el.setAttribute("fill", p.color || COLOR_FONDO);
      el.setAttribute("stroke", p.borde || "#5d6d7e");
      el.setAttribute("stroke-width", p.ancho || 1);
      el.setAttribute("stroke-linejoin", "round");
      el.setAttribute("opacity", p.opacidad || 0.95);
      if (p.title) {
        const t = document.createElementNS(NS_SVG, "title");
        t.textContent = p.title;
        el.appendChild(t);
      }
      svg.appendChild(el);
    }
  }
  // etiquetas al final (encima de todo)
  for (const capa of capas) {
    for (const p of capa) {
      if (!p.etiqueta || !p.puntos || p.puntos.length < 3) continue;
      const bbp = bboxDe([p.puntos]);
      const anchoPx = (bbp.x1 - bbp.x0) * escala;
      const altoPx = (bbp.y1 - bbp.y0) * escala;
      if (etiquetaMinPx && (anchoPx < etiquetaMinPx || altoPx < 12)) continue;
      const cx = p.puntos.reduce((s, q) => s + q[0], 0) / p.puntos.length;
      const cy = p.puntos.reduce((s, q) => s + q[1], 0) / p.puntos.length;
      const t = document.createElementNS(NS_SVG, "text");
      t.setAttribute("x", X(cx));
      t.setAttribute("y", Y(cy) - (p.sub ? 5 : 0));
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("font-size", "11");
      t.setAttribute("fill", "#1b2631");
      t.textContent = p.etiqueta;
      svg.appendChild(t);
      if (p.sub) {
        const s2 = document.createElementNS(NS_SVG, "text");
        s2.setAttribute("x", X(cx));
        s2.setAttribute("y", Y(cy) + 9);
        s2.setAttribute("text-anchor", "middle");
        s2.setAttribute("font-size", "9");
        s2.setAttribute("fill", "#5d6d7e");
        s2.textContent = p.sub;
        svg.appendChild(s2);
      }
    }
  }
}

// ---------------------------------------------------------------- formas ---
function initFormas() {
  $$("#modos-forma .ficha-preset").forEach((b) =>
    b.addEventListener("click", () => {
      ESTADO.modoForma = b.dataset.modo;
      renderFormas(); guardarEstado();
    }));
  $("#btn-generar").addEventListener("click", generar);
  $("#btn-ala").addEventListener("click", () => {
    ESTADO.zonas.push({ contorno: [[0, 0], [12, 0], [12, 9], [0, 9]],
                        rol: "ala " + (ESTADO.zonas.length + 1) });
    renderAlas(); guardarEstado();
  });
  // parámetros numéricos -> estado
  const bindea = (id, grupo, clave) => {
    const el = $("#" + id);
    el.addEventListener("input", () => {
      ESTADO[grupo][clave] = el.type === "checkbox" ? el.checked
        : (el.type === "number" ? Number(el.value) : el.value);
      guardarEstado();
    });
  };
  bindea("ajuste", "simple", "ajuste");
  bindea("chaflanes", "simple", "chaflanes");
  bindea("patio", "simple", "patio");
  bindea("rad-radio-ext", "radial", "radio_ext");
  bindea("rad-nucleo", "radial", "radio_nucleo");
  bindea("rad-corredor", "radial", "corredor_m");
  bindea("rad-sectores", "radial", "sectores");
  bindea("rad-niveles", "radial", "niveles");
  bindea("y-nucleo", "y", "radio_nucleo");
  bindea("y-largo", "y", "largo_ala");
  bindea("y-ancho", "y", "ancho_ala");
  bindea("y-alas", "y", "n_alas");
  bindea("y-corredor", "y", "corredor_m");
  bindea("y-niveles", "y", "niveles");
  bindea("y-largos", "y", "largos");
  bindea("x-largo", "x", "largo_barra");
  bindea("x-ancho", "x", "ancho_barra");
  bindea("x-corredor", "x", "corredor_m");
  bindea("x-angulo", "x", "angulo");
  bindea("x-niveles", "x", "niveles");
  bindea("rj-columnas", "rejilla", "columnas");
  bindea("rj-filas", "rejilla", "filas");
  bindea("rj-pasillo", "rejilla", "pasillo_m");
}

function renderFormas() {
  $$("#modos-forma .ficha-preset").forEach((b) =>
    b.classList.toggle("activo", b.dataset.modo === ESTADO.modoForma));
  $$(".panel-forma").forEach((p) =>
    p.classList.toggle("oculto", p.dataset.panel !== ESTADO.modoForma));
  const s = ESTADO.simple, r = ESTADO.radial, y = ESTADO.y,
    x = ESTADO.x, rj = ESTADO.rejilla;
  $("#ajuste").value = s.ajuste;
  $("#chaflanes").checked = !!s.chaflanes;
  $("#patio").checked = !!s.patio;
  $("#rad-radio-ext").value = r.radio_ext;
  $("#rad-nucleo").value = r.radio_nucleo;
  $("#rad-corredor").value = r.corredor_m;
  $("#rad-sectores").value = r.sectores;
  $("#rad-niveles").value = r.niveles;
  $("#y-nucleo").value = y.radio_nucleo;
  $("#y-largo").value = y.largo_ala;
  $("#y-ancho").value = y.ancho_ala;
  $("#y-alas").value = y.n_alas;
  $("#y-corredor").value = y.corredor_m;
  $("#y-niveles").value = y.niveles;
  $("#y-largos").value = y.largos;
  $("#x-largo").value = x.largo_barra;
  $("#x-ancho").value = x.ancho_barra;
  $("#x-corredor").value = x.corredor_m;
  $("#x-angulo").value = x.angulo;
  $("#x-niveles").value = x.niveles;
  $("#rj-columnas").value = rj.columnas;
  $("#rj-filas").value = rj.filas;
  $("#rj-pasillo").value = rj.pasillo_m;
  renderAlas();
}

function renderAlas() {
  const cuerpo = $("#tabla-alas tbody");
  cuerpo.innerHTML = "";
  ESTADO.zonas.forEach((ala, i) => {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td");
    const ta = document.createElement("textarea");
    ta.rows = 2; ta.className = "mono";
    ta.value = JSON.stringify(ala.contorno);
    ta.addEventListener("change", () => {
      try { ESTADO.zonas[i].contorno = JSON.parse(ta.value); }
      catch (_) { /* se conserva el anterior */ }
      guardarEstado();
    });
    td1.appendChild(ta);
    const td2 = document.createElement("td");
    const rol = document.createElement("input");
    rol.type = "text"; rol.value = ala.rol;
    rol.addEventListener("input", () => {
      ESTADO.zonas[i].rol = rol.value; guardarEstado();
    });
    td2.appendChild(rol);
    const td3 = document.createElement("td");
    const borrar = document.createElement("button");
    borrar.className = "borrar"; borrar.textContent = "Quitar";
    borrar.addEventListener("click", () => {
      if (ESTADO.zonas.length <= 2) {
        avisoGenerar("Multi-ala necesita 2 o más alas.");
        return;
      }
      ESTADO.zonas.splice(i, 1); renderAlas(); guardarEstado();
    });
    td3.appendChild(borrar);
    tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3);
    cuerpo.appendChild(tr);
  });
}

function avisoGenerar(msg) {
  const av = $("#aviso-generar");
  av.textContent = msg;
  av.classList.remove("oculto");
}

function programaParams() {
  // el programa (qué) viaja como texto o fichas según la pestaña 1
  if (ESTADO.modoPrograma === "texto") {
    return { texto: ESTADO.quickTexto, nombre: ESTADO.nombre };
  }
  return {
    fichas: ESTADO.fichas.map((f) => ({
      space_type: f.space_type, cantidad: f.cantidad })),
    nombre: ESTADO.nombre,
  };
}

async function generar() {
  const boton = $("#btn-generar");
  boton.disabled = true;
  $("#aviso-generar").classList.add("oculto");
  limpiarError();
  try {
    let metodo, params;
    const prog = programaParams();
    if (ESTADO.modoForma === "simple") {
      const cont = contornoActual();
      if (!cont) throw "El contorno es ilegible: revise la pestaña 2.";
      params = Object.assign({}, prog, {
        contorno: cont,
        ajuste: ESTADO.simple.ajuste,
        chaflanes: !!ESTADO.simple.chaflanes,
        patio: !!ESTADO.simple.patio,
      });
      metodo = ESTADO.modoPrograma === "texto"
        ? "generar_quick" : "generar_edificacion";
    } else if (ESTADO.modoForma === "radial") {
      metodo = "generar_radial";
      params = Object.assign({}, prog, ESTADO.radial);
    } else if (ESTADO.modoForma === "y") {
      metodo = "generar_y";
      params = Object.assign({}, prog, ESTADO.y);
      params.largos_alas = String(ESTADO.y.largos || "")
        .split(",").map((s) => parseFloat(s.trim()))
        .filter((n) => !isNaN(n));
      if (!params.largos_alas.length) delete params.largos_alas;
      delete params.largos;
    } else if (ESTADO.modoForma === "x") {
      metodo = "generar_x";
      params = Object.assign({}, prog, ESTADO.x);
    } else if (ESTADO.modoForma === "zonas") {
      metodo = "generar_zonas";
      params = Object.assign({}, prog, {
        zonas: ESTADO.zonas.map((a) => ({
          contorno: a.contorno, rol: a.rol })),
      });
    } else {
      const cont = contornoActual();
      if (!cont) throw "La rejilla necesita el contorno de la pestaña 2.";
      metodo = "generar_rejilla";
      params = Object.assign({}, prog, { contorno: cont }, ESTADO.rejilla);
    }
    RESULTADO = await llamar(metodo, params);
    PIEZA_ACTIVA = 0;
    guardarEstado();
    irVista("resultado");
  } catch (e) {
    avisoGenerar(decorarError(e));
    mostrarError(decorarError(e));
  } finally {
    boton.disabled = false;
  }
}

// ------------------------------------------------------------- resultado ---
function esCompuesto(res) {
  return res && (res.tipo === "zonas" || res.tipo === "rejilla");
}

function piezasDe(res) {
  // aplana el resultado en piezas dibujables:
  // [{titulo, contorno, reparto:[nivel], totales, avisos}]
  if (esCompuesto(res)) {
    return (res.zonas || []).map((z, i) => ({
      titulo: (res.tipo === "rejilla" ? "Celda " : "Ala ") + (i + 1) +
        (z.rol ? " · " + z.rol : ""),
      contorno: z.contorno,
      reparto: z.reparto || [],
      totales: z.totales || {},
      avisos: z.avisos || [],
    }));
  }
  return [{
    titulo: res.tipo === "radial" ? "Planta radial"
      : res.tipo === "y_radial" ? "Torre en Y"
      : res.tipo === "x_radial" ? "Hospital en X" : "Encaje al contorno",
    contorno: null,
    reparto: res.reparto || [],
    totales: res.totales || {},
    avisos: res.avisos || [],
  }];
}

function renderResultado() {
  const sin = $("#sin-resultado"), con = $("#con-resultado");
  if (!RESULTADO) { sin.classList.remove("oculto"); con.classList.add("oculto"); return; }
  sin.classList.add("oculto"); con.classList.remove("oculto");

  const t = RESULTADO.totales || {}, m = RESULTADO.metricas;
  const chips = $("#chips-kpi");
  chips.innerHTML = "";
  const kpi = (texto, clase) => {
    const d = document.createElement("span");
    d.className = "kpi" + (clase ? " " + clase : "");
    d.textContent = texto;
    chips.appendChild(d);
  };
  kpi(RESULTADO.niveles + " nivel/es");
  if (t.aprovechamiento_pct != null)
    kpi("Aprovechamiento: " + num(t.aprovechamiento_pct, 1) + " %",
      RESULTADO.dentro_del_contorno === false ? "malo" : "");
  if (t.area_aprovechada != null)
    kpi("Área aprovechada: " + num(t.area_aprovechada, 1) + " m²");
  if (t.area_contorno != null)
    kpi("Contorno: " + num(t.area_contorno, 1) + " m²");
  kpi(RESULTADO.dentro_del_contorno === false
    ? "¡FUERA del contorno!" : "Dentro del contorno",
    RESULTADO.dentro_del_contorno === false ? "malo" : "ok");
  if (m) {
    kpi("Puntuación: " + num(m.puntuacion, 1), "ok");
    kpi("Ocupación: " + num(m.ocupacion_pct, 1) + " %");
    kpi("Circulación: " + num(m.circulacion_pct, 1) + " %");
    kpi("Cumplimiento: " + num(m.cumplimiento_pct, 1) + " %");
    if (m.locales_fuera) kpi("Locales fuera: " + m.locales_fuera, "malo");
  }

  // tabs: pieza · nivel
  const piezas = piezasDe(RESULTADO);
  const tabs = $("#tabs-contenedor");
  tabs.innerHTML = "";
  const totalTabs = piezas.reduce((s, p) => s + Math.max(p.reparto.length, 1), 0);
  if (totalTabs > 1 || piezas.length > 1) tabs.classList.remove("oculto");
  else tabs.classList.add("oculto");
  let idx = 0;
  piezas.forEach((p, pi) => {
    const niveles = Math.max(p.reparto.length, 1);
    for (let ni = 0; ni < niveles; ni++) {
      const b = document.createElement("button");
      b.textContent = (piezas.length > 1 ? p.titulo + " · " : "") +
        "Nivel " + (p.reparto[ni] ? p.reparto[ni].nivel : ni + 1);
      if (idx === PIEZA_ACTIVA) b.className = "activo";
      const captura = idx;
      b.addEventListener("click", () => { PIEZA_ACTIVA = captura; renderResultado(); });
      tabs.appendChild(b);
      idx++;
    }
  });

  // pieza+nivel activos
  let activo = PIEZA_ACTIVA;
  let pieza = piezas[0], nivel = null;
  for (const p of piezas) {
    const niveles = Math.max(p.reparto.length, 1);
    if (activo < niveles) { pieza = p; nivel = p.reparto[activo] || null; break; }
    activo -= niveles;
  }

  dibujarPlanta(pieza, nivel);
  renderMetricas(m, pieza);
  renderLocales(nivel, pieza);
  renderAvisos(pieza);
}

function dibujarPlanta(pieza, nivel) {
  const svg = $("#plano");
  const capas = [];
  const piezas = [];
  if (!nivel) { dibujarSVG(svg, { poligonos: [], fondo: pieza.contorno }); return; }
  if (nivel.pasillo)
    piezas.push({ puntos: nivel.pasillo.poligono || nivel.pasillo.rect,
      color: COLOR_PASILLO, etiqueta: nivel.pasillo.nombre,
      sub: num(nivel.pasillo.area_m2, 1) + " m²",
      title: nivel.pasillo.nombre });
  for (const p of nivel.pasillos || [])
    piezas.push({ puntos: p.poligono || p.rect, color: COLOR_PASILLO,
      etiqueta: p.nombre, sub: num(p.area_m2, 1) + " m²",
      title: (p.ala != null ? "ala " + p.ala + " · " : "") + p.nombre });
  if (nivel.escalera)
    piezas.push({ puntos: nivel.escalera.rect, color: COLOR_ESCALERA,
      etiqueta: nivel.escalera.nombre, sub: num(nivel.escalera.area_m2, 1) + " m²" });
  if (nivel.patio)
    piezas.push({ puntos: nivel.patio.rect, color: COLOR_PATIO,
      etiqueta: nivel.patio.nombre, sub: num(nivel.patio.area_m2, 1) + " m²" });
  for (const l of nivel.locales || [])
    piezas.push({ puntos: l.poligono || l.rect,
      color: PALETA[l.flujo] || COLOR_FONDO,
      etiqueta: l.nombre, sub: num(l.area_m2, 1) + " m²", title: l.nombre });
  capas.push(piezas);
  dibujarSVG(svg, { poligonos: capas, fondo: pieza.contorno,
    etiquetaMinPx: 42 });
}

function renderMetricas(m, pieza) {
  const cont = $("#metricas");
  if (!m) {
    cont.innerHTML = par("Métricas", "no disponibles para compuestos") +
      par("Aviso", "los totales por ala/celda llegan en cada tab");
    return;
  }
  cont.innerHTML =
    par("Puntuación", num(m.puntuacion, 2)) +
    par("Área construida", num(m.area_construida_m2, 1) + " m²") +
    par("Área útil", num(m.area_util_m2, 1) + " m²") +
    par("Circulación", num(m.circulacion_pct, 1) + " %") +
    par("Ocupación", num(m.ocupacion_pct, 1) + " %") +
    par("Cumplimiento", num(m.cumplimiento_pct, 1) + " %") +
    par("Locales fuera", m.locales_fuera || 0) +
    par("Motivo", m.motivo || "—");
}

function renderLocales(nivel, pieza) {
  const cont = $("#tabla-locales");
  if (!nivel || !nivel.locales) {
    cont.innerHTML = '<div class="aviso">Sin locales en este nivel.</div>';
    return;
  }
  let html = '<table><tr><th></th><th>Local</th><th>Área</th><th>Flujo</th></tr>';
  const fila = (color, nombre, area, flujo) =>
    "<tr><td><span class='swatch' data-c='" + color + "'></span></td>" +
    "<td>" + esc(nombre) + "</td><td>" + num(area, 1) + " m²</td><td>" +
    esc(flujo || "") + "</td></tr>";
  if (nivel.pasillo)
    html += fila(COLOR_PASILLO, nivel.pasillo.nombre, nivel.pasillo.area_m2, "circulación");
  for (const p of nivel.pasillos || [])
    html += fila(COLOR_PASILLO, p.nombre, p.area_m2, "corredor");
  if (nivel.escalera)
    html += fila(COLOR_ESCALERA, nivel.escalera.nombre, nivel.escalera.area_m2, "circulación");
  if (nivel.patio)
    html += fila(COLOR_PATIO, nivel.patio.nombre, nivel.patio.area_m2, "exterior");
  for (const l of nivel.locales)
    html += fila(PALETA[l.flujo] || COLOR_FONDO, l.nombre, l.area_m2, l.flujo);
  html += "</table>";
  cont.innerHTML = html;
  // el swatch usa data-c porque CSP prohíbe el atributo style
  $$("#tabla-locales .swatch").forEach((s) => s.style.background = s.dataset.c);
}

function renderAvisos(pieza) {
  const cont = $("#avisos");
  let html = "";
  const chs = (RESULTADO.chaflanes || []);
  if (chs.length) {
    html += '<div class="aviso">Chaflanes 45°: ' + chs.length +
      " — " + chs.map((c) => esc(c.local || "")).join(", ") +
      " (pérdida total " + num(chs.reduce((s, c) => s + (c.perdida_m2 || 0), 0), 2) + " m²)</div>";
  }
  for (const a of pieza.avisos || [])
    html += '<div class="aviso">' + esc(a) + "</div>";
  for (const a of RESULTADO.avisos || [])
    html += '<div class="aviso">' + esc(a) + "</div>";
  cont.innerHTML = html || '<div class="aviso">Sin avisos: generación limpia.</div>';
}

// ------------------------------------------------------------- exportar ---
function initExportar() {
  $("#exp-carpeta").addEventListener("input", () => {
    ESTADO.exportar.carpeta = $("#exp-carpeta").value; guardarEstado();
  });
  $("#exp-base").addEventListener("input", () => {
    ESTADO.exportar.base = $("#exp-base").value; guardarEstado();
  });
  $$("#exp-formatos input").forEach((cb) =>
    cb.addEventListener("change", () => {
      ESTADO.exportar.formatos = $$("#exp-formatos input:checked")
        .map((c) => c.value);
      guardarEstado();
    }));
  $("#exp-muros").addEventListener("change", () => {
    ESTADO.exportar.muros = $("#exp-muros").checked; guardarEstado();
  });
  $("#exp-proyecto").addEventListener("change", () => {
    ESTADO.exportar.con_proyecto = $("#exp-proyecto").checked; guardarEstado();
  });
  $("#exp-mobiliario").addEventListener("change", () => {
    ESTADO.exportar.mobiliario = $("#exp-mobiliario").value; guardarEstado();
  });
  $("#btn-exportar").addEventListener("click", exportar);
}

function renderExportarVista() {
  const hay = !!RESULTADO;
  $("#sin-resultado-exp").classList.toggle("oculto", hay);
  $("#con-exportar").classList.toggle("oculto", !hay);
  if (!hay) return;
  const e = ESTADO.exportar;
  $("#exp-carpeta").value = e.carpeta;
  $("#exp-base").value = e.base;
  $$("#exp-formatos input").forEach((cb) =>
    cb.checked = e.formatos.includes(cb.value));
  $("#exp-muros").checked = !!e.muros;
  $("#exp-proyecto").checked = !!e.con_proyecto;
  $("#exp-mobiliario").value = e.mobiliario;
  if (!e.carpeta) resolverCarpetaDescargas();
}

async function resolverCarpetaDescargas() {
  try {
    const dir = await window.__TAURI__.core.invoke("carpeta_descargas");
    if (dir) {
      ESTADO.exportar.carpeta = dir + "/ARQ_GEN";
      $("#exp-carpeta").value = ESTADO.exportar.carpeta;
      guardarEstado();
    }
  } catch (_) { /* sin Tauri o sin descargas: la ruta se escribe a mano */ }
}

async function exportar() {
  const boton = $("#btn-exportar");
  boton.disabled = true;
  $("#aviso-exportar").classList.add("oculto");
  limpiarError();
  try {
    if (!RESULTADO || !RESULTADO.id)
      throw "Necesita un resultado (GENERAR) antes de exportar.";
    const carpeta = String(ESTADO.exportar.carpeta || "").trim();
    if (!carpeta) throw "Escriba la carpeta de destino (ruta absoluta).";
    const mob = ESTADO.exportar.mobiliario;
    const params = {
      id: RESULTADO.id,
      carpeta,
      nombre_base: ESTADO.exportar.base || "proyecto_arqgen",
      formatos: ESTADO.exportar.formatos,
      trazar_muros: !!ESTADO.exportar.muros,
      con_proyecto: !!ESTADO.exportar.con_proyecto,
      mobiliario: mob === "auto" ? null : mob === "si",
    };
    const res = await llamar("aplicar_exportar", params);
    const cuerpo = $("#tabla-archivos tbody");
    cuerpo.innerHTML = "";
    const filas = [];
    for (const [fmt, info] of Object.entries(res.archivos || {})) {
      filas.push("<tr><td>" + esc(fmt) + "</td><td class='mono'>" +
        esc(info.ruta) + "</td><td>" + num(info.bytes, 0) + " B</td></tr>");
    }
    if (res.proyecto) {
      filas.push("<tr><td>PROYECTO</td><td class='mono'>" +
        esc(res.proyecto.ruta) + "</td><td>" + num(res.proyecto.bytes, 0) +
        " B</td></tr>");
    }
    cuerpo.innerHTML = filas.join("");
    $("#exp-resultado").classList.remove("oculto");
    const errs = Object.entries(res.errores || {});
    $("#exp-errores").innerHTML = errs.length
      ? "<div class='aviso error'>Formatos con error: " +
        errs.map(([f, m]) => esc(f) + ": " + esc(m)).join(" · ") + "</div>"
      : "";
    guardarEstado();
  } catch (e) {
    const msg = decorarError(e);
    $("#aviso-exportar").textContent = msg;
    $("#aviso-exportar").classList.remove("oculto");
    mostrarError(msg);
  } finally {
    boton.disabled = false;
  }
}

// -------------------------------------------------------------- proyecto ---
function initProyecto() {
  $("#fichero-proyecto").addEventListener("change", () => {
    const fichero = $("#fichero-proyecto").files[0];
    if (!fichero) return;
    const lector = new FileReader();
    lector.onload = () => {
      try {
        const snap = JSON.parse(String(lector.result));
        if (snap.format !== "ARQ_GEN_SNAPSHOT")
          throw "No es una instantánea ARQ_GEN_SNAPSHOT.";
        const ent = snap.entities || {};
        const datos = $("#proyecto-datos");
        const pr = snap.project || {};
        datos.innerHTML =
          par("Nombre", pr.name || "—") +
          par("Cliente", pr.client || "—") +
          par("Dirección", pr.address || "—") +
          par("Moneda", pr.currency || "—") +
          par("Formato", snap.format + " v" + snap.version);
        const chips = $("#proyecto-recuentos");
        chips.innerHTML = "";
        let espacios = 0, niveles = 0, muros = 0;
        for (const [tipo, filas] of Object.entries(ent)) {
          const n = (filas || []).length;
          if (tipo === "SPACE") espacios = n;
          if (tipo === "LEVEL") niveles = n;
          if (tipo === "WALL") muros = n;
          const d = document.createElement("span");
          d.className = "kpi";
          d.textContent = tipo + ": " + n;
          chips.appendChild(d);
        }
        $("#proyecto-info").classList.remove("oculto");
        $("#proyecto-errores").innerHTML =
          '<div class="aviso">Lectura local: ' + niveles + " nivel(es), " +
          espacios + " espacio(s), " + muros + " muro(s). " +
          "Para importar al motor: ARQ_GEN import <archivo>.</div>";
      } catch (e2) {
        mostrarError("Instantánea ilegible: " + e2);
      }
    };
    lector.readAsText(fichero);
  });
}

// ------------------------------------------------------------------ init ---
cargarEstado();
initPrograma();
initContorno();
initFormas();
initExportar();
initProyecto();
renderPrograma();
renderContorno();
renderFormas();
comprobarMotor();
cargarCatalogo();
