import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { localRequest } from '@/project';
import Graph from './Graph';
import SourceDetail from './SourceDetail';
import { Change, Comparison, ImportEdge, MapView, fileName, neighborhood, shortSha } from './model';
import './style.css';

const changes: Change[] = ['added', 'removed', 'modified', 'unchanged'];

function ComparisonView({comparison}: {comparison: Comparison}) {
  const [view, setView] = useState<MapView>('changes');
  const [focus, setFocus] = useState(true);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [edge, setEdge] = useState<ImportEdge | null>(null);
  const related = useMemo(() => neighborhood(comparison), [comparison]);
  const nodes = useMemo(() => comparison.nodes.filter(n => (!focus || related.size === 0 || related.has(n.id))
    && `${n.beforePath || ''} ${n.afterPath || ''}`.toLowerCase().includes(query.toLowerCase())), [comparison, focus, related, query]);
  const counts = changes.map(status => ({status, count: comparison.nodes.filter(n => n.status === status).length}));
  const selectNode = (id: string) => {setSelected(id); setEdge(null);};
  const selectEdge = (value: ImportEdge) => {setSelected(value.source); setEdge(value);};
  const node = comparison.nodes.find(n => n.id === selected);
  return <section className="comparison-result">
    <div className="comparison-result-heading"><div><p className="comparison-eyebrow">PINNED COMPARISON · PYTHON IMPORTS</p><h2>{comparison.name} — structural changes</h2></div><span className="local-pill">Local analysis · no AI calls</span></div>
    <div className="revision-grid">
      <div><span>Before · merge base</span><code title={comparison.mergeBaseSha}>{shortSha(comparison.mergeBaseSha)}</code></div>
      <div><span>After · {comparison.headRef}</span><code title={comparison.headSha}>{shortSha(comparison.headSha)}</code></div>
      <div><span>Requested base · {comparison.baseRef}</span><code title={comparison.baseSha}>{shortSha(comparison.baseSha)}</code></div>
    </div>
    <p className="comparison-muted">Source directory: {comparison.sourceRoot || '(repository root)'}. Files are grouped by their original directory across both revisions. Uncommitted changes are excluded.</p>
    <div className="change-summary">{counts.map(({status, count}) => <span className={`change-badge ${status}`} key={status}>{count} {status}</span>)}<span>{comparison.edges.filter(e => e.status !== 'unchanged').length} changed import relationships</span></div>
    {related.size === 0 && <p className="empty-message">No file or resolved dependency changes in this comparison.</p>}
    <div className="map-controls">
      <div className="comparison-tabs">{(['changes', 'before', 'after'] as const).map(value => <button key={value} aria-pressed={view === value} onClick={() => setView(value)}>{value === 'changes' ? 'Changes map' : value === 'before' ? 'Before map' : 'After map'}</button>)}</div>
      <label><input type="checkbox" checked={focus} onChange={e => setFocus(e.target.checked)} /> Changed neighborhood</label>
      <input aria-label="Filter files" placeholder="Filter files or directories…" value={query} onChange={e => setQuery(e.target.value)} />
    </div>
    <p className="comparison-muted">Arrows point from importer to imported file. Faded elements are absent in the selected revision; positions stay fixed. Showing {nodes.length} of {comparison.nodes.length} files.</p>
    <div className="comparison-map-layout">
      <nav className="comparison-file-list" aria-label="Comparison files">{nodes.length ? nodes.map(n => <button key={n.id} aria-label={`Inspect ${fileName(n)}`} aria-pressed={selected === n.id} onClick={() => selectNode(n.id)}>
        <span className={`file-dot ${n.status}`} /><span>{fileName(n)}{n.renamed && <small>was {n.beforePath}</small>}</span><small>{n.status}</small>
      </button>) : <p>No files match this filter.</p>}</nav>
      <Graph comparison={comparison} nodes={nodes} view={view} selected={selected} selectedEdge={edge?.id || null} onNode={selectNode} onEdge={selectEdge} />
    </div>
    {node ? <SourceDetail key={node.id} comparison={comparison} node={node} edge={edge} onNode={selectNode} /> : <div className="comparison-empty">Select a file or arrow to follow a structural change to its source and diff.</div>}
    <details className="comparison-coverage"><summary>Analysis coverage · {comparison.notices.length} notices</summary>
      <p>Only statically resolvable Python imports under the selected source directory produce edges. No resolved edge does not mean no dependency. Limits per snapshot: {comparison.limits.files.toLocaleString()} entries, {comparison.limits.fileBytes / 1024} KiB per file, {comparison.limits.totalBytes / 1024 / 1024} MiB total.</p>
      <ul>{comparison.notices.map((notice, i) => <li key={i}><code>{shortSha(notice.revision)} · {notice.path}{notice.line ? ':' + notice.line : ''}</code><span>{notice.reason}</span></li>)}</ul>
    </details>
  </section>;
}

export default function StructuralCompare() {
  const [path, setPath] = useState('');
  const [base, setBase] = useState('main');
  const [head, setHead] = useState('HEAD');
  const [sourceRoot, setSourceRoot] = useState('');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRef(0);
  useEffect(() => () => {requestId.current += 1;}, []);
  async function compare(event: FormEvent) {
    event.preventDefault();
    const request = ++requestId.current;
    setComparison(null); setBusy(true); setError('');
    try {
      const result: Comparison = await localRequest('compare', {path: path.trim(), base: base.trim(), head: head.trim(), sourceRoot: sourceRoot.trim()});
      if (requestId.current === request) setComparison(result);
    } catch (e) {if (requestId.current === request) setError(e instanceof Error ? e.message : String(e));}
    finally {if (requestId.current === request) setBusy(false);}
  }
  return <div className="structural-compare">
    <header className="comparison-header"><Link to="/">← CodeMap projects</Link><span>PR review workspace</span></header>
    <div className="comparison-intro"><p className="comparison-eyebrow">UNDERSTAND WHAT CHANGED</p><h1>Review structural changes</h1><p>Compare committed versions, see the changed dependencies, and follow each relationship to the code behind it.</p></div>
    <form onSubmit={event => void compare(event)} className="comparison-form">
      <label className="repository-input">Git repository path<input required disabled={busy} value={path} onChange={e => setPath(e.target.value)} placeholder="Repository path accessible to the local service" /></label>
      <label>Base ref<input required disabled={busy} value={base} onChange={e => setBase(e.target.value)} /></label>
      <label>Head ref<input required disabled={busy} value={head} onChange={e => setHead(e.target.value)} /></label>
      <label>Python source directory <span>(optional)</span><input disabled={busy} value={sourceRoot} onChange={e => setSourceRoot(e.target.value)} placeholder="e.g. src or python" /></label>
      <button className="compare-submit" disabled={busy || !path.trim() || !base.trim() || !head.trim()}>{busy ? 'Comparing…' : 'Compare revisions'}</button>
      <p>Paths are resolved by the local service, including WSL paths when it runs in WSL. Comparison uses the merge base and head. Source stays local and your working tree is unchanged.</p>
    </form>
    {busy && <p role="status" className="comparison-empty">Reading committed snapshots and resolving Python imports…</p>}
    {error && <p role="alert" className="comparison-error">{error}</p>}
    {comparison && <ComparisonView key={comparison.id} comparison={comparison} />}
  </div>;
}
