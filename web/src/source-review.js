// Read-only evidence from the CURRENT Rust result and a bibliographic inventory.
// Project context is a self-report, NOT proof of a standard's legal scope or
// edition. Never produce "complies", "fails" or a definitive "not applicable".
const citedByNc598 = ['NC 337:2004', 'NC 391-1:2004', 'NC 391-2:2004'];
const leadStatus = 'preview_only_official_edition_and_rights_unverified';

function referencesFrom(inventory) {
  if (inventory?.target_jurisdiction !== 'CU' ||
      inventory.status !== 'bibliographic_inventory_only_not_a_ruleset' ||
      !/^[0-9a-f]{40}$/.test(inventory.source_commit || '') ||
      !Array.isArray(inventory.documents) || !Array.isArray(inventory.external_leads) ||
      inventory.documents.some((document) => document.runtime_eligible !== false) ||
      inventory.external_leads.some((lead) => lead.runtime_eligible !== false)) {
    throw new Error('Inventario de fuentes incompatibles: no se puede hacer una lectura normativa.');
  }
  const copies = inventory.documents.filter((document) => document.printed_id === 'NC 598:2009');
  if (copies.length !== 1) throw new Error('La copia NC 598:2009 falta o está duplicada.');
  const copy = copies[0];
  if (copy.jurisdiction !== 'CU' || copy.target_use !== 'conditional_scope_review' ||
      !/^[0-9a-f]{64}$/.test(copy.sha256 || '')) {
    throw new Error('Falta la copia inventariada de NC 598:2009 con alcance condicional.');
  }
  const references = citedByNc598.map((id) => {
    const matches = inventory.external_leads.filter((lead) => lead.printed_id_claimed === id);
    if (matches.length !== 1) throw new Error(`Falta o se duplica la pista bibliográfica ${id}.`);
    const lead = matches[0];
    let url;
    try { url = new URL(lead.url); } catch { throw new Error(`Enlace externo inválido: ${id}.`); }
    if (lead.status !== leadStatus || lead.runtime_eligible !== false ||
        'file' in lead || 'sha256' in lead || 'pdf_pages' in lead ||
        url.protocol !== 'https:' || url.hostname !== 'es.scribd.com' ||
        url.username || url.password || url.port || url.search || url.hash ||
        !/^\/document\/\d+\/[\w-]+$/.test(url.pathname)) {
      throw new Error(`La pista ${id} no es una vista externa no verificada.`);
    }
    return { id, url: lead.url, status: 'third_party_preview_unverified' };
  });
  return { pdf: { id: copy.printed_id, sha256: copy.sha256, source_commit: inventory.source_commit }, references };
}

function drawnWindow(window) {
  return window && typeof window === 'object' && !Array.isArray(window) &&
    Number.isFinite(window.width) && window.width > 0 &&
    Number.isFinite(window.height) && window.height > 0 &&
    Number.isFinite(window.opening?.width) && window.opening.width > 0 &&
    Number.isFinite(window.opening?.depth) && window.opening.depth > 0;
}

function bathroomEvidence(input, result, alternative) {
  if (result.status === 'infeasible' && alternative === null) return null; // no plan, no observation
  if (result.status !== 'ok' || !result.alternatives?.includes(alternative) ||
      !Array.isArray(alternative?.rooms) || !Number.isSafeInteger(input.program?.bathrooms)) {
    throw new Error('No hay una alternativa actual de Rust para observar los huecos dibujados.');
  }
  const rooms = alternative.rooms.filter((room) => room.type === 'bathroom');
  if (rooms.length !== input.program.bathrooms) {
    throw new Error('El número de baños no coincide con el programa de la entrada.');
  }
  if (alternative.bathroom_ventilation_status !== 'not_evaluated' ||
      rooms.some((room) => room.ventilation_status !== 'not_evaluated' ||
        room.daylight_status !== 'not_evaluated')) {
    throw new Error('La luz natural o ventilación del resultado no corresponde al alcance no evaluado.');
  }
  const evidence = { total: rooms.length, without_window: [], with_drawn_window: [], unknown: [] };
  for (const room of rooms) {
    if (typeof room.id !== 'string' || !room.id) throw new Error('Baño sin identificador de Rust.');
    if (!Object.hasOwn(room, 'window')) evidence.unknown.push(room.id);
    else if (room.window === null && room.window_geometry_status === 'not_drawn') evidence.without_window.push(room.id);
    else if (drawnWindow(room.window) && room.window_geometry_status === 'exterior_opening_drawn_only') evidence.with_drawn_window.push(room.id);
    else evidence.unknown.push(room.id);
  }
  return evidence;
}

