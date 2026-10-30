// Interacción de lectura e importación de instantáneas sin ventana Tauri.
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
class Elemento {
  constructor() {
    this.handlers = {}; this.children = []; this.files = []; this.textContent = "";
    const clases = new Set();
    this.classList = {add: (x) => clases.add(x), remove: (x) => clases.delete(x),
      contains: (x) => clases.has(x)};
  }
  addEventListener(nombre, fn) { this.handlers[nombre] = fn; }
  appendChild(e) { this.children.push(e); }
  emitir(nombre) { return this.handlers[nombre](); }
  click() { this.pulsado = true; }
}
const elementos = new Map();
const $ = (s) => { if (!elementos.has(s)) elementos.set(s, new Elemento()); return elementos.get(s); };
const llamadas = [], confirmaciones = [], vistas = [], errores = [];
const contexto = {$, console, document: {createElement: () => new Elemento()},
  window: {confirm: (mensaje) => { confirmaciones.push(mensaje); return true; }},
  FileReader: class { readAsText(f) { this.result = f.contenido; this.onload(); } },
  llamar: (metodo, params) => new Promise((resolver, rechazar) => llamadas.push({metodo, params, resolver, rechazar})),
  par: (k, v) => k + v, mostrarError: (e) => errores.push(e), decorarError: String,
  irVista: (v) => vistas.push(v), reiniciarVista3D: () => {},
};
const codigo = fs.readFileSync("src/app.js", "utf8");
const inicio = codigo.indexOf("function initProyecto()");
const fin = codigo.indexOf("// ------------------------------------------------------------------ init ---", inicio);
assert.ok(inicio > 0 && fin > inicio);
vm.createContext(contexto);
vm.runInContext("let RESULTADO = null, MODELO3D_EDITADO = false, MUTACION3D = false, PIEZA_ACTIVA = 0;\n" +
  codigo.slice(inicio, fin) + "\ninitProyecto();", contexto);
async function pruebas() {
  const fichero = $("#fichero-proyecto");
  fichero.files = [{size: 100, contenido: JSON.stringify({format: "ARQ_GEN_SNAPSHOT", version: "1.0",
    project: {name: "Ejemplo"}, entities: {STAIR: [{id: "s"}]}})}];
  fichero.emitir("change");
  assert.equal($("#proyecto-info").classList.contains("oculto"), false);
  $("#proyecto-editar-3d").emitir("click");
  assert.equal(llamadas.length, 1);
  assert.equal(llamadas[0].metodo, "proyecto_editar_3d");
  assert.match(llamadas[0].params.contenido, /ARQ_GEN_SNAPSHOT/);
  llamadas[0].resolver({id: "an2", tipo: "proyecto_importado", nombre: "Ejemplo"});
  await new Promise((r) => setImmediate(r));
  assert.equal(vm.runInContext("RESULTADO.id", contexto), "an2");
  assert.deepEqual(vistas, ["resultado"]);
  assert.equal($("#btn-vista-3d").pulsado, true);
  vm.runInContext("MODELO3D_EDITADO = true", contexto);
  $("#proyecto-editar-3d").emitir("click");
  assert.equal(confirmaciones.length, 1);
  const pendiente = llamadas[1];
  // Cambiar de resultado durante la importación no debe sustituirlo.
  vm.runInContext("RESULTADO = {id: 'an3'}", contexto);
  pendiente.resolver({id: "an4"});
  await new Promise((r) => setImmediate(r));
  assert.equal(vm.runInContext("RESULTADO.id", contexto), "an3");
  assert.match($("#estado-proyecto-3d").textContent, /cambió/);
  fichero.files = [{size: 17 * 1024 * 1024}]; fichero.emitir("change");
  assert.match(errores[0], /16 MiB/);
  assert.equal($("#proyecto-info").classList.contains("oculto"), true);
  console.log("abrir proyecto 3D: OK");
}
pruebas().catch((e) => { console.error(e); process.exitCode = 1; });
