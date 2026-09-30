import './style.css';
import knowledge from '../../knowledge/generic-house.json';
import sources from '../../knowledge/source-manifest.json';
import { reviewSanitaryScope, describeDeclaredContext } from './source-review.js';
import { readBriefForm, writeBriefForm } from './brief.js';
import { archiveScenario, comparisonKey, comparisonLimit, comparisonReport, hypothesisFields } from './comparison.js';
import { maxArchiveBytes, parseArchiveText, verifyArchive } from './archive.js';
import { conceptualReport } from './report.js';
import { snapshotWorkspace, verifyWorkspace, saveLocalWorkspace, readLocalWorkspace, removeLocalWorkspace } from './workspace.js';
import { portfolioLimit, maxPortfolioBytes, newProject, revisedProject, listProjects, readProject,
  saveProject, deleteProject, exportPortfolio, verifyPortfolio, parsePortfolioText, replacePortfolio } from './portfolio.js';
import { createCheckpoints } from './checkpoints.js';
import { loadCore, callCore } from './core-client.js';
import { makeExplorationArchive, verifyExplorationArchive, explorationLimit } from './exploration.js';
import { buildDrawingPackage } from './drawing-package.js';

const el = (id) => document.getElementById(id);
const form = el('brief-form');
const number = (value, digits = 1) => new Intl.NumberFormat('es-ES', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
let engine;
let run;
let runInput;
let evaluated = null;
let comparisonRecords = [];
let comparisonNotice = '';
const pressureControls = hypothesisFields;
let selectionIndex = 0;
let stale = false;
let revision = 0;
let selectedRoom = null;
let portfolioEntries = [];
let activeProject = null; // {id, edit_token, name}; editing is never an automatic save.
let portfolioDirty = false;
let portfolioBusy = false;
let portfolioListSequence = 0;
let exploration = null; // {input, seed_count, result}; never implicitly saved
let exploreWorker = null;
let exploreBusy = false;
let exploreJobToken = 0;
const checkpoints = createCheckpoints(knowledge, (input) => invokeCore(input));
let historyDetached = false; // an invalid result did not create a checkpoint
let choice;
try { choice = JSON.parse(localStorage.getItem('arqgen.mvp0.choice') || 'null'); } catch { choice = null; }

function getInput() {
  if (!form.reportValidity()) return null;
  return readBriefForm(form.elements, knowledge, pressureControls);
}

function invokeCore(input) { return callCore(engine, 'arq_generate', input); }

function setState(text, spinning = false) {
  const state = el('engine-state');
  state.hidden = false;
  state.replaceChildren();
  if (spinning) {
    const spinner = document.createElement('span');
    spinner.className = 'spinner';
    state.append(spinner);
  }
  state.append(document.createTextNode(text));
  el('result-view').hidden = true;
  el('empty-view').hidden = true;
}

function renderRejections(id, result) {
  const host = el(id);
  host.replaceChildren();
  host.hidden = result?.status !== 'ok' && result?.status !== 'infeasible';
  if (host.hidden) return;
  const heading = document.createElement('strong');
  heading.textContent = 'Descartes de esta búsqueda · no dictamen general';
  const detail = document.createElement('p');
  if (!result.generated) {
    detail.textContent = 'Sin variantes evaluadas: el escenario falló una comprobación previa.';
  } else {
    detail.textContent = `${result.rejected} de ${result.generated} variantes descartadas. Una variante se cuenta una vez, por su primer motivo de rechazo.`;
  }
  host.append(heading, detail);
  if (!result.rejection_summary?.length) return;
  const list = document.createElement('ul');
  for (const { reason, count } of result.rejection_summary) {
    const row = document.createElement('li');
    const amount = document.createElement('strong');
    amount.textContent = `${count} ×`;
    const explanation = document.createElement('span');
    explanation.textContent = reason;
    row.append(amount, explanation);
    list.append(row);
  }
  host.append(list);
}

function renderEmpty(result, input = null) {
  runInput = null;
  el('engine-state').hidden = true;
  el('result-view').hidden = true;
  el('empty-view').hidden = false;
  el('empty-kicker').textContent = result?.status === 'infeasible' ? 'SIN SOLUCIÓN EN ESTE CORTE' : 'NO SE PUDO GENERAR';
  el('empty-title').textContent = result?.status === 'infeasible' ? 'No hay una propuesta válida entre las exploradas.' : 'Revisa los datos de entrada.';
  el('empty-message').textContent = result?.status === 'infeasible'
    ? `No mostramos propuestas que incumplan reglas duras. Podrían existir otras configuraciones fuera de este generador. Ajusta la parcela o el programa para probar de nuevo. El trazado frontal comprueba SOLO las bandas 2D declaradas (recta o dos giros): si se bloquea, no se han buscado otras rutas ni probado acceso vial/legal.${result.site_plot?.rear_notches?.length ? ' Los recortes posteriores son parte del croquis autodeclarado, NO linderos ni edificabilidad legal verificados.' : ''}${result.site_reservations?.areas?.length ? ' Se evitaron en planta las zonas voluntarias dibujadas, NO un deslinde o requisito legal verificado.' : ''}`
    : (result?.message || 'El motor no pudo procesar esta solicitud.');
  const list = el('empty-reasons');
  list.replaceChildren();
  for (const message of result?.reasons || []) {
    const item = document.createElement('li');
    item.textContent = message;
    list.append(item);
  }
  renderRejections('empty-rejections', result);
  el('empty-scope').textContent = result?.status === 'infeasible'
    ? `Sin alternativa: no hay ventanas de baño que observar. NC 598, luz natural y ventilación NO EVALUADAS. ${describeDeclaredContext(reviewSanitaryScope(input, result, null, sources))}`
    : 'No se evaluó el ámbito de NC 598, la iluminación natural ni la ventilación.';
  setActionEnabled(false);
}

function metric(label, value, display, warning = false) {
  const container = document.createElement('div');
  container.className = 'metric';
  const head = document.createElement('div');
  head.className = 'metric-head';
  const name = document.createElement('span');
  name.textContent = label;
  const val = document.createElement('strong');
  val.textContent = display;
  head.append(name, val);
  const track = document.createElement('div');
  track.className = 'metric-track';
  const fill = document.createElement('div');
  fill.className = `metric-fill${warning ? ' warn' : ''}`;
  fill.style.width = `${Math.max(0, Math.min(100, value * 100))}%`;
  track.append(fill);
  container.append(head, track);
  return container;
}

function renderMetrics(alt) {
  const m = alt.metrics;
  el('area-gross').textContent = `${number(alt.built_area)} m²`;
  el('area-usable').textContent = `${number(alt.usable_area)} m²`;
  el('area-walls').textContent = `${number(alt.wall_allowance_area)} m²`;
  const list = el('metric-list');
  list.replaceChildren(
    metric('Porcentaje útil / bruto', alt.usable_area / alt.built_area, `${number(alt.usable_area / alt.built_area * 100, 0)} %`),
    metric('Ajuste a huella deseada', m.area_fit, `${number(m.area_fit * 100, 0)} %`),
    metric('Circulación / área útil', 1 - m.circulation_ratio, `${number(m.circulation_ratio * 100)} %`, m.circulation_ratio > knowledge.corridor.soft_max_ratio),
    metric('Separación del acceso', m.privacy_score, `${number(m.privacy_score * 100, 0)} %`),
    metric('Proximidad cocina-baño', m.service_score, `${number(m.service_score * 100, 0)} %`),
    metric('Dormitorios con ventana E', m.east_bedroom_score, `${number(m.east_bedroom_score * 100, 0)} %`),
  );
  el('space-count').textContent = `${alt.rooms.length} espacios`;
  const plotNote = el('site-plot-summary');
  const plot = run.site_plot;
  const cuts = plot.rear_notches;
  plotNote.hidden = cuts.length === 0;
  plotNote.textContent = cuts.length
    ? `${cuts.length === 2 ? 'Contorno con dos esquinas posteriores recortadas' : 'Parcela en L'} del solicitante: ${cuts.map((notch, i) => `recorte ${i + 1} ${notch.side === 'left' ? 'izquierdo' : 'derecho'} de ${number(notch.width, 2)} × ${number(notch.depth, 2)} m`).join('; ')}, FUERA del contorno dibujado. Área del croquis: ${number(run.site.plot_area, 2)} m² (NO superficie catastral). Retiros demo solo desde la caja exterior: bordes de los entrantes, calle, linderos, luz y ventilación NO evaluados.`
    : '';
  const approachNote = el('site-approach-summary');
  const approach = alt.front_approach;
  approachNote.hidden = false;
  approachNote.textContent = `${approach.turns.length ? `Rodeo frontal ortogonal de ${number(approach.width, 2)} m con dos giros declarados: borde x=${number(approach.front_contact.x, 2)}, giro y=${number(approach.turns[0].y, 2)} y puerta x=${number(approach.door_contact.x, 2)}, y=${number(approach.door_contact.y, 2)} m` : `Franja frontal recta de ${number(approach.width, 2)} m centrada en la puerta: ${approach.segments.length ? `desde y=0 hasta y=${number(approach.door_contact.y, 2)} m` : 'puerta en el borde frontal; no hay franja exterior dibujada'}`}. Las bandas completas no cruzan las exclusiones declaradas en planta. SOLO croquis 2D: NO se verifican calle, derecho de paso, cotas, barreras, accesibilidad ni acceso real. No se buscaron otras rutas.`;
  const reserveNote = el('site-reservation-summary');
  const zones = run.site_reservations.areas;
  reserveNote.hidden = zones.length === 0;
  reserveNote.textContent = zones.length
    ? `${zones.length} ${zones.length === 1 ? 'reserva voluntaria declarada' : 'reservas voluntarias declaradas'}: ${zones.map((area, i) =>
      `${i + 1}: x=${number(area.x, 2)}, y=${number(area.y, 2)}, ${number(area.width, 2)} × ${number(area.depth, 2)} m`).join('; ')}. Ninguna invade la huella bruta ni el trazado frontal 2D elegido. Croquis y derechos NO verificados; acceso exterior, luz y ventilación NO evaluados.`
    : '';
  const bathrooms = alt.rooms.filter((room) => room.type === 'bathroom');
  const reserved = bathrooms.filter((room) => room.bath_exhaust?.geometry_status === 'outlet_and_route_reserved');
  el('exhaust-summary').textContent = `${reserved.length} / ${bathrooms.length} baños con salida de extracción reservada`;
  const airflow = el('airflow-summary');
  airflow.replaceChildren();
  for (const room of bathrooms) {
    const check = room.bath_airflow;
    if (!check || check.status !== 'nominal_precheck_only') continue;
    const row = document.createElement('div');
    row.className = 'airflow-row';
    const title = document.createElement('strong');
    title.textContent = `${room.label} · Q objetivo ${number(check.target_flow_m3h)} m³/h`;
    const detail = document.createElement('span');
    detail.textContent = `${number(check.target_ach)} ren/h × ${number(check.room_volume_m3)} m³ supuestos; ventilador de referencia EN AIRE LIBRE ${number(check.fan_reference_free_air_rating_m3h)} m³/h. Holgura ${number(check.transfer.assumed_door_undercut_m * 1000, 0)} mm: ${number(check.transfer.velocity_at_target_mps, 2)} / ${number(check.transfer.max_velocity_mps, 2)} m/s. Sección ideal ${number(check.duct.assumed_section_m2, 4)} m²: ${number(check.duct.velocity_at_target_mps, 2)} / ${number(check.duct.max_velocity_mps, 2)} m/s. Base ${number(check.duct.assumed_bottom_m, 2)} m, techo supuesto ${number(check.assumed_ceiling_height_m, 2)} m.`;
    row.append(title, detail);
    const pressure = room.bath_pressure;
    if (pressure?.status === 'hypothetical_pressure_screen_only') {
      const pressureLine = document.createElement('span');
      pressureLine.className = 'pressure-scenario';
      pressureLine.textContent = `Presión HIPOTÉTICA ${number(pressure.pressure_budget.assumed_total_pa, 2)} Pa / límite de referencia ${number(pressure.fan_reference.reference_pressure_pa, 1)} Pa. Capacidad de REFERENCIA lineal al presupuesto ${number(pressure.fan_reference.assumed_linear_capacity_at_budget_m3h)} m³/h ≥ objetivo. Escenario interpolado SIN equipo identificado ni pérdidas reales; caudal entregado y ventilación: NO EVALUADOS.`;
      row.append(pressureLine);
    }
    airflow.append(row);
  }
  const schedule = el('space-schedule');
  schedule.replaceChildren();
  const zoneOrder = { public: 0, service: 1, private: 2 };
  for (const room of [...alt.rooms].sort((a, b) => (zoneOrder[a.zone] - zoneOrder[b.zone]) || a.rect.y - b.rect.y)) {
    const row = document.createElement('div');
    row.className = 'schedule-row';
    const name = document.createElement('span');
    name.textContent = room.label;
    const area = document.createElement('strong');
    area.textContent = `${number(room.usable_area)} m²`;
    row.append(name, area);
    schedule.append(row);
  }
  const warningBox = el('warnings');
  warningBox.replaceChildren();
  for (const warning of alt.warnings) {
    const item = document.createElement('div');
    item.className = 'warning';
    item.textContent = `ⓘ  ${warning}`;
    warningBox.append(item);
  }
}

function renderScope(alt) {
  const review = reviewSanitaryScope(runInput, run, alt, sources);
  el('scope-review').classList.toggle('stale', stale);
  el('scope-stale').hidden = !stale;
  el('scope-status').textContent = 'NO EVALUADO';
  el('scope-context').textContent = describeDeclaredContext(review);
  const baths = review.bathrooms;
  el('scope-daylight').textContent = baths
    ? `${baths.with_drawn_window.length} de ${baths.total} baños con vano de fachada dibujado en planta; ${baths.without_window.length} sin vano${baths.unknown.length ? `; ${baths.unknown.length} sin dato coherente de vano` : ''}. Objetivo geométrico solo ILUSTRATIVO, no umbral NC 598. Antepecho, vidrio, obstrucciones exteriores, luz natural efectiva y ventilación: NO EVALUADOS.`
    : 'No existe un plano que permita observar ventanas. Luz natural y ventilación: NO EVALUADAS.';
  el('scope-source-note').textContent = `NC 598:2009: copia inventariada en commit ${review.source.source_commit.slice(0, 12)} (SHA-256 ${review.source.sha256.slice(0, 12)}…). La huella identifica bytes, NO la edición vigente. Las tres dependencias siguientes son solo vistas de terceros.`;
  const items = el('scope-leads');
  items.replaceChildren();
  for (const ref of review.dependencies) {
    const row = document.createElement('li');
    const link = document.createElement('a');
    link.href = ref.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.referrerPolicy = 'no-referrer';
    link.textContent = ref.id;
    const note = document.createElement('span');
    note.textContent = ' · Enlace externo: vista de tercero; autenticidad, vigencia y derechos sin verificar';
    row.append(link, note);
    items.append(row);
  }
}

function renderTrace(roomId = null) {
  const alt = run.alternatives[selectionIndex];
  const list = el('trace-list');
  list.replaceChildren();
  const decisions = alt.decisions.filter((d) => d.entity_id === (roomId || alt.id));
  const prompt = el('trazabilidad').querySelector('.trace-prompt');
  const room = alt.rooms.find((r) => r.id === roomId);
  const ventilation = room?.bath_exhaust
    ? `extracción reservada a fachada ${room.bath_exhaust.direction} (${number(room.bath_exhaust.run_length, 2)} m); objetivo nominal ${number(room.bath_airflow.target_flow_m3h)} m³/h; caudal ENTREGADO no evaluado`
    : room?.window ? `ventana ${room.window.direction}; ventilación no certificada` : 'ventilación no evaluada';
  prompt.textContent = room
    ? `${room.label} · ${number(room.usable_area)} m² útiles · puerta ${number(room.door.width, 2)} m · ${ventilation}`
    : (run.site_plot.rear_notches.length || run.site_reservations.areas.length
      ? 'Consulta las decisiones de parcela: contorno, trazado frontal y zonas voluntarias son croquis 2D sin levantamiento, calle, retiro del entrante ni validez legal verificados. Selecciona un local para su traza.'
      : 'El trazado frontal elegido solo comprueba bandas 2D hasta la puerta, NO calle, accesibilidad o derecho de paso. Selecciona un local para ver su traza.');
  const equipment = el('trace-equipment');
  equipment.hidden = !room;
  if (room) equipment.textContent = `${room.furnishings.map((item) => item.label).join(' · ')}. Huellas y zonas de uso sin choque; ruta geométrica de ${number(knowledge.furnishings.min_aisle, 2)} m. ${room.bath_exhaust ? 'Reserva y presión supuesta NO son un conducto instalado ni rendimiento medido; caudal entregado no evaluado. ' : ''}No demuestra accesibilidad ni ergonomía normativa.`;
  for (const decision of decisions) {
    const card = document.createElement('div');
    card.className = 'trace-card';
    const mark = document.createElement('span');
    mark.textContent = '◇';
    const description = document.createElement('div');
    const text = document.createElement('p');
    text.textContent = decision.explanation;
    const code = document.createElement('small');
    code.textContent = decision.rule;
    description.append(text, code);
    card.append(mark, description);
    list.append(card);
  }
  for (const group of el('plan').querySelectorAll('[data-room-id]')) {
    group.classList.toggle('selected', group.dataset.roomId === roomId);
  }
}

function currentChoice() {
  const alt = run?.alternatives[selectionIndex];
  return choice && alt && choice.input_hash === run.input_hash && choice.candidate_id === alt.id ? choice : null;
}

function renderChoice() {
  const approved = currentChoice();
  el('choice-title').textContent = approved ? 'Preferencia preliminar registrada.' : 'Tu criterio es el último paso.';
  el('choice-subtitle').textContent = approved ? `Marcada el ${new Date(approved.chosen_at).toLocaleString('es-ES')}. No certifica la propuesta.`
    : 'Selecciona la propuesta que deseas desarrollar.';
  el('approve').textContent = approved ? 'Preferida ✓' : 'Marcar como preferida ↗';
  for (const button of el('alternatives').children) {
    const item = run.alternatives[Number(button.dataset.index)];
    button.querySelector('.alt-picked').textContent = choice && choice.input_hash === run.input_hash && choice.candidate_id === item.id ? '✓ Preferida' : '↗';
  }
}

function renderOption(index) {
  selectionIndex = index;
  selectedRoom = null;
  const alt = run.alternatives[index];
  for (const button of el('alternatives').children) {
    button.setAttribute('aria-selected', button.dataset.index === String(index) ? 'true' : 'false');
    button.tabIndex = Number(button.dataset.index) === index ? 0 : -1;
  }
  el('alt-panel').setAttribute('aria-labelledby', `alt-tab-${index}`);
  el('plan-title').textContent = alt.label;
  // SVG is constructed from numeric inputs and fixed labels in the trusted Rust engine.
  el('plan').innerHTML = alt.svg;
  const plan = el('plan').querySelector('svg');
  plan.setAttribute('role', 'group');
  plan.setAttribute('aria-label', `Plano interactivo de ${alt.label}: elige un local para consultar su trazabilidad`);
  el('plan').querySelectorAll('[data-room-id]').forEach((group) => {
    group.setAttribute('role', 'button');
    group.setAttribute('tabindex', '0');
    group.setAttribute('aria-label', `Explorar ${alt.rooms.find((room) => room.id === group.dataset.roomId).label}`);
    const inspect = () => { selectedRoom = group.dataset.roomId; renderTrace(selectedRoom); };
    group.addEventListener('click', inspect);
    group.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inspect(); }
    });
  });
  renderMetrics(alt);
  renderScope(alt);
  renderTrace();
  renderChoice();
  if (!el('drawing-preview').hidden && el('drawing-preview').open) renderDrawingPreview();
}

