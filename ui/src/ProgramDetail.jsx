import { useState } from 'react';

export const humanize = (value) => value.replaceAll('_', ' ');
export const Status = ({ value }) => <span className={`status status-${value}`}>{humanize(value)}</span>;
const Count = ({ value }) => value === null ? <span className="muted">Not recorded</span> : value.toLocaleString();
const Evidence = ({ refs }) => refs.length ? <ul className="reference-list">{refs.map((ref) => <li key={ref}><code>{ref}</code></li>)}</ul> : <p className="muted">No evidence reference recorded.</p>;

function Overview({ program }) {
  return <>
    <dl className="detail-facts">
      <div><dt>Current version</dt><dd><code>{program.current_version ?? 'Not recorded'}</code></dd></div>
      <div><dt>Rule catalog</dt><dd>{program.catalog_complete ? 'Recorded complete' : 'Incomplete or unverified'}</dd></div>
      <div><dt>Processes</dt><dd>{program.process_ids.join(', ') || 'No process binding'}</dd></div>
    </dl>
    <h3>Acceptance gates</h3>
    <ul className="gate-list">{program.gates.map((gate) => <li key={gate.gate_id}>
      <span>{humanize(gate.gate_id)}<small>{gate.current ? 'Current version' : 'Version not current'} · {gate.evidence_refs.length} evidence refs</small></span>
      <Status value={gate.status} />
    </li>)}</ul>
    <h3>Blockers and findings</h3>
    {program.blockers.length === 0 && program.findings.length === 0 ? <p className="muted">No blockers or findings recorded.</p> : <ul className="finding-list">
      {program.blockers.map((row, index) => <li key={`${row.blocker_id}-${index}`}><code>{row.blocker_id}</code><span>{humanize(row.category)}</span></li>)}
      {program.findings.map((row) => <li key={row.finding_id}><code>{row.finding_id}</code><span>{row.severity} · {row.resolved ? 'resolution recorded' : 'unresolved'}</span></li>)}
    </ul>}
  </>;
}

function Rules({ program }) {
  return <>
    <p className="detail-intro">Every retained rule needs 100 positive and 100 negative passing cases, with current evidence.</p>
    <p className="rule-totals">{program.rule_counts.business} business · {program.rule_counts.technical} technical · {program.rule_counts.mixed} mixed</p>
    {!program.rules.length ? <p className="muted">No rules recorded. A complete catalog is still required.</p> : <div className="detail-table-scroll" tabIndex="0" role="region" aria-label="Rule validation table"><table className="detail-table">
      <thead><tr><th>Rule</th><th>Positive</th><th>Negative</th><th>Evidence</th></tr></thead>
      <tbody>{program.rules.map((rule) => <tr key={rule.rule_id}>
        <th scope="row"><code>{rule.rule_id}</code><small>{rule.category} · {rule.lifecycle}</small></th>
        <td><Count value={rule.positive_passed} /><small>of 100 required</small></td>
        <td><Count value={rule.negative_passed} /><small>of 100 required</small></td>
        <td>{rule.lifecycle === 'retired' ? 'Retired' : rule.quota_met ? 'Quota met' : 'Gap'}<small>{rule.current ? 'Current' : 'Not current'}</small></td>
      </tr>)}</tbody>
    </table></div>}
  </>;
}

function References({ program }) {
  return <>
    <p className="detail-intro">References identify recorded receipts. This viewer does not open artifacts or independently verify their contents.</p>
    {['conversion', 'rule_catalog', 'retirement'].map((name) => <section className="evidence-group" key={name}><h3>{humanize(name)}</h3><p className="muted">{humanize(program[name].status)} · {program[name].current ? 'Current version' : 'Not current'}</p><Evidence refs={program[name].evidence_refs} /></section>)}
    {program.gates.map((gate) => <section className="evidence-group" key={gate.gate_id}><h3>{humanize(gate.gate_id)}</h3><Evidence refs={gate.evidence_refs} /></section>)}
    {program.rules.map((rule) => <section className="evidence-group" key={rule.rule_id}><h3>Rule {rule.rule_id}</h3><Evidence refs={rule.evidence_refs} /></section>)}
    {program.findings.map((finding) => <section className="evidence-group" key={finding.finding_id}><h3>Finding {finding.finding_id}</h3><Evidence refs={finding.evidence_refs} /></section>)}
  </>;
}

function Dependencies({ program }) {
  return <>
    <h3>Process bindings</h3>
    {(program.consumers ?? []).length ? <ul className="binding-list">{program.consumers.map((row, index) => <li key={`${row.process_id}-${row.step_id}-${index}`}>
      <strong>{row.process_id} / {row.step_id}</strong><span>{row.provider} · {row.version ?? 'No version'} · {row.current ? 'Current' : 'Not current'}</span>
    </li>)}</ul> : <p className="muted">No detailed process bindings recorded.</p>}
    <h3>Sparkflow migration</h3>
    <p className="detail-intro">Python stays active until the replacement flow and affected dependencies are validated.</p>
    {!program.migrations.length ? <p className="muted">No ETL migration steps recorded.</p> : <ul className="binding-list">{program.migrations.map((flow) => <li key={flow.migration_id}>
      <strong>{flow.label}</strong><code>{flow.migration_id}</code><span>{humanize(flow.stage)}{flow.blocked ? ' · Blocked' : ''}</span>
      <span>Depends on: {flow.depends_on.join(', ') || 'None recorded'}</span>
    </li>)}</ul>}
  </>;
}

export function ProgramDetail({ program, onClose }) {
  const [tab, setTab] = useState('Overview');
  return <aside className="program-detail" aria-label={`Details for ${program.program_id}`}>
    <div className="detail-heading"><div><h2>{program.program_id}</h2><p>{program.label}</p></div><button className="text-button" onClick={onClose} aria-label="Close program details">Close</button></div>
    <div className="detail-status"><Status value={program.state} /><span>Recorded status</span></div>
    <nav className="detail-tabs" aria-label="Program detail views">{['Overview', 'Rules', 'Evidence', 'Dependencies'].map((name) => <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}</nav>
    <div className="detail-content">
      {tab === 'Overview' && <Overview program={program} />}
      {tab === 'Rules' && <Rules program={program} />}
      {tab === 'Evidence' && <References program={program} />}
      {tab === 'Dependencies' && <Dependencies program={program} />}
    </div>
  </aside>;
}
