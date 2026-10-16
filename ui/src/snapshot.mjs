export const MAX_BYTES = 8 * 1024 * 1024;
export const STATES = ['completed', 'converted', 'in_progress', 'blocked', 'stale', 'unverified', 'unknown', 'retired'];
export const GATES = ['unit_cases', 'legacy_comparison', 'record_trace', 'code_quality', 'security', 'independent_audit'];
const RESERVED = new Set(['__proto__', 'constructor', 'prototype']);
const fail = (message) => { throw new Error(message); };
const check = (condition, message) => { if (!condition) fail(message); };
const keys = (value, names) => {
  check(value && typeof value === 'object' && !Array.isArray(value), 'Expected a snapshot object.');
  check(Object.keys(value).every((key) => names.includes(key) && !RESERVED.has(key)), 'Unexpected fields. Import a sanitized progress snapshot.');
};
const array = (value) => { check(Array.isArray(value) && value.length <= 20000, 'Invalid or oversized collection.'); return value; };
const id = (value) => check(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(value) && !RESERVED.has(value.toLowerCase()), 'Invalid evidence or program identifier.');
const label = (value) => check(typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9 _().:-]{0,79}$/.test(value), 'Invalid display label.');
const count = (value) => check(Number.isSafeInteger(value) && value >= 0, 'Invalid count.');
const bool = (value) => check(typeof value === 'boolean', 'Invalid recorded state.');
const choice = (value, values) => check(values.includes(value), 'Unknown recorded status.');
const nullableId = (value) => { if (value !== null) id(value); };
const refs = (values) => { array(values).forEach(id); check(new Set(values).size === values.length, 'Duplicate reference.'); };
const unique = (values, field) => {
  const seen = new Set();
  array(values).forEach((value) => { id(value[field]); check(!seen.has(value[field]), 'Duplicate inventory identifier.'); seen.add(value[field]); });
};
const receipt = (row, legacy = false, allowed = ['passed', 'failed', 'pending', 'blocked', 'unknown']) => {
  choice(row.status, [...allowed, ...(legacy ? ['approved_difference'] : [])]);
  bool(row.current); nullableId(row.version); refs(row.evidence_refs);
  check(!row.current || row.version !== null, 'Current receipt is missing its version.');
};