function renderRun(result, input) {
  run = result;
  runInput = structuredClone(input);
  selectionIndex = 0;
  stale = false;
  el('engine-state').hidden = true;
  el('empty-view').hidden = true;
  el('result-view').hidden = false;
  el('export-feedback').hidden = true;
  el('export-feedback').textContent = '';
  el('result-count').textContent = `/ ${String(result.alternatives.length).padStart(2, '0')}`;
  el('result-stamp').textContent = `SEMILLA ${input.seed}`;
  el('result-status').textContent = 'VIABLES';
  el('result-status').classList.remove('stale');
  el('selection-note').textContent = result.selection_note;
  renderRejections('run-rejections', result);
  const list = el('alternatives');
  list.replaceChildren();
  result.alternatives.forEach((alt, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'alt-card';
    button.setAttribute('role', 'tab');
    button.dataset.index = index;
    button.id = `alt-tab-${index}`;
    button.setAttribute('aria-controls', 'alt-panel');
    button.setAttribute('aria-label', `Alternativa ${String.fromCharCode(65 + index)}: ${alt.label}`);
    const id = document.createElement('span');
    id.className = 'alt-index';
    id.textContent = `ALTERNATIVA 0${index + 1} · PARETO ${alt.pareto_layer + 1}`;
    const title = document.createElement('strong');
    title.className = 'alt-title';
    title.textContent = alt.label;
    title.title = alt.label;
    const bottom = document.createElement('span');
    bottom.className = 'alt-bottom';
    const area = document.createElement('strong');
    area.textContent = `${number(alt.built_area)} m²`;
    const pick = document.createElement('span');
    pick.className = 'alt-picked';
    bottom.append(area, pick);
    button.append(id, title, bottom);
    button.addEventListener('click', () => renderOption(index));
    button.addEventListener('keydown', (event) => {
      const last = result.alternatives.length - 1;
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % (last + 1);
      else if (event.key === 'ArrowLeft') next = (index + last) % (last + 1);
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = last;
      if (next !== undefined) {
        event.preventDefault();
        renderOption(next);
        list.children[next].focus();
      }
    });
    list.append(button);
  });
  renderOption(0);
  setActionEnabled(true);
  renderDrawingPreview();
}

