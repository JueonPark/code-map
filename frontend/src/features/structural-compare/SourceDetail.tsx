import { useEffect, useRef, useState } from 'react';
import { localRequest } from '@/project';
import { Comparison, Detail, FileNode, ImportEdge, Source, fileName, shortSha } from './model';

function SourceLines({source, ranges}: {source: Source; ranges: {startLine: number; endLine: number}[]}) {
  const container = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const first = container.current?.querySelector<HTMLElement>('.evidence-line');
    if (first && container.current) container.current.scrollTop = Math.max(0, first.offsetTop - container.current.offsetTop - 30);
  }, [source, ranges]);
  return <pre ref={container} className="source-code">{source.content.split(/\r?\n/).map((line, i) => <span key={i} data-source-line={i + 1}
    className={ranges.some(r => i + 1 >= r.startLine && i + 1 <= r.endLine) ? 'source-line evidence-line' : 'source-line'}>
    <span className="line-number" aria-hidden="true">{i + 1}</span><code>{line || ' '}</code>
  </span>)}</pre>;
}

export default function SourceDetail({comparison, node, edge, onNode}: {
  comparison: Comparison; node: FileNode; edge: ImportEdge | null; onNode: (id: string) => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<'diff' | 'before' | 'after'>('diff');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setDetail(null); setError('');
    localRequest('compare/detail', {id: comparison.id, nodeId: node.id}).then((value: Detail) => {
      if (active && value.id === comparison.id && value.nodeId === node.id) setDetail(value);
    }).catch(e => {if (active) setError(e instanceof Error ? e.message : String(e));});
    return () => {active = false;};
  }, [comparison.id, node.id, attempt]);
  const byId = new Map(comparison.nodes.map(n => [n.id, n]));
  const incoming = comparison.edges.filter(e => e.target === node.id);
  const outgoing = comparison.edges.filter(e => e.source === node.id);
  const source = detail && tab !== 'diff' ? detail[tab] : null;
  const ranges = edge && tab !== 'diff' ? edge[tab] : [];
  return <section className="comparison-detail" data-testid="source-detail" aria-label="Source and diff evidence">
    <p className="comparison-breadcrumb">{comparison.name} / {node.module} / {fileName(node).split('/').pop()}</p>
    <h3>{fileName(node)}</h3>
    <p><span className={`change-badge ${node.status}`}>{node.status}</span>{node.renamed && ` Git rename: ${node.beforePath} → ${node.afterPath} (${node.renameScore}% similarity)`}</p>
    {edge && <div className="edge-evidence">
      <strong>Import evidence: {fileName(byId.get(edge.source)!)} → {fileName(byId.get(edge.target)!)}</strong>
      {(['before', 'after'] as const).map(side => edge[side].map((e, i) => <button key={`${side}-${i}`} onClick={() => setTab(side)}>
        {side === 'before' ? 'Before' : 'After'}: {e.path}:{e.startLine}–{e.endLine} · {shortSha(e.revision)}
      </button>))}
    </div>}
    <div className="comparison-tabs" aria-label="Evidence view">{(['diff', 'before', 'after'] as const).map(value => <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{value === 'diff' ? 'Diff' : value === 'before' ? 'Before source' : 'After source'}</button>)}</div>
    {error ? <div role="alert"><p>{error}</p><button onClick={() => setAttempt(n => n + 1)}>Retry evidence</button></div> : !detail ? <p role="status">Loading pinned source…</p> : tab === 'diff' ? <pre className="source-code diff-code">{detail.diff.split('\n').map((line, i) => <span key={i} className={`source-line ${line.startsWith('+') ? 'diff-added' : line.startsWith('-') ? 'diff-removed' : ''}`}>{line || ' '}</span>)}</pre> : source ? <>
      <p className="source-caption">{source.path} · <code>{source.revision}</code></p>
      <SourceLines source={source} ranges={ranges} />
    </> : <p>This file does not exist in this revision.</p>}
    <div className="comparison-relations">
      <div><h4>Direct importers · review candidates</h4>{incoming.length ? incoming.map(e => <button key={e.id} onClick={() => onNode(e.source)}>{fileName(byId.get(e.source)!)} <span className={`change-badge ${e.status}`}>{e.status}</span></button>) : <p>No resolved direct importers in the analyzed scope.</p>}</div>
      <div><h4>Imports from this file</h4>{outgoing.length ? outgoing.map(e => <button key={e.id} onClick={() => onNode(e.target)}>{fileName(byId.get(e.target)!)} <span className={`change-badge ${e.status}`}>{e.status}</span></button>) : <p>No resolved imports in the analyzed scope.</p>}</div>
    </div>
    <p className="comparison-muted">Relationships are static source observations, including conditional imports. They do not prove execution or downstream behavior changes.</p>
  </section>;
}