function keysAre(value, expected) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === expected.length && expected.every((field) => Object.hasOwn(value, field));
}

// Strictly positive common area; touching edges have zero overlap. Never
// replace this test with an EPS threshold for declared exclusions.
function intersectionArea(r, s) {
  return Math.max(0, Math.min(r.x + r.width, s.x + s.width) - Math.max(r.x, s.x)) *
    Math.max(0, Math.min(r.y + r.depth, s.y + s.depth) - Math.max(r.y, s.y));
}

// The core echoes a locally computed 2D outline; no polygon from a stored
// SVG or from a third-party PDF can become a surveyed boundary here.
function verifiedPlotSketch(input, result) {
  const source = input.site.plot_outline;
  const echo = result.site_plot;
  const w = input.site.width;
  const d = input.site.depth;
  if (!keysAre(source, ['provenance', 'shape', 'rear_notches']) ||
      !keysAre(echo, ['provenance', 'geometry_status', 'shape', 'rear_notches', 'vertices']) ||
      source.provenance !== 'user_sketch_unverified' || echo.provenance !== source.provenance ||
      echo.geometry_status !== 'orthogonal_plot_sketch_2d_only' ||
      echo.shape !== source.shape || !Number.isFinite(w) || w < 4 || w > 200 ||
      !Number.isFinite(d) || d < 4 || d > 200) {
    throw new Error('Contorno de parcela incompatible: croquis no verificado.');
  }
  const cuts = source.rear_notches;
  if (!Array.isArray(cuts) || cuts.length > 2 ||
      source.shape !== ['rectangle', 'rear_corner_notch', 'rear_both_corners_notched'][cuts.length] ||
      !Array.isArray(echo.rear_notches) || echo.rear_notches.length !== cuts.length ||
      cuts.some((cut, i) => !keysAre(cut, ['side', 'width', 'depth']) ||
        !keysAre(echo.rear_notches[i], ['side', 'width', 'depth']) ||
        !['left', 'right'].includes(cut.side) || echo.rear_notches[i].side !== cut.side ||
        !Number.isFinite(cut.width) || cut.width < 1 || cut.width > w - 1 ||
        !Number.isFinite(cut.depth) || cut.depth < 1 || cut.depth > d - 1 ||
        echo.rear_notches[i].width !== cut.width ||
        echo.rear_notches[i].depth !== cut.depth) ||
      (cuts.length === 2 && (cuts[0].side === cuts[1].side ||
        cuts[0].width + cuts[1].width > w - 1))) {
    throw new Error('Recortes posteriores incompatibles: esquinas distintas y franja central de 1 m ilustrativo requeridas.');
  }
  const left = cuts.find((cut) => cut.side === 'left');
  const right = cuts.find((cut) => cut.side === 'right');
  const vertices = [[0, 0], [w, 0]];
  if (right) vertices.push([w, d - right.depth], [w - right.width, d - right.depth],
    [w - right.width, d]);
  else vertices.push([w, d]);
  if (left) vertices.push([left.width, d], [left.width, d - left.depth],
    [0, d - left.depth]);
  else vertices.push([0, d]);
  const removed = cuts.reduce((sum, cut) => sum + cut.width * cut.depth, 0);
  if (!Array.isArray(echo.vertices) || echo.vertices.length !== vertices.length ||
      echo.vertices.some((point, i) => !keysAre(point, ['x', 'y']) ||
        point.x !== vertices[i][0] || point.y !== vertices[i][1]) ||
      (result.status === 'ok' &&
        (!Number.isFinite(result.site?.plot_area) ||
         Math.abs(result.site.plot_area - (w * d - removed)) > 1e-7))) {
    throw new Error('Vértices o área del croquis de parcela incompatibles.');
  }
}

