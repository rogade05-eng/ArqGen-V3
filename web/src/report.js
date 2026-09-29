// Readable transcript of an already validated Rust result. No additional
// engineering calculation, regulatory claim, or rendered external SVG.
import { reviewSanitaryScope, describeDeclaredContext } from './source-review.js';

const safe = (value) => String(value).replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
const rounded = (value, digits = 2) => new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
}).format(value);

export function conceptualReport(input, result, index, sourceInventory) {
  if (result?.status !== 'ok' || !Array.isArray(result.alternatives) ||
      !Number.isInteger(index) || index < 0 || index >= result.alternatives.length ||
      result.rule_id !== input?.rules?.id || result.rule_version !== input.rules.version) {
    throw new Error('No existe una alternativa validada para esta entrada y este ruleset.');
  }
  const alt = result.alternatives[index];
  const scope = reviewSanitaryScope(input, result, alt, sourceInventory);
  const reserved = result.site_reservations.areas; // echoed and checked by reviewSanitaryScope
  const cuts = result.site_plot.rear_notches; // echoed and checked by reviewSanitaryScope
  const approach = scope.approach;
  const trace = approach.segments.length === 0
    ? `franja recta de ${rounded(approach.width)} m; puerta en el borde frontal del croquis: no hay franja exterior modelada`
    : approach.shape === 'orthogonal_front_detour'
      ? `rodeo ortogonal de ${rounded(approach.width)} m con dos giros declarados: borde x=${rounded(approach.front_contact.x)}, y=0; giro a y=${rounded(approach.turns[0].y)}; puerta x=${rounded(approach.door_contact.x)}, y=${rounded(approach.door_contact.y)} m. Sus tres bandas completas no cruzan las exclusiones dibujadas`
      : `franja recta de ${rounded(approach.width)} m centrada en la puerta dibujada, desde el borde y=0 hasta y=${rounded(approach.door_contact.y)} m. No cruza las exclusiones dibujadas`;
  if (alt.bathroom_ventilation_status !== 'not_evaluated' ||
      alt.rooms.some((room) => room.type === 'bathroom' &&
        (room.ventilation_status !== 'not_evaluated' ||
          room.bath_pressure?.delivered_flow_status !== 'not_evaluated'))) {
    throw new Error('El estado de ventilación no corresponde al alcance ilustrativo de esta ficha.');
  }
  const lines = [
    'ARQ GEN · FICHA DE ANTEPROYECTO CONCEPTUAL',
    'ESQUEMA EXPERIMENTAL · NO APTO PARA OBRA · REVISIÓN PROFESIONAL OBLIGATORIA',
    '',
    'Esta ficha transcribe una alternativa del núcleo Rust validada contra reglas genéricas ILUSTRATIVAS.',
    'No certifica normativa, accesibilidad, estructura, evacuación legal, luz natural efectiva ni ventilación efectiva.',
    'No hay equipo de extracción identificado, pérdidas reales ni caudal entregado medido o calculado.',
    '',
    '1. ENTRADA Y TRAZABILIDAD',
    `Motor: ${safe(result.engine_version)} | Entrada: ${safe(result.request_schema)} | Ruleset: ${safe(result.rule_id)}@${safe(result.rule_version)}`,
    `Huella de la entrada (no firma criptográfica): ${safe(result.input_hash)}`,
    `Semilla: ${input.seed} | Alternativa mostrada: ${safe(alt.id)} — ${safe(alt.label)}`,
    `Caja exterior del croquis: ${input.site.width} × ${input.site.depth} m; orientación de frente: ${safe(input.site.front_orientation)}.`,
    `Programa: ${input.program.bedrooms} dormitorio(s), ${input.program.bathrooms} baño(s), huella orientativa ${input.program.target_built_area} m².`,
    `Contorno de parcela declarado: ${cuts.length === 0 ? 'rectángulo completo' : cuts.length === 1 ? `forma en L con recorte posterior ${cuts[0].side === 'left' ? 'izquierdo' : 'derecho'} de ${rounded(cuts[0].width)} × ${rounded(cuts[0].depth)} m FUERA de la parcela dibujada` : `dos esquinas posteriores recortadas FUERA de la parcela dibujada: ${cuts.map((cut, i) => `${i + 1} ${cut.side === 'left' ? 'izquierda' : 'derecha'} ${rounded(cut.width)} × ${rounded(cut.depth)} m`).join('; ')}`}. NO levantamiento, catastro, linderos ni derechos verificados. Retiros ilustrativos solo desde la caja exterior, NO desde los entrantes; no se acredita acceso exterior real.`,
    `Croquis voluntario de parcela: ${reserved.length ? reserved.map((area, i) =>
      `${reserved.length === 2 ? `zona ${i + 1}: ` : ''}rectángulo x=${rounded(area.x)}, y=${rounded(area.y)}, ancho=${rounded(area.width)}, fondo=${rounded(area.depth)} m`).join('; ') + `; excluido${reserved.length === 2 ? 's' : ''} de la huella y las bandas del trazado frontal 2D` : 'sin zonas reservadas'}. Fuente: solicitante, NO levantamiento, lindero ni derecho verificado.`,

    `Aproximación frontal: ${trace}. SOLO croquis 2D; NO certifica vía pública, derecho de paso, cota, pavimento, obstáculos, accesibilidad ni acceso efectivo. No se buscaron rutas distintas a la declarada.`,
    '',
    '2. ÁMBITO DE NC 598 Y LUZ NATURAL · SOLO OBSERVACIÓN',
    `NC 598:2009 · NO EVALUADA. ${safe(describeDeclaredContext(scope))}`,
    `Baños con vano de fachada dibujado: ${scope.bathrooms.with_drawn_window.length}/${scope.bathrooms.total} (${scope.bathrooms.with_drawn_window.map(safe).join(', ') || 'ninguno'}). Baños sin ventana dibujada: ${scope.bathrooms.without_window.length}/${scope.bathrooms.total}; vano sin dato coherente: ${scope.bathrooms.unknown.length}.`,
    `Objetivo de abertura del ruleset ILUSTRATIVO: ${rounded(input.rules.spaces.bathroom.window_ratio * 100)} % del área útil; NO es umbral NC 598 ni cálculo de iluminancia.`,
    'Iluminación natural: NO EVALUADA. Una ventana en planta no acredita antepecho, acristalamiento, obstrucciones ni luz efectiva; requiere revisión profesional. La extracción reservada tampoco acredita ventilación.',
    `NC 598:2009 identificada por copia SHA-256 ${scope.source.sha256} del commit ${scope.source.source_commit}: estos bytes NO prueban edición vigente, autenticidad editorial ni permisos.`,
    `NC 337 y NC 391-1/-2: ${scope.dependencies.map((ref) => ref.id).join(', ')}; solo vistas de terceros sin edición/vigencia/derechos confirmados. No se han aplicado umbrales normativos.`,
    'Inventario: knowledge/source-manifest.json del build web actual. NO forma parte del hash de entrada del motor Rust ni del ruleset demo.',
    '',
    '3. SUPERFICIES DEL ESQUEMA',
    `Área del croquis de parcela: ${rounded(result.site.plot_area)} m² (NO superficie catastral); envolvente demo dentro del croquis y no reservada: ${rounded(result.site.unreserved_buildable_area)} m² (cota superior 2D, NO edificabilidad legal); huella máxima en este modelo: ${rounded(result.site.max_footprint)} m²; área construida máxima por FAR demo: ${rounded(result.site.max_built_area)} m².`,
    `Huella bruta elegida: ${rounded(alt.built_area)} m²; área útil: ${rounded(alt.usable_area)} m²; reserva para muros y vanos: ${rounded(alt.wall_allowance_area)} m².`,
    'Áreas modeladas en 2D y aquí redondeadas a centésimas, no medición para obra.',
    '',
    '4. LOCALES · ÁREAS ÚTILES',
  ];
  for (const room of alt.rooms) {
    lines.push(`- ${safe(room.label)} (${safe(room.id)}): ${rounded(room.usable_area)} m²; zona ${safe(room.zone)}; ventilación: ${safe(room.ventilation_status)}.`);
    if (room.type === 'bathroom') {
      lines.push(`  Extracción solo reservada en planta. Q OBJETIVO nominal: ${rounded(room.bath_airflow.target_flow_m3h, 1)} m³/h; presupuesto de presión HIPOTÉTICO: ${rounded(room.bath_pressure.pressure_budget.assumed_total_pa)} Pa.`);
      lines.push('  Caudal entregado: NO EVALUADO. Ventilación efectiva: NO EVALUADA.');
    }
  }
  lines.push('', '5. DECISIONES TRAZABLES · DATOS DEMO');
  for (const decision of alt.decisions) {
    lines.push(`- [${safe(decision.rule)}] ${safe(decision.explanation)}`);
  }
  lines.push('', '6. RESULTADOS DE ESTA BÚSQUEDA LIMITADA',
    `Variantes ensayadas: ${result.generated}; descartadas: ${result.rejected}; alternativas mostradas: ${result.alternatives.length}.`,
    'Cada motivo corresponde al primer fallo detectado en una variante. No demuestra inviabilidad universal.');
  for (const { reason, count } of result.rejection_summary) lines.push(`- ${count} × ${safe(reason)}`);
  if (!result.rejection_summary.length) lines.push('- Sin descartes en las variantes ensayadas.');
  for (const warning of alt.warnings) lines.push(`Aviso: ${safe(warning)}`);
  lines.push('', 'FIN · Preferencia de usuario, si la hubiera, NO es aprobación técnica.', '');
  return lines.join('\n');
}
