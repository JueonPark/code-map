import { analyzeProject, currentProject } from '@/project';
import { prompts, PromptName } from './prompts';
const pending = new Map<string, Promise<string>>();
export function validateAnalysis(promptName: PromptName, result: string): string {
  const graphPrompts = ['P2_R2_systemStructureDot', 'P3_R3_businessLocalGraph', 'P7_R7_projectStructureJson', 'P9_R9_functionCallFlow'];
  const jsonPrompts = ['P2_R2_systemStructureDot', 'P7_R7_projectStructureJson', 'P4_R4_businessFlowAnalysis', 'P5_R5_componentRelationAnalysis', 'P8_R8_functionCallLocalDesc', 'P10_R10_functionCallLocalExplain'];
  if (graphPrompts.includes(promptName) && !/```dot\n[\s\S]+?\n```/.test(result)) {
    throw new Error('Analysis did not contain a DOT graph. Please retry.');
  }
  if (jsonPrompts.includes(promptName)) {
    try {
      const match = /```json\n([\s\S]*?)\n```/.exec(result);
      const value = JSON.parse(match ? match[1] : result);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
      if (promptName === 'P8_R8_functionCallLocalDesc' && !value.highlightedInheritance) throw new Error();
      if (promptName === 'P10_R10_functionCallLocalExplain' && !value.relevantInheritance) throw new Error();
    } catch { throw new Error('Analysis returned an invalid explanation format. Please retry.'); }
  }
  return result;
}
export async function requestAssistant(promptName: PromptName, content: string): Promise<string> {
  const prompt = prompts[promptName];
  if (!prompt) throw new Error('Unsupported analysis prompt: ' + promptName);
  const key = JSON.stringify([currentProject()?.id, promptName, content]);
  let request = pending.get(key);
  if (!request) {
    request = analyzeProject(prompt.content + '\n\n' + content).then(result => validateAnalysis(promptName, result)).finally(() => pending.delete(key));
    pending.set(key, request);
  }
  return request;
}
