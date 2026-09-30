// Versioned 2D intermediate geometry derived from validated Rust v8 cells.
// This is NOT a floor-elevation model: z, storey heights, sills and roof are
// unknown. Refuse holes, detached parts, overlapping cells or dangling vanos.
export const planEnvelopeFormat = 'arqgen-plan-envelope-2d-v1';
const EPS = 1e-7;

function requireGeometry(ok, reason) {
  if (!ok) throw new Error(`Envolvente 2D no verificable: ${reason}`);
}
const finite = (n) => typeof n === 'number' && Number.isFinite(n);
const near = (a, b) => Math.abs(a - b) <= EPS;
const key = (p) => `${p[0]},${p[1]}`;

function axes(coordinates) {
  const sorted = coordinates.sort((a, b) => a - b);
  const result = [];
  for (const coordinate of sorted) {
    if (!result.length || !near(coordinate, result.at(-1))) result.push(coordinate);
  }
  requireGeometry(result.length >= 2 && result.length <= 128, 'demasiados ejes para una huella simple.');
  return result;
}

function point(i, j, xs, ys) { return { x: xs[i], y: ys[j] }; }
function signedArea(vertices) {
  return vertices.reduce((sum, p, i) => {
    const q = vertices[(i + 1) % vertices.length];
    return sum + p.x * q.y - q.x * p.y;
  }, 0) / 2;
}
function straight(a, b, c) {
  return (near(a.x, b.x) && near(b.x, c.x) && (b.y - a.y) * (c.y - b.y) > 0) ||
    (near(a.y, b.y) && near(b.y, c.y) && (b.x - a.x) * (c.x - b.x) > 0);
}

// Merge the exact gross planning cells into ONE oriented orthogonal boundary.
// A grid split at every source rectangle edge makes partial/shared edges
// explicit; no bounding box or guessed shape can replace this union.
export function outlineRectUnion(rectangles, expectedArea) {
  requireGeometry(Array.isArray(rectangles) && rectangles.length > 0 && rectangles.length <= 300 &&
    finite(expectedArea) && expectedArea > 0, 'celdas o superficie bruta inválidas.');
  for (const r of rectangles) {
    requireGeometry(r && [r.x, r.y, r.width, r.depth].every(finite) &&
      r.x >= 0 && r.y >= 0 && r.width > EPS && r.depth > EPS &&
      r.x + r.width <= 200 + EPS && r.y + r.depth <= 200 + EPS, 'celda bruta inválida.');
  }
  const xs = axes(rectangles.flatMap((r) => [r.x, r.x + r.width]));
  const ys = axes(rectangles.flatMap((r) => [r.y, r.y + r.depth]));
  const nx = xs.length - 1, ny = ys.length - 1;
  requireGeometry(nx * ny <= 12000, 'rejilla excesiva; no se dibujó un perímetro.');
  const occupied = new Uint8Array(nx * ny);
  const index = (i, j) => j * nx + i;
  const axisIndex = (axis, coordinate) => {
    const found = axis.findIndex((n) => near(n, coordinate));
    requireGeometry(found !== -1, 'límite de celda inconsistente.');
    return found;
  };
  for (const r of rectangles) {
    const left = axisIndex(xs, r.x), right = axisIndex(xs, r.x + r.width);
    const top = axisIndex(ys, r.y), bottom = axisIndex(ys, r.y + r.depth);
    requireGeometry(left < right && top < bottom, 'celda degenerada después de ajustar ejes.');
    for (let j = top; j < bottom; j++) {
      for (let i = left; i < right; i++) {
        requireGeometry(!occupied[index(i, j)], 'celdas brutas solapadas.');
        occupied[index(i, j)] = 1;
      }
    }
  }
  let gridArea = 0;
  const exposed = [];
  const push = (from, to) => exposed.push({ from, to });
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      if (!occupied[index(i, j)]) continue;
      gridArea += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j]);
      if (j === 0 || !occupied[index(i, j - 1)]) push([i, j], [i + 1, j]);
      if (i === nx - 1 || !occupied[index(i + 1, j)]) push([i + 1, j], [i + 1, j + 1]);
      if (j === ny - 1 || !occupied[index(i, j + 1)]) push([i + 1, j + 1], [i, j + 1]);
      if (i === 0 || !occupied[index(i - 1, j)]) push([i, j + 1], [i, j]);
    }
  }
  requireGeometry(exposed.length >= 4, 'contorno vacío.');
  const outgoing = new Map();
  for (const edge of exposed) {
    requireGeometry(!outgoing.has(key(edge.from)), 'contacto por un punto o vértice ambiguo.');
    outgoing.set(key(edge.from), edge);
  }
  // Start at the top-left exterior corner and walk clockwise (y points down).
  const first = [...outgoing.keys()].map((k) => k.split(',').map(Number))
    .sort((a, b) => a[1] - b[1] || a[0] - b[0])[0];
  const visited = new Set();
  const raw = [];
  let position = first;
  do {
    const edge = outgoing.get(key(position));
    requireGeometry(edge && !visited.has(key(position)), 'perímetro interrumpido o ramificado.');
    raw.push(point(...position, xs, ys));
    visited.add(key(position));
    position = edge.to;
    requireGeometry(raw.length <= exposed.length, 'perímetro sin cierre.');
  } while (key(position) !== key(first));
  requireGeometry(visited.size === exposed.length,
    'hay huecos, patios o cuerpos separados: se necesita un modelo de varios contornos.');
  const vertices = raw.filter((p, i) => !straight(raw[(i + raw.length - 1) % raw.length], p,
    raw[(i + 1) % raw.length]));
  requireGeometry(vertices.length >= 4 && vertices.length <= 96, 'contorno simplificado inválido.');
  const area = signedArea(vertices);
  const tolerance = Math.max(1e-5, expectedArea * 1e-7);
  requireGeometry(area > 0 && Math.abs(area - gridArea) <= tolerance &&
    Math.abs(area - expectedArea) <= tolerance,
  `superficie bruta incoherente: perímetro ${area.toFixed(3)} m², Rust ${expectedArea.toFixed(3)} m².`);
  const sides = [];
  for (let i = 0; i < vertices.length; i++) {
    const from = vertices[i], to = vertices[(i + 1) % vertices.length];
    const side = near(from.y, to.y) ? (to.x > from.x ? 'top' : 'bottom')
      : near(from.x, to.x) ? (to.y > from.y ? 'right' : 'left') : null;
    requireGeometry(Boolean(side) && near(from.x, to.x) !== near(from.y, to.y), 'borde no ortogonal.');
    sides.push({ id: `P${String(i + 1).padStart(2, '0')}`, from, to,
      plan_side: side, length_m: Math.abs(to.x - from.x) + Math.abs(to.y - from.y) });
  }
  return { vertices, sides, gross_area_m2: area,
    perimeter_m: sides.reduce((sum, edge) => sum + edge.length_m, 0) };
}

