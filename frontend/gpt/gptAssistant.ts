import { analyzeProject, currentProject } from '@/project';
import { prompts, PromptName } from './prompts';
const pending = new Map<string, Promise<string>>();
export async function requestAssistant(promptName: PromptName, content: string): Promise<string> {
  const prompt = prompts[promptName];
  if (!prompt) throw new Error('Unsupported analysis prompt: ' + promptName);
  const key = JSON.stringify([currentProject()?.id, promptName, content]);
  let request = pending.get(key);
  if (!request) {
    request = analyzeProject(prompt.content + '\n\n' + content).finally(() => pending.delete(key));
    pending.set(key, request);
  }
  return request;
}