function validateProgram(program) {
  keys(program, ['program_id', 'label', 'current_version', 'state', 'converted', 'completed', 'process_ids', 'consumers', 'conversion', 'rule_catalog', 'retirement', 'catalog_complete', 'rule_counts', 'rules', 'gates', 'findings', 'blockers', 'migrations']);
  id(program.program_id); label(program.label); nullableId(program.current_version);
  choice(program.state, STATES); bool(program.converted); bool(program.completed); bool(program.catalog_complete); refs(program.process_ids);
  for (const [field, statuses] of [['conversion', ['converted', 'pending', 'failed', 'unknown']], ['rule_catalog', ['complete', 'partial', 'pending', 'unknown']], ['retirement', ['accepted', 'pending', 'unknown']]]) {
    keys(program[field], ['status', 'current', 'version', 'evidence_refs']); receipt(program[field], false, statuses);
    check(program[field].current === (program.current_version !== null && program[field].version === program.current_version), 'Receipt version disagrees with its current marker.');
  }
  const hasReceipt = (row, status) => row.status === status && row.current && row.evidence_refs.length > 0;
  check(program.converted === (hasReceipt(program.conversion, 'converted') && program.state !== 'retired'), 'Conversion status disagrees with its receipt.');
  check(program.catalog_complete === hasReceipt(program.rule_catalog, 'complete'), 'Catalog status disagrees with its receipt.');
  array(program.consumers).forEach((row) => {
    keys(row, ['process_id', 'step_id', 'provider', 'version', 'current']);
    id(row.process_id); id(row.step_id); nullableId(row.version); bool(row.current);
    choice(row.provider, ['python', 'sparkflow', 'mainframe', 'unknown']);
    check(row.current === (program.current_version !== null && row.version === program.current_version), 'Consumer binding version disagrees with its current marker.');
  });
  const consumerProcesses = new Set(program.consumers.map((row) => row.process_id));
  check(consumerProcesses.size === program.process_ids.length && program.process_ids.every((process) => consumerProcesses.has(process)), 'Process references disagree with consumer bindings.');
  keys(program.rule_counts, ['business', 'technical', 'mixed', 'total', 'retained', 'retired', 'quota_met']);
  Object.values(program.rule_counts).forEach(count);
  unique(program.rules, 'rule_id');
  program.rules.forEach((row) => {
    keys(row, ['rule_id', 'category', 'lifecycle', 'positive_passed', 'negative_passed', 'quota_met', 'current', 'evidence_refs']);
    choice(row.category, ['business', 'technical', 'mixed']); choice(row.lifecycle, ['retained', 'retired']);
    [row.positive_passed, row.negative_passed].forEach((value) => { if (value !== null) count(value); });
    bool(row.quota_met); bool(row.current); refs(row.evidence_refs);
    const quota = row.current && row.evidence_refs.length > 0 && row.positive_passed >= 100 && row.negative_passed >= 100;
    check(row.quota_met === quota, 'Rule quotas disagree with their recorded counts.');
  });
  const ruleCounts = Object.fromEntries(['business', 'technical', 'mixed'].map((category) => [category, program.rules.filter((row) => row.category === category).length]));
  ruleCounts.total = program.rules.length;
  ruleCounts.retired = program.rules.filter((row) => row.lifecycle === 'retired').length;
  ruleCounts.retained = ruleCounts.total - ruleCounts.retired;
  ruleCounts.quota_met = program.rules.filter((row) => row.lifecycle === 'retained' && row.quota_met).length;
  check(Object.entries(ruleCounts).every(([key, value]) => program.rule_counts[key] === value), 'Rule totals disagree with the inventory.');
  unique(program.gates, 'gate_id');
  check(program.gates.length === GATES.length && GATES.every((gate) => program.gates.some((row) => row.gate_id === gate)), 'Required gates are missing.');
  program.gates.forEach((row) => {
    keys(row, ['gate_id', 'status', 'current', 'version', 'evidence_refs']); receipt(row, row.gate_id === 'legacy_comparison');
    check(row.current === (program.current_version !== null && row.version === program.current_version), 'Gate version disagrees with its current marker.');
  });
  unique(program.findings, 'finding_id');
  program.findings.forEach((row) => {
    keys(row, ['finding_id', 'severity', 'status', 'finding_state', 'resolved', 'evidence_refs']);
    choice(row.severity, ['critical', 'high', 'medium', 'low', 'info']); choice(row.status, ['open', 'remediated', 'accepted']);
    choice(row.finding_state, ['open', 'fixed_pending_verification', 'closed_verified', 'false_positive_with_evidence', 'accepted_risk']);
    bool(row.resolved); refs(row.evidence_refs);
    const expectedStatus = row.finding_state === 'closed_verified' ? 'remediated' : ['false_positive_with_evidence', 'accepted_risk'].includes(row.finding_state) ? 'accepted' : 'open';
    check(row.status === expectedStatus, 'Finding status disagrees with its resolution state.');
    check(!row.resolved || (expectedStatus !== 'open' && row.evidence_refs.length > 0 && !(row.finding_state === 'accepted_risk' && ['critical', 'high'].includes(row.severity))), 'Finding resolution lacks an eligible state or evidence.');
  });
  array(program.blockers).forEach((row) => {
    keys(row, ['blocker_id', 'category']); id(row.blocker_id); id(row.category);
  });
  unique(program.migrations, 'migration_id');
  program.migrations.forEach((row) => {
    keys(row, ['migration_id', 'label', 'stage', 'depends_on', 'blocked']); label(row.label);
    choice(row.stage, ['identified', 'design', 'python_active', 'ready', 'flow_validated', 'sparkflow_active', 'retired', 'blocked', 'stale', 'unknown']);
    refs(row.depends_on); bool(row.blocked);
  });
  check(program.completed === (program.state === 'completed'), 'Completion state is inconsistent.');
  if (program.state === 'retired') check(hasReceipt(program.retirement, 'accepted') && program.process_ids.length === 0 && (program.consumers ?? []).length === 0, 'Retirement lacks a receipt or still has process bindings.');
  if (program.completed) check(program.converted && program.catalog_complete && ruleCounts.retained > 0 && ruleCounts.quota_met === ruleCounts.retained && program.blockers.length === 0 && program.findings.every((row) => row.resolved && !(['critical', 'high'].includes(row.severity) && row.finding_state === 'accepted_risk')) && program.gates.every((row) => ['passed', 'approved_difference'].includes(row.status) && row.current && row.evidence_refs.length), 'Completion lacks required recorded gates.');
}

