import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MAX_BYTES, parseSnapshot, selectPrograms } from '../src/snapshot.mjs';

const demo = JSON.parse(readFileSync(new URL('../src/demo-progress.json', import.meta.url), 'utf8'));
const clone = () => structuredClone(demo);

test('explicit fictional demo matches the exporter contract', () => {
  const value = parseSnapshot(JSON.stringify(demo));
  assert.equal(value.fictional, true);
  assert.equal(value.counters.total_programs, 7);
  assert.equal(value.counters.completed_programs, 1);
});
test('unknown raw source fields are rejected', () => {
  const value = clone(); value.programs[0].source = 'private';
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /sanitized/);
});
test('summary cannot disagree with program rows', () => {
  const value = clone(); value.counters.completed_programs = 99;
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /totals disagree/);
});
test('100 positive and 99 negative cannot be presented as quota met', () => {
  const value = clone();
  const rule = value.programs.find((row) => row.completed).rules[0];
  rule.negative_passed = 99;
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /quotas disagree/);
});
test('HTML and arbitrary URL references are rejected', () => {
  for (const bad of ['<img src=x>', 'javascript:alert(1)', '../private']) {
    const value = clone(); value.programs[0].gates[0].evidence_refs = [bad];
    assert.throws(() => parseSnapshot(JSON.stringify(value)), /identifier/);
  }
});
test('reserved properties are rejected before import', () => {
  assert.throws(() => parseSnapshot('{"__proto__":{"polluted":true}}'), /not valid/);
  assert.equal({}.polluted, undefined);
});
test('oversized and invalid JSON fail with recoverable errors', () => {
  assert.throws(() => parseSnapshot(' '.repeat(MAX_BYTES + 1)), /8 MiB/);
  assert.throws(() => parseSnapshot('{'), /not valid/);
});
test('duplicate program identifiers are rejected', () => {
  const value = clone(); value.programs[1].program_id = value.programs[0].program_id;
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /Duplicate/);
});
test('missing acceptance gates fail closed', () => {
  const value = clone(); value.programs[0].gates.pop();
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /gates are missing/);
});
test('status and search filters preserve original inventory totals', () => {
  const before = JSON.stringify(demo);
  const selected = selectPrograms(demo.programs, '', 'completed', '', 'program');
  assert.equal(selected.length, 1);
  assert.equal(selectPrograms(demo.programs, selected[0].program_id.toLowerCase(), '', '', 'status').length, 1);
  assert.equal(JSON.stringify(demo), before);
});
test('process filter includes shared programs only once', () => {
  const process = demo.processes[0];
  const rows = selectPrograms(demo.programs, '', '', process.process_id, 'gaps');
  assert.equal(rows.length, process.total_programs);
  assert.equal(new Set(rows.map((row) => row.program_id)).size, rows.length);
});
test('nonfinite and negative validation counts fail', () => {
  for (const bad of [-1, '100', 1e100]) {
    const value = clone(); value.programs.find((row) => row.rules.length).rules[0].positive_passed = bad;
    assert.throws(() => parseSnapshot(JSON.stringify(value)), /count/);
  }
});

test('open and pending findings cannot claim resolution', () => {
  for (const state of ['open', 'fixed_pending_verification']) {
    const value = clone();
    value.programs.find((row) => row.completed).findings.push({ finding_id: 'SEC-OPEN', severity: 'high', status: 'open', finding_state: state, resolved: true, evidence_refs: [] });
    assert.throws(() => parseSnapshot(JSON.stringify(value)), /finding/i);
  }
});
test('verified finding resolution requires evidence', () => {
  const value = clone();
  value.programs.find((row) => row.completed).findings.push({ finding_id: 'SEC-CLOSED', severity: 'low', status: 'remediated', finding_state: 'closed_verified', resolved: true, evidence_refs: [] });
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /finding/i);
});
test('missing process references require recorded blockers', () => {
  const value = clone(); value.processes = [];
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /process reference/i);
});
test('completed process cannot have a failed integration gate', () => {
  const value = clone(); value.processes[0].state = 'completed'; value.processes[0].integration.status = 'failed';
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /process completion/i);
});
test('process binding freshness must match individual bindings', () => {
  const value = clone(); value.processes[0].bindings_current = !value.processes[0].bindings_current;
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /binding/i);
});
test('current integration receipt cannot omit its version', () => {
  const value = clone();
  value.processes[0].integration.current = true;
  value.processes[0].integration.version = null;
  assert.throws(() => parseSnapshot(JSON.stringify(value)), /version/i);
});