// Independently reconstruct all full-width bands in Rust's selected sketch.
// This is NEVER evidence of a street, a right of way, accessible travel or levels.
function verifiedFrontApproach(input, result, alternative) {
  const source = input.site.front_approach;
  const echo = result.site_approach;
  const width = source?.width;
  const half = width / 2;
  const straight = source?.shape === 'straight_front_strip' &&
    source.front_x === null && source.turn_y === null;
  const detour = source?.shape === 'orthogonal_front_detour' &&
    Number.isFinite(source.front_x) && source.front_x >= half &&
    source.front_x <= input.site.width - half &&
    Number.isFinite(source.turn_y) && source.turn_y >= half &&
    source.turn_y <= input.site.depth - half;
  if (!keysAre(source, ['provenance', 'shape', 'width', 'front_x', 'turn_y']) ||
      !keysAre(echo, ['provenance', 'geometry_status', 'shape', 'width', 'front_x', 'turn_y',
        'street_connection_status', 'right_of_way_status', 'accessibility_status']) ||
      source.provenance !== 'user_sketch_unverified' || echo.provenance !== source.provenance ||
      !(straight || detour) || echo.shape !== source.shape ||
      echo.front_x !== source.front_x || echo.turn_y !== source.turn_y ||
      echo.geometry_status !== 'declared_front_trace_sketch_2d_only' ||
      echo.street_connection_status !== 'not_evaluated' ||
      echo.right_of_way_status !== 'not_evaluated' || echo.accessibility_status !== 'not_evaluated' ||
      !Number.isFinite(width) || width < 0.9 || width > Math.min(6, input.site.width) ||
      echo.width !== width || !Number.isFinite(input.rules?.doors?.main) ||
      width + 1e-7 < input.rules.doors.main) {
    throw new Error('Trazado frontal incompatible: no se acreditan acceso ni derechos de paso.');
  }
  if (result.status !== 'ok' || alternative === null) return null;
  if (!result.alternatives?.includes(alternative)) {
    throw new Error('No hay una alternativa actual de Rust para observar el trazado frontal.');
  }
  const a = alternative.front_approach;
  const door = alternative.entrance?.opening;
  const setback = input.rules?.setbacks?.front;
  const close = (a, b) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= 1e-7;
  if (!keysAre(a, ['geometry_status', 'shape', 'width', 'segments', 'turns',
      'front_contact', 'door_contact']) ||
      !keysAre(door, ['x', 'y', 'width', 'depth']) ||
      !keysAre(a.front_contact, ['x', 'y']) || !keysAre(a.door_contact, ['x', 'y']) ||
      !Array.isArray(a.segments) || !Array.isArray(a.turns) ||
      !Number.isFinite(setback) || setback < 0 || !close(result.site?.buildable?.y, setback) ||
      !close(door.y, setback) || !close(door.width, alternative.entrance.width) ||
      !close(alternative.corridor?.x + alternative.corridor?.width / 2, door.x + door.width / 2) ||
      a.shape !== source.shape || !close(a.width, width)) {
    throw new Error('El trazado frontal no corresponde a la puerta dibujada por Rust.');
  }
  const doorX = door.x + door.width / 2;
  const frontX = straight ? doorX : source.front_x;
  if (!close(a.front_contact.x, frontX) || !close(a.front_contact.y, 0) ||
      !close(a.door_contact.x, doorX) || !close(a.door_contact.y, setback) ||
      doorX - half < -1e-7 || doorX + half > input.site.width + 1e-7) {
    throw new Error('El trazado frontal no conecta el borde dibujado con la puerta.');
  }
  let segments;
  let turns = [];
  let status;
  if (straight) {
    segments = setback <= 1e-7 ? [] :
      [{ x: doorX - half, y: 0, width, depth: setback }];
    status = segments.length ? 'strip_clear_of_declared_exclusions_2d_only' :
      'door_at_front_boundary_2d_only';
  } else {
    if (Math.abs(frontX - doorX) < width || source.turn_y - half < 0 ||
        source.turn_y + half > setback) {
      throw new Error('Los dos giros no caben con el ancho completo en el retiro frontal.');
    }
    turns = [{ x: frontX, y: source.turn_y }, { x: doorX, y: source.turn_y }];
    segments = [
      { x: frontX - half, y: 0, width, depth: source.turn_y },
      { x: Math.min(frontX, doorX), y: source.turn_y - half,
        width: Math.abs(frontX - doorX), depth: width },
      { x: doorX - half, y: source.turn_y, width, depth: setback - source.turn_y },
    ];
    status = 'orthogonal_detour_clear_of_declared_exclusions_2d_only';
  }
  if (a.geometry_status !== status || a.segments.length !== segments.length ||
      a.turns.length !== turns.length ||
      a.turns.some((point, i) => !keysAre(point, ['x', 'y']) ||
        !close(point.x, turns[i].x) || !close(point.y, turns[i].y)) ||
      a.segments.some((band, i) => !keysAre(band, ['x', 'y', 'width', 'depth']) ||
        !Object.keys(segments[i]).every((key) => close(band[key], segments[i][key])))) {
    throw new Error('Las bandas frontales no coinciden con el croquis y la puerta.');
  }
  const excluded = [
    ...input.site.plot_outline.rear_notches.map((notch) => ({
      x: notch.side === 'left' ? 0 : input.site.width - notch.width,
      y: input.site.depth - notch.depth, width: notch.width, depth: notch.depth,
    })),
    ...input.site.reserved_areas,
  ];
  // Also test the exact exported coordinates: the equality tolerance above
  // must NEVER let a sub-EPS tampering cross a reserved edge unnoticed.
  if ([...segments, ...a.segments].some((band) => band.x < -1e-7 || band.y < -1e-7 ||
      band.x + band.width > input.site.width + 1e-7 || band.y + band.depth > setback + 1e-7 ||
      excluded.some((region) => intersectionArea(band, region) > 0))) {
    throw new Error('Una banda frontal cruza un recorte o reserva del croquis.');
  }
  return a;
}

