import { useMemo } from 'react';
import { Comparison, FileNode, ImportEdge, MapView, fileName, layout } from './model';

const colors = {added: '#16825e', removed: '#be3b48', modified: '#b07610', unchanged: '#748297'};

export default function Graph({comparison, nodes, view, selected, selectedEdge, onNode, onEdge}: {
  comparison: Comparison; nodes: FileNode[]; view: MapView; selected: string | null; selectedEdge: string | null;
  onNode: (id: string) => void; onEdge: (edge: ImportEdge) => void;
}) {
  const {positions, modules, height} = useMemo(() => layout(nodes), [nodes]);
  const byId = new Map(comparison.nodes.map(n => [n.id, n]));
  return <div className="comparison-graph-scroll" aria-label="Dependency map">
    <svg className="comparison-graph" width="960" height={height} viewBox={`0 0 960 ${height}`} aria-label="File dependency graph">
      <defs>{Object.entries(colors).map(([status, color]) => <marker key={status} id={`arrow-${status}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill={color} /></marker>)}</defs>
      {modules.map(group => <g key={group.name}>
        <rect x="12" y={group.y} width="932" height={group.height} rx="12" fill="#f6f8fb" stroke="#dde4ee" />
        <text x="28" y={group.y + 25} className="module-label">{group.name === '.' ? 'Repository root' : group.name}</text>
      </g>)}
      {comparison.edges.map(edge => {
        const start = positions.get(edge.source), end = positions.get(edge.target);
        if (!start || !end) return null;
        const path = edge.source === edge.target
          ? `M${start.x + 270},${start.y + 15} C${start.x + 302},${start.y - 15} ${start.x + 302},${start.y + 85} ${start.x + 270},${start.y + 50}`
          : `M${start.x + 140},${start.y + 64} C${start.x + 140},${start.y + 104} ${end.x + 140},${end.y - 38} ${end.x + 140},${end.y}`;
        const absent = view !== 'changes' && edge[view].length === 0;
        const color = colors[edge.status];
        const label = `Inspect import ${fileName(byId.get(edge.source)!)} → ${fileName(byId.get(edge.target)!)}`;
        return <g key={edge.id} role="button" tabIndex={0} aria-label={label} opacity={absent ? 0.13 : 1}
          onClick={() => onEdge(edge)} onKeyDown={event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); onEdge(edge);}}}>
          <title>{label} ({edge.status})</title>
          <path d={path} fill="none" stroke="transparent" strokeWidth="16" />
          <path d={path} fill="none" stroke={color} strokeWidth={selectedEdge === edge.id ? 4 : 2} strokeDasharray={edge.status === 'removed' ? '6 4' : undefined} markerEnd={`url(#arrow-${edge.status})`} />
        </g>;
      })}
      {nodes.map(node => {
        const position = positions.get(node.id)!;
        const path = (view === 'before' ? node.beforePath : node.afterPath) || fileName(node);
        const absent = view === 'before' ? !node.beforePath : view === 'after' ? !node.afterPath : false;
        return <g key={node.id} data-node-id={node.id} transform={`translate(${position.x},${position.y})`} role="button" tabIndex={0}
          aria-label={`Select ${fileName(node)}`} onClick={() => onNode(node.id)}
          onKeyDown={event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); onNode(node.id);}}} opacity={absent ? 0.3 : 1}>
          <title>{path} · {node.status}{absent ? ' · absent in this revision' : ''}</title>
          <rect width="280" height="64" rx="8" fill="white" stroke={selected === node.id ? '#2464ce' : colors[node.status]} strokeWidth={selected === node.id ? 3 : 1.5} />
          <rect width="5" height="44" x="1" y="10" rx="2" fill={colors[node.status]} />
          <text x="15" y="26" className="file-label">{path.length > 32 ? '…' + path.slice(-31) : path}</text>
          <text x="15" y="47" className="status-label">{node.renamed ? 'renamed · ' : ''}{node.status}{absent ? ' · absent' : ''}</text>
        </g>;
      })}
    </svg>
  </div>;
}