function setActionEnabled(enabled) {
  for (const id of ['approve', 'export-json', 'export-svg', 'export-drawings', 'export-report']) el(id).disabled = !enabled;
  el('drawing-preview').hidden = !enabled;
  if (!enabled) el('drawing-preview-grid').replaceChildren();
}

function renderDrawingPreview() {
  const details = el('drawing-preview');
  const grid = el('drawing-preview-grid');
  grid.replaceChildren();
  if (details.hidden || !details.open || !run || stale || !runInput) return;
  try {
    const pkg = buildDrawingPackage(runInput, run, selectionIndex);
    for (const sheet of pkg.sheets) {
      const card = document.createElement('figure');
      card.className = 'drawing-preview-card';
      const image = document.createElement('img');
      // Render as an image, never as trusted DOM/HTML. Self-contained and offline.
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(sheet.svg)}`;
      image.alt = `${sheet.number}: ${sheet.title}, 1:${sheet.denominator}. Croquis no apto para obra.`;
      const caption = document.createElement('figcaption');
      caption.textContent = `${sheet.number} · ${sheet.title} · 1:${sheet.denominator}`;
      card.append(image, caption);
      grid.append(card);
    }
  } catch (error) {
    grid.textContent = `No se puede mostrar el paquete: ${error.message}`;
  }
}

function renderComparison() {
  const items = el('comparison-items');
  items.replaceChildren();
  el('comparison-count').textContent = `${comparisonRecords.length} / ${comparisonLimit} GUARDADOS`;
  const sameBrief = !comparisonRecords.length || (evaluated &&
    comparisonKey(evaluated.input) === comparisonKey(comparisonRecords[0].input) &&
    evaluated.generation.engine_version === comparisonRecords[0].generation.engine_version);
  const duplicate = evaluated && comparisonRecords.some(({ generation }) =>
    generation.input_hash === evaluated.generation.input_hash);
  el('save-scenario').disabled = !evaluated || stale || !sameBrief || duplicate || comparisonRecords.length >= comparisonLimit;
  el('export-comparison').disabled = comparisonRecords.length < 2;
  el('clear-comparison').disabled = !comparisonRecords.length;
  el('save-local').disabled = !engine || !evaluated || stale || !('indexedDB' in window);
  el('comparison-message').textContent = comparisonNotice || (stale && evaluated
    ? 'Hay cambios sin regenerar: la corrida editada aún no forma parte de esta comparación.'
    : !comparisonRecords.length
      ? 'Genera y guarda una primera corrida para iniciar la comparación.'
      : !evaluated
        ? 'La entrada actual no produjo una corrida guardable; las corridas previas permanecen en el cuaderno.'
        : !sameBrief
          ? 'El encargo o las reglas no coinciden: limpia la comparación antes de guardar.'
        : duplicate
          ? 'Esta corrida ya está guardada. Cambia una hipótesis y regenera para contrastarla.'
          : comparisonRecords.length >= comparisonLimit
            ? 'Límite de tres corridas: elimina una para guardar otra.'
            : 'Guarda una nueva corrida con el mismo encargo para contrastar los resultados.');

  comparisonRecords.forEach(({ input, generation }, index) => {
    const card = document.createElement('article');
    card.className = 'scenario-card';
    if (!stale && evaluated?.generation.input_hash === generation.input_hash) card.classList.add('active');
    const eyebrow = document.createElement('span');
    eyebrow.className = 'scenario-eyebrow';
    eyebrow.textContent = `ESCENARIO ${String(index + 1).padStart(2, '0')} · SOLO HIPOTÉTICO`;
    const title = document.createElement('h3');
    title.textContent = generation.status === 'ok' ? 'Con propuestas' : 'Sin propuesta en esta búsqueda';
    const params = document.createElement('p');
    params.className = 'scenario-params';
    const pressure = input.rules.bath_pressure;
    const cuts = input.site.plot_outline.rear_notches.map((cut, i) =>
      `recorte ${i + 1} ${cut.side === 'left' ? 'izquierdo' : 'derecho'} ${cut.width} × ${cut.depth} m`).join('; ');
    const zones = input.site.reserved_areas.map((area, i) =>
      ` + zona ${i + 1} 2D x=${area.x}, y=${area.y}, ${area.width} × ${area.depth} m`).join('');
    params.textContent = `2.º punto: ${pressure.fan_reference_pressure_pa} Pa / ${pressure.fan_reference_flow_m3h} m³/h · reserva de presión: ${pressure.assumed_reserve_pa} Pa · parcela: ${cuts || 'rectángulo'}${zones} (NO verificado)`;
    const state = document.createElement('p');
    state.className = `scenario-state${generation.status === 'infeasible' ? ' infeasible' : ''}`;
    state.textContent = generation.status === 'ok' ? 'Alternativas validadas por las reglas demo' : 'Ninguna alternativa pasó las reglas demo';
    const stats = document.createElement('div');
    stats.className = 'scenario-stats';
    for (const value of [`${generation.generated} ensayadas`, `${generation.rejected} descartadas`, `${generation.alternatives.length} mostradas`]) {
      const tag = document.createElement('span');
      tag.textContent = value;
      stats.append(tag);
    }
    const reasons = document.createElement('ul');
    reasons.className = 'scenario-reasons';
    const rows = generation.rejection_summary.length
      ? generation.rejection_summary.map(({ count, reason }) => `${count} × ${reason}`)
      : generation.generated === 0 ? generation.reasons : ['Sin descartes en las variantes ensayadas.'];
    for (const reason of rows || []) {
      const row = document.createElement('li');
      row.textContent = reason;
      reasons.append(row);
    }
    const hash = document.createElement('small');
    hash.className = 'scenario-hash';
    hash.textContent = `Entrada ${generation.input_hash} · ${generation.engine_version}`;
    const actions = document.createElement('div');
    actions.className = 'scenario-actions';
    const inspect = document.createElement('button');
    inspect.type = 'button';
    inspect.textContent = 'Regenerar y examinar ↗';
    inspect.setAttribute('aria-label', `Regenerar y examinar escenario ${index + 1}`);
    inspect.addEventListener('click', () => revisitScenario(comparisonRecords[index]));
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'scenario-remove';
    remove.textContent = 'Eliminar';
    remove.setAttribute('aria-label', `Eliminar escenario ${index + 1}`);
    remove.addEventListener('click', () => {
      comparisonRecords = comparisonRecords.filter(({ generation: entry }) => entry.input_hash !== generation.input_hash);
      comparisonNotice = '';
      portfolioDirty = true;
      renderComparison();
      recordHistory();
    });
    actions.append(inspect, remove);
    card.append(eyebrow, title, params, state, stats, reasons, hash, actions);
    items.append(card);
  });
  renderPortfolioControls();
}

function reflectPlotFields() {
  const enabled = form.elements.plot_notch_enabled.checked;
  const fields = el('plot-notch-fields');
  fields.hidden = !enabled;
  fields.disabled = !enabled;
  const secondToggle = form.elements.plot_notch_2_enabled;
  secondToggle.disabled = !enabled;
  if (!enabled) secondToggle.checked = false;
  const second = el('plot-notch-2-fields');
  second.hidden = !(enabled && secondToggle.checked);
  second.disabled = second.hidden;
  // Native form feedback only; Rust independently checks dimensions, unique
  // opposite sides and the 1 m illustrative rear strip for every JSON input.
  const width = Number(form.elements.width.value);
  const depth = Number(form.elements.depth.value);
  const both = enabled && secondToggle.checked;
  form.elements.notch_width.max = String(width - 1 - (both ? Number(form.elements.notch_2_width.value) : 0));
  form.elements.notch_2_width.max = String(width - 1 - (both ? Number(form.elements.notch_width.value) : 0));
  form.elements.notch_depth.max = String(depth - 1);
  form.elements.notch_2_depth.max = String(depth - 1);
  reflectApproachFields();
}

function reflectApproachFields() {
  const detour = form.elements.approach_shape.value === 'orthogonal_front_detour';
  const group = el('approach-detour-fields');
  group.hidden = !detour;
  group.disabled = !detour;
  const width = Number(form.elements.width.value);
  const band = Number(form.elements.approach_width.value);
  const half = band / 2;
  form.elements.approach_width.max = String(Math.min(6, width));
  form.elements.approach_width.min = String(Math.max(0.9, knowledge.doors.main));
  form.elements.approach_front_x.min = String(half);
  form.elements.approach_front_x.max = String(width - half);
  form.elements.approach_turn_y.min = String(half);
  form.elements.approach_turn_y.max = String(knowledge.setbacks.front - half);
}

function reflectReservationFields() {
  const enabled = form.elements.reserve_enabled.checked;
  const fields = el('reservation-fields');
  fields.hidden = !enabled;
  fields.disabled = !enabled;
  const secondToggle = form.elements.reserve_2_enabled;
  secondToggle.disabled = !enabled;
  if (!enabled) secondToggle.checked = false;
  const second = el('reservation-2-fields');
  second.hidden = !(enabled && secondToggle.checked);
  second.disabled = second.hidden;
}

function putInputOnForm(input) {
  writeBriefForm(form.elements, input, pressureControls);
  reflectPlotFields();
  reflectReservationFields();
}

function renderHistoryControls() {
  const state = checkpoints.status();
  el('history-count').textContent = `${state.position} / ${state.total} · solo esta sesión`;
  el('history-undo').disabled = !engine || !(state.canUndo || (state.total && (stale || historyDetached)));
  el('history-redo').disabled = !engine || stale || historyDetached || !state.canRedo;
}
function recordHistory(reset = false) {
  try {
    if (evaluated && !stale) {
      if (reset) checkpoints.reset(evaluated, comparisonRecords);
      else checkpoints.record(evaluated, comparisonRecords);
      historyDetached = false;
      showFeedback('history-feedback', '');
    } else if (!stale) historyDetached = true;
  } catch (error) {
    showFeedback('history-feedback', `No se anotó el estado: ${error.message}`, true);
  }
  renderHistoryControls();
}
function restoreHistory(delta) {
  if (!engine) return;
  if (delta === 1 && (stale || historyDetached)) return;
  const change = stale || historyDetached ? 0 : delta;
  try {
    const prepared = checkpoints.prepare(change); // full replay BEFORE any UI mutation
    ++importSequence;
    revision++;
    comparisonRecords = prepared.records;
    putInputOnForm(prepared.focus.input);
    adoptEvaluation(prepared.focus.input, prepared.focus.generation);
    checkpoints.commit(prepared);
    historyDetached = false;
    portfolioDirty = true; // restoring does not silently update an opened project
    el('generate-button').disabled = false;
    renderPortfolioList();
    showFeedback('history-feedback', change === 0
      ? 'Se descartaron cambios no generados; la última corrida validada se recalculó con Rust.'
      : `Estado ${checkpoints.status().position} restaurado y recalculado con Rust. No se guardó en la cartera.`);
    renderHistoryControls();
  } catch (error) {
    showFeedback('history-feedback', `No se restauró la corrida: ${error.message}`, true);
    renderHistoryControls();
  }
}

function revisitScenario(record) {
  putInputOnForm(record.input);
  invalidateRun();
  comparisonNotice = '';
  regenerate(); // Replay through Rust, not a cached claim of current validity.
  el('propuestas').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function adoptEvaluation(input, result) {
  cancelExploration('La corrida cambió: lote anterior descartado.');
  evaluated = ['ok', 'infeasible'].includes(result.status)
    ? { input: structuredClone(input), generation: result } : null;
  stale = false;
  comparisonNotice = '';
  if (result.status !== 'ok' || !result.alternatives?.length) {
    run = null;
    renderEmpty(result, input);
  } else renderRun(result, input);
  renderComparison();
  renderExploration();
}

function regenerate(event) {
  event?.preventDefault();
  const input = getInput();
  if (!input || !engine) return;
  cancelExploration('Se inicia una nueva corrida; lote anterior descartado.');
  const requestRevision = ++revision;
  setActionEnabled(false);
  setState('Buscando organizaciones viables con el motor Rust…', true);
  el('generate-button').disabled = true;
  setTimeout(() => {
    if (requestRevision !== revision) {
      el('generate-button').disabled = false;
      return;
    }
    try {
      adoptEvaluation(input, invokeCore(input));
      recordHistory();
    } catch (error) {
      run = null;
      evaluated = null;
      historyDetached = true;
      renderEmpty({ status: 'error', message: error.message });
      renderComparison();
      renderHistoryControls();
      renderExploration();
    } finally { el('generate-button').disabled = false; }
  }, 12);
}

function discardChoice() {
  choice = null;
  try { localStorage.removeItem('arqgen.mvp0.choice'); } catch { /* memory-only session */ }
  if (run && !stale) renderChoice();
}

function saveChoice() {
  if (!run || stale) return;
  const alt = run.alternatives[selectionIndex];
  choice = { input_hash: run.input_hash, candidate_id: alt.id, kind: 'user_preference_preliminary', chosen_at: new Date().toISOString() };
  try { localStorage.setItem('arqgen.mvp0.choice', JSON.stringify(choice)); } catch { /* private browsing: memory-only */ }
  renderChoice();
}

function download(contents, mime, name) {
  const blob = new Blob([contents], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function showFeedback(id, message, failed = false) {
  const feedback = el(id);
  feedback.hidden = !message;
  feedback.dataset.state = failed ? 'error' : 'ok';
  feedback.textContent = message;
}
const showImportFeedback = (message, failed = false) => showFeedback('import-feedback', message, failed);
const showLocalFeedback = (message, failed = false) => showFeedback('local-feedback', message, failed);

function renderExploration() {
  el('explore-start').disabled = !engine || !evaluated || stale || exploreBusy;
  el('explore-cancel').disabled = !exploreBusy && !exploration;
  el('explore-export').disabled = !exploration || stale || exploreBusy;
  el('explore-import').disabled = !engine || exploreBusy;
  el('explore-count').disabled = exploreBusy;
  const grid = el('explore-grid');
  grid.replaceChildren();
  const audit = el('explore-audit');
  const content = el('explore-audit-content');
  content.replaceChildren();
  audit.hidden = !exploration;
  if (!exploration) {
    el('explore-summary').textContent = exploreBusy
      ? 'Explorando o verificando en un proceso separado. Puedes cancelar sin alterar la planta ni la cartera.'
      : 'Genera un encargo y explora semillas para ampliar la búsqueda limitada.';
    return;
  }
  const { result, seed_count: count } = exploration;
  el('explore-summary').textContent = `${count} semillas · ${result.generated} variantes ensayadas · ${result.rejected} descartadas · ${result.valid} validadas por reglas demo · ${result.pareto_front_size} en frente Pareto 1 del lote · ${result.alternatives.length} propuestas mostradas. ${result.status === 'infeasible' ? 'Ninguna pasó esta búsqueda; podrían existir otras soluciones fuera del modelo.' : 'No hay óptimo global ni dictamen legal.'}`;
  const summary = document.createElement('p');
  summary.textContent = 'Cada variante se cuenta una vez por su primer motivo de rechazo. Semillas consecutivas con vuelta tras 4294967295; no se ensayan otros programas, rutas ni normas.';
  content.append(summary);
  const perSeed = document.createElement('ul');
  for (const row of result.seed_runs) {
    const item = document.createElement('li');
    item.textContent = `Semilla ${row.seed}: ${row.generated} intentos, ${row.rejected} descartes, ${row.generated - row.rejected} válidas${row.reasons.length ? ` · ${row.reasons.join('; ')}` : ''}.`;
    perSeed.append(item);
  }
  content.append(perSeed);
  const heading = document.createElement('p');
  heading.textContent = 'Motivos agregados de rechazo (no prueba de inviabilidad real):';
  content.append(heading);
  const reasons = document.createElement('ul');
  for (const row of result.rejection_summary) {
    const item = document.createElement('li');
    item.textContent = `${row.count} × ${row.reason}`;
    reasons.append(item);
  }
  if (!reasons.childElementCount) {
    const item = document.createElement('li');
    item.textContent = 'Sin descartes en las variantes ensayadas, o sin variantes por una comprobación previa.';
    reasons.append(item);
  }
  content.append(reasons);

  for (const { seed, candidate: alt } of result.alternatives) {
    const card = document.createElement('article');
    card.className = 'explore-card';
    const eyebrow = document.createElement('span');
    eyebrow.className = 'scenario-eyebrow';
    eyebrow.textContent = `SEMILLA ${seed} · FRENTE PARETO ${alt.pareto_layer + 1} DEL LOTE`;
    const title = document.createElement('h3');
    title.textContent = alt.label;
    const plan = document.createElement('img');
    plan.className = 'explore-plan';
    plan.alt = `Croquis conceptual ${alt.label}, semilla ${seed}; no apto para obra`;
    // An image, not injected HTML: only freshly generated/replayed Rust SVG.
    plan.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(alt.svg)}`;
    const metrics = document.createElement('ul');
    metrics.className = 'explore-stats';
    for (const [label, value] of [
      ['Huella bruta', `${number(alt.built_area)} m²`],
      ['Área útil', `${number(alt.usable_area)} m²`],
      ['Ajuste de área', `${number(alt.metrics.area_fit * 100, 0)} %`],
      ['Circulación / útil', `${number(alt.metrics.circulation_ratio * 100)} %`],
      ['Privacidad (heurística)', `${number(alt.metrics.privacy_score * 100, 0)} %`],
      ['Cocina-baño (heurística)', `${number(alt.metrics.service_score * 100, 0)} %`],
    ]) {
      const item = document.createElement('li');
      const strong = document.createElement('strong');
      strong.textContent = value;
      item.append(strong, label);
      metrics.append(item);
    }
    const note = document.createElement('p');
    note.className = 'explore-note';
    note.textContent = 'Solo geometría ilustrativa validada en Rust. Parcela, acceso y reglas sin verificar; no se calculó luz natural ni ventilación efectiva.';
    const id = document.createElement('small');
    id.textContent = `ID ${alt.id} · otros objetivos: circulación, dormitorios al E.`;
    const actions = document.createElement('div');
    actions.className = 'scenario-actions';
    const svg = document.createElement('button');
    svg.type = 'button';
    svg.textContent = '↓ Croquis SVG';
    svg.addEventListener('click', () => {
      if (exploration?.result === result && !stale) download(alt.svg, 'image/svg+xml;charset=utf-8', `arqgen-lote-CONCEPTUAL-${alt.id}.svg`);
    });
    actions.append(svg);
    const detail = document.createElement('details');
    detail.className = 'explore-audit';
    const caption = document.createElement('summary');
    caption.textContent = 'Ver decisiones y advertencias Rust';
    const decisions = document.createElement('ul');
    for (const decision of alt.decisions) {
      const item = document.createElement('li');
      item.textContent = `${decision.rule}: ${decision.explanation}`;
      decisions.append(item);
    }
    for (const warning of alt.warnings) {
      const item = document.createElement('li');
      item.textContent = `AVISO: ${warning}`;
      decisions.append(item);
    }
    detail.append(caption, decisions);
    card.append(eyebrow, title, plan, metrics, note, id, actions, detail);
    grid.append(card);
  }
}

