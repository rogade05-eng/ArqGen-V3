// A presentation-only projection of the CURRENT validated Rust v8 result.
// No new architecture, heights, floors, setbacks or code compliance is inferred.
// Separate from candidate.svg: legacy replay and input hashes remain unchanged.
import { strToU8, zipSync } from 'fflate';
import { extractPlanEnvelope } from './plan-envelope.js';

export const drawingPackageFormat = 'arqgen-conceptual-svg-sheets-v2';
const PAPER = { width: 297, height: 420 }; // ISO A3 portrait, in millimetres.
const VIEW = { x: 35, y: 67, width: 227, height: 250 };
const FRAME = { x: 16, y: 48, width: 265, height: 290 };
const SCALES = [50, 100, 200, 500, 1000, 2000, 5000];
const FIXED_MTIME = new Date('1980-01-01T00:00:00.000Z');

function ensure(condition, message = 'La geometría no permite componer láminas.') {
  if (!condition) throw new Error(message);
}
const finite = (n) => typeof n === 'number' && Number.isFinite(n);
const near = (a, b) => Math.abs(a - b) <= 1e-5;
const fmt = (n, digits = 2) => n.toFixed(digits);
const xml = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c]);

function checkedRect(r, width, depth) {
  ensure(r && [r.x, r.y, r.width, r.depth].every(finite) && r.width > 0 && r.depth > 0 &&
    r.x >= -1e-6 && r.y >= -1e-6 && r.x + r.width <= width + 1e-6 &&
    r.y + r.depth <= depth + 1e-6, 'Rectángulo de la alternativa fuera del croquis o inválido.');
  return r;
}

function bounds(rects) {
  ensure(rects.length > 0);
  const x = Math.min(...rects.map((r) => r.x));
  const y = Math.min(...rects.map((r) => r.y));
  const right = Math.max(...rects.map((r) => r.x + r.width));
  const bottom = Math.max(...rects.map((r) => r.y + r.depth));
  return { x, y, width: right - x, depth: bottom - y };
}