export function validateSnapshot(value) {
  keys(value, ['schema_version', 'kind', 'fictional', 'demo_notice', 'observed_at', 'inventory_sha256', 'inventory_status', 'completeness', 'counters', 'programs', 'processes']);
  check(value.schema_version === 1 && value.kind === 'conversion_progress', 'Unsupported file. Export a version 1 conversion progress snapshot.');
  bool(value.fictional); choice(value.inventory_status, ['unverified', 'partial', 'complete']);
  if (value.demo_notice !== undefined) check(value.fictional && typeof value.demo_notice === 'string' && value.demo_notice.length <= 500, 'Invalid demo notice.');
  check(value.completeness === 'declared_not_verified', 'Unsupported evidence assurance.');
  check(typeof value.observed_at === 'string' && value.observed_at.length <= 40 && Number.isFinite(Date.parse(value.observed_at)), 'Invalid snapshot time.');
  check(typeof value.inventory_sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.inventory_sha256), 'Invalid inventory fingerprint.');
  unique(value.programs, 'program_id'); value.programs.forEach(validateProgram);
  const membersByProcess = new Map();
  const bindingsByProcess = new Map();
  value.programs.forEach((program) => program.process_ids.forEach((process) => {
    if (!membersByProcess.has(process)) membersByProcess.set(process, []);
    membersByProcess.get(process).push(program);
  }));
  value.programs.forEach((program) => program.consumers.forEach((binding) => {
    if (!bindingsByProcess.has(binding.process_id)) bindingsByProcess.set(binding.process_id, []);
    bindingsByProcess.get(binding.process_id).push(binding);
  }));
  unique(value.processes, 'process_id');
  const knownProcesses = new Set(value.processes.map((row) => row.process_id));
  value.programs.forEach((program) => program.process_ids.forEach((process) => {
    check(knownProcesses.has(process) || (program.state === 'blocked' && program.blockers.some((blocker) => blocker.blocker_id === process && blocker.category === 'unknown_process_reference')), 'Unknown process reference lacks a recorded blocker.');
  }));
  value.processes.forEach((row) => {
    keys(row, ['process_id', 'label', 'program_ids', 'total_programs', 'completed_programs', 'state', 'bindings_current', 'integration']); label(row.label); refs(row.program_ids);
    bool(row.bindings_current);
    count(row.total_programs); count(row.completed_programs); choice(row.state, STATES);
    keys(row.integration, ['status', 'current', 'version', 'evidence_refs']); receipt(row.integration);
    const members = membersByProcess.get(row.process_id) ?? [];
    const memberIds = new Set(row.program_ids);
    check(row.total_programs === members.length && row.completed_programs === members.filter((program) => program.completed).length && row.program_ids.length === members.length && members.every((program) => memberIds.has(program.program_id)), 'Process totals disagree with the inventory.');
    const bindings = bindingsByProcess.get(row.process_id) ?? [];
    check(row.bindings_current === (bindings.length > 0 && bindings.every((binding) => binding.current && ['python', 'sparkflow'].includes(binding.provider))), 'Process binding freshness disagrees with individual bindings.');
    const complete = members.length > 0 && members.every((program) => program.completed) && row.bindings_current && row.integration.status === 'passed' && row.integration.current && row.integration.evidence_refs.length > 0;
    check((row.state === 'completed') === complete, 'Process completion lacks required current bindings and integration evidence.');
  });
  const counters = {
    total_programs: value.programs.length,
    active_programs: value.programs.filter((row) => row.state !== 'retired').length,
    converted_programs: value.programs.filter((row) => row.converted).length,
    completed_programs: value.programs.filter((row) => row.completed).length,
    blocked_programs: value.programs.filter((row) => row.state === 'blocked').length,
    stale_programs: value.programs.filter((row) => row.state === 'stale').length,
    unknown_programs: value.programs.filter((row) => ['unknown', 'unverified'].includes(row.state)).length,
    retired_programs: value.programs.filter((row) => row.state === 'retired').length,
  };
  keys(value.counters, [...Object.keys(counters), 'completion_percent']);
  check(Object.entries(counters).every(([key, number]) => value.counters[key] === number), 'Summary totals disagree with the program inventory.');
  const percent = counters.active_programs ? Math.round(10000 * counters.completed_programs / counters.active_programs) / 100 : null;
  check(value.counters.completion_percent === percent, 'Completion percentage disagrees with the active inventory.');
  return value;
}

function rejectDuplicateKeys(text) {
  // JSON.parse has already validated the grammar. Scan tokens so duplicate
  // properties cannot disappear before schema checks, including escaped names.
  const stack = [];
  for (const [token] of text.matchAll(/"(?:[^"\\]|\\[\s\S])*"|[{}\[\],]/g)) {
    if (token === '{') stack.push({ names: new Set(), key: true });
    else if (token === '[') stack.push(null);
    else if (token === '}' || token === ']') stack.pop();
    else {
      const object = stack.at(-1);
      if (token === ',' && object) object.key = true;
      else if (token[0] === '"' && object?.key) {
        const name = JSON.parse(token);
        check(!object.names.has(name), 'Duplicate JSON key. Export a new sanitized snapshot.');
        object.names.add(name);
        object.key = false;
      }
    }
  }
}

export function parseSnapshot(text) {
  check(typeof text === 'string' && new TextEncoder().encode(text).length <= MAX_BYTES, 'File exceeds the 8 MiB limit. Export a smaller snapshot.');
  let value;
  try {
    value = JSON.parse(text, (key, item) => {
      check(!RESERVED.has(key.toLowerCase()), 'Reserved JSON field.');
      return item;
    });
  } catch { fail('The file is not valid progress JSON. Export a new sanitized snapshot.'); }
  rejectDuplicateKeys(text);
  return validateSnapshot(value);
}

export function selectPrograms(programs, query, state, process, sort) {
  const term = query.trim().toLowerCase();
  const rows = programs.filter((program) =>
    (!term || `${program.program_id} ${program.label}`.toLowerCase().includes(term)) &&
    (!state || program.state === state) && (!process || program.process_ids.includes(process)));
  return rows.sort((a, b) => sort === 'status' ? a.state.localeCompare(b.state) || a.program_id.localeCompare(b.program_id) : sort === 'gaps' ? (b.rule_counts.retained - b.rule_counts.quota_met) - (a.rule_counts.retained - a.rule_counts.quota_met) || a.program_id.localeCompare(b.program_id) : a.program_id.localeCompare(b.program_id));
}