function cancelExploration(message = '') {
  const hadWork = exploreBusy || !!exploration;
  ++exploreJobToken;
  if (exploreWorker) exploreWorker.terminate();
  exploreWorker = null;
  exploreBusy = false;
  exploration = null;
  renderExploration();
  if (message && hadWork) showFeedback('explore-status', message);
}

// All-or-nothing adoption after worker completion. A token plus revision and
// import sequence prevents an interrupted or outdated worker from committing.
function startExplorerWorker(job, token, startingRevision, sequence = null) {
  const worker = new Worker(new URL('./explorer.worker.js', import.meta.url), { type: 'module' });
  exploreWorker = worker;
  const finish = (data) => {
    if (exploreWorker !== worker || exploreJobToken !== token) return;
    worker.terminate();
    exploreWorker = null;
    exploreBusy = false;
    if (revision !== startingRevision || (sequence !== null && sequence !== importSequence)) {
      renderExploration();
      showFeedback('explore-status', 'El encargo cambió durante la operación; el lote no se abrió.');
      return;
    }
    try {
      if (data.type === 'error') throw new Error(data.message);
      if (job.type === 'explore' && data.type === 'explore') {
        if (!['ok', 'infeasible'].includes(data.result?.status) || data.result.base_seed !== job.input.seed ||
            data.result.seed_count !== job.seed_count || data.result.engine_version !== evaluated?.generation.engine_version) {
          throw new Error('Rust devolvió un lote incompatible con el encargo actual.');
        }
        exploration = { input: structuredClone(job.input), seed_count: job.seed_count, result: data.result };
        showFeedback('explore-status', 'Lote calculado con Rust. No se guardó en la cartera: descarga JSON si quieres conservarlo.');
      } else if (job.type === 'verify' && data.type === 'verify') {
        const checked = data.verified;
        if ((portfolioDirty || activeProject || comparisonRecords.length || stale) &&
            !window.confirm('El lote pasó el replay con Rust. ¿Reemplazar el encargo en pantalla y vaciar el cuaderno sin guardar estos cambios en la cartera? Descarga antes tus archivos si quieres conservarlos.')) {
          showFeedback('explore-status', 'Apertura cancelada: encargo, proyecto y lote anterior permanecen sin cambios.');
          renderExploration();
          return;
        }
        const generation = invokeCore(checked.input); // baseline Rust replay before any UI change
        if (!['ok', 'infeasible'].includes(generation?.status) || generation.engine_version !== checked.result.engine_version) {
          throw new Error('El encargo base ya no coincide con el motor local.');
        }
        revision++;
        comparisonRecords = [];
        putInputOnForm(checked.input);
        activeProject = null;
        portfolioDirty = false;
        el('portfolio-name').value = '';
        discardChoice();
        adoptEvaluation(checked.input, generation); // clears any prior exploration
        recordHistory(true);
        renderPortfolioList();
        el('generate-button').disabled = false;
        exploration = checked;
        showImportFeedback('');
        showFeedback('explore-status', `Lote de ${checked.seed_count} semillas reproducido y comparado íntegramente con Rust; encargo base también regenerado. Ni archivo ni croquis constituyen aprobación.`);
      } else throw new Error('Respuesta de exploración desconocida.');
    } catch (error) {
      showFeedback('explore-status', `No se completó la exploración: ${error.message}`, true);
    }
    renderExploration();
  };
  worker.onmessage = ({ data }) => finish(data);
  worker.onerror = (error) => { error.preventDefault(); finish({ type: 'error', message: error.message || 'El proceso de exploración falló.' }); };
  try { worker.postMessage(job); }
  catch (error) { worker.terminate(); exploreWorker = null; throw error; }
}

