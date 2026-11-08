export type Change = 'added' | 'removed' | 'modified' | 'unchanged';
export type MapView = 'changes' | 'before' | 'after';
export type FileNode = {
  id: string; beforePath: string | null; afterPath: string | null; status: Change;
  renamed: boolean; renameScore: number | null; module: string; language: string;
};
export type Evidence = {
  revision: string; path: string; startLine: number; endLine: number; text: string;
};
export type ImportEdge = {
  id: string; source: string; target: string; kind: string; status: Change;
  before: Evidence[]; after: Evidence[];
};
export type Comparison = {
  id: string; name: string; sourceRoot: string; baseRef: string; headRef: string;
  baseSha: string; headSha: string; mergeBaseSha: string;
  nodes: FileNode[]; edges: ImportEdge[];
  notices: {revision: string; path: string; reason: string; line?: number}[];
  limits: {files: number; fileBytes: number; totalBytes: number};
};
export type Source = {path: string; revision: string; content: string};
export type Detail = {id: string; nodeId: string; before: Source | null; after: Source | null; diff: string};
export const fileName = (node: FileNode) => node.afterPath || node.beforePath || '';
export const shortSha = (sha: string) => sha.slice(0, 10);

export function neighborhood(comparison: Comparison) {
  const changed = new Set(comparison.nodes.filter(n => n.status !== 'unchanged').map(n => n.id));
  comparison.edges.filter(e => e.status !== 'unchanged').forEach(e => {changed.add(e.source); changed.add(e.target);});
  const result = new Set(changed);
  comparison.edges.forEach(e => {
    if (changed.has(e.source) || changed.has(e.target)) {result.add(e.source); result.add(e.target);}
  });
  return result;
}

// Lay out the union once. Version toggles only change appearance, never coordinates.
export function layout(nodes: FileNode[]) {
  const groups = new Map<string, FileNode[]>();
  [...nodes].sort((a, b) => fileName(a).localeCompare(fileName(b))).forEach(node => {
    groups.set(node.module, [...(groups.get(node.module) || []), node]);
  });
  const positions = new Map<string, {x: number; y: number}>();
  const modules: {name: string; y: number; height: number}[] = [];
  let y = 16;
  [...groups.keys()].sort().forEach(name => {
    const files = groups.get(name)!;
    const height = 42 + Math.ceil(files.length / 3) * 112;
    modules.push({name, y, height});
    files.forEach((file, i) => positions.set(file.id, {x: 28 + (i % 3) * 310, y: y + 40 + Math.floor(i / 3) * 112}));
    y += height + 20;
  });
  return {positions, modules, height: Math.max(y, 180)};
}
