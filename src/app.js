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
let VISTA3D_SECUENCIA = 0; // descarta respuestas de una vista ya sustituida
let CAMARA3D = { azimut: 30, elevacion: 35 };

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
  if (MUTACION3D) { mostrarError("Espere a que termine la operación 3D anterior."); return; }
  if (MODELO3D_EDITADO && !window.confirm("El resultado actual tiene ediciones 3D. " +
      "Al generar otro dejará de poder editarlas aquí. Exporte antes una instantánea si desea conservarlas. ¿Continuar?")) return;
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
    reiniciarVista3D();
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
  const importado = RESULTADO.tipo === "proyecto_importado";
  $("#datos-analisis").classList.toggle("oculto", importado);
  $("#avisos-analisis").classList.toggle("oculto", importado);
  $("#resumen-proyecto-3d").classList.toggle("oculto", !importado);
  if (importado) {
    $("#resumen-proyecto-3d").textContent = "Proyecto importado: " + (RESULTADO.nombre || "sin nombre") +
      ". " + (RESULTADO.avisos || []).join(" · ");
    return;
  }

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

// ------------------------------------------------------------- vista 3D ---
// Encuadre interactivo normalizado para conservar zoom/desplazamiento al orbitar.
let NAVEGACION3D = {zoom: 1, panX: 0, panY: 0, base: null, arrastre: null};
let SELECCION3D = null, SELECCION3D_SECUENCIA = 0, MODELO3D_EDITADO = false;
let SUPRIMIR_CLICK3D = false, CAMARA_PROYECTADA3D = null;
let MODELO3D_SIN_EXPORTAR = false, CAMBIOS3D = 0, MUTACION3D = false;
let ORBITA3D_TIMER = null, ORBITA3D_EN_CURSO = false, ORBITA3D_PENDIENTE = false;

function reiniciarVista3D() {
  // Una petición de otro resultado puede llegar más tarde: no la mostramos.
  VISTA3D_SECUENCIA++;
  CAMARA3D = { azimut: 30, elevacion: 35 };
  NAVEGACION3D = {zoom: 1, panX: 0, panY: 0, base: null, arrastre: null};
  if (ORBITA3D_TIMER) clearTimeout(ORBITA3D_TIMER);
  ORBITA3D_TIMER = null; ORBITA3D_PENDIENTE = false;
  SELECCION3D = null; SELECCION3D_SECUENCIA++; MODELO3D_EDITADO = false; CAMARA_PROYECTADA3D = null;
  MODELO3D_SIN_EXPORTAR = false;
  $("#propiedades-3d").replaceChildren();
  $("#visor-3d").classList.add("oculto");
  $("#btn-vista-3d").textContent = "Mostrar vista 3D";
  $("#btn-vista-3d").setAttribute("aria-expanded", "false");
  $("#nivel-3d").replaceChildren(new Option("Todos", ""));
  $("#proyeccion-3d").value = "ortogonal";
  $("#explosion-3d").value = "0";
  $("#modelo-3d").replaceChildren();
  $("#estado-3d").textContent = "";
  $("#avisos-3d").replaceChildren();
}

