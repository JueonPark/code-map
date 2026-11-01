import { useEffect, useRef } from 'react';
import { requestAssistant } from './gptAssistant';
import { QueryType, queryDefinitions, generateContent } from './queryDefinitions';
interface Props {
  queryType: QueryType;
  params?: Record<string, string>;
  onResponseReceived?: (response: string | null, error?: string | null, type?: string) => void;
  onLoadingChange?: (loading: boolean) => void;
}
export function GptComponent({ queryType, params = {}, onResponseReceived, onLoadingChange }: Props) {
  const callbacks = useRef({ onResponseReceived, onLoadingChange });
  callbacks.current = { onResponseReceived, onLoadingChange };
  const content = generateContent(queryType, params);
  useEffect(() => {
    let active = true;
    callbacks.current.onLoadingChange?.(true);
    requestAssistant(queryDefinitions[queryType].promptName, content).then(result => {
      if (active) callbacks.current.onLoadingChange?.(false);
      if (active) callbacks.current.onResponseReceived?.(result, null, queryType);
    }).catch(error => {
      if (active) callbacks.current.onLoadingChange?.(false);
      if (active) callbacks.current.onResponseReceived?.(null, String(error.message || error), queryType);
    }).finally(() => { if (active) callbacks.current.onLoadingChange?.(false); });
    return () => { active = false; };
  }, [queryType, content]);
  return null;
}