function verifiedDrawing(input, generation, index) {
  ensure(input?.request_schema === 'arqgen-brief-v8' && generation?.status === 'ok' &&
    Number.isInteger(index) && index >= 0 && index < generation.alternatives?.length,
  'Solo se documenta una alternativa vigente generada y validada por Rust.');
  const alt = generation.alternatives[index];
  const { width, depth, front_orientation: front } = input.site || {};
  ensure(finite(width) && finite(depth) && width > 0 && depth > 0 && width <= 200 && depth <= 200 &&
    ['N', 'E', 'S', 'W'].includes(front) &&
    typeof generation.input_hash === 'string' && /^[a-f0-9]{16}$/.test(generation.input_hash) &&
    typeof alt.id === 'string' && /^cand-[a-f0-9]{16}-\d+$/.test(alt.id) &&
    alt.id.startsWith(`cand-${generation.input_hash}-`) &&
    typeof alt.label === 'string' && alt.label.length < 80 &&
    typeof alt.svg === 'string' && alt.svg.includes('NO APTO PARA OBRA') &&
    Array.isArray(alt.rooms) && alt.rooms.length >= 4 && alt.rooms.length <= 12 &&
    Array.isArray(alt.wall_zones) && alt.wall_zones.length > 0 && alt.wall_zones.length < 250 &&
    Array.isArray(alt.corridor_usable_segments) && alt.corridor_usable_segments.length > 0 &&
    Array.isArray(alt.front_approach?.segments) && alt.front_approach.segments.length <= 3 &&
    Array.isArray(input.site.reserved_areas) && input.site.reserved_areas.length <= 2 &&
    Array.isArray(generation.site_plot?.vertices) &&
    [4, 6, 8].includes(generation.site_plot.vertices.length) &&
    generation.site_plot.shape === input.site.plot_outline?.shape &&
    Array.isArray(generation.site_plot.rear_notches) &&
    generation.site_plot.rear_notches.length === input.site.plot_outline?.rear_notches?.length &&
    generation.site_plot.rear_notches.every((cut, i) =>
      cut.side === input.site.plot_outline.rear_notches[i].side &&
      near(cut.width, input.site.plot_outline.rear_notches[i].width) &&
      near(cut.depth, input.site.plot_outline.rear_notches[i].depth)) &&
    generation.site_approach?.shape === input.site.front_approach?.shape,
  'El resultado no ofrece geometría v8 íntegra para documentar.');
  for (const p of generation.site_plot.vertices) {
    ensure(finite(p.x) && finite(p.y) && p.x >= 0 && p.y >= 0 && p.x <= width && p.y <= depth);
  }
  ensure(near(Math.max(...generation.site_plot.vertices.map((p) => p.x)), width) &&
    near(Math.max(...generation.site_plot.vertices.map((p) => p.y)), depth) &&
    new Set(alt.rooms.map((room) => room.id)).size === alt.rooms.length,
  'El croquis o sus locales no corresponden al encargo vigente.');
  const footprint = [
    ...alt.wall_zones,
    ...alt.corridor_usable_segments,
    ...alt.rooms.map((room) => room.usable_rect),
  ].map((r) => checkedRect(r, width, depth));
  checkedRect(alt.corridor, width, depth);
  checkedRect(alt.entrance?.opening, width, depth);
  ensure(alt.rooms.every((room) => {
    if (typeof room.id !== 'string' || !/^(living-dining|kitchen|bedroom-[1-4]|bathroom-[1-2])$/.test(room.id) ||
        typeof room.label !== 'string' || room.label.length > 40 ||
        !['living_dining', 'kitchen', 'bedroom', 'bathroom'].includes(room.type) ||
        !['left', 'right'].includes(room.side) ||
        !finite(room.usable_area) || room.usable_area <= 0 ||
        !Array.isArray(room.furnishings) || room.furnishings.length > 8) return false;
    checkedRect(room.usable_rect, width, depth);
    checkedRect(room.door?.opening, width, depth);
    if (!near(room.usable_rect.width * room.usable_rect.depth, room.usable_area)) return false;
    if (room.window) checkedRect(room.window.opening, width, depth);
    for (const item of room.furnishings) checkedRect(item.footprint, width, depth);
    return true;
  }), 'Uno de los locales carece de geometría o área validada.');
  for (const rect of input.site.reserved_areas || []) checkedRect(rect, width, depth);
  for (const rect of alt.front_approach?.segments || []) checkedRect(rect, width, depth);
  ensure([alt.built_area, alt.usable_area, alt.wall_allowance_area, alt.circulation_usable_area].every(finite) &&
    near(alt.built_area, alt.usable_area + alt.wall_allowance_area) &&
    near(alt.usable_area, alt.circulation_usable_area + alt.rooms.reduce((n, r) => n + r.usable_area, 0)),
  'El cuadro de áreas no coincide con la alternativa de Rust.');
  const envelope = extractPlanEnvelope(alt, front); // area, continuity and every exterior opening verified
  return { input, generation, alt, width, depth, front, envelope, box: bounds(footprint) };
}

function paperTransform(box) {
  const denominator = SCALES.find((n) => box.width * 1000 / n <= VIEW.width &&
    box.depth * 1000 / n <= VIEW.height);
  ensure(denominator, 'El croquis no cabe en una hoja A3 a las escalas disponibles.');
  const unit = 1000 / denominator; // millimetres on the paper per metre of the 2D model.
  const x = VIEW.x + (VIEW.width - box.width * unit) / 2;
  const y = VIEW.y + (VIEW.height - box.depth * unit) / 2;
  return {
    denominator, unit,
    X: (m) => x + (m - box.x) * unit,
    Y: (m) => y + (m - box.y) * unit,
    minX: x, minY: y, maxX: x + box.width * unit, maxY: y + box.depth * unit,
  };
}

