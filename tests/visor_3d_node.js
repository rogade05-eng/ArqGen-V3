// Comprueba la lógica del visor sin navegador ni dependencias externas.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Elemento {
  constructor(id) {
    this.id = id;
    this.textContent = "";
    this.value = "";
    this.children = [];
    this.attributes = {};
    this.handlers = {};
    const clases = new Set();
    this.classList = {
      add: (x) => clases.add(x),
      contains: (x) => clases.has(x),
      toggle: (x, fuerza) => fuerza ? clases.add(x) : clases.delete(x),
    };
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  removeAttribute(k) { delete this.attributes[k]; }
  querySelectorAll() { return this.children.filter((x) => x.id === "polygon"); }
  getBoundingClientRect() { return {left: 0, top: 0, width: 800, height: 400}; }
  setPointerCapture() {}
  replaceChildren(...elementos) { this.children = elementos; }
  appendChild(elemento) { this.children.push(elemento); }
  add(elemento) { this.children.push(elemento); }
  addEventListener(evento, fn) { this.handlers[evento] = fn; }
  emitir(evento, e = {}) { return this.handlers[evento]({type: evento, preventDefault() {}, stopPropagation() {}, ...e}); }
}
const elementos = new Map();
function $(id) {
  if (!elementos.has(id)) elementos.set(id, new Elemento(id));
  return elementos.get(id);
}
$("#visor-3d").classList.add("oculto");
$("#proyeccion-3d").value = "ortogonal";
$("#explosion-3d").value = "0";
const pendientes = [];
const contexto = {
  $, console, Number, setTimeout, clearTimeout,
  window: {confirm: () => true},
  document: {
    createElement: (tipo) => new Elemento(tipo),
    createElementNS: (_, tipo) => new Elemento(tipo),
  },
  Option: function (texto, valor) { this.textContent = texto; this.value = valor; },
  llamar: (metodo, params) => new Promise((resolver, rechazar) => {
    pendientes.push({ metodo, params, resolver, rechazar });
  }),
  num: (n, dec) => Number(n).toFixed(dec),
  decorarError: String,
};
vm.createContext(contexto);
const codigo = fs.readFileSync("src/app.js", "utf8");
const inicio = codigo.indexOf("let NAVEGACION3D =");
const fin = codigo.indexOf("// ------------------------------------------------------------- exportar ---", inicio);
assert.ok(inicio > 0 && fin > inicio, "No se encuentra el visor 3D");
vm.runInContext("let RESULTADO = { id: 'an1' }; let VISTA3D_SECUENCIA = 0; " +
  "let CAMARA3D = {azimut: 30, elevacion: 35};\n" + codigo.slice(inicio, fin) +
  "\ninitVista3D();", contexto);
const muestra = {
  encuadre: [0, 0, 10, 8], niveles: [{nombre: "Piso 1", cota_m: 0}],
  caras: [{puntos: [[0, 0], [10, 0], [0, 8]], color: "#123456", entidad_id: "m1", entidad_tipo: "WALL"}],
  avisos: ["<img src=x onerror=alert(1)>"],
};