const worldFace = (front, planSide) => {
  const directions = ['N', 'E', 'S', 'W'];
  const index = directions.indexOf(front);
  requireGeometry(index !== -1, 'orientación del frente desconocida.');
  const offset = { top: 0, right: 1, bottom: 2, left: 3 }[planSide];
  return directions[(index + offset) % 4];
};

// A span must lie on ONE measured boundary side. It is not an elevation:
// the given Rust window.height has no sill/head elevation or verified glazing.
function boundaryOpening(boundary, { id, roomId, kind, opening, width, planSide, front, direction }) {
  requireGeometry(opening && [opening.x, opening.y, opening.width, opening.depth, width].every(finite) &&
    width > EPS && ['top', 'right', 'bottom', 'left'].includes(planSide), `vano ${id} inválido.`);
  const face = planSide === 'top' ? opening.y : planSide === 'bottom' ? opening.y + opening.depth
    : planSide === 'left' ? opening.x : opening.x + opening.width;
  const start = ['left', 'right'].includes(planSide) ? opening.y : opening.x;
  const span = ['left', 'right'].includes(planSide) ? opening.depth : opening.width;
  requireGeometry(near(span, width) && (!direction || direction === worldFace(front, planSide)),
    `orientación/ancho del vano ${id} no coinciden con Rust.`);
  const segment = boundary.sides.find((edge) => edge.plan_side === planSide &&
    near(['top', 'bottom'].includes(planSide) ? edge.from.y : edge.from.x, face) &&
    // Compare along the varying axis; the other is constant on this edge.
    start >= (['top', 'bottom'].includes(planSide) ? Math.min(edge.from.x, edge.to.x) : Math.min(edge.from.y, edge.to.y)) - EPS &&
    start + span <= (['top', 'bottom'].includes(planSide) ? Math.max(edge.from.x, edge.to.x) : Math.max(edge.from.y, edge.to.y)) + EPS);
  requireGeometry(segment, `vano ${id} no pertenece al contorno bruto exterior.`);
  const forward = planSide === 'top' || planSide === 'right';
  const offset = forward ? start - (['top', 'bottom'].includes(planSide) ? segment.from.x : segment.from.y)
    : (['top', 'bottom'].includes(planSide) ? segment.from.x : segment.from.y) - (start + span);
  requireGeometry(offset >= -EPS && offset + span <= segment.length_m + EPS,
    `vano ${id} rebasa un quiebro de la huella.`);
  const along = (distance) => ['top', 'bottom'].includes(planSide)
    ? { x: segment.from.x + (planSide === 'top' ? 1 : -1) * distance, y: segment.from.y }
    : { x: segment.from.x, y: segment.from.y + (planSide === 'right' ? 1 : -1) * distance };
  return { id, kind, room_id: roomId, segment_id: segment.id, plan_side: planSide,
    world_orientation_declared: worldFace(front, planSide), offset_m: offset,
    span_m: span, from: along(offset), to: along(offset + span) };
}

