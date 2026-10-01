/**
 * Memory Service: Persistent store & context synthesis for user's queries
 * Pure user memory without mock or sample data.
 */

import { QueryMemoryItem } from '../types';

const MEMORY_STORAGE_KEY = 'aerolex_eu_user_query_memory_v2';

export function getQueryMemory(): QueryMemoryItem[] {
  try {
    const raw = localStorage.getItem(MEMORY_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    return JSON.parse(raw);
  } catch (err) {
    console.error('Failed to read query memory from localStorage', err);
    return [];
  }
}

export function saveQueryMemory(items: QueryMemoryItem[]): void {
  try {
    localStorage.setItem(MEMORY_STORAGE_KEY, JSON.stringify(items));
  } catch (err) {
    console.error('Failed to save query memory to localStorage', err);
  }
}

export function recordQuery(entry: Omit<QueryMemoryItem, 'id' | 'timestamp' | 'isActiveInContext'> & { isActiveInContext?: boolean }): QueryMemoryItem {
  const current = getQueryMemory();
  const newItem: QueryMemoryItem = {
    id: 'mem-' + Date.now() + '-' + Math.random().toString(36).substring(2, 7),
    timestamp: Date.now(),
    isActiveInContext: entry.isActiveInContext ?? true,
    ...entry,
  };

  // Add at the beginning (most recent first)
  const updated = [newItem, ...current];
  saveQueryMemory(updated);
  return newItem;
}

export function updateMemoryItem(id: string, updates: Partial<QueryMemoryItem>): void {
  const current = getQueryMemory();
  const index = current.findIndex(item => item.id === id);
  if (index !== -1) {
    current[index] = { ...current[index], ...updates };
    saveQueryMemory([...current]);
  }
}

export function toggleMemoryContextActive(id: string): void {
  const current = getQueryMemory();
  const item = current.find(i => i.id === id);
  if (item) {
    item.isActiveInContext = !item.isActiveInContext;
    saveQueryMemory([...current]);
  }
}

export function toggleMemoryPin(id: string): void {
  const current = getQueryMemory();
  const item = current.find(i => i.id === id);
  if (item) {
    item.isPinned = !item.isPinned;
    saveQueryMemory([...current]);
  }
}

export function deleteMemoryItem(id: string): void {
  const current = getQueryMemory();
  const updated = current.filter(item => item.id !== id);
  saveQueryMemory(updated);
}

export function clearMemory(keepPinned: boolean = true): void {
  if (keepPinned) {
    const current = getQueryMemory();
    const pinned = current.filter(item => item.isPinned);
    saveQueryMemory(pinned);
  } else {
    saveQueryMemory([]);
  }
}

/**
 * Builds conversational context string from previous user queries to inject into LLM prompts
 */
export function buildMemoryContextPrompt(maxItems: number = 4): { contextString: string; usedItemIds: string[] } {
  const items = getQueryMemory();
  const activeItems = items.filter(item => item.isActiveInContext);
  
  activeItems.sort((a, b) => {
    if (a.isPinned && !b.isPinned) return -1;
    if (!a.isPinned && b.isPinned) return 1;
    return b.timestamp - a.timestamp;
  });

  const selected = activeItems.slice(0, maxItems);
  if (selected.length === 0) {
    return { contextString: '', usedItemIds: [] };
  }

  const lines = selected.map((item, idx) => {
    const snippet = item.answerSnippet || item.fullAnswer?.slice(0, 200) || 'Query processed';
    return `Query #${idx + 1}: "${item.query}"\nSummary / Key finding: ${snippet}`;
  });

  return {
    contextString: lines.join('\n\n'),
    usedItemIds: selected.map(s => s.id)
  };
}

export function exportMemoryAsMarkdown(): string {
  const items = getQueryMemory();
  let md = `# EU Aviation Regulations - User Query Memory Log\nExported: ${new Date().toISOString()}\nTotal Queries Recorded: ${items.length}\n\n`;

  items.forEach((item, index) => {
    const dateStr = new Date(item.timestamp).toLocaleString();
    md += `## ${index + 1}. ${item.query}\n`;
    md += `*Timestamp: ${dateStr} · Type: ${item.type.toUpperCase()}${item.origin ? ` · Origin: ${item.origin}` : ''}*\n\n`;
    if (item.fullAnswer) {
      md += `### Answer / Response\n${item.fullAnswer}\n\n`;
    }
    if (item.retrievedChunks && item.retrievedChunks.length > 0) {
      md += `### Referenced Chunks\n`;
      item.retrievedChunks.forEach(chunk => {
        md += `- **${chunk.chunk_id}** (${chunk.source.toUpperCase()}): ${chunk.path.join(' > ')}\n`;
      });
      md += '\n';
    }
    md += `---\n\n`;
  });

  return md;
}