function text(x, y, value, size = 3.1, color = '#253a40', extra = '') {
  return `<text x="${fmt(x)}" y="${fmt(y)}" font-family="Arial,DejaVu Sans,sans-serif" font-size="${size}" fill="${color}" ${extra}>${xml(value)}</text>`;
}
function line(x1, y1, x2, y2, color = '#789097', width = 0.23, extra = '') {
  return `<line x1="${fmt(x1)}" y1="${fmt(y1)}" x2="${fmt(x2)}" y2="${fmt(y2)}" stroke="${color}" stroke-width="${width}" ${extra}/>`;
}
function rect(r, t, fill, stroke = 'none', sw = 0.25, extra = '') {
  return `<rect x="${fmt(t.X(r.x))}" y="${fmt(t.Y(r.y))}" width="${fmt(r.width * t.unit)}" height="${fmt(r.depth * t.unit)}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" ${extra}/>`;
}

function compass(front) {
  const direction = { N: [0, -1], E: [-1, 0], S: [0, 1], W: [1, 0] }[front];
  const angle = { N: 0, E: 270, S: 180, W: 90 }[front];
  const x = 263, y = 62;
  return `<circle cx="${x}" cy="${y}" r="10" fill="#fff" stroke="#b8c6c2" stroke-width="0.3"/>` +
    `<g transform="translate(${x} ${y}) rotate(${angle})"><path d="M0 -7 L-2 4 L0 2 L2 4 Z" fill="#234e4b"/><circle r="0.7" fill="#234e4b"/></g>` +
    text(x + direction[0] * 9.4, y + direction[1] * 9.4 + 0.9, 'N', 2.6, '#234e4b', 'text-anchor="middle"');
}

function scaleBar(t) {
  const metres = t.denominator <= 100 ? 5 : t.denominator <= 500 ? 10 : 50;
  const segment = metres * t.unit / 2;
  const x = 23, y = 329;
  return `<rect x="${x}" y="${y}" width="${fmt(segment)}" height="2.2" fill="#253a40"/>` +
    `<rect x="${fmt(x + segment)}" y="${y}" width="${fmt(segment)}" height="2.2" fill="#fff" stroke="#253a40" stroke-width="0.2"/>` +
    text(x, y - 1.2, '0', 2.45) + text(x + segment, y - 1.2, `${metres / 2}`, 2.45, '#253a40', 'text-anchor="middle"') +
    text(x + segment * 2, y - 1.2, `${metres} m`, 2.45, '#253a40', 'text-anchor="end"');
}

function header(code, title, subtitle) {
  return `<rect width="297" height="420" fill="#fff"/>` +
    `<rect x="0" y="0" width="297" height="7" fill="#1d3940"/>` +
    `<rect x="16" y="15" width="28" height="25" fill="#c9e1d5"/>` +
    text(30, 31, 'AG', 11, '#173d39', 'font-weight="700" text-anchor="middle"') +
    text(52, 19, 'ARQ GEN  /  DOSSIER DE ANTEPROYECTO', 3.5, '#648179', 'font-weight="700" letter-spacing="0.8"') +
    text(52, 31, `${code}   ${title}`, 7.0, '#1e363d', 'font-weight="700"') +
    text(52, 39, subtitle, 3.05, '#566d70') +
    `<rect x="${FRAME.x}" y="${FRAME.y}" width="${FRAME.width}" height="${FRAME.height}" fill="#fcfdfb" stroke="#b5c7bf" stroke-width="0.35"/>`;
}

