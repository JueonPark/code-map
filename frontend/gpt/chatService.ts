import { analyzeProject, currentProject } from '@/project';
class ChatService {
  private history: { role: string; content: string }[] = [];
  private projectId: string | undefined;
  async initializeThread() {
    const id = currentProject()?.id;
    if (id !== this.projectId) { this.history = []; this.projectId = id; }
    return id;
  }
  async sendMessage(message: string, onUpdate: (content: string) => void) {
    await this.initializeThread();
    const text = await analyzeProject(message, this.history.slice(-18));
    this.history.push({ role: 'user', content: message }, { role: 'assistant', content: text });
    this.history = this.history.slice(-18);
    onUpdate(text);
    return text;
  }
}
export default new ChatService();
