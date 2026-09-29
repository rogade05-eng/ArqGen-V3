// Lossless form mapping for the current versioned Rust request. Parsing and
// authoritative validation still happen in Rust, never in the presentation.
export const requestSchema = 'arqgen-brief-v8';
export const reservationProvenance = 'user_sketch_unverified';

const reserveFields = ['x', 'y', 'width', 'depth'];
const reserveSlots = [
  { toggle: 'reserve_enabled', names: Object.fromEntries(reserveFields.map((key) => [key, `reserve_${key}`])),
    defaults: { x: 4.5, y: 12, width: 2, depth: 2 } },
  { toggle: 'reserve_2_enabled', names: Object.fromEntries(reserveFields.map((key) => [key, `reserve_2_${key}`])),
    defaults: { x: 13, y: 12, width: 2, depth: 2 } },
];
const notchDefaults = { side: 'left', width: 4, depth: 10 };
const secondNotchDefaults = { width: 3, depth: 9 };
const keysAre = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));

export function readBriefForm(fields, demoRules, hypothesisFields) {
  const rules = structuredClone(demoRules);
  for (const key of hypothesisFields) rules.bath_pressure[key] = Number(fields[key].value);
  const firstCut = fields.plot_notch_enabled.checked;
  const secondCut = firstCut && fields.plot_notch_2_enabled.checked;
  const firstSide = fields.notch_side.value;
  const rearNotches = firstCut ? [
    { side: firstSide, width: Number(fields.notch_width.value),
      depth: Number(fields.notch_depth.value) },
    ...(secondCut ? [{ side: firstSide === 'left' ? 'right' : 'left',
      width: Number(fields.notch_2_width.value), depth: Number(fields.notch_2_depth.value) }] : []),
  ] : [];
  return {
    request_schema: requestSchema,
    site: {
      width: Number(fields.width.value),
      depth: Number(fields.depth.value),
      front_orientation: fields.front_orientation.value,
      plot_outline: {
        provenance: reservationProvenance,
        shape: rearNotches.length === 2 ? 'rear_both_corners_notched' :
          rearNotches.length === 1 ? 'rear_corner_notch' : 'rectangle',
        rear_notches: rearNotches,
      },
      front_approach: {
        provenance: reservationProvenance,
        shape: fields.approach_shape.value,
        width: Number(fields.approach_width.value),
        front_x: fields.approach_shape.value === 'orthogonal_front_detour'
          ? Number(fields.approach_front_x.value) : null,
        turn_y: fields.approach_shape.value === 'orthogonal_front_detour'
          ? Number(fields.approach_turn_y.value) : null,
      },
      reservation_provenance: reservationProvenance,
      // The second slot is a supplement, not a standalone reservation: the
      // first checkbox must be active before it is serialized.
      reserved_areas: reserveSlots.filter((slot, index) =>
        fields[slot.toggle].checked && (index === 0 || fields.reserve_enabled.checked))
        .map((slot) => Object.fromEntries(reserveFields.map((key) =>
          [key, Number(fields[slot.names[key]].value)]))),
    },
    program: {
      bedrooms: Number(fields.bedrooms.value),
      bathrooms: Number(fields.bathrooms.value),
      target_built_area: Number(fields.target_built_area.value),
    },
    project_context: {
      jurisdiction: fields.project_jurisdiction.value,
      housing_class: fields.housing_class.value,
      occupants: fields.occupants.value === '' ? null : Number(fields.occupants.value),
      accessibility_needs: fields.accessibility_needs.value,
      provenance: 'self_reported_unverified',
    },
    seed: Number(fields.seed.value),
    rules,
  };
}

