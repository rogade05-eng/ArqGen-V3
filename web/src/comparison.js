// Presentation-only archive. Every generation is produced by the Rust core;
// these helpers neither score alternatives nor calculate delivered airflow.
export const hypothesisFields = [
  'fan_reference_pressure_pa',
  'fan_reference_flow_m3h',
  'assumed_reserve_pa',
];
export const comparisonLimit = 3;

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function serialized(value) { return JSON.stringify(canonical(value)); }

// Only the three UI-controlled assumptions may differ within a comparison.
export function comparisonKey(input) {
  const rules = structuredClone(input.rules);
  for (const key of hypothesisFields) delete rules.bath_pressure[key];
  return serialized({ request_schema: input.request_schema, site: input.site,
    program: input.program, project_context: input.project_context, seed: input.seed, rules });
}

function validGeneration(result) {
  if (!result || !['ok', 'infeasible'].includes(result.status) ||
      typeof result.input_hash !== 'string' || !result.input_hash ||
      typeof result.engine_version !== 'string' || !result.engine_version ||
      !Array.isArray(result.alternatives) || !Array.isArray(result.rejection_summary) ||
      !Number.isSafeInteger(result.generated) || !Number.isSafeInteger(result.rejected) ||
      result.generated < 0 || result.rejected < 0 || result.rejected > result.generated) return false;
  if (result.rejection_summary.some((row) => !row || typeof row.reason !== 'string' ||
    !row.reason || !Number.isSafeInteger(row.count) || row.count < 1)) return false;
  if (result.rejection_summary.reduce((sum, row) => sum + row.count, 0) !== result.rejected) return false;
  return result.status === 'ok' ? result.alternatives.length > 0 :
    result.alternatives.length === 0 && result.rejected === result.generated;
}

export function archiveScenario(records, input, result) {
  if (!input || input.request_schema !== 'arqgen-brief-v8' ||
      !input.project_context || !result?.project_context ||
      result.request_schema !== input.request_schema || result.applicability?.status !== 'not_evaluated' ||
      serialized(result.project_context) !== serialized(input.project_context) ||
      !validGeneration(result)) return { records, reason: 'invalid' };
  let key;
  try { key = comparisonKey(input); } catch { return { records, reason: 'invalid' }; }
  if (records.length && (comparisonKey(records[0].input) !== key ||
      records[0].generation.engine_version !== result.engine_version)) {
    return { records, reason: 'different_brief' };
  }
  const existing = records.find(({ generation }) => generation.input_hash === result.input_hash);
  if (existing) {
    return { records, reason: serialized(existing.input) === serialized(input) &&
      serialized(existing.generation) === serialized(result) ? 'duplicate' : 'hash_conflict' };
  }
  if (records.length >= comparisonLimit) return { records, reason: 'full' };
  return { records: [...records, structuredClone({ input, generation: result })], reason: 'saved' };
}

export function comparisonReport(records) {
  if (records.length < 2 || records.length > comparisonLimit) throw new Error('Se requieren entre 2 y 3 escenarios.');
  let checked = [];
  for (const { input, generation } of records) {
    const attempt = archiveScenario(checked, input, generation);
    if (attempt.reason !== 'saved') throw new Error(`Escenarios no comparables: ${attempt.reason}.`);
    checked = attempt.records;
  }
  return {
    format: 'arqgen-illustrative-comparison-v8',
    engine_version: checked[0].generation.engine_version,
    varying_assumptions: [...hypothesisFields],
    ventilation_status: 'not_evaluated',
    scenarios: checked,
  };
}