function dibujarVista3D(vista) {
  const svg = $("#modelo-3d");
  svg.replaceChildren();
  const caja = vista.encuadre;
  CAMARA_PROYECTADA3D = vista.camara || null;
  if (!Array.isArray(caja) || caja.length !== 4 || !caja.every(Number.isFinite) ||
      !Array.isArray(vista.caras) || !vista.caras.length) {
    svg.setAttribute("viewBox", "0 0 100 100");
    return;
  }
  const [x, y, ancho, alto] = caja;
  const margen = Math.max(ancho, alto, 1) * 0.06;
  NAVEGACION3D.base = [x - margen, y - margen,
    Math.max(ancho, 0.01) + 2 * margen, Math.max(alto, 0.01) + 2 * margen];
  aplicarEncuadre3D();
  const ns = "http://www.w3.org/2000/svg";
  for (const cara of vista.caras) {
    if (!Array.isArray(cara.puntos) || cara.puntos.length < 3 ||
        !cara.puntos.every((p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite))) continue;
    const poligono = document.createElementNS(ns, "polygon");
    poligono.setAttribute("points", cara.puntos.map((p) => p.join(",")).join(" "));
    poligono.setAttribute("fill", /^#[0-9a-f]{6}$/i.test(cara.color) ? cara.color : "#aeb9c4");
    const seleccionado = SELECCION3D && cara.entidad_id === SELECCION3D.id &&
      cara.entidad_tipo === SELECCION3D.tipo;
    poligono.setAttribute("stroke", seleccionado ? "#ff9000" : "#5d6d7e");
    poligono.setAttribute("stroke-width", seleccionado ? "2" : "0.7");
    poligono.setAttribute("vector-effect", "non-scaling-stroke");
    if (cara.entidad_id && cara.entidad_tipo) {
      poligono.setAttribute("data-entidad-id", cara.entidad_id);
      if (Array.isArray(cara.centro_mundo) && cara.centro_mundo.length === 3)
        poligono.setAttribute("data-centro-mundo", cara.centro_mundo.join(","));
      poligono.addEventListener("click", (e) => { e.stopPropagation(); if (!SUPRIMIR_CLICK3D) seleccionar3D(cara); });
    }
    svg.appendChild(poligono);
  }
}

function cajaActual3D() {
  const b = NAVEGACION3D.base;
  if (!b) return null;
  const w = b[2] / NAVEGACION3D.zoom, h = b[3] / NAVEGACION3D.zoom;
  return [b[0] + b[2] / 2 - w / 2 + NAVEGACION3D.panX * b[2],
    b[1] + b[3] / 2 - h / 2 + NAVEGACION3D.panY * b[3], w, h];
}
function aplicarEncuadre3D() {
  const caja = cajaActual3D();
  if (caja) $("#modelo-3d").setAttribute("viewBox", caja.join(" "));
}
// Intersección de un rayo de pantalla con el plano horizontal del punto
// agarrado. Devuelve null cerca del horizonte o del plano de recorte.
function planoXY3D(sx, sy, z, cam) {
  const az = cam.azimut * Math.PI / 180, el = cam.elevacion * Math.PI / 180;
  const c = Math.cos(az), s = Math.sin(az), ce = Math.cos(el), se = Math.sin(el);
  if (!cam.perspectiva) {
    const yr = sy / se;
    return [c*sx + s*yr, -s*sx + c*yr];
  }
  const [cx, cy, cz] = cam.centro, d = cam.distancia, pz = z - cz;
  if (!(d > 0)) return null;
  const den = se + sy*ce/d;
  if (Math.abs(den) < 1e-7) return null;
  const yr = (sy*(1-pz*se/d) + pz*ce) / den;
  const q = 1-(yr*ce+pz*se)/d;
  if (q <= Math.max(cam.cerca_fraccion || 0.12, 0.25/d)) return null;
  const xr = sx*q;
  const punto = [cx+c*xr+s*yr, cy-s*xr+c*yr];
  return punto.every(Number.isFinite) ? punto : null;
}

// Altura del punto de agarre tras moverlo verticalmente en pantalla.
function alturaDesdePantalla3D(centro, dy, cam) {
  const az = cam.azimut*Math.PI/180, el = cam.elevacion*Math.PI/180;
  const se = Math.sin(el), ce = Math.cos(el);
  if (!cam.perspectiva) return centro[2] - dy/ce;
  const [cx,cy,cz] = cam.centro, d = cam.distancia;
  if (!(d > 0)) return null;
  const yr = (centro[0]-cx)*Math.sin(az) + (centro[1]-cy)*Math.cos(az);
  const pz = centro[2]-cz, q = 1-(yr*ce+pz*se)/d;
  if (q <= Math.max(cam.cerca_fraccion || 0.12, 0.25/d)) return null;
  const sy = (yr*se-pz*ce)/q + dy;
  const den = sy*se/d-ce;
  if (Math.abs(den) < 1e-7) return null;
  const nuevoZ = (sy*(1-yr*ce/d)-yr*se)/den;
  const nuevoQ = 1-(yr*ce+nuevoZ*se)/d;
  return Number.isFinite(nuevoZ) && nuevoQ > Math.max(cam.cerca_fraccion || 0.12, 0.25/d)
    ? cz+nuevoZ : null;
}

function limpiarSeleccion3D() {
  SELECCION3D = null; SELECCION3D_SECUENCIA++;
  $("#propiedades-3d").replaceChildren();
  // Actualizar las aristas sin volver al motor.
  const svg = $("#modelo-3d");
  for (const p of svg.querySelectorAll("polygon")) {
    p.setAttribute("stroke", "#5d6d7e"); p.setAttribute("stroke-width", "0.7");
  }
}
async function seleccionar3D(cara) {
  if (!RESULTADO || !RESULTADO.id) return;
  const idResultado = RESULTADO.id, secuencia = ++SELECCION3D_SECUENCIA;
  const panel = $("#propiedades-3d");
  panel.textContent = "Cargando propiedades…";
  try {
    const info = await llamar("elemento_3d", {id: idResultado, tipo: cara.entidad_tipo,
      elemento_id: cara.entidad_id});
    if (secuencia !== SELECCION3D_SECUENCIA || !RESULTADO || RESULTADO.id !== idResultado) return;
    SELECCION3D = info;
    panel.replaceChildren();
    const titulo = document.createElement("h4");
    titulo.textContent = info.tipo + " · " + (info.nombre || info.codigo || info.id);
    panel.appendChild(titulo);
    const svg = $("#modelo-3d");
    for (const p of svg.querySelectorAll("polygon")) {
      const activo = p.getAttribute("data-entidad-id") === info.id;
      p.setAttribute("stroke", activo ? "#ff9000" : "#5d6d7e");
      p.setAttribute("stroke-width", activo ? "2" : "0.7");
    }
    if (!info.campos.length) {
      const aviso = document.createElement("p");
      aviso.textContent = "Elemento identificado; sus propiedades todavía no son editables aquí.";
      panel.appendChild(aviso);
      return;
    }
    const formulario = document.createElement("form"), entradas = [];
    for (const campo of info.campos) {
      const etiqueta = document.createElement("label"), entrada = document.createElement(campo.tipo === "opcion" ? "select" : "input");
      etiqueta.textContent = campo.etiqueta;
      if (campo.tipo === "opcion") {
        for (const opcion of campo.opciones || []) entrada.add(new Option(opcion, opcion));
      } else {
        entrada.type = campo.tipo === "numero" ? "number" : "text";
        if (campo.tipo === "numero") { entrada.step = "any"; entrada.min = campo.min; entrada.max = campo.max; }
      }
      entrada.required = true; entrada.value = campo.valor;
      etiqueta.appendChild(entrada); formulario.appendChild(etiqueta);
      entradas.push({campo, entrada});
    }
    const boton = document.createElement("button"); boton.type = "submit"; boton.textContent = "Guardar cambios";
    const mensaje = document.createElement("p"); mensaje.setAttribute("role", "status");
    mensaje.textContent = (info.avisos || []).join(" · ");
    formulario.appendChild(boton); panel.appendChild(formulario); panel.appendChild(mensaje);
    if (info.tipo === "STAIR") {
      const borrar = document.createElement("button");
      borrar.type = "button"; borrar.textContent = "Borrar escalera";
      panel.appendChild(borrar);
      borrar.addEventListener("click", async () => {
        if (MUTACION3D) { mensaje.textContent = "Espere a que termine la operación 3D anterior."; return; }
        if (!window.confirm("¿Borrar esta escalera? Puede deshacer el cambio en esta sesión.")) return;
        MUTACION3D = true; borrar.disabled = true; boton.disabled = true;
        try {
          await llamar("borrar_escalera_3d", {id: idResultado, elemento_id: info.id, revision: info.revision});
          if (RESULTADO && RESULTADO.id === idResultado) {
            MODELO3D_EDITADO = true; MODELO3D_SIN_EXPORTAR = true; CAMBIOS3D++;
            if (secuencia === SELECCION3D_SECUENCIA) limpiarSeleccion3D();
            await actualizarVista3D();
          }
        } catch (e) { mensaje.textContent = "No se pudo borrar: " + decorarError(e); }
        finally { borrar.disabled = false; boton.disabled = false; MUTACION3D = false; }
      });
    }
    formulario.addEventListener("submit", async (e) => {
      e.preventDefault();
      const valores = {};
      for (const {campo, entrada} of entradas) {
        const valor = campo.tipo === "numero" ? Number(entrada.value) : entrada.value;
        if (valor !== campo.valor) valores[campo.campo] = valor;
      }
      if (!Object.keys(valores).length) { mensaje.textContent = "No hay cambios."; return; }
      if (MUTACION3D) { mensaje.textContent = "Espere a que termine la operación 3D anterior."; return; }
      MUTACION3D = true; boton.disabled = true; mensaje.textContent = "Guardando…";
      try {
        const actualizado = await llamar("editar_3d", {id: idResultado, tipo: info.tipo,
          elemento_id: info.id, revision: info.revision, valores});
        if (RESULTADO && RESULTADO.id === idResultado) {
          MODELO3D_EDITADO = true; MODELO3D_SIN_EXPORTAR = true; CAMBIOS3D++;
        }
        if (secuencia !== SELECCION3D_SECUENCIA || !RESULTADO || RESULTADO.id !== idResultado) return;
        SELECCION3D = actualizado;
        Object.assign(info, actualizado);
        for (const {campo, entrada} of entradas) {
          const nuevo = info.campos.find((c) => c.campo === campo.campo);
          campo.valor = nuevo.valor; entrada.value = nuevo.valor;
        }
        mensaje.textContent = "Guardado en la sesión. Exporte con muros y mobiliario automático. " +
          (info.avisos || []).join(" · ");
        actualizarVista3D();
      } catch (e) { mensaje.textContent = "No se pudo guardar: " + decorarError(e); }
      finally { boton.disabled = false; MUTACION3D = false; }
    });
  } catch (e) {
    if (secuencia === SELECCION3D_SECUENCIA) panel.textContent = "No se pudo seleccionar: " + decorarError(e);
  }
}

// Coalescer evita inundar el sidecar con una petición por cada píxel.
function solicitarOrbita3D() {
  ORBITA3D_PENDIENTE = true;
  if (ORBITA3D_EN_CURSO || ORBITA3D_TIMER) return;
  ORBITA3D_TIMER = setTimeout(async () => {
    ORBITA3D_TIMER = null;
    if (!ORBITA3D_PENDIENTE) return;
    ORBITA3D_PENDIENTE = false; ORBITA3D_EN_CURSO = true;
    try { await actualizarVista3D(); }
    finally {
      ORBITA3D_EN_CURSO = false;
      if (ORBITA3D_PENDIENTE) solicitarOrbita3D();
    }
  }, 50);
}

async function actualizarVista3D() {
  if (!RESULTADO || !RESULTADO.id || $("#visor-3d").classList.contains("oculto")) return;
  const id = RESULTADO.id;
  const secuencia = ++VISTA3D_SECUENCIA;
  const nivel = $("#nivel-3d").value;
  $("#estado-3d").textContent = "Generando vista 3D…";
  try {
    const vista = await llamar("vista_3d", {
      id, azimut: CAMARA3D.azimut, elevacion: CAMARA3D.elevacion,
      perspectiva: $("#proyeccion-3d").value === "perspectiva",
      nivel: nivel === "" ? null : Number(nivel),
      explosion_m: Number($("#explosion-3d").value),
    });
    if (secuencia !== VISTA3D_SECUENCIA || !RESULTADO || RESULTADO.id !== id) return;
    const selector = $("#nivel-3d");
    selector.replaceChildren(new Option("Todos", ""));
    (vista.niveles || []).forEach((n, i) => {
      selector.add(new Option(n.nombre + " (" + num(n.cota_m, 1) + " m)", String(i)));
    });
    selector.value = nivel;
    dibujarVista3D(vista);
    $("#estado-3d").textContent = vista.caras.length
      ? "Azimut " + CAMARA3D.azimut + "° · elevación " + CAMARA3D.elevacion + "°"
      : "No hay geometría para mostrar.";
    const avisos = $("#avisos-3d");
    avisos.replaceChildren();
    for (const aviso of vista.avisos || []) {
      const item = document.createElement("div");
      item.className = "aviso";
      item.textContent = aviso;
      avisos.appendChild(item);
    }
  } catch (e) {
    if (secuencia !== VISTA3D_SECUENCIA || !RESULTADO || RESULTADO.id !== id) return;
    $("#modelo-3d").replaceChildren();
    $("#estado-3d").textContent = "No se pudo generar la vista 3D: " + decorarError(e);
  }
}

function initVista3D() {
  $("#crear-escalera-3d").addEventListener("click", async () => {
    if (!RESULTADO || !RESULTADO.id || MUTACION3D) return;
    const id = RESULTADO.id, boton = $("#crear-escalera-3d");
    const nivel = $("#nivel-3d").value;
    MUTACION3D = true; boton.disabled = true;
    try {
      const info = await llamar("crear_escalera_3d", {id,
        tipo: $("#tipo-nueva-escalera").value, nivel: nivel === "" ? null : Number(nivel)});
      if (!RESULTADO || RESULTADO.id !== id) return;
      MODELO3D_EDITADO = true; MODELO3D_SIN_EXPORTAR = true; CAMBIOS3D++;
      await seleccionar3D({entidad_id: info.id, entidad_tipo: "STAIR"});
      actualizarVista3D();
    } catch (e) {
      if (RESULTADO && RESULTADO.id === id)
        $("#propiedades-3d").textContent = "No se pudo crear la escalera: " + decorarError(e);
    } finally { boton.disabled = false; MUTACION3D = false; }
  });
  for (const [selector, metodo] of [["#deshacer-3d", "deshacer_3d"], ["#rehacer-3d", "rehacer_3d"]]) {
    $(selector).addEventListener("click", async () => {
      if (!RESULTADO || !RESULTADO.id || MUTACION3D) return;
      const id = RESULTADO.id, boton = $(selector);
      MUTACION3D = true; boton.disabled = true;
      try {
        await llamar(metodo, {id});
        if (!RESULTADO || RESULTADO.id !== id) return;
        MODELO3D_EDITADO = true; MODELO3D_SIN_EXPORTAR = true; CAMBIOS3D++;
        limpiarSeleccion3D();
        actualizarVista3D();
      } catch (e) {
        if (RESULTADO && RESULTADO.id === id)
          $("#propiedades-3d").textContent = decorarError(e);
      } finally { boton.disabled = false; MUTACION3D = false; }
    });
  }
  const svg = $("#modelo-3d");
  svg.addEventListener("contextmenu", (e) => e.preventDefault());
  svg.addEventListener("pointerdown", (e) => {
    // Mayús+izquierdo mueve XY; Ctrl+Mayús+izquierdo mueve Z.
    // Se aplica una sola mutación validada al soltar, no por cada píxel.
    if (e.button === 0 && e.shiftKey && SELECCION3D && RESULTADO &&
        ["STAIR", "FURNITURE"].includes(SELECCION3D.tipo) && !MUTACION3D &&
        NAVEGACION3D.base &&
        e.target && e.target.getAttribute("data-entidad-id") === SELECCION3D.id) {
      const x = SELECCION3D.campos.find((c) => c.campo === "x"),
            y = SELECCION3D.campos.find((c) => c.campo === "y");
      const z = SELECCION3D.campos.find((c) => c.campo === "base_offset_m");
      const cam = CAMARA_PROYECTADA3D || {perspectiva:false, azimut:CAMARA3D.azimut,
        elevacion:CAMARA3D.elevacion, centro:[0,0,0], distancia:0};
      const centro = (e.target.getAttribute("data-centro-mundo") || "0,0,0").split(",").map(Number);
      if (!x || !y || (e.ctrlKey && !z) || centro.length !== 3 || !centro.every(Number.isFinite) ||
          (cam.perspectiva && !CAMARA_PROYECTADA3D)) return;
      const rect = svg.getBoundingClientRect(), caja = cajaActual3D();
      if (!rect.width || !rect.height) return;
      const escala = Math.max(caja[2]/rect.width, caja[3]/rect.height);
      const sx = caja[0]+caja[2]/2+(e.clientX-rect.left-rect.width/2)*escala;
      const sy = caja[1]+caja[3]/2+(e.clientY-rect.top-rect.height/2)*escala;
      const puntoInicial = planoXY3D(sx, sy, centro[2], cam);
      if (!e.ctrlKey && !puntoInicial) { $("#estado-3d").textContent = "No se puede arrastrar cerca del horizonte."; return; }
      e.preventDefault(); svg.setPointerCapture(e.pointerId);
      NAVEGACION3D.arrastre = {id: e.pointerId, boton: 0, inicioX: e.clientX,
        inicioY: e.clientY, movido: false, seleccion: SELECCION3D,
        resultadoId: RESULTADO.id, seleccionSecuencia: SELECCION3D_SECUENCIA,
        originalX: x.valor, originalY: y.valor, originalZ: z ? z.valor : 0,
        vertical: !!e.ctrlKey, centro, camara: cam, sx, sy, puntoInicial, px: 0, py: 0,
        azimut: CAMARA3D.azimut, elevacion: CAMARA3D.elevacion,
        proyeccion: $("#proyeccion-3d").value, caja: cajaActual3D().join(",")};
      return;
    }
    if ((e.button !== 1 && e.button !== 2) || !NAVEGACION3D.base) return;
    e.preventDefault();
    svg.setPointerCapture(e.pointerId);
    NAVEGACION3D.arrastre = {id: e.pointerId, x: e.clientX, y: e.clientY,
      boton: e.button, movido: false};
  });
  svg.addEventListener("pointermove", (e) => {
    const a = NAVEGACION3D.arrastre;
    if (!a || a.id !== e.pointerId || !NAVEGACION3D.base) return;
    if (a.boton === 0) {
      const rect = svg.getBoundingClientRect(), caja = cajaActual3D();
      if (!rect.width || !rect.height) return;
      const escala = Math.max(caja[2] / rect.width, caja[3] / rect.height);
      a.px = a.vertical ? 0 : (e.clientX - a.inicioX) * escala;
      a.py = (e.clientY - a.inicioY) * escala;
      a.movido = Math.hypot(e.clientX-a.inicioX, e.clientY-a.inicioY) > 3;
      for (const p of svg.querySelectorAll("polygon"))
        if (p.getAttribute("data-entidad-id") === a.seleccion.id)
          p.setAttribute("transform", a.movido ? `translate(${a.px} ${a.py})` : "");
      return;
    }
    const dx = e.clientX - a.x, dy = e.clientY - a.y;
    a.x = e.clientX; a.y = e.clientY;
    if (dx || dy) a.movido = true;
    if (a.boton === 2 || e.shiftKey) {
      const rect = svg.getBoundingClientRect(), caja = cajaActual3D();
      if (!rect.width || !rect.height) return;
      const escala = Math.max(caja[2] / rect.width, caja[3] / rect.height);
      NAVEGACION3D.panX -= dx * escala / NAVEGACION3D.base[2];
      NAVEGACION3D.panY -= dy * escala / NAVEGACION3D.base[3];
      aplicarEncuadre3D();
    } else {
      CAMARA3D.azimut = ((CAMARA3D.azimut + dx * 0.4) % 360 + 360) % 360;
      CAMARA3D.elevacion = Math.max(8, Math.min(80, CAMARA3D.elevacion - dy * 0.4));
      solicitarOrbita3D();
    }
  });
  const terminar = (e) => {
    const a = NAVEGACION3D.arrastre;
    if (!a || a.id !== e.pointerId) return;
    NAVEGACION3D.arrastre = null;
    if (a.boton === 0) {
      for (const p of svg.querySelectorAll("polygon")) p.removeAttribute("transform");
      if (e.type === "pointercancel" || !a.movido) return;
      SUPRIMIR_CLICK3D = true; setTimeout(() => { SUPRIMIR_CLICK3D = false; }, 0);
      if (MUTACION3D || !RESULTADO || RESULTADO.id !== a.resultadoId ||
          SELECCION3D_SECUENCIA !== a.seleccionSecuencia) return;
      if (CAMARA3D.azimut !== a.azimut || CAMARA3D.elevacion !== a.elevacion ||
          $("#proyeccion-3d").value !== a.proyeccion || cajaActual3D().join(",") !== a.caja ||
          (CAMARA_PROYECTADA3D && CAMARA_PROYECTADA3D !== a.camara)) {
        $("#estado-3d").textContent = "La cámara cambió durante el arrastre; vuelva a intentarlo.";
        return;
      }
      let valores;
      if (a.vertical) {
        const altura = alturaDesdePantalla3D(a.centro, a.py, a.camara);
        if (altura === null) { $("#estado-3d").textContent = "Movimiento vertical fuera de la cámara."; return; }
        valores = {base_offset_m: a.originalZ + altura - a.centro[2]};
      } else {
        const punto = planoXY3D(a.sx+a.px, a.sy+a.py, a.centro[2], a.camara);
        if (!punto) { $("#estado-3d").textContent = "Movimiento fuera del plano visible."; return; }
        valores = {x: a.originalX+punto[0]-a.puntoInicial[0],
                   y: a.originalY+punto[1]-a.puntoInicial[1]};
      }
      MUTACION3D = true;
      llamar("editar_3d", {id: a.resultadoId, tipo: a.seleccion.tipo,
        elemento_id: a.seleccion.id, revision: a.seleccion.revision, valores})
        .then(async () => {
          if (!RESULTADO || RESULTADO.id !== a.resultadoId) return;
          MODELO3D_EDITADO = true; MODELO3D_SIN_EXPORTAR = true; CAMBIOS3D++;
          if (SELECCION3D_SECUENCIA === a.seleccionSecuencia)
            await seleccionar3D({entidad_id: a.seleccion.id, entidad_tipo: a.seleccion.tipo});
          await actualizarVista3D();
        })
        .catch((error) => { $("#estado-3d").textContent = "No se pudo mover: " + decorarError(error); })
        .finally(() => { MUTACION3D = false; });
      return;
    }
    if (e.type !== "pointercancel" && a.boton === 2 && !a.movido) limpiarSeleccion3D();
  };
  svg.addEventListener("pointerup", terminar);
  svg.addEventListener("pointercancel", terminar);
  svg.addEventListener("wheel", (e) => {
    const b = NAVEGACION3D.base, caja = cajaActual3D();
    if (!b || !caja) return;
    e.preventDefault();
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const escala = Math.max(caja[2] / rect.width, caja[3] / rect.height);
    const cx = (e.clientX - rect.left - rect.width / 2) * escala;
    const cy = (e.clientY - rect.top - rect.height / 2) * escala;
    const factor = Math.exp(-Math.max(-100, Math.min(100, e.deltaY)) * 0.003);
    const anterior = NAVEGACION3D.zoom;
    NAVEGACION3D.zoom = Math.max(0.25, Math.min(20, anterior * factor));
    const proporcion = 1 - anterior / NAVEGACION3D.zoom;
    NAVEGACION3D.panX += cx * proporcion / b[2];
    NAVEGACION3D.panY += cy * proporcion / b[3];
    aplicarEncuadre3D();
  }, {passive: false});
  svg.addEventListener("click", (e) => { if (!SUPRIMIR_CLICK3D && e.target === svg) limpiarSeleccion3D(); });
  $("#btn-vista-3d").addEventListener("click", () => {
    const visor = $("#visor-3d"), abrir = visor.classList.contains("oculto");
    visor.classList.toggle("oculto", !abrir);
    $("#btn-vista-3d").textContent = abrir ? "Ocultar vista 3D" : "Mostrar vista 3D";
    $("#btn-vista-3d").setAttribute("aria-expanded", String(abrir));
    if (abrir) actualizarVista3D();
    else {
      VISTA3D_SECUENCIA++; limpiarSeleccion3D();
      ORBITA3D_PENDIENTE = false;
    }
  });
  $("#giro-izq-3d").addEventListener("click", () => {
    CAMARA3D.azimut = (CAMARA3D.azimut + 345) % 360; actualizarVista3D();
  });
  $("#giro-der-3d").addEventListener("click", () => {
    CAMARA3D.azimut = (CAMARA3D.azimut + 15) % 360; actualizarVista3D();
  });
  $("#menos-elev-3d").addEventListener("click", () => {
    CAMARA3D.elevacion = Math.max(8, CAMARA3D.elevacion - 5); actualizarVista3D();
  });
  $("#mas-elev-3d").addEventListener("click", () => {
    CAMARA3D.elevacion = Math.min(80, CAMARA3D.elevacion + 5); actualizarVista3D();
  });
  ["#proyeccion-3d", "#nivel-3d", "#explosion-3d"].forEach((id) =>
    $(id).addEventListener("change", actualizarVista3D));
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
  if (MUTACION3D) { mostrarError("Espere a que termine la operación 3D anterior."); return; }
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
    const cambiosAlExportar = CAMBIOS3D;
    const res = await llamar("aplicar_exportar", params);
    if (res.proyecto && RESULTADO && RESULTADO.id === params.id && CAMBIOS3D === cambiosAlExportar)
      MODELO3D_SIN_EXPORTAR = false;
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
    $("#exp-errores").innerHTML = (errs.length
      ? "<div class='aviso error'>Formatos con error: " +
        errs.map(([f, m]) => esc(f) + ": " + esc(m)).join(" · ") + "</div>"
      : "") + (res.avisos || []).map((a) => "<div class='aviso'>" + esc(a) + "</div>").join("");
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
  let contenido = "", secuenciaFichero = 0;
  $("#fichero-proyecto").addEventListener("change", () => {
    const secuencia = ++secuenciaFichero;
    contenido = "";
    $("#proyecto-info").classList.add("oculto");
    const fichero = $("#fichero-proyecto").files[0];
    if (!fichero) return;
    if (fichero.size > 16 * 1024 * 1024) {
      mostrarError("La instantánea supera 16 MiB."); return;
    }
    const lector = new FileReader();
    lector.onload = () => {
      if (secuencia !== secuenciaFichero) return;
      try {
        const texto = String(lector.result), snap = JSON.parse(texto);
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
        $("#proyecto-errores").textContent = "Lectura local: " + niveles + " nivel(es), " +
          espacios + " espacio(s), " + muros + " muro(s).";
        $("#estado-proyecto-3d").textContent = "";
        contenido = texto;
      } catch (e2) {
        mostrarError("Instantánea ilegible: " + e2);
      }
    };
    lector.onerror = () => { if (secuencia === secuenciaFichero) mostrarError("No se pudo leer la instantánea."); };
    lector.readAsText(fichero);
  });
  $("#proyecto-editar-3d").addEventListener("click", async () => {
    if (!contenido) return;
    if (MUTACION3D) { $("#estado-proyecto-3d").textContent = "Espere a que termine la operación 3D anterior."; return; }
    if (MODELO3D_EDITADO && !window.confirm("El modelo actual tiene ediciones. " +
        "Al abrir otro dejará de poder editarlas aquí. Exporte antes una instantánea. ¿Continuar?")) return;
    const boton = $("#proyecto-editar-3d"), seq = secuenciaFichero, anterior = RESULTADO;
    boton.disabled = true; $("#estado-proyecto-3d").textContent = "Importando copia temporal…";
    try {
      const proyecto = await llamar("proyecto_editar_3d", {contenido});
      if (seq !== secuenciaFichero || RESULTADO !== anterior) {
        $("#estado-proyecto-3d").textContent = "El resultado o archivo cambió; seleccione y abra de nuevo.";
        return;
      }
      RESULTADO = proyecto; reiniciarVista3D(); PIEZA_ACTIVA = 0;
      irVista("resultado");
      $("#btn-vista-3d").click();
    } catch (e) { $("#estado-proyecto-3d").textContent = "No se pudo importar: " + decorarError(e); }
    finally { boton.disabled = false; }
  });
}

// ------------------------------------------------------------------ init ---
window.addEventListener("beforeunload", (e) => {
  if (MODELO3D_SIN_EXPORTAR || MUTACION3D) { e.preventDefault(); e.returnValue = ""; }
});
cargarEstado();
initPrograma();
initContorno();
initFormas();
initVista3D();
initExportar();
initProyecto();
renderPrograma();
renderContorno();
renderFormas();
comprobarMotor();
cargarCatalogo();