function areaSchedule(d) {
  const { alt } = d;
  let out = `<rect x="16" y="342" width="265" height="47" fill="#f3f7f5"/>` +
    text(22, 348, 'LOCALES · SUPERFICIE ÚTIL DEL CROQUIS', 3.2, '#2b5c52', 'font-weight="700"');
  const order = { living_dining: 0, kitchen: 1, bedroom: 2, bathroom: 3 };
  const rooms = [...alt.rooms].sort((a, b) => order[a.type] - order[b.type] || a.id.localeCompare(b.id));
  for (const [i, room] of rooms.entries()) {
    const y = 353.5 + i * 4.85;
    out += text(23, y, `${room.label}  ·  ${room.id}`, 2.8, '#24393e') +
      text(160, y, `${fmt(room.usable_area)} m²`, 2.8, '#24393e', 'text-anchor="end"');
  }
  out += line(169, 344, 169, 387, '#ceded7', 0.28) +
    text(177, 348, 'ÁREAS DE RUST · NO CATASTRALES', 3.0, '#2b5c52', 'font-weight="700"');
  const rows = [
    ['Huella bruta', alt.built_area], ['Útil total', alt.usable_area],
    ['Muros · previsión', alt.wall_allowance_area], ['Circulación útil', alt.circulation_usable_area],
  ];
  rows.forEach(([name, value], i) => {
    const y = 356 + i * 6.5;
    out += text(177, y, name, 2.9) + text(273, y, `${fmt(value)} m²`, 2.95, '#1e4b45', 'text-anchor="end" font-weight="700"');
  });
  return out;
}

function footer(d, code, t) {
  return `<rect x="16" y="392" width="265" height="24" fill="#1d3940"/>` +
    text(22, 399, `${code}   |   1:${t.denominator} nominal en A3`, 3.4, '#f0f6f1', 'font-weight="700"') +
    text(275, 399, `SEED ${d.input.seed} · ${d.generation.input_hash}`, 2.75, '#b9ded2', 'text-anchor="end"') +
    text(22, 405.7, `ALTERNATIVA ${d.alt.id}`, 2.7, '#d4e8df') +
    text(22, 412.2, 'NO APTO PARA OBRA · SIN NORMA CUBANA VERIFICADA · SIN ACCESO NI VENTILACIÓN COMPROBADOS · IMPRESIÓN 100%', 2.35, '#ffd2bc');
}

function titleNote(message) {
  return text(22, 323, message, 2.55, '#647b72');
}

function dimensions(t, box, site = false) {
  const { minX: left, minY: top, maxX: right, maxY: bottom } = t;
  const y = top - 9, x = left - 9;
  let out = line(left, top - 1, left, y - 3) + line(right, top - 1, right, y - 3) +
    line(left, y, right, y, '#405a60', 0.28) +
    line(left, y - 1.5, left, y + 1.5, '#405a60', 0.28) +
    line(right, y - 1.5, right, y + 1.5, '#405a60', 0.28) +
    text((left + right) / 2, y - 1.65, `${fmt(box.width)} m${site ? ' · parcela declarada' : ' · ext. huella'}`, 2.65, '#284950', 'text-anchor="middle"');
  out += line(left - 1, top, x - 3, top) + line(left - 1, bottom, x - 3, bottom) +
    line(x, top, x, bottom, '#405a60', 0.28) +
    line(x - 1.5, top, x + 1.5, top, '#405a60', 0.28) +
    line(x - 1.5, bottom, x + 1.5, bottom, '#405a60', 0.28) +
    `<text x="${fmt(x - 1.6)}" y="${fmt((top + bottom) / 2)}" text-anchor="middle" transform="rotate(-90 ${fmt(x - 1.6)} ${fmt((top + bottom) / 2)})" font-family="Arial,sans-serif" font-size="2.65" fill="#284950">${fmt(box.depth)} m${site ? ' · parcela' : ' · ext. huella'}</text>`;
  return out;
}

function polygonPath(vertices, t) {
  return vertices.map((p, i) => `${i ? 'L' : 'M'} ${fmt(t.X(p.x))} ${fmt(t.Y(p.y))}`).join(' ') + ' Z';
}