export function writeBriefForm(fields, input, hypothesisFields) {
  if (input?.request_schema !== requestSchema) {
    throw new Error('No se puede mostrar una entrada de versión anterior en el formulario.');
  }
  const { site, program, project_context: context, seed, rules } = input;
  if (!keysAre(site, ['width', 'depth', 'front_orientation', 'plot_outline',
      'front_approach', 'reservation_provenance', 'reserved_areas']) ||
      site.reservation_provenance !== reservationProvenance ||
      !Array.isArray(site.reserved_areas) || site.reserved_areas.length > 2 ||
      site.reserved_areas.some((area) => !keysAre(area, reserveFields))) {
    throw new Error('Este formulario solo admite hasta dos rectángulos voluntarios de parcela no verificados.');
  }
  const plot = site.plot_outline;
  const cuts = plot?.rear_notches;
  if (!keysAre(plot, ['provenance', 'shape', 'rear_notches']) ||
      plot.provenance !== reservationProvenance ||
      !Array.isArray(cuts) || cuts.length > 2 ||
      !(['rectangle', 'rear_corner_notch', 'rear_both_corners_notched'][cuts.length] === plot.shape) ||
      cuts.some((cut) => !keysAre(cut, ['side', 'width', 'depth']) ||
        !['left', 'right'].includes(cut.side)) ||
      (cuts.length === 2 && cuts[0].side === cuts[1].side)) {
    throw new Error('Este formulario solo admite hasta dos recortes posteriores en esquinas opuestas del croquis no verificado.');
  }
  const approach = site.front_approach;
  if (!keysAre(approach, ['provenance', 'shape', 'width', 'front_x', 'turn_y']) ||
      approach.provenance !== reservationProvenance ||
      !Number.isFinite(approach.width) || approach.width < 0.9 ||
      approach.width > Math.min(6, site.width) ||
      !((approach.shape === 'straight_front_strip' && approach.front_x === null &&
          approach.turn_y === null) ||
        (approach.shape === 'orthogonal_front_detour' &&
          Number.isFinite(approach.front_x) &&
          approach.front_x >= approach.width / 2 &&
          approach.front_x <= site.width - approach.width / 2 &&
          Number.isFinite(approach.turn_y) &&
          approach.turn_y >= approach.width / 2 &&
          approach.turn_y <= site.depth - approach.width / 2))) {
    throw new Error('Este formulario solo admite una franja recta o un rodeo ortogonal 2D autodeclarado.');
  }
  const { reserved_areas: areas, reservation_provenance: _provenance,
    plot_outline: _plot, front_approach: _approach, ...siteFields } = site;
  for (const [field, value] of Object.entries({ ...siteFields, ...program, seed, ...Object.fromEntries(
    hypothesisFields.map((key) => [key, rules.bath_pressure[key]]),
  ) })) fields[field].value = String(value);
  fields.plot_notch_enabled.checked = cuts.length > 0;
  fields.notch_side.value = cuts[0]?.side ?? notchDefaults.side;
  fields.notch_width.value = String(cuts[0]?.width ?? notchDefaults.width);
  fields.notch_depth.value = String(cuts[0]?.depth ?? notchDefaults.depth);
  fields.plot_notch_2_enabled.checked = cuts.length === 2;
  fields.notch_2_width.value = String(cuts[1]?.width ?? secondNotchDefaults.width);
  fields.notch_2_depth.value = String(cuts[1]?.depth ?? secondNotchDefaults.depth);
  fields.approach_shape.value = approach.shape;
  fields.approach_width.value = String(approach.width);
  fields.approach_front_x.value = String(approach.front_x ?? 11.5);
  fields.approach_turn_y.value = String(approach.turn_y ?? 1.6);
  reserveSlots.forEach((slot, index) => {
    fields[slot.toggle].checked = areas.length > index;
    for (const key of reserveFields) {
      fields[slot.names[key]].value = String(areas[index]?.[key] ?? slot.defaults[key]);
    }
  });
  fields.project_jurisdiction.value = context.jurisdiction;
  fields.housing_class.value = context.housing_class;
  fields.occupants.value = context.occupants === null ? '' : String(context.occupants);
  fields.accessibility_needs.value = context.accessibility_needs;
}
