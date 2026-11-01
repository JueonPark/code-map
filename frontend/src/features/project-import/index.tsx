import { useEffect, useState } from 'react';
import { currentProject, localRequest, Project } from '@/project';
export default function ProjectImport() {
  const [path, setPath] = useState('');
  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<{ready: boolean; model: string; roots: string[] } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const current = currentProject();
  useEffect(() => { localRequest('status').then(setStatus).catch(e => setError(e.message)); }, []);
  async function load(kind: string, input: unknown) {
    setBusy(true); setError(''); setProject(null); setConsent(false);
    try { setProject(await localRequest('import/' + kind, input)); setStatus(await localRequest('status')); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function start(view: string) {
    if (!project || !consent) return;
    setBusy(true); setError('');
    try {
      await localRequest('approve', { id: project.id });
      sessionStorage.setItem('codemap-project', JSON.stringify({id: project.id, name: project.name}));
      // Full navigation clears graph, node-selection, and conversation state.
      window.location.assign('/understand/' + view);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); }
  }
  return <main className="mx-auto max-w-4xl p-8 overflow-y-auto h-screen">
    <h1 className="text-3xl font-semibold">Import a project</h1>
    <p className="my-4">Choose a directory or ZIP archive. Review the source list before sending anything to AI.</p>
    {current && <p className="mb-4">Current project: <strong>{current.name}</strong>. Import another project to switch.</p>}
    <form onSubmit={e => {e.preventDefault(); void load('path', {path});}} className="border rounded-lg p-4">
      <label htmlFor="project-path">Local directory path</label>
      <input id="project-path" value={path} onChange={e => setPath(e.target.value)} placeholder="Path accessible to the local service" className="border rounded p-2 w-full my-2" />
      <p className="text-sm text-gray-600 mb-3">Paths are read by the local service. Run it inside WSL for Linux paths, or on Windows for Windows/WSL UNC paths.</p>
      <button disabled={busy || !path.trim()} className="bg-blue-700 disabled:opacity-40 text-white rounded px-4 py-2">Preview directory</button>
    </form>
    <label className="block border rounded-lg p-4 my-4">ZIP archive (up to 10 MiB)
      <input aria-label="ZIP archive" type="file" accept=".zip,application/zip" disabled={busy} className="block mt-2" onChange={e => {const file=e.target.files?.[0]; if(file) void load('zip', file); e.target.value='';}} />
    </label>
    {busy && <p role="status">Working…</p>}
    {error && <p role="alert" className="p-3 bg-red-50 text-red-800 rounded">{error}</p>}
    {status && <p className="text-sm my-3">Allowed directories: {status.roots.join(', ')}. {status.ready ? 'Analysis model: ' + status.model : 'Analysis unavailable: set OPENAI_API_KEY and OPENAI_MODEL on the local service. You can still preview imports.'}</p>}
    {project && <section className="border rounded-lg p-5 my-4">
      <h2 className="text-xl font-semibold">{project.name} — import complete</h2>
      <p>{project.files.length} files · {project.size.toLocaleString()} bytes. Original files are read-only.</p>
      <h3 className="font-semibold mt-4">Files sent when you start analysis</h3>
      <ul className="max-h-64 overflow-auto text-sm font-mono bg-gray-50 p-3 my-2">{project.files.map(f => <li key={f.path}>{f.path} ({f.size} bytes)</li>)}</ul>
      <details><summary>{project.excluded.length} excluded entries</summary><ul className="max-h-40 overflow-auto text-sm">{project.excluded.map((f,i) => <li key={i}>{f.path}: {f.reason}</li>)}</ul></details>
      <label className="block my-4"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> I reviewed these files. Send their complete contents and my questions to OpenAI for analysis. API charges may apply.</label>
      <div className="flex gap-3 flex-wrap">{[['business-comps', 'Business Components'], ['function-call', 'Function Call']].map(([view,label]) => <button key={view} disabled={busy || !consent || !status?.ready} onClick={() => void start(view)} className="bg-blue-700 disabled:opacity-40 text-white rounded px-4 py-2">Analyze {label}</button>)}</div>
    </section>}
  </main>;
}