function siteSheet(d) {
  const box = { x: 0, y: 0, width: d.width, depth: d.depth };
  const t = paperTransform(box);
  let out = header('A-01', 'EMPLAZAMIENTO', 'Contorno y aproximación declarados · vivienda unifamiliar · una planta') +
    `<path d="${polygonPath(d.generation.site_plot.vertices, t)}" fill="#ebf2e9" stroke="#436860" stroke-width="0.75" stroke-dasharray="1.2 0.7"/>`;
  // One exact continuous gross outline: no bounding rectangle or antialias
  // seams between source cells, and its area is checked against Rust.
  out += `<path d="${polygonPath(d.envelope.footprint.vertices, t)}" fill="#49695a"/>`;
  for (const reservation of d.input.site.reserved_areas) {
    out += rect(reservation, t, '#e9bb9e', '#ab603e', 0.3, 'stroke-dasharray="1 0.5"');
  }
  for (const band of d.alt.front_approach.segments) {
    out += rect(band, t, '#cce2de', '#467f75', 0.35, 'stroke-dasharray="1.5 0.8"');
  }
  out += dimensions(t, box, true) + compass(d.front) + scaleBar(t) +
    titleNote('HUELLA OSCURA: geometría bruta · NARANJA: reservas declaradas · VERDE CLARO: trazado 2D') +
    areaSchedule(d) + footer(d, 'A-01', t);
  return { svg: wrapSvg(d, 'A-01', out), denominator: t.denominator };
}

function roomColor(type, furnished) {
  if (!furnished) return '#fffefb';
  return { living_dining: '#e1eee5', kitchen: '#e3f0ed', bedroom: '#f1ecdf', bathroom: '#e6eff2' }[type];
}

function doorMarks(d, t) {
  let out = '';
  for (const room of d.alt.rooms) {
    const door = room.door;
    out += rect(door.opening, t, '#fffefb');
    const hinge = room.side === 'left' ? room.usable_rect.x + room.usable_rect.width : room.usable_rect.x;
    const end = hinge + (room.side === 'left' ? -door.width : door.width);
    const centerY = door.y;
    const hingeY = centerY - door.width / 2;
    const radius = door.width * t.unit;
    out += `<path d="M ${fmt(t.X(hinge))} ${fmt(t.Y(centerY + door.width / 2))} A ${fmt(radius)} ${fmt(radius)} 0 0 ${room.side === 'left' ? 1 : 0} ${fmt(t.X(end))} ${fmt(t.Y(hingeY))}" fill="none" stroke="#a27a55" stroke-width="0.23"/>` +
      line(t.X(hinge), t.Y(hingeY), t.X(end), t.Y(hingeY), '#a27a55', 0.3);
  }
  const door = d.alt.entrance;
  out += rect(door.opening, t, '#fffefb');
  const hx = door.opening.x;
  const hy = door.swing.y;
  const r = door.width * t.unit;
  out += `<path d="M ${fmt(t.X(door.opening.x + door.opening.width))} ${fmt(t.Y(hy))} A ${fmt(r)} ${fmt(r)} 0 0 1 ${fmt(t.X(hx))} ${fmt(t.Y(hy + door.width))}" fill="none" stroke="#a27a55" stroke-width="0.23"/>` +
    line(t.X(hx), t.Y(hy), t.X(hx), t.Y(hy + door.width), '#a27a55', 0.3);
  for (const room of d.alt.rooms) {
    if (room.window) out += rect(room.window.opening, t, '#9dd2d1', '#287780', 0.4);
  }
  return out;
}

function furniture(d, t) {
  let out = '';
  for (const room of d.alt.rooms) {
    for (const item of room.furnishings) {
      const r = item.footprint;
      out += rect(r, t, '#fff8ea', '#998b72', 0.3, 'rx="0.9"');
      if (item.type === 'bed' || item.type === 'dining_table' || item.type === 'sofa') {
        out += line(t.X(r.x + r.width * 0.15), t.Y(r.y + r.depth * 0.26),
          t.X(r.x + r.width * 0.85), t.Y(r.y + r.depth * 0.26), '#ae9c7d', 0.23);
      } else if (item.type === 'shower' || item.type === 'basin' || item.type === 'toilet') {
        out += `<ellipse cx="${fmt(t.X(r.x + r.width / 2))}" cy="${fmt(t.Y(r.y + r.depth / 2))}" rx="${fmt(Math.min(r.width * t.unit * 0.28, 4))}" ry="${fmt(Math.min(r.depth * t.unit * 0.28, 4))}" fill="none" stroke="#ae9c7d" stroke-width="0.22"/>`;
      }
    }
  }
  return out;
}