export function extractPlanEnvelope(alt, front) {
  requireGeometry(alt && typeof alt.id === 'string' && Array.isArray(alt.wall_zones) &&
    Array.isArray(alt.corridor_usable_segments) && Array.isArray(alt.rooms),
  'la alternativa no contiene las celdas brutas v8.');
  const boundary = outlineRectUnion([
    ...alt.wall_zones, ...alt.corridor_usable_segments,
    ...alt.rooms.map((r) => r.usable_rect),
  ], alt.built_area);
  requireGeometry(alt.corridor && alt.entrance?.opening &&
    [alt.corridor.x, alt.corridor.y, alt.corridor.width, alt.entrance.opening.y].every(finite) &&
    near(alt.corridor.y, alt.entrance.opening.y) &&
    alt.entrance.opening.x >= alt.corridor.x - EPS &&
    alt.entrance.opening.x + alt.entrance.opening.width <= alt.corridor.x + alt.corridor.width + EPS,
  'la entrada dibujada no desemboca en el corredor frontal.');
  const entrance = boundaryOpening(boundary, { id: 'D-ENT', roomId: null, kind: 'entrada_2d',
    opening: alt.entrance.opening, width: alt.entrance.width,
    planSide: 'top', front, direction: front });
  const windows = alt.rooms.filter((r) => r.window).map((room) => {
    const cell = room.rect, window = room.window, opening = window.opening;
    requireGeometry(['left', 'right'].includes(room.side) && cell && opening &&
      [cell.x, cell.y, cell.width, cell.depth, window.x, window.y, window.height].every(finite) &&
      window.height > EPS &&
      opening.y >= cell.y - EPS && opening.y + opening.depth <= cell.y + cell.depth + EPS &&
      near(room.side === 'left' ? opening.x : opening.x + opening.width,
        room.side === 'left' ? cell.x : cell.x + cell.width) &&
      near(window.x, room.side === 'left' ? cell.x : cell.x + cell.width) &&
      near(window.y, opening.y + window.width / 2),
    `ventana de ${room.id} separada de su propio local.`);
    return boundaryOpening(boundary, {
      id: `V-${room.id}`, roomId: room.id, kind: 'ventana_dibujada_2d',
      opening, width: window.width,
      planSide: room.side, front, direction: window.direction,
    });
  });
  const openings = [entrance, ...windows];
  for (const edge of boundary.sides) {
    const onEdge = openings.filter((opening) => opening.segment_id === edge.id)
      .sort((a, b) => a.offset_m - b.offset_m);
    for (let i = 1; i < onEdge.length; i++) {
      requireGeometry(onEdge[i].offset_m >= onEdge[i - 1].offset_m + onEdge[i - 1].span_m - EPS,
        'vanos solapados en el perímetro.');
    }
  }
  return {
    format: planEnvelopeFormat,
    source_candidate_id: alt.id,
    coordinate_system: 'xy_site_front_left_origin_metres_y_to_rear',
    level: { index: 0, elevation_m: null, status: 'single_level_plan_2d_only' },
    footprint: boundary,
    perimeter_openings: openings,
    not_modelled: ['other_levels', 'sills', 'heads', 'floor_elevations', 'roof', 'sections',
      'elevations', 'legal_facades', 'real_street_access'],
  };
}