// A verified echo of the *applicant's sketch*, never proof of a surveyed
// boundary or a legal/no-build restriction. Independent from the PDF inventory.
function verifiedReservationSketch(input, result) {
  const source = input.site;
  const echo = result.site_reservations;
  const fields = ['x', 'y', 'width', 'depth'];
  if (!keysAre(source, ['width', 'depth', 'front_orientation', 'plot_outline', 'front_approach', 'reservation_provenance', 'reserved_areas']) ||
      source.reservation_provenance !== 'user_sketch_unverified' ||
      !Array.isArray(source.reserved_areas) || source.reserved_areas.length > 2 ||
      !keysAre(echo, ['provenance', 'geometry_status', 'areas']) ||
      echo.provenance !== 'user_sketch_unverified' ||
      echo.geometry_status !== 'footprint_exclusion_2d_only' ||
      !Array.isArray(echo.areas) || echo.areas.length !== source.reserved_areas.length ||
      source.reserved_areas.some((area, i) => !keysAre(area, fields) ||
        !keysAre(echo.areas[i], fields) || fields.some((key) =>
          !Number.isFinite(area[key]) || area[key] !== echo.areas[i][key]))) {
    throw new Error('Croquis de reserva de parcela incompatible: no implica validez legal.');
  }
  const removed = source.plot_outline.rear_notches.map((notch) => ({
    x: notch.side === 'left' ? 0 : source.width - notch.width,
    y: source.depth - notch.depth, width: notch.width, depth: notch.depth,
  }));
  const zones = source.reserved_areas;
  if (zones.some((area, i) => area.x < 0 || area.y < 0 || area.width < 0.1 ||
      area.depth < 0.1 || area.x + area.width > source.width ||
      area.y + area.depth > source.depth ||
      removed.some((cut) => intersectionArea(area, cut) > 0) ||
      zones.slice(i + 1).some((next) => intersectionArea(area, next) > 0))) {
    throw new Error('Croquis de reserva de parcela incompatible: zonas solapadas, fuera del contorno o en el recorte.');
  }
  if (result.status !== 'ok') return;
  const s = input.rules?.setbacks;
  const actual = result.site?.buildable;
  const expected = { x: s?.left, y: s?.front,
    width: source.width - s?.left - s?.right, depth: source.depth - s?.front - s?.rear };
  if (!keysAre(actual, fields) ||
      fields.some((key) => !Number.isFinite(expected[key]) ||
        !Number.isFinite(actual[key]) || Math.abs(actual[key] - expected[key]) > 1e-7) ||
      expected.width <= 0 || expected.depth <= 0 ||
      !Number.isFinite(result.site.unreserved_buildable_area) ||
      Math.abs(result.site.unreserved_buildable_area - (
        expected.width * expected.depth -
        removed.reduce((sum, cut) => sum + intersectionArea(expected, cut), 0) -
        zones.reduce((sum, zone) => sum + intersectionArea(expected, zone), 0)
      )) > 1e-7) {
    throw new Error('El área disponible del croquis no coincide con el descuento único de las reservas.');
  }
}