function partialRoomDimensions(d, t) {
  let out = '';
  // Each segment is the clear-room depth from Rust; never suggest these are
  // facade axes, wall centre lines or a continuous chain if gaps exist.
  for (const room of d.alt.rooms) {
    const r = room.usable_rect;
    const x = room.side === 'left' ? t.minX - 5 : t.maxX + 5;
    const y1 = t.Y(r.y), y2 = t.Y(r.y + r.depth);
    if (y2 - y1 < 9) continue;
    out += line(x, y1, x, y2, '#7b9798', 0.22) +
      line(x - 1.3, y1, x + 1.3, y1) + line(x - 1.3, y2, x + 1.3, y2) +
      `<text x="${fmt(x + (room.side === 'left' ? -1 : 1) * 1.5)}" y="${fmt((y1 + y2) / 2)}" text-anchor="middle" transform="rotate(-90 ${fmt(x + (room.side === 'left' ? -1 : 1) * 1.5)} ${fmt((y1 + y2) / 2)})" font-family="Arial,sans-serif" font-size="2.2" fill="#456a6b">${fmt(r.depth)} m</text>`;
  }
  return out;
}

function planSheet(d, furnished, dimensioned) {
  const code = dimensioned ? 'A-03' : 'A-02';
  const title = dimensioned ? 'PLANTA · COTAS ESQUEMÁTICAS' : 'PLANTA · AMUEBLADA';
  const t = paperTransform(d.box);
  let out = header(code, title, `Alternativa: ${d.alt.label} · geometría de Rust · nivel único sin cotas de altura`);
  // Same numeric wall, room, opening and furniture coordinates in every view.
  for (const zone of d.alt.wall_zones) out += rect(zone, t, '#273d40');
  for (const zone of d.alt.corridor_usable_segments) out += rect(zone, t, '#e9f0eb');
  for (const room of d.alt.rooms) out += rect(room.usable_rect, t, roomColor(room.type, furnished), '#839b91', 0.2, `data-room-id="${xml(room.id)}"`);
  if (furnished) out += furniture(d, t);
  out += doorMarks(d, t);
  for (const room of d.alt.rooms) {
    const r = room.usable_rect;
    const x = t.X(r.x + r.width / 2), y = t.Y(r.y + r.depth / 2);
    if (r.width * t.unit < 17 || r.depth * t.unit < 10) continue;
    // A light backing keeps labels legible over schematic equipment, without
    // moving any fixture or misrepresenting an illustrated clearance.
    out += `<rect x="${fmt(x - 13)}" y="${fmt(y - (dimensioned ? 5.5 : 3.7))}" width="26" height="${dimensioned ? '11' : '7.4'}" rx="1" fill="#fff" fill-opacity="0.90"/>` +
      text(x, y - (dimensioned ? 1.45 : 0.55), room.label, 2.65, '#233d3c', 'font-weight="700" text-anchor="middle"') +
      text(x, y + (dimensioned ? 2.35 : 2.2),
        dimensioned ? `${fmt(r.width)} × ${fmt(r.depth)} m · ${fmt(room.usable_area)} m²` : `${fmt(room.usable_area)} m²`,
        dimensioned ? 1.95 : 2.35, '#42625d', 'text-anchor="middle"');
  }
  if (dimensioned) out += dimensions(t, d.box) + partialRoomDimensions(d, t);
  out += compass(d.front) + scaleBar(t) +
    titleNote(dimensioned
      ? 'COTAS ÚTILES DE LOCALES Y EXTENSIÓN DE HUELLA · NO MEDIDAS DE EJES O FACHADAS REALES'
      : 'ESTANCIAS Y MUEBLES ILUSTRATIVOS · HUECOS, GIROS Y MUROS DEL MISMO CANDIDATO RUST') +
    areaSchedule(d) + footer(d, code, t);
  return { svg: wrapSvg(d, code, out), denominator: t.denominator };
}

