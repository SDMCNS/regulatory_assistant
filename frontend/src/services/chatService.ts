import { ChatSession, ChatMessage, DocSection } from '../types';
import { get, set } from 'idb-keyval';

const CHATS_KEY = 'aerolex_chats_v1';

let inMemoryChats: ChatSession[] | null = null;

export async function initChats(): Promise<void> {
  if (inMemoryChats !== null) return;
  
  try {
    const dbChats = await get<ChatSession[]>(CHATS_KEY);
    if (dbChats && dbChats.length > 0) {
      inMemoryChats = dbChats;
    } else {
      // Synchronous fallback / Migration from localStorage
      const raw = localStorage.getItem(CHATS_KEY);
      if (raw) {
        inMemoryChats = JSON.parse(raw);
        // Async migration to IndexedDB
        set(CHATS_KEY, inMemoryChats)
          .then(() => localStorage.removeItem(CHATS_KEY))
          .catch(e => console.error("IDB migration failed", e));
      } else {
        inMemoryChats = [];
      }
    }
  } catch (e) {
    console.error('Error initializing chats', e);
    inMemoryChats = [];
  }
}

export function getChats(): ChatSession[] {
  if (inMemoryChats === null) {
    inMemoryChats = []; // Fallback if called before init
  }
  return inMemoryChats;
}

export function saveChats(chats: ChatSession[]) {
  inMemoryChats = chats;
  set(CHATS_KEY, chats).catch(e => console.error("IDB save failed", e));
  window.dispatchEvent(new Event('chat_updated'));
}

export function createChat(title: string = 'New Chat'): ChatSession {
  const newChat: ChatSession = {
    id: 'chat-' + Date.now(),
    title,
    messages: [
      {
        id: 'welcome-msg-' + Date.now(),
        role: 'assistant',
        content: `### New Chat Session: ${title}
You can bookmark regulatory sections and use them as context for this chat.`,
        timestamp: Date.now(),
      }
    ],
    savedSections: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  const chats = getChats();
  chats.push(newChat);
  saveChats(chats);
  return newChat;
}

export function updateChat(chatId: string, updates: Partial<ChatSession>) {
  const chats = getChats();
  const index = chats.findIndex(c => c.id === chatId);
  if (index !== -1) {
    chats[index] = { ...chats[index], ...updates, updatedAt: Date.now() };
    saveChats(chats);
  }
}

export function addMessageToChat(chatId: string, message: ChatMessage) {
  const chats = getChats();
  const index = chats.findIndex(c => c.id === chatId);
  if (index !== -1) {
    chats[index].messages.push(message);
    chats[index].updatedAt = Date.now();
    saveChats(chats);
  }
}

export function addSectionToChat(chatId: string, section: DocSection) {
  const chats = getChats();
  const index = chats.findIndex(c => c.id === chatId);
  if (index !== -1) {
    // avoid duplicates
    if (!chats[index].savedSections.some(s => s.id === section.id)) {
      chats[index].savedSections.push(section);
      chats[index].updatedAt = Date.now();
      saveChats(chats);
    }
  }
}

export function getChat(chatId: string): ChatSession | undefined {
  return getChats().find(c => c.id === chatId);
}

export function deleteChat(chatId: string) {
  const chats = getChats();
  saveChats(chats.filter(c => c.id !== chatId));
}

export function toggleSectionInChat(chatId: string, sectionId: string) {
  const chats = getChats();
  const index = chats.findIndex(c => c.id === chatId);
  if (index !== -1) {
    const secIndex = chats[index].savedSections.findIndex(s => s.id === sectionId);
    if (secIndex !== -1) {
      const current = chats[index].savedSections[secIndex].enabled;
      chats[index].savedSections[secIndex].enabled = current === false ? true : false;
      chats[index].updatedAt = Date.now();
      saveChats(chats);
    }
  }
}
