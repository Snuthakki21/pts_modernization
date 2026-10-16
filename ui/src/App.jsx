import { useMemo, useRef, useState } from 'react';
import { MAX_BYTES, STATES, parseSnapshot, selectPrograms } from './snapshot.mjs';
import { ProgramDetail, Status, humanize } from './ProgramDetail.jsx';
import demo from './demo-progress.json';

function Summary({ snapshot }) {
  const counts = snapshot?.counters;
  return <section className="inventory-summary" aria-label="Full inventory totals">
    <div className="completion-line"><h2>Inventory at a glance</h2><p>{counts ? <><strong>{counts.completed_programs} of {counts.active_programs}</strong> active programs completed</> : 'Import a snapshot to see recorded progress.'}</p></div>
    <dl className="summary-ledger">
      {[['Total inventory', counts?.total_programs], ['Completed', counts?.completed_programs], ['Converted', counts?.converted_programs], ['Blocked', counts?.blocked_programs], ['Stale', counts?.stale_programs], ['Retired', counts?.retired_programs]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === undefined ? <span className="not-loaded">Not loaded</span> : value.toLocaleString()}</dd></div>)}
    </dl>
    <p className="summary-note">Completed includes recorded rule quotas, comparison, trace, quality, security and independent audit gates. Converted alone is not completed.</p>
  </section>;
}