const contextFields = ['jurisdiction', 'housing_class', 'occupants', 'accessibility_needs', 'provenance'];
const reviewFields = ['status', 'declared_scope', 'missing_context', 'source_status', 'daylight_status', 'ventilation_status'];

// Both the self-report and the Rust echo must agree. The status is ALWAYS
// unevaluated; a candidate from self-report is not a legal finding about NC 598.
function verifiedContext(input, result) {
  const context = input.project_context;
  const echo = result.project_context;
  const review = result.applicability;
  const validOccupants = context?.occupants === null ||
    (Number.isSafeInteger(context?.occupants) && context.occupants >= 1 && context.occupants <= 20);
  const missing = [];
  if (context?.jurisdiction === 'unreported') missing.push('jurisdiction');
  if (context?.housing_class === 'unreported') missing.push('housing_class');
  if (context?.occupants === null) missing.push('occupants');
  if (context?.accessibility_needs === 'unreported') missing.push('accessibility_needs');
  const candidate = context?.jurisdiction === 'CU' && context?.housing_class === 'urban_social';
  if (input?.request_schema !== 'arqgen-brief-v8' || result?.request_schema !== input.request_schema ||
      !keysAre(context, contextFields) || !keysAre(echo, contextFields) ||
      !contextFields.every((field) => echo[field] === context[field]) ||
      !['unreported', 'CU', 'outside_CU'].includes(context.jurisdiction) ||
      !['unreported', 'urban_social', 'other'].includes(context.housing_class) ||
      !validOccupants || !['unreported', 'declared', 'none_declared'].includes(context.accessibility_needs) ||
      context.provenance !== 'self_reported_unverified' ||
      !keysAre(review, reviewFields) || review.status !== 'not_evaluated' ||
      review.declared_scope !== (candidate ? 'candidate_from_self_report_only' : 'undetermined') ||
      !Array.isArray(review.missing_context) ||
      review.missing_context.length !== missing.length ||
      review.missing_context.some((field, index) => field !== missing[index]) ||
      review.source_status !== 'no_verified_cuban_ruleset' ||
      review.daylight_status !== 'not_evaluated' || review.ventilation_status !== 'not_evaluated') {
    throw new Error('Contexto declarado o revisión Rust incompatible: no se puede evaluar aplicabilidad.');
  }
  return { context: { ...echo }, review, missing };
}