function startExploration() {
  if (!engine || !evaluated || stale || exploreBusy) return;
  const count = Number(el('explore-count').value);
  if (!Number.isInteger(count) || count < 2 || count > explorationLimit) return;
  cancelExploration();
  const input = structuredClone(evaluated.input);
  const token = ++exploreJobToken;
  exploreBusy = true;
  renderExploration();
  showFeedback('explore-status', `Ensayando ${count} semillas con Rust en un proceso cancelable…`);
  try { startExplorerWorker({ type: 'explore', input, seed_count: count }, token, revision); }
  catch (error) {
    exploreBusy = false;
    renderExploration();
    showFeedback('explore-status', `No arrancó la exploración: ${error.message}`, true);
  }
}

async function importExplorationFile(file) {
  if (!file || exploreBusy) return;
  const sequence = ++importSequence;
  const startingRevision = revision;
  const token = ++exploreJobToken;
  exploreBusy = true;
  renderExploration();
  showFeedback('explore-status', 'Leyendo el JSON; se comprobarán todas las semillas fuera del hilo de la interfaz…');
  try {
    if (!engine) throw new Error('El núcleo Rust aún no está disponible.');
    if (!file.size || file.size > maxArchiveBytes) throw new Error('Archivo vacío o mayor de 8 MiB.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
    if (token !== exploreJobToken || startingRevision !== revision || sequence !== importSequence) return;
    const document = parseArchiveText(text);
    startExplorerWorker({ type: 'verify', document }, token, startingRevision, sequence);
  } catch (error) {
    if (token === exploreJobToken) {
      exploreBusy = false;
      renderExploration();
      showFeedback('explore-status', `No se abrió el lote: ${error.message}`, true);
    }
  } finally { el('explore-file').value = ''; }
}

let importSequence = 0;
async function importFile(file) {
  if (!file) return;
  const sequence = ++importSequence;
  const initialRevision = revision;
  el('import-archive').disabled = true;
  showImportFeedback('Leyendo y verificando el archivo con el núcleo Rust local…');
  try {
    if (!engine) throw new Error('El núcleo Rust aún no está disponible.');
    if (!file.size || file.size > maxArchiveBytes) throw new Error('Archivo vacío o mayor de 8 MiB.');
    const bytes = await file.arrayBuffer();
    if (revision !== initialRevision || sequence !== importSequence) {
      throw new Error('El formulario cambió durante la importación. Repite la operación.');
    }
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const verified = verifyArchive(parseArchiveText(text), knowledge, invokeCore);
    if (revision !== initialRevision || sequence !== importSequence) {
      throw new Error('El formulario cambió durante la importación. Repite la operación.');
    }
    // Commit atomically only after ALL scenarios have been re-run and matched.
    revision++;
    comparisonRecords = verified.records;
    putInputOnForm(verified.focus.input);
    activeProject = null; // individual/comparison imports do not overwrite an opened project
    portfolioDirty = false;
    el('portfolio-name').value = '';
    discardChoice();
    adoptEvaluation(verified.focus.input, verified.focus.generation);
    recordHistory(true);
    renderPortfolioList();
    el('generate-button').disabled = false;
    const detail = verified.kind === 'comparison' ? `${comparisonRecords.length} corridas` : 'una corrida';
    showImportFeedback(`Importadas ${detail}. Cada entrada fue regenerada y comparada con Rust; los SVG del archivo no se usaron. La preferencia del archivo no constituye aprobación.`);
  } catch (error) {
    showImportFeedback(`No se importó el archivo: ${error.message}`, true);
  } finally {
    el('import-file').value = '';
    el('import-archive').disabled = !engine;
  }
}

async function saveWorkspace() {
  if (!evaluated || stale || !engine) return;
  el('save-local').disabled = true;
  try {
    const document = snapshotWorkspace(evaluated, comparisonRecords);
    await saveLocalWorkspace(document); // one IndexedDB readwrite transaction, never implicit autosave
    showLocalFeedback('Copia guardada en este navegador. Reabrirla volverá a verificar todas las corridas con Rust. Descarga JSON como respaldo externo.');
  } catch (error) {
    showLocalFeedback(`No se guardó la copia local: ${error.message}`, true);
  } finally { renderComparison(); }
}

async function loadWorkspace() {
  const sequence = ++importSequence; // local reopen and file import cannot both commit
  const initialRevision = revision;
  el('load-local').disabled = true;
  showLocalFeedback('Reabriendo y verificando cada corrida con el núcleo Rust local…');
  try {
    if (!engine) throw new Error('El núcleo Rust aún no está disponible.');
    const document = await readLocalWorkspace();
    if (revision !== initialRevision || sequence !== importSequence) {
      throw new Error('El formulario cambió mientras se abría la copia. Repite la operación.');
    }
    if (!document) throw new Error('No hay una copia local guardada en este navegador.');
    const verified = verifyWorkspace(document, knowledge, invokeCore);
    if (revision !== initialRevision || sequence !== importSequence) {
      throw new Error('El formulario cambió mientras se verificaba la copia. Repite la operación.');
    }
    revision++;
    comparisonRecords = verified.records;
    putInputOnForm(verified.focus.input);
    activeProject = null; // the single-slot snapshot remains separate from the portfolio
    portfolioDirty = false;
    el('portfolio-name').value = '';
    discardChoice();
    adoptEvaluation(verified.focus.input, verified.focus.generation);
    recordHistory(true);
    renderPortfolioList();
    el('generate-button').disabled = false;
    showImportFeedback('');
    showLocalFeedback(`Copia reabierta: ${verified.records.length} corridas guardadas y el encargo actual, regenerados con Rust. Una preferencia previa no es una aprobación técnica.`);
  } catch (error) {
    showLocalFeedback(`No se reabrió la copia: ${error.message}`, true);
  } finally {
    el('load-local').disabled = !engine;
  }
}

async function deleteWorkspace() {
  if (!window.confirm('¿Borrar la copia guardada en este navegador? No se borran el cuaderno en pantalla ni los JSON descargados.')) return;
  ++importSequence; // cancel a concurrent local reopen or file import before it can commit
  el('delete-local').disabled = true;
  try {
    await removeLocalWorkspace();
    showLocalFeedback('Copia local borrada. El cuaderno en pantalla y tus descargas no se modificaron.');
  } catch (error) {
    showLocalFeedback(`No se borró la copia: ${error.message}`, true);
  } finally { el('delete-local').disabled = !('indexedDB' in window); }
}

function renderPortfolioControls() {
  const usable = !!engine && 'indexedDB' in window && !portfolioBusy;
  el('portfolio-count').textContent = `${portfolioEntries.length} / ${portfolioLimit} PROYECTOS`;
  el('portfolio-create').disabled = !usable || !evaluated || stale || portfolioEntries.length >= portfolioLimit;
  el('portfolio-update').disabled = !usable || !evaluated || stale || !activeProject;
  el('portfolio-export').disabled = !usable || !portfolioEntries.length;
  el('portfolio-import').disabled = !usable;
  el('project-breadcrumb').textContent = activeProject
    ? `${activeProject.name}${portfolioDirty ? ' · sin actualizar' : ''}` : 'Proyecto sin guardar';
}
function renderPortfolioList() {
  const host = el('portfolio-list');
  host.replaceChildren();
  if (!portfolioEntries.length) {
    const empty = document.createElement('p');
    empty.className = 'portfolio-empty';
    empty.textContent = 'Cartera vacía. Genera un encargo y guárdalo de forma explícita; descarga un respaldo fuera del navegador.';
    host.append(empty);
  }
  for (const entry of portfolioEntries) {
    const card = document.createElement('article');
    card.className = 'portfolio-item';
    if (entry.id === activeProject?.id) card.classList.add('active');
    const title = document.createElement('h3');
    title.textContent = entry.name; // untrusted label: never innerHTML
    const description = document.createElement('p');
    description.textContent = `Guardado ${new Date(entry.updated_at).toLocaleString('es-ES')} · ${Array.isArray(entry.snapshot.scenarios) ? entry.snapshot.scenarios.length : '¿?'} corridas · contenido SIN REVALIDAR hasta abrir o descargar.`;
    const actions = document.createElement('div');
    actions.className = 'scenario-actions';
    const open = document.createElement('button');
    open.type = 'button';
    open.textContent = 'Abrir y verificar con Rust';
    open.setAttribute('aria-label', `Abrir y verificar ${entry.name}`);
    open.disabled = portfolioBusy || !engine;
    open.addEventListener('click', () => { void openPortfolioProject(entry.id); });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'scenario-remove';
    remove.textContent = 'Borrar';
    remove.setAttribute('aria-label', `Borrar ${entry.name}`);
    remove.disabled = portfolioBusy;
    remove.addEventListener('click', () => { void removePortfolioProject(entry); });
    actions.append(open, remove);
    card.append(title, description, actions);
    host.append(card);
  }
  renderPortfolioControls();
}
function setPortfolioBusy(value) {
  portfolioBusy = value;
  renderPortfolioList();
}
async function refreshPortfolio() {
  const sequence = ++portfolioListSequence;
  const entries = await listProjects();
  if (sequence !== portfolioListSequence) return;
  portfolioEntries = entries;
  renderPortfolioList();
}
const portfolioFeedback = (message, error = false) => showFeedback('portfolio-status', message, error);

async function savePortfolioProject(asNew) {
  if (portfolioBusy || !engine || !evaluated || stale || (asNew && portfolioEntries.length >= portfolioLimit)) return;
  if (!asNew && !activeProject) return;
  const startingRevision = revision;
  const startingName = el('portfolio-name').value;
  setPortfolioBusy(true);
  try {
    const entry = asNew
      ? newProject(startingName, evaluated, comparisonRecords)
      : revisedProject(portfolioEntries.find(({ id }) => id === activeProject.id),
        startingName, evaluated, comparisonRecords);
    await saveProject(entry, asNew ? null : activeProject.edit_token);
    if (asNew) discardChoice(); // identical hashes in distinct jobs do not inherit a preference
    portfolioDirty = startingRevision !== revision || startingName !== el('portfolio-name').value;
    if (asNew && !portfolioDirty) recordHistory(true); // new independent job, no undo across projects
    activeProject = { id: entry.id, edit_token: entry.edit_token, name: entry.name };
    if (!portfolioDirty) el('portfolio-name').value = entry.name;
    await refreshPortfolio();
    portfolioFeedback(`Proyecto «${entry.name}» ${asNew ? 'creado' : 'actualizado'}. ${portfolioDirty ? 'El formulario cambió mientras se guardaba: vuelve a generar y actualizar para conservar esos cambios. ' : ''}Las corridas se revalidarán al abrirlo; descarga la cartera JSON como respaldo externo.`);
  } catch (error) { portfolioFeedback(`No se guardó el proyecto: ${error.message}`, true); }
  finally { setPortfolioBusy(false); }
}
async function openPortfolioProject(id) {
  if (portfolioBusy || !engine) return;
  if (portfolioDirty && !window.confirm('Hay cambios sin guardar en el formulario/cuaderno. ¿Abrir otro proyecto y descartarlos?')) return;
  const sequence = ++importSequence;
  const startingRevision = revision;
  setPortfolioBusy(true);
  portfolioFeedback('Reabriendo: comprobando íntegramente cada corrida con Rust/WASM…');
  try {
    const entry = await readProject(id);
    if (!entry) throw new Error('El proyecto ya no existe en este navegador.');
    const verified = verifyWorkspace(entry.snapshot, knowledge, invokeCore);
    if (sequence !== importSequence || startingRevision !== revision) {
      throw new Error('El formulario cambió durante la apertura. Repite la operación.');
    }
    revision++;
    comparisonRecords = verified.records;
    putInputOnForm(verified.focus.input);
    discardChoice();
    adoptEvaluation(verified.focus.input, verified.focus.generation);
    recordHistory(true);
    activeProject = { id: entry.id, edit_token: entry.edit_token, name: entry.name };
    portfolioDirty = false;
    el('portfolio-name').value = entry.name;
    el('generate-button').disabled = false;
    renderPortfolioList();
    portfolioFeedback(`Proyecto «${entry.name}» abierto: ${verified.records.length} corridas y encargo actual regenerados y comparados con Rust. El croquis no es un lindero legal; no hay aprobación.`);
  } catch (error) { portfolioFeedback(`No se abrió el proyecto: ${error.message}`, true); }
  finally { setPortfolioBusy(false); }
}
async function removePortfolioProject(entry) {
  if (portfolioBusy || !window.confirm(`¿Borrar «${entry.name}» de este navegador? No se borra ningún JSON ya descargado.`)) return;
  setPortfolioBusy(true);
  try {
    await deleteProject(entry.id, entry.edit_token);
    ++importSequence; // a concurrent reopen cannot commit after deletion
    if (activeProject?.id === entry.id) activeProject = null;
    await refreshPortfolio();
    portfolioFeedback(`«${entry.name}» borrado. El formulario en pantalla y los archivos descargados permanecen sin cambios.`);
  } catch (error) { portfolioFeedback(`No se borró el proyecto: ${error.message}`, true); }
  finally { setPortfolioBusy(false); }
}
async function downloadPortfolio() {
  if (portfolioBusy || !engine) return;
  setPortfolioBusy(true);
  portfolioFeedback('Reproduciendo todas las corridas antes de descargar el respaldo…');
  try {
    const entries = await listProjects();
    const document = exportPortfolio(entries, knowledge, invokeCore);
    download(JSON.stringify(document), 'application/json;charset=utf-8',
      `arqgen-cartera-CONCEPTUAL-${document.exported_at.slice(0, 10)}.json`);
    portfolioFeedback(`${entries.length} proyectos revalidados y exportados. El JSON no está cifrado ni firmado: consérvalo bajo tu control.`);
  } catch (error) { portfolioFeedback(`No se descargó la cartera: ${error.message}`, true); }
  finally { setPortfolioBusy(false); }
}
async function importPortfolioFile(file) {
  if (!file || portfolioBusy) return;
  const sequence = ++importSequence;
  const startingRevision = revision;
  setPortfolioBusy(true);
  portfolioFeedback('Leyendo y revalidando todas las corridas antes de sustituir cualquier proyecto…');
  try {
    if (!engine) throw new Error('Rust aún no está disponible.');
    if (!file.size || file.size > maxPortfolioBytes) throw new Error('Respaldo vacío o mayor de 16 MiB.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
    const document = parsePortfolioText(text);
    const verified = verifyPortfolio(document, knowledge, invokeCore);
    if (sequence !== importSequence || startingRevision !== revision) {
      throw new Error('El formulario cambió mientras se verificaba el respaldo. Repite la operación.');
    }
    if (!window.confirm(`Se verificaron ${verified.length} proyectos. ¿REEMPLAZAR toda la cartera local (${portfolioEntries.length} proyectos)? La pantalla actual no cambiará; exporta un respaldo antes si necesitas conservarla.`)) {
      portfolioFeedback('Restauración cancelada; no se sustituyó ningún proyecto.'); return;
    }
    await replacePortfolio(document, knowledge, invokeCore); // replay again; ONE atomic readwrite transaction
    activeProject = null;
    portfolioDirty = false;
    el('portfolio-name').value = '';
    await refreshPortfolio();
    portfolioFeedback(`${verified.length} proyectos restaurados atómicamente tras revalidar todas las corridas con Rust. La pantalla no se alteró: abre un proyecto de la lista para verlo.`);
  } catch (error) { portfolioFeedback(`No se restauró la cartera: ${error.message}`, true); }
  finally { el('portfolio-file').value = ''; setPortfolioBusy(false); }
}

function invalidateRun() {
  cancelExploration('Cambió el formulario: lote anterior descartado; vuelve a generar antes de explorar.');
  revision++;
  stale = true;
  portfolioDirty = true;
  showImportFeedback('');
  showFeedback('history-feedback', '');
  if (!el('engine-state').hidden || !el('empty-view').hidden) {
    setState('Cambios pendientes. Genera de nuevo para evaluar esta entrada.');
  }
  if (run) {
    el('result-status').textContent = 'SIN REGENERAR';
    el('result-status').classList.add('stale');
    el('scope-review').classList.add('stale');
    el('scope-stale').hidden = false;
    el('choice-title').textContent = 'Hay cambios pendientes.';
    el('choice-subtitle').textContent = 'Regenera para marcar una preferencia o exportar las nuevas condiciones.';
    setActionEnabled(false);
  }
  renderComparison();
  renderHistoryControls();
  renderExploration();
}

form.addEventListener('submit', regenerate);
form.addEventListener('input', (event) => {
  if (['plot_notch_enabled', 'plot_notch_2_enabled', 'notch_width', 'notch_2_width', 'width', 'depth'].includes(event.target.name)) reflectPlotFields();
  if (['approach_shape', 'approach_width'].includes(event.target.name)) reflectApproachFields();
  if (['reserve_enabled', 'reserve_2_enabled'].includes(event.target.name)) reflectReservationFields();
  if (!pressureControls.includes(event.target.name) && comparisonRecords.length) {
    comparisonRecords = [];
    comparisonNotice = 'Comparación reiniciada: cambió el encargo (incluido el croquis de parcela), su contexto declarado o la semilla.';
  } else comparisonNotice = '';
  invalidateRun();
});
el('new-seed').addEventListener('click', () => {
  const field = form.elements.seed;
  field.value = String((Number(field.value) + 1) % 4294967296);
  if (comparisonRecords.length) {
    comparisonRecords = [];
    comparisonNotice = 'Comparación reiniciada: cambió la semilla.';
  }
  invalidateRun();
  regenerate();
});
el('reset-scenario').addEventListener('click', () => {
  for (const key of pressureControls) form.elements[key].value = String(knowledge.bath_pressure[key]);
  comparisonNotice = '';
  invalidateRun();
  regenerate();
});
el('save-scenario').addEventListener('click', () => {
  if (!evaluated || stale) return;
  const attempt = archiveScenario(comparisonRecords, evaluated.input, evaluated.generation);
  comparisonRecords = attempt.records;
  comparisonNotice = {
    saved: 'Corrida guardada. Cambia una hipótesis, regenera y guarda otra para contrastar.',
    duplicate: 'Esta corrida ya figura en el cuaderno.',
    different_brief: 'La parcela, trazado frontal o zonas voluntarias, el programa, contexto, semilla o reglas fijas no coinciden: limpia la comparación.',
    hash_conflict: 'Conflicto de identidad entre entradas: no se guardó la corrida.',
    full: 'Límite de tres corridas: elimina una antes de guardar.',
    invalid: 'No se guardó: falta una respuesta válida del núcleo.',
  }[attempt.reason];
  if (attempt.reason === 'saved') portfolioDirty = true;
  renderComparison();
  if (attempt.reason === 'saved') recordHistory();
});
el('clear-comparison').addEventListener('click', () => {
  comparisonRecords = [];
  comparisonNotice = 'Cuaderno vaciado. Puedes guardar una nueva corrida.';
  portfolioDirty = true;
  renderComparison();
  recordHistory();
});
el('export-comparison').addEventListener('click', () => {
  try {
    const report = comparisonReport(comparisonRecords);
    download(JSON.stringify(report, null, 2), 'application/json;charset=utf-8',
      `arqgen-comparativa-${report.scenarios[0].generation.input_hash}.json`);
  } catch (error) {
    comparisonNotice = error.message;
    renderComparison();
  }
});
el('explore-start').addEventListener('click', startExploration);
el('explore-cancel').addEventListener('click', () => cancelExploration('Exploración cancelada y lote borrado de esta pestaña.'));
el('explore-export').addEventListener('click', () => {
  if (!exploration || stale || exploreBusy) return;
  try {
    const doc = makeExplorationArchive(exploration.input, exploration.seed_count, exploration.result);
    download(JSON.stringify(doc), 'application/json;charset=utf-8', `arqgen-lote-CONCEPTUAL-semilla-${doc.input.seed}.json`);
    showFeedback('explore-status', 'Lote descargado. Al reabrirlo se repetirán todas las semillas con el Rust local.');
  } catch (error) { showFeedback('explore-status', `No se descargó el lote: ${error.message}`, true); }
});
el('explore-import').addEventListener('click', () => el('explore-file').click());
el('explore-file').addEventListener('change', (event) => { void importExplorationFile(event.target.files?.[0]); });
el('import-archive').addEventListener('click', () => el('import-file').click());
el('import-file').addEventListener('change', (event) => { void importFile(event.target.files?.[0]); });
el('save-local').addEventListener('click', () => { void saveWorkspace(); });
el('load-local').addEventListener('click', () => { void loadWorkspace(); });
el('delete-local').addEventListener('click', () => { void deleteWorkspace(); });
el('portfolio-create').addEventListener('click', () => { void savePortfolioProject(true); });
el('portfolio-update').addEventListener('click', () => { void savePortfolioProject(false); });
el('portfolio-export').addEventListener('click', () => { void downloadPortfolio(); });
el('portfolio-import').addEventListener('click', () => el('portfolio-file').click());
el('portfolio-file').addEventListener('change', (event) => { void importPortfolioFile(event.target.files?.[0]); });
el('portfolio-name').addEventListener('input', () => {
  if (activeProject && el('portfolio-name').value !== activeProject.name) {
    portfolioDirty = true;
    renderPortfolioControls();
  }
});
el('history-undo').addEventListener('click', () => restoreHistory(-1));
el('history-redo').addEventListener('click', () => restoreHistory(1));
el('approve').addEventListener('click', saveChoice);
el('toggle-clearances').addEventListener('click', () => {
  const visible = el('plan').classList.toggle('show-clearances');
  el('toggle-clearances').setAttribute('aria-pressed', String(visible));
});
el('export-svg').addEventListener('click', () => {
  if (run && !stale) download(run.alternatives[selectionIndex].svg, 'image/svg+xml;charset=utf-8', `arqgen-${run.alternatives[selectionIndex].id}.svg`);
});
el('drawing-preview').addEventListener('toggle', renderDrawingPreview);
el('export-drawings').addEventListener('click', () => {
  if (!run || stale || !runInput) return;
  try {
    const packageSvg = buildDrawingPackage(runInput, run, selectionIndex);
    download(packageSvg.bytes, 'application/zip', packageSvg.filename);
    showFeedback('export-feedback', 'Descargadas 4 láminas SVG A3 de la misma alternativa: emplazamiento, planta amueblada, cotas esquemáticas y envolvente/vanos 2D validados. El JSON de nivel 0 NO conoce alturas. Ni cortes, fachadas, hotel u hospital están modelados. NO APTO PARA OBRA.');
  } catch (error) {
    showFeedback('export-feedback', `No se exportaron las láminas: ${error.message}`, true);
  }
});
el('export-report').addEventListener('click', () => {
  if (!run || stale || !runInput) return;
  try {
    const report = conceptualReport(runInput, run, selectionIndex, sources);
    download(report, 'text/plain;charset=utf-8', `arqgen-ficha-CONCEPTUAL-${run.alternatives[selectionIndex].id}.txt`);
  } catch (error) {
    const feedback = el('export-feedback');
    feedback.hidden = false;
    feedback.dataset.state = 'error';
    feedback.textContent = `No se exportó la ficha: ${error.message}`;
  }
});
el('export-json').addEventListener('click', () => {
  if (run && !stale && runInput) download(JSON.stringify({ input: runInput, generation: run, selection: choice && choice.input_hash === run.input_hash ? choice : null }, null, 2),
    'application/json;charset=utf-8', `arqgen-${run.input_hash}.json`);
});

reflectPlotFields();
reflectReservationFields();
for (const key of pressureControls) form.elements[key].value = String(knowledge.bath_pressure[key]);
const freeAir = knowledge.bath_airflow.fan_free_air_rating;
form.elements.fan_reference_flow_m3h.max = String(Math.min(500, freeAir));
el('free-air-reference').textContent = `Punto nominal fijo: 0 Pa / ${number(freeAir)} m³/h (aire libre).`;
el('scenario-hint').textContent = `El caudal del segundo punto debe ser < ${number(freeAir)} m³/h. Otros coeficientes demo fijos; caudal entregado NO EVALUADO.`;
el('rule-version').textContent = `${knowledge.id} · v${knowledge.version} · 3 supuestos editables · no certificada`;
el('geometry-rules').textContent = `Retiros: ${number(knowledge.setbacks.front)} m frente · ${number(knowledge.setbacks.rear)} m fondo · ${number(knowledge.setbacks.left)} / ${number(knowledge.setbacks.right)} m laterales. Muros en planta: ${number(knowledge.walls.exterior * 100, 0)} cm exteriores y ${number(knowledge.walls.partition * 100, 0)} cm tabiques.`;
// Production builds pre-cache the exact HTML/CSS/JS/WASM bundle. This never stores
// projects: documents remain in the browser only until the user exports them.
if (window.isTauri) {
  // In a desktop bundle the assets are shipped with WebView2; a service worker
  // is unnecessary (and its availability varies by custom protocol).
  el('offline-label').textContent = 'Aplicación de escritorio · sin nube';
} else if (import.meta.env.PROD) {
  const label = el('offline-label');
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`, { scope: import.meta.env.BASE_URL })
        .then(() => navigator.serviceWorker.ready)
        .then(() => { label.textContent = 'Disponible sin conexión'; })
        .catch(() => { label.textContent = 'Caché offline no disponible'; });
    });
  } else {
    label.textContent = 'Caché offline no disponible';
  }
}
renderComparison();
renderPortfolioList();
renderHistoryControls();
renderExploration();
loadCore().then((module) => {
  engine = module;
  el('import-archive').disabled = false;
  el('load-local').disabled = !('indexedDB' in window);
  el('delete-local').disabled = !('indexedDB' in window);
  if ('indexedDB' in window) {
    void refreshPortfolio().catch((error) => portfolioFeedback(`No se pudo leer la cartera: ${error.message}`, true));
  } else portfolioFeedback('IndexedDB no está disponible; usa descargas JSON individuales como respaldo.', true);
  regenerate();
}).catch((error) => {
  renderEmpty({ status: 'error', message: `No se pudo iniciar el núcleo Rust: ${error.message}` });
});