function ProgramTable({ programs, selected, onSelect }) {
  const [page, setPage] = useState(0);
  const lastPage = Math.max(0, Math.ceil(programs.length / 50) - 1);
  const currentPage = Math.min(page, lastPage);
  return <><div className="table-scroll" role="region" tabIndex="0" aria-label="Conversion inventory table"><table className="inventory-table">
    <thead><tr><th scope="col">Program</th><th scope="col">Process</th><th scope="col">Recorded status</th><th scope="col">Rule quotas</th><th scope="col">Gates</th></tr></thead>
    <tbody>{programs.slice(currentPage * 50, currentPage * 50 + 50).map((program) => <tr key={program.program_id} className={selected === program.program_id ? 'selected' : ''}>
      <th scope="row"><button className="program-link" aria-pressed={selected === program.program_id} onClick={() => onSelect(program.program_id)}>{program.program_id}</button><small>{program.label}</small></th>
      <td>{program.process_ids.join(', ') || <span className="muted">Unassigned</span>}</td>
      <td><Status value={program.state} /></td>
      <td><strong>{program.rule_counts.quota_met} / {program.rule_counts.retained}</strong><small>retained rules</small></td>
      <td>{program.gates.filter((gate) => ['passed', 'approved_difference'].includes(gate.status) && gate.current && gate.evidence_refs.length).length} / {program.gates.length}<small>recorded ready</small></td>
    </tr>)}</tbody>
  </table></div>{lastPage > 0 && <div className="pagination"><button className="secondary-button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><span>Page {currentPage + 1} of {lastPage + 1}</span><button className="secondary-button" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>Next</button></div>}</>;
}

export function App() {
  const [snapshot, setSnapshot] = useState(null);
  const [query, setQuery] = useState('');
  const [state, setState] = useState('');
  const [process, setProcess] = useState('');
  const [sort, setSort] = useState('program');
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const fileInput = useRef(null);
  const selectedButton = useRef(null);
  const load = (next) => {
    setSnapshot(next); setSelected(null); setQuery(''); setState(''); setProcess(''); setError('');
    setMessage(`${next.fictional ? 'Fictional demo' : 'Snapshot'} loaded. ${next.programs.length} programs.`);
  };
  const importFile = async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    setBusy(true); setError('');
    try {
      if (file.size > MAX_BYTES) throw new Error('File exceeds the 8 MiB limit. Export a smaller snapshot.');
      load(parseSnapshot(await file.text()));
    } catch (problem) { setError(problem.message || 'Unable to read this snapshot. Try exporting it again.'); }
    finally { setBusy(false); event.target.value = ''; }
  };
  const programs = useMemo(() => selectPrograms(snapshot?.programs ?? [], query, state, process, sort), [snapshot, query, state, process, sort]);
  const program = snapshot?.programs.find((item) => item.program_id === selected);
  const clearFilters = () => { setQuery(''); setState(''); setProcess(''); };
  const selectProgram = (id) => { selectedButton.current = document.activeElement; setSelected(id); };
  const closeDetail = () => { setSelected(null); selectedButton.current?.focus(); };
  return <>
    <a className="skip-link" href="#main">Skip to inventory</a>
    <header className="masthead"><div className="masthead-inner"><a className="wordmark" href="#main">Conversion workspace</a><span className="read-only">Read-only view</span></div></header>
    <nav className="workspace-nav" aria-label="Workspace"><a href="#inventory" aria-current="page">Program inventory</a><a href="#snapshot-context">Snapshot details</a></nav>
    <main id="main">
      <div className="page-heading"><div><h1>Conversion progress</h1><p>From mainframe inventory to validated, reusable code.</p></div><div className="file-actions">
        <button className="secondary-button" disabled={busy} onClick={() => { try { load(parseSnapshot(JSON.stringify(demo))); } catch (problem) { setError(problem.message); } }}>Load fictional demo</button>
        <button className="primary-button" disabled={busy} onClick={() => fileInput.current?.click()}>{busy ? 'Reading snapshot…' : 'Import snapshot'}</button>
        <input ref={fileInput} type="file" accept="application/json,.json" onChange={importFile} className="visually-hidden" aria-label="Select sanitized progress snapshot" tabIndex="-1" />
      </div></div>
      <p className="visually-hidden" role="status" aria-live="polite">{message}</p>
      {error && <div className="notice notice-error" role="alert"><strong>Snapshot not loaded.</strong> {error} Your previous view is unchanged.</div>}
      {snapshot?.fictional && <div className="notice notice-demo"><strong>Fictional demo.</strong> These programs and results illustrate the workspace. They are not application evidence.<button className="text-button" onClick={() => { setSnapshot(null); setSelected(null); clearFilters(); setMessage('Demo cleared.'); }}>Clear demo</button></div>}
      <Summary snapshot={snapshot} />
      <section id="inventory" className="inventory-section" aria-labelledby="inventory-title">
        <div className="section-heading"><h2 id="inventory-title">Program inventory</h2><span>{programs.length} shown / {snapshot?.programs.length ?? 0} total</span></div>
        <div className="filters">
          <label className="search-field">Search programs<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Program ID or name" disabled={!snapshot} /></label>
          <label>Process<select value={process} onChange={(event) => setProcess(event.target.value)} disabled={!snapshot}><option value="">All processes</option>{snapshot?.processes.map((row) => <option key={row.process_id} value={row.process_id}>{row.process_id}</option>)}</select></label>
          <label>Status<select value={state} onChange={(event) => setState(event.target.value)} disabled={!snapshot}><option value="">All statuses</option>{STATES.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label>
          <label>Sort by<select value={sort} onChange={(event) => setSort(event.target.value)} disabled={!snapshot}><option value="program">Program ID</option><option value="status">Status</option><option value="gaps">Most rule gaps</option></select></label>
        </div>
        <div className={`work-area ${program ? 'has-selection' : ''}`}>
          <div className="inventory-content" aria-busy={busy}>
            {!snapshot ? <div className="empty-state"><h3>Your inventory starts here</h3><p>Import a sanitized progress snapshot to compare total programs with completed conversions and inspect the evidence behind each status.</p><p className="muted">Data stays in this browser tab. Reloading clears the view.</p></div> : !programs.length ? <div className="empty-state"><h3>{snapshot.programs.length ? 'No programs match these filters' : 'No programs recorded'}</h3><p>{snapshot.programs.length ? 'Try a different program, process or status.' : 'This snapshot contains no program inventory. Nothing has been marked complete.'}</p>{snapshot.programs.length > 0 && <button className="secondary-button" onClick={clearFilters}>Clear filters</button>}</div> : <ProgramTable programs={programs} selected={selected} onSelect={selectProgram} />}
          </div>
          {program && <ProgramDetail key={program.program_id} program={program} onClose={closeDetail} />}
        </div>
      </section>
      <section id="snapshot-context" className="snapshot-context"><h2>Snapshot details</h2>{snapshot ? <>
        <dl><div><dt>Observed</dt><dd>{new Date(snapshot.observed_at).toLocaleString()}</dd></div><div><dt>Inventory coverage</dt><dd>{humanize(snapshot.inventory_status)} · declared, not independently verified</dd></div><div><dt>Inventory fingerprint</dt><dd><code>{snapshot.inventory_sha256}</code></dd></div></dl>
        <p>Counts describe this snapshot only. Check the source inventory and evidence before accepting a conversion.</p>
      </> : <p>No snapshot loaded. The demo is optional and clearly labeled.</p>}</section>
    </main>
    <footer>Conversion workspace · Local evidence viewer · Independent design inspired by public banking interfaces.</footer>
  </>;
}