function envelopeSheet(d) {
  const code = 'A-04';
  const t = paperTransform(d.box);
  const { footprint, perimeter_openings: openings } = d.envelope;
  ensure(openings.length <= 9, 'Demasiados vanos para el índice de A-04: dividir antes de documentar.');
  let out = header(code, 'ENVOLVENTE · PLANTA 2D',
    'Perímetro bruto y vanos dibujados · NO es alzado, corte ni fachada verificada') +
    `<path d="${polygonPath(footprint.vertices, t)}" fill="#e9f1ed" stroke="#294f4c" stroke-width="0.75"/>`;
  // Segment lengths and IDs come from the one measured 2D polygon, never its
  // bounding box. Short returns are still in the JSON, but not squeezed into
  // misleading or illegible dimension text on the paper.
  for (const edge of footprint.sides) {
    const distance = edge.length_m * t.unit;
    if (distance < 16) continue;
    const x = (t.X(edge.from.x) + t.X(edge.to.x)) / 2;
    const y = (t.Y(edge.from.y) + t.Y(edge.to.y)) / 2;
    const label = `${edge.id} · ${fmt(edge.length_m)} m`;
    if (edge.plan_side === 'top' || edge.plan_side === 'bottom') {
      const labelY = edge.plan_side === 'top' ? y - 4.1
        : y + 5.4 <= VIEW.y + VIEW.height - 2 ? y + 5.4 : y - 2.7;
      out += text(x, labelY, label, 2.55, '#32675d',
        'font-weight="700" text-anchor="middle"');
    } else {
      const lx = x + (edge.plan_side === 'left' ? -4.4 : 5.1);
      out += `<text x="${fmt(lx)}" y="${fmt(y)}" transform="rotate(-90 ${fmt(lx)} ${fmt(y)})" ` +
        `text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="2.55" fill="#32675d">${xml(label)}</text>`;
    }
  }
  for (const opening of openings) {
    const color = opening.kind === 'entrada_2d' ? '#bc734e' : '#288899';
    out += line(t.X(opening.from.x), t.Y(opening.from.y), t.X(opening.to.x),
      t.Y(opening.to.y), color, 1.3);
  }
  out += compass(d.front) + scaleBar(t) +
    titleNote('CONTORNO BRUTO VALIDADO · AZUL: VENTANA 2D · NARANJA: PUERTA · SIN COTAS Z') +
    `<rect x="16" y="342" width="265" height="47" fill="#f3f7f5"/>` +
    text(22, 348, 'VANOS DIBUJADOS SOBRE EL PERÍMETRO · EN PLANTA', 3, '#2b5c52', 'font-weight="700"') +
    text(274, 348, `P=${fmt(footprint.perimeter_m)} m · A=${fmt(footprint.gross_area_m2)} m²`,
      2.85, '#255e54', 'text-anchor="end" font-weight="700"') +
    line(169, 344, 169, 387, '#ceded7', 0.28);
  openings.forEach((opening, i) => {
    const y = 353.5 + i * 3.7;
    out += text(22, y, `${opening.id} · ${opening.room_id || 'Entrada desde frente declarado'}`, 2.55) +
      text(175, y, `${opening.segment_id} · ${opening.world_orientation_declared}`, 2.6) +
      text(272, y, `${fmt(opening.span_m)} m en planta`, 2.6, '#1e4b45',
        'text-anchor="end" font-weight="700"');
  });
  out += footer(d, code, t);
  return { svg: wrapSvg(d, code, out), denominator: t.denominator };
}

function wrapSvg(d, code, inner) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${PAPER.width}mm" height="${PAPER.height}mm" viewBox="0 0 ${PAPER.width} ${PAPER.height}" role="img" aria-label="${xml(code)} · plano conceptual ARQ GEN, NO APTO PARA OBRA" data-package-format="${drawingPackageFormat}" data-engine-hash="${xml(d.generation.input_hash)}" data-candidate-id="${xml(d.alt.id)}">${inner}</svg>`;
}