async function pruebas() {
  // La inversa en perspectiva debe recuperar puntos a diferentes cotas.
  const inversa = vm.runInContext(`(() => {
    const cam = {perspectiva:true, azimut:37, elevacion:35,
      centro:[3,4,5], distancia:50, cerca_fraccion:0.12};
    function proyecta(x,y,z) {
      const az=cam.azimut*Math.PI/180, el=cam.elevacion*Math.PI/180;
      x-=cam.centro[0]; y-=cam.centro[1]; z-=cam.centro[2];
      const xr=x*Math.cos(az)-y*Math.sin(az), yr=x*Math.sin(az)+y*Math.cos(az);
      const q=1-(yr*Math.cos(el)+z*Math.sin(el))/cam.distancia;
      return [xr/q,(yr*Math.sin(el)-z*Math.cos(el))/q];
    }
    const a=[13,8,4], b=[18,12,4], c=[13,8,7];
    const pa=proyecta(...a), pb=proyecta(...b), pc=proyecta(...c);
    return { a:planoXY3D(...pa,a[2],cam), b:planoXY3D(...pb,b[2],cam),
      z:alturaDesdePantalla3D(a,pc[1]-pa[1],cam),
      horizonte:planoXY3D(0,-cam.distancia*Math.tan(cam.elevacion*Math.PI/180),4,cam)};
  })()`, contexto);
  assert.ok(Math.abs(inversa.a[0]-13)<1e-9 && Math.abs(inversa.a[1]-8)<1e-9);
  assert.ok(Math.abs(inversa.b[0]-18)<1e-9 && Math.abs(inversa.b[1]-12)<1e-9);
  assert.ok(Math.abs(inversa.z-7)<1e-9);
  assert.equal(inversa.horizonte, null);
  $("#btn-vista-3d").emitir("click");
  assert.equal(pendientes.length, 1);
  assert.equal(pendientes[0].metodo, "vista_3d");
  assert.equal(pendientes[0].params.id, "an1");
  assert.equal($("#btn-vista-3d").attributes["aria-expanded"], "true");

  $("#giro-der-3d").emitir("click");
  assert.equal(pendientes[1].params.azimut, 45);
  pendientes[0].resolver(muestra); // respuesta obsoleta, no debe dibujarse
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal($("#modelo-3d").children.length, 0);
  pendientes[1].resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal($("#modelo-3d").children.length, 1);
  assert.equal($("#modelo-3d").children[0].attributes.fill, "#123456");
  assert.ok($("#modelo-3d").attributes.viewBox);
  assert.equal($("#avisos-3d").children[0].textContent, muestra.avisos[0]);
  assert.equal($("#nivel-3d").children.length, 2);

  const svg = $("#modelo-3d");
  const antesZoom = svg.attributes.viewBox;
  svg.emitir("wheel", {clientX: 400, clientY: 200, deltaY: -100});
  assert.notEqual(svg.attributes.viewBox, antesZoom, "rueda acerca");
  const antesPan = svg.attributes.viewBox;
  svg.emitir("pointerdown", {button: 1, pointerId: 1, clientX: 100, clientY: 100});
  svg.emitir("pointermove", {pointerId: 1, clientX: 130, clientY: 120, shiftKey: true});
  svg.emitir("pointerup", {pointerId: 1});
  assert.notEqual(svg.attributes.viewBox, antesPan, "mayús + central desplaza");
  const panDerecho = svg.attributes.viewBox;
  svg.emitir("pointerdown", {button: 2, pointerId: 2, clientX: 100, clientY: 100});
  svg.emitir("pointermove", {pointerId: 2, clientX: 110, clientY: 110});
  svg.emitir("pointerup", {pointerId: 2});
  assert.notEqual(svg.attributes.viewBox, panDerecho, "arrastrar derecho desplaza");

  svg.children[0].emitir("click");
  const consulta = pendientes.pop();
  assert.equal(consulta.metodo, "elemento_3d");
  assert.equal(consulta.params.elemento_id, "m1");
  consulta.resolver({id: "m1", tipo: "WALL", nombre: "Muro", revision: 1,
    campos: [{campo: "height_m", etiqueta: "Altura", tipo: "numero", valor: 3, min: 0.01, max: 100}]});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(svg.children[0].attributes.stroke, "#ff9000");
  const panel = $("#propiedades-3d"), formulario = panel.children[1];
  formulario.children[0].children[0].value = "4";
  formulario.emitir("submit");
  const edicion = pendientes.pop();
  assert.equal(edicion.metodo, "editar_3d");
  assert.equal(edicion.params.valores.height_m, 4);
  edicion.resolver({id: "m1", tipo: "WALL", nombre: "Muro", revision: 2,
    campos: [{campo: "height_m", etiqueta: "Altura", tipo: "numero", valor: 4, min: 0.01, max: 100}]});
  await new Promise((resolve) => setImmediate(resolve));
  const redibujo = pendientes.pop();
  assert.equal(redibujo.metodo, "vista_3d"); redibujo.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  svg.emitir("pointerdown", {button: 2, pointerId: 3, clientX: 0, clientY: 0});
  svg.emitir("pointerup", {pointerId: 3});
  assert.equal(panel.children.length, 0, "clic derecho quita selección");

  // Crear y editar escaleras sin sustituir el resto del proyecto.
  $("#tipo-nueva-escalera").value = "L";
  $("#nivel-3d").value = "0";
  $("#crear-escalera-3d").emitir("click");
  const creacion = pendientes.pop();
  assert.equal(creacion.metodo, "crear_escalera_3d");
  assert.equal(creacion.params.tipo, "L");
  assert.equal(creacion.params.nivel, 0);
  creacion.resolver({id: "s1"});
  await new Promise((resolve) => setImmediate(resolve));
  const seleccionEscalera = pendientes.pop();
  assert.equal(seleccionEscalera.metodo, "elemento_3d");
  seleccionEscalera.resolver({id: "s1", tipo: "STAIR", nombre: "Escalera", revision: 1,
    avisos: ["Revisar normativa"],
    campos: [{campo: "tipo", etiqueta: "Tipología", tipo: "opcion", valor: "L", opciones: ["recta", "L", "U", "caracol"]}]});
  await new Promise((resolve) => setImmediate(resolve));
  const formEsc = panel.children[1], selectTipo = formEsc.children[0].children[0];
  assert.equal(selectTipo.id, "select");
  assert.equal(selectTipo.children.length, 4);
  assert.match(panel.children[2].textContent, /Revisar normativa/);
  const dibujadoEscalera = pendientes.pop();
  assert.equal(dibujadoEscalera.metodo, "vista_3d");
  dibujadoEscalera.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  selectTipo.value = "U";
  formEsc.emitir("submit");
  const edicionEscalera = pendientes.pop();
  assert.equal(edicionEscalera.metodo, "editar_3d");
  assert.equal(edicionEscalera.params.valores.tipo, "U");
  edicionEscalera.resolver({id: "s1", tipo: "STAIR", nombre: "Escalera", revision: 2,
    avisos: ["Revise el hueco"],
    campos: [{campo: "tipo", etiqueta: "Tipología", tipo: "opcion", valor: "U", opciones: ["recta", "L", "U", "caracol"]}]});
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(panel.children[2].textContent, /Revise el hueco/);
  const dibujoFinal = pendientes.pop(); dibujoFinal.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  $("#deshacer-3d").emitir("click");
  const undo = pendientes.pop(); assert.equal(undo.metodo, "deshacer_3d");
  $("#rehacer-3d").emitir("click");
  assert.equal(pendientes.length, 2, "no ejecutar rehacer mientras deshacer está en curso");
  undo.resolver({existe: true});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(panel.children.length, 0);
  const dibujoUndo = pendientes.pop(); dibujoUndo.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  $("#rehacer-3d").emitir("click");
  const redo = pendientes.pop(); assert.equal(redo.metodo, "rehacer_3d");
  redo.resolver({existe: true});
  await new Promise((resolve) => setImmediate(resolve));
  const dibujoRedo = pendientes.pop(); dibujoRedo.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  $("#nivel-3d").value = "";

  svg.emitir("pointerdown", {button: 1, pointerId: 4, clientX: 100, clientY: 100});
  svg.emitir("pointermove", {pointerId: 4, clientX: 150, clientY: 90});
  svg.emitir("pointerup", {pointerId: 4});
  await new Promise((resolve) => setTimeout(resolve, 80));
  const orbita = pendientes.pop();
  assert.equal(orbita.metodo, "vista_3d");
  assert.equal(orbita.params.azimut, 65);
  assert.equal(orbita.params.elevacion, 39);
  // Mientras el sidecar está ocupado, agrupar movimientos en una sola petición.
  svg.emitir("pointerdown", {button: 1, pointerId: 5, clientX: 0, clientY: 0});
  svg.emitir("pointermove", {pointerId: 5, clientX: 10, clientY: 0});
  svg.emitir("pointermove", {pointerId: 5, clientX: 20, clientY: 0});
  svg.emitir("pointerup", {pointerId: 5});
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(pendientes.length, 2, "no emitir más órbitas mientras hay una en curso");
  orbita.resolver(muestra);
  await new Promise((resolve) => setTimeout(resolve, 80));
  const ultimaOrbita = pendientes.pop();
  assert.equal(ultimaOrbita.params.azimut, 73);
  ultimaOrbita.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));

  // El borrado de una escalera requiere confirmación y usa su revisión.
  vm.runInContext(`seleccionar3D({entidad_id:"s1",entidad_tipo:"STAIR"})`, contexto);
  const consultaBorrar = pendientes.pop();
  consultaBorrar.resolver({id:"s1", tipo:"STAIR", revision:7,
    campos:[{campo:"x", etiqueta:"X", tipo:"numero", valor:10, min:-100, max:100}]});
  await new Promise((resolve) => setImmediate(resolve));
  panel.children[3].emitir("click");
  const borrar = pendientes.pop();
  assert.equal(borrar.metodo, "borrar_escalera_3d");
  assert.equal(borrar.params.revision, 7);
  borrar.resolver({borrado:true});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(panel.children.length, 0);
  const dibujoBorrar = pendientes.pop();
  assert.equal(dibujoBorrar.metodo, "vista_3d");
  dibujoBorrar.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));

  // Arrastre en plano XY: selección previa, vista ortográfica, un solo RPC.
  vm.runInContext(`SELECCION3D = {id:"s1", tipo:"STAIR", revision:7,
    campos:[{campo:"x",valor:10},{campo:"y",valor:20}]};
    CAMARA3D = {azimut:0,elevacion:30};`, contexto);
  svg.children[0].setAttribute("data-entidad-id", "s1");
  const objetivo = svg.children[0];
  svg.emitir("pointerdown", {button:0, shiftKey:true, pointerId:6, clientX:100, clientY:100, target:objetivo});
  svg.emitir("pointermove", {pointerId:6, clientX:120, clientY:110});
  assert.match(objetivo.attributes.transform, /translate/);
  svg.emitir("pointerup", {pointerId:6});
  const movimiento = pendientes.pop();
  assert.equal(movimiento.metodo, "editar_3d");
  assert.equal(movimiento.params.revision, 7);
  // En azimut cero y elevación 30°, para 20px horizontal y 10px
  // vertical el desplazamiento en X e Y tiene la misma magnitud.
  assert.ok(Math.abs((movimiento.params.valores.x-10)-(movimiento.params.valores.y-20)) < 1e-9);
  movimiento.resolver({});
  await new Promise((resolve) => setImmediate(resolve));
  const seleccionMovida = pendientes.pop();
  assert.equal(seleccionMovida.metodo, "elemento_3d");
  seleccionMovida.resolver({id:"s1", tipo:"STAIR", revision:8,
    campos:[{campo:"x", tipo:"numero", valor:movimiento.params.valores.x},
            {campo:"y", tipo:"numero", valor:movimiento.params.valores.y}]});
  await new Promise((resolve) => setImmediate(resolve));
  const redibujoMovimiento = pendientes.pop();
  assert.equal(redibujoMovimiento.metodo, "vista_3d");
  redibujoMovimiento.resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));

  // Gestos reales con cámara perspectiva: cancelación no debe mutar,
  // XY y altura deben emitir una única edición con la revisión vigente.
  $("#proyeccion-3d").value = "perspectiva";
  vm.runInContext(`CAMARA_PROYECTADA3D = {perspectiva:true, azimut:0, elevacion:30,
      centro:[0,0,0], distancia:100, cerca_fraccion:0.12};
    SELECCION3D = {id:"s1", tipo:"STAIR", revision:9,
      campos:[{campo:"x",valor:10},{campo:"y",valor:20},{campo:"base_offset_m",valor:0.5}]};`, contexto);
  let cara = svg.children[0];
  cara.setAttribute("data-entidad-id", "s1");
  cara.setAttribute("data-centro-mundo", "1,1,2");
  let cantidad = pendientes.length;
  svg.emitir("pointerdown", {button:0, shiftKey:true, ctrlKey:true, pointerId:7, clientX:400, clientY:200, target:cara});
  svg.emitir("pointermove", {pointerId:7, clientX:400, clientY:180});
  assert.match(cara.attributes.transform, /translate/);
  svg.emitir("pointercancel", {pointerId:7});
  assert.equal(cara.attributes.transform, undefined);
  assert.equal(pendientes.length, cantidad, "cancelar no guarda cambios");
  svg.emitir("pointerdown", {button:0, shiftKey:true, pointerId:8, clientX:400, clientY:200, target:cara});
  svg.emitir("pointermove", {pointerId:8, clientX:420, clientY:205});
  svg.emitir("pointerup", {pointerId:8});
  const movPers = pendientes.pop();
  assert.equal(movPers.metodo, "editar_3d");
  assert.equal(movPers.params.revision, 9);
  assert.ok(Number.isFinite(movPers.params.valores.x) && Number.isFinite(movPers.params.valores.y));
  assert.notEqual(movPers.params.valores.x, 10);
  movPers.resolver({});
  await new Promise((resolve) => setImmediate(resolve));
  pendientes.pop().resolver({id:"s1",tipo:"STAIR",revision:10,
    campos:[{campo:"x",valor:10},{campo:"y",valor:20},{campo:"base_offset_m",valor:0.5}]});
  await new Promise((resolve) => setImmediate(resolve));
  pendientes.pop().resolver({...muestra, camara:{perspectiva:true,azimut:0,elevacion:30,
    centro:[0,0,0],distancia:100,cerca_fraccion:0.12}});
  await new Promise((resolve) => setImmediate(resolve));
  cara = svg.children[0];
  cara.setAttribute("data-entidad-id", "s1");
  cara.setAttribute("data-centro-mundo", "1,1,2");
  svg.emitir("pointerdown", {button:0, shiftKey:true, ctrlKey:true, pointerId:9, clientX:400, clientY:200, target:cara});
  svg.emitir("pointermove", {pointerId:9, clientX:400, clientY:180});
  svg.emitir("pointerup", {pointerId:9});
  const movZ = pendientes.pop();
  assert.equal(movZ.metodo, "editar_3d");
  assert.equal(movZ.params.revision, 10);
  assert.ok(movZ.params.valores.base_offset_m > 0.5);
  assert.deepEqual(Object.keys(movZ.params.valores), ["base_offset_m"]);
  movZ.resolver({});
  await new Promise((resolve) => setImmediate(resolve));
  pendientes.pop().resolver({id:"s1",tipo:"STAIR",revision:11,campos:[]});
  await new Promise((resolve) => setImmediate(resolve));
  pendientes.pop().resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));

  $("#proyeccion-3d").value = "perspectiva";
  $("#explosion-3d").value = "3";
  $("#nivel-3d").value = "0";
  $("#nivel-3d").emitir("change");
  assert.equal(pendientes[2].params.nivel, 0);
  assert.equal(pendientes[2].params.perspectiva, true);
  assert.equal(pendientes[2].params.explosion_m, 3);
  pendientes[2].rechazar("sin motor");
  await new Promise((resolve) => setImmediate(resolve));
  assert.match($("#estado-3d").textContent, /sin motor/);
  assert.equal($("#modelo-3d").children.length, 0);
  $("#proyeccion-3d").emitir("change");
  $("#btn-vista-3d").emitir("click"); // cerrar invalida la petición
  pendientes[3].resolver(muestra);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal($("#modelo-3d").children.length, 0);
  assert.equal($("#btn-vista-3d").attributes["aria-expanded"], "false");
  vm.runInContext("RESULTADO = {id: 'an2'}; reiniciarVista3D()", contexto);
  assert.equal($("#modelo-3d").children.length, 0);
  assert.equal($("#nivel-3d").children.length, 1);
  console.log("visor 3D: OK");
}
pruebas().catch((err) => { console.error(err); process.exitCode = 1; });
