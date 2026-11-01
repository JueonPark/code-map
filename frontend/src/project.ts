export type Project = { id: string; name: string; size: number; files: { path: string; size: number }[]; excluded: { path: string; reason: string }[] };
export function currentProject(): { id: string; name: string } | null {
  try { return JSON.parse(sessionStorage.getItem('codemap-project') || 'null'); } catch { return null; }
}
export async function localRequest(path: string, body: unknown = {}) {
  const response = await fetch('/api/' + path, {
    method: 'POST', headers: { 'Content-Type': body instanceof File ? 'application/zip' : 'application/json', 'X-CodeMap-Request': '1' },
    body: body instanceof File ? body : JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({ error: 'Start the CodeMap local service, then retry.' }));
  if (!response.ok) throw new Error(result.error || 'Local service request failed.');
  return result;
}
export async function analyzeProject(prompt: string, history: {role: string; content: string}[] = []) {
  const project = currentProject();
  if (!project) throw new Error('Import and approve a project from the home page first.');
  return (await localRequest('analyze', { id: project.id, prompt, history })).text as string;
}