export function reviewSanitaryScope(input, result, alternative, inventory) {
  const sources = referencesFrom(inventory);
  if (!keysAre(input, ['request_schema', 'site', 'program', 'project_context', 'seed', 'rules']) ||
      !keysAre(input.site, ['width', 'depth', 'front_orientation', 'plot_outline', 'front_approach', 'reservation_provenance', 'reserved_areas']) ||
      !keysAre(input.program, ['bedrooms', 'bathrooms', 'target_built_area']) ||
      input.rules?.regulatory_status !== 'illustrative_not_certified' ||
      !['ok', 'infeasible'].includes(result?.status) ||
      (result.status === 'ok' && (result.regulatory_status !== 'illustrative_not_certified' ||
        result.rule_id !== input.rules.id || result.rule_version !== input.rules.version)) ||
      (result.status === 'infeasible' && (result.regulatory_status !== undefined ||
        !Array.isArray(result.alternatives) || result.alternatives.length !== 0))) {
    throw new Error('Esta entrada no admite una revisión de aplicabilidad con el ruleset demostrativo.');
  }
  const { context, review, missing } = verifiedContext(input, result);
  verifiedPlotSketch(input, result);
  verifiedReservationSketch(input, result);
  const approach = verifiedFrontApproach(input, result, alternative);
  return {
    approach,
    regulatory_status: review.status,
    daylight_status: review.daylight_status,
    ventilation_status: review.ventilation_status,
    scope: review.declared_scope,
    context,
    missing_context: missing,
    source: sources.pdf,
    dependencies: sources.references,
    bathrooms: bathroomEvidence(input, result, alternative),
  };
}

// Wording shared by the live view, an infeasible run, and the TXT transcript.
// Only call with reviewSanitaryScope's verified, non-normative result.
export function describeDeclaredContext(review) {
  const location = {
    unreported: 'sin declarar', CU: 'Cuba (declaración sin comprobar)',
    outside_CU: 'fuera de Cuba (declaración sin comprobar)',
  }[review.context.jurisdiction];
  const housing = {
    unreported: 'sin declarar', urban_social: 'vivienda social urbana (declaración sin comprobar)',
    other: 'otra clase (declaración sin comprobar)',
  }[review.context.housing_class];
  const accessibility = {
    unreported: 'sin declarar', declared: 'necesidades declaradas por el solicitante',
    none_declared: 'no declaradas por el solicitante; NO implica exención',
  }[review.context.accessibility_needs];
  if (!location || !housing || !accessibility || review.regulatory_status !== 'not_evaluated' ||
      !['candidate_from_self_report_only', 'undetermined'].includes(review.scope)) {
    throw new Error('No se puede describir un contexto no verificado.');
  }
  const occupants = review.context.occupants === null ? 'sin declarar' :
    `${review.context.occupants} (declaración sin comprobar)`;
  const scope = review.scope === 'candidate_from_self_report_only'
    ? 'Los datos declarados señalan un posible ámbito a estudiar de NC 598:2009, NO su aplicabilidad legal.'
    : 'El ámbito de NC 598:2009 sigue indeterminado; otra clase o ubicación declarada NO equivale a exención.';
  const missingLabels = {
    jurisdiction: 'ubicación', housing_class: 'clase de vivienda',
    occupants: 'ocupantes', accessibility_needs: 'necesidades de accesibilidad',
  };
  const pending = review.missing_context.length
    ? ` Datos sin declarar: ${review.missing_context.map((key) => missingLabels[key]).join(', ')}.` : '';
  return `Ubicación: ${location}; clase de vivienda: ${housing}; ocupantes: ${occupants}; accesibilidad: ${accessibility}. ${scope}${pending} Cuba es objetivo del inventario, no ubicación asumida. Edición oficial, vigencia, ámbito y cumplimiento: NO EVALUADOS.`;
}