export function buildDrawingPackage(input, generation, index) {
  const d = verifiedDrawing(input, generation, index);
  const sheets = [
    { number: 'A-01', title: 'Emplazamiento declarado', filename: 'A-01-emplazamiento.svg', ...siteSheet(d) },
    { number: 'A-02', title: 'Planta amueblada', filename: 'A-02-planta-amueblada.svg', ...planSheet(d, true, false) },
    { number: 'A-03', title: 'Planta con cotas esquemáticas', filename: 'A-03-planta-cotas.svg', ...planSheet(d, false, true) },
    { number: 'A-04', title: 'Envolvente y vanos 2D', filename: 'A-04-envolvente-2d.svg', ...envelopeSheet(d) },
  ];
  const manifest = {
    format: drawingPackageFormat,
    engine_version: generation.engine_version,
    request_schema: input.request_schema,
    input_hash: generation.input_hash,
    candidate_id: d.alt.id,
    seed: input.seed,
    model: 'single_floor_housing_schematic',
    units: 'metres_in_model_mm_on_A3_paper',
    sheets: sheets.map((s) => ({ number: s.number, title: s.title, filename: s.filename,
      paper: 'ISO_A3_portrait_297x420mm', nominal_scale: `1:${s.denominator}` })),
    spatial_model: { filename: 'nivel-0-2d.json', format: d.envelope.format,
      floor_index: 0, elevation_m: null, status: 'derived_from_rust_v8_plan_not_replayable_alone' },
    excluded_not_modelled: ['multi_floor', 'sections', 'elevations', 'roof', 'height', 'hospital', 'hotel',
      'real_access', 'delivered_ventilation', 'cuban_regulatory_compliance'],
    status: 'illustrative_not_certified',
  };
  const readme = [
    'ARQ GEN · LÁMINAS CONCEPTUALES SVG · NO APTO PARA OBRA',
    `Alternativa ${d.alt.id} · huella ${fmt(d.alt.built_area)} m² · semilla ${input.seed}.`,
    '',
    'Cuatro hojas ISO A3 vertical: A-01 emplazamiento, A-02 planta amueblada, A-03 cotas esquemáticas y A-04 envolvente/vanos 2D.',
    'Todas las vistas usan el mismo candidato validado por Rust; no son cuatro alternativas arquitectónicas.',
    'nivel-0-2d.json deriva el perímetro y vanos del plan Rust, sin alturas, niveles adicionales, fachadas ni cubierta.',
    'Las cotas proceden de rectángulos útiles, extensión y contorno bruto del croquis; NO son levantamiento ni plano para obra.',
    'Abrir/ imprimir a tamaño A3 al 100%; el visor o impresora puede cambiar la escala. Comprobar dimensiones antes de cualquier uso.',
    'origen-v8.json se puede importar en ARQ GEN para volver a ejecutar la entrada en Rust antes de adoptarla.',
    'No hay varias plantas, cortes, fachadas ni cubierta porque faltan niveles y alturas modelados.',
    'Hospital y hotel son tipologías FUTURAS; estas láminas son únicamente de vivienda esquemática.',
    'Sin norma cubana verificada, linderos, derechos de acceso, ventilación efectiva ni QA Windows. NO APTO PARA OBRA.',
    '',
  ].join('\n');
  const archive = Object.fromEntries([
    ...sheets.map((s) => [s.filename, s.svg]),
    ['nivel-0-2d.json', JSON.stringify(d.envelope, null, 2)],
    ['manifest.json', JSON.stringify(manifest, null, 2)],
    ['origen-v8.json', JSON.stringify({ input, generation, selection: null }, null, 2)],
    ['LEEME-ANTES-DE-USAR.txt', readme],
  ].map(([name, contents]) => [name, [strToU8(contents), { mtime: FIXED_MTIME }]]));
  const bytes = zipSync(archive, { level: 6 });
  ensure(bytes.length < 2_000_000, 'El paquete documental excede el límite local de 2 MB.');
  return { filename: `arqgen-laminas-CONCEPTUAL-${d.alt.id}.zip`, bytes, sheets, manifest, envelope: d.envelope };
}
