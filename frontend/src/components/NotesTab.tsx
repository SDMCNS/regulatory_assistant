import React, { useState, useEffect } from 'react';
import { 
  Plus, 
  Trash2, 
  FileText, 
  RefreshCw, 
  BookOpen, 
  Layers,
  Database,
  Search,
  Eye,
  Trash
} from 'lucide-react';
import { marked } from 'marked';
import { 
  AppSettings, 
  NoteSummaryItem, 
  CreateNoteRequest, 
  NoteSectionInput,
  NoteDetailResponse 
} from '../types';
import { 
  listNotes, 
  createNote, 
  getNote, 
  deleteNote, 
  embedNote 
} from '../services/apiClient';

interface NotesTabProps {
  settings: AppSettings;
}

export const NotesTab: React.FC<NotesTabProps> = ({ settings }) => {
  const [notes, setNotes] = useState<NoteSummaryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedNote, setSelectedNote] = useState<NoteDetailResponse | null>(null);
  
  const [isCreating, setIsCreating] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newType, setNewType] = useState('daily_journal');
  const [newProject, setNewProject] = useState('');
  const [newAuthor, setNewAuthor] = useState('');
  const [newTags, setNewTags] = useState('');
  const [newSections, setNewSections] = useState<NoteSectionInput[]>([
    { heading: 'General Notes', content: '' }
  ]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchNotes = async () => {
    setLoading(true);
    try {
      const data = await listNotes('all', settings);
      setNotes(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotes();
  }, [settings]);

  const handleSelectNote = async (documentId: string) => {
    setIsCreating(false);
    setLoading(true);
    try {
      const data = await getNote(documentId, settings);
      setSelectedNote(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteNote = async (documentId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this note?')) return;
    try {
      await deleteNote(documentId, settings);
      if (selectedNote?.document_id === documentId) setSelectedNote(null);
      fetchNotes();
    } catch (err: any) {
      alert(`Error deleting note: ${err.message}`);
    }
  };

  const handleEmbedNote = async (documentId: string) => {
    try {
      await embedNote(documentId, settings);
      alert('Note embedded successfully.');
      handleSelectNote(documentId);
      fetchNotes();
    } catch (err: any) {
      alert(`Error embedding note: ${err.message}`);
    }
  };

  const handleCreateSubmit = async () => {
    if (!newTitle.trim()) {
      alert('Title is required');
      return;
    }
    
    setIsSubmitting(true);
    try {
      const req: CreateNoteRequest = {
        title: newTitle.trim(),
        note_type: newType.trim(),
        project: newProject.trim() || undefined,
        author: newAuthor.trim() || undefined,
        tags: newTags.split(',').map(t => t.trim()).filter(Boolean),
        auto_embed: true,
        sections: newSections.filter(s => s.heading.trim() || s.content.trim())
      };
      await createNote(req, settings);
      setIsCreating(false);
      setNewTitle('');
      setNewSections([{ heading: 'General Notes', content: '' }]);
      fetchNotes();
    } catch (err: any) {
      alert(`Error creating note: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col md:flex-row h-full">
      {/* Sidebar: List of Notes */}
      <div className="w-full md:w-80 border-r border-slate-800 bg-slate-900/50 flex flex-col h-full overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-amber-400" />
            Notes & Journals
          </h2>
          <button
            onClick={() => {
              setIsCreating(true);
              setSelectedNote(null);
            }}
            className="p-1.5 text-slate-400 hover:text-sky-400 hover:bg-slate-800 rounded transition-colors"
            title="Create New Note"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading && !notes.length ? (
            <div className="text-center p-4 text-slate-500 text-xs">Loading...</div>
          ) : notes.length === 0 ? (
            <div className="text-center p-4 text-slate-500 text-xs">No notes found.</div>
          ) : (
            notes.map(note => (
              <div 
                key={note.document_id}
                onClick={() => handleSelectNote(note.document_id)}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedNote?.document_id === note.document_id
                    ? 'bg-slate-800 border-sky-500/50'
                    : 'bg-slate-800/40 border-slate-700/50 hover:bg-slate-800 hover:border-slate-600'
                }`}
              >
                <div className="flex justify-between items-start mb-1">
                  <h3 className="text-sm font-medium text-slate-200 truncate">{note.title}</h3>
                  <button 
                    onClick={(e) => handleDeleteNote(note.document_id, e)}
                    className="text-slate-500 hover:text-red-400 p-0.5 rounded"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="flex items-center gap-2 text-[10px] text-slate-400">
                  <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 uppercase tracking-wider">
                    {note.note_type}
                  </span>
                  <span>{new Date(note.date).toLocaleDateString()}</span>
                  {note.is_embedded && (
                    <span title="Embedded" className="ml-auto flex items-center">
                      <Database className="w-3 h-3 text-emerald-400" />
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-950">
        {isCreating ? (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-3xl mx-auto space-y-6">
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <h2 className="text-lg font-semibold text-slate-200">Create New Note</h2>
                <div className="flex gap-2">
                  <button 
                    onClick={() => setIsCreating(false)}
                    className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 rounded border border-slate-700 transition-colors"
                  >
                    Cancel
                  </button>
                  <button 
                    onClick={handleCreateSubmit}
                    disabled={isSubmitting}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-amber-600 hover:bg-amber-500 text-white rounded border border-amber-500 transition-colors disabled:opacity-50"
                  >
                    {isSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                    Save Note
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400">Title</label>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={e => setNewTitle(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-500"
                    placeholder="E.g., Weekly Team Sync"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400">Note Type</label>
                  <select
                    value={newType}
                    onChange={e => setNewType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-500"
                  >
                    <option value="daily_journal">Daily Journal</option>
                    <option value="meeting_minutes">Meeting Minutes</option>
                    <option value="project_note">Project Note</option>
                    <option value="general">General</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400">Project (Optional)</label>
                  <input
                    type="text"
                    value={newProject}
                    onChange={e => setNewProject(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-500"
                    placeholder="E.g., AeroLex V2"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400">Tags (Comma separated)</label>
                  <input
                    type="text"
                    value={newTags}
                    onChange={e => setNewTags(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-500"
                    placeholder="planning, design, urgent"
                  />
                </div>
              </div>

              <div className="space-y-4 pt-4 border-t border-slate-800">
                <h3 className="text-sm font-medium text-slate-300">Sections</h3>
                {newSections.map((sec, idx) => (
                  <div key={idx} className="bg-slate-900 border border-slate-800 p-4 rounded-lg space-y-3">
                    <div className="flex justify-between items-center">
                      <input
                        type="text"
                        value={sec.heading}
                        onChange={e => {
                          const updated = [...newSections];
                          updated[idx].heading = e.target.value;
                          setNewSections(updated);
                        }}
                        className="bg-transparent border-b border-slate-700 px-1 py-1 text-sm font-medium text-slate-200 focus:outline-none focus:border-amber-500 w-1/2"
                        placeholder="Section Heading"
                      />
                      <button 
                        onClick={() => setNewSections(newSections.filter((_, i) => i !== idx))}
                        className="text-slate-500 hover:text-red-400"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    <textarea
                      value={sec.content}
                      onChange={e => {
                        const updated = [...newSections];
                        updated[idx].content = e.target.value;
                        setNewSections(updated);
                      }}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 font-mono focus:outline-none focus:border-amber-500 min-h-[120px]"
                      placeholder="Markdown content for this section..."
                    />
                  </div>
                ))}
                <button
                  onClick={() => setNewSections([...newSections, { heading: '', content: '' }])}
                  className="w-full py-2 border border-dashed border-slate-700 text-slate-400 rounded-lg text-sm hover:border-amber-500 hover:text-amber-400 transition-colors flex items-center justify-center gap-2"
                >
                  <Plus className="w-4 h-4" />
                  Add Section
                </button>
              </div>
            </div>
          </div>
        ) : selectedNote ? (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-4xl mx-auto bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
              <div className="p-6 border-b border-slate-800 flex items-start justify-between bg-slate-800/30">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="px-2 py-0.5 rounded bg-amber-900/30 border border-amber-800/50 text-amber-400 text-[10px] uppercase font-bold tracking-wider">
                      {selectedNote.note_type}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">{selectedNote.document_id}</span>
                  </div>
                  <h2 className="text-2xl font-bold text-slate-100">{selectedNote.title}</h2>
                  <div className="flex items-center gap-4 mt-3 text-xs text-slate-400">
                    {selectedNote.project && <span>Project: {selectedNote.project}</span>}
                    {selectedNote.author && <span>Author: {selectedNote.author}</span>}
                    <span>Date: {new Date(selectedNote.date).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {!selectedNote.is_embedded && (
                    <button
                      onClick={() => handleEmbedNote(selectedNote.document_id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-emerald-900/30 hover:bg-emerald-800/40 text-emerald-400 rounded border border-emerald-800/50 transition-colors"
                    >
                      <Database className="w-3.5 h-3.5" />
                      Embed Now
                    </button>
                  )}
                  <button
                    onClick={() => setSelectedNote(null)}
                    className="p-1.5 text-slate-400 hover:bg-slate-800 rounded border border-slate-700 transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
              {selectedNote.sections && selectedNote.sections.length > 0 ? (
                <div className="p-6 space-y-4">
                  {selectedNote.sections.map((sec, idx) => (
                    <div key={idx} className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
                      <div className="bg-slate-800/50 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                            Section {idx + 1}
                          </span>
                          <h3 className="text-sm font-medium text-slate-200">
                            {sec.heading}
                          </h3>
                        </div>
                        {sec.tags && sec.tags.length > 0 && (
                          <div className="flex items-center gap-1">
                            {sec.tags.map((tag, tIdx) => (
                              <span key={tIdx} className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-400">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div 
                        className="p-5 prose prose-invert max-w-none prose-sm prose-slate"
                        dangerouslySetInnerHTML={{ __html: marked.parse(sec.content) }}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-6 prose prose-invert max-w-none prose-sm prose-slate">
                  {selectedNote.rendered_markdown ? (
                    <div dangerouslySetInnerHTML={{ __html: selectedNote.rendered_markdown }} />
                  ) : (
                    <pre className="whitespace-pre-wrap font-mono text-xs">{selectedNote.markdown_doc}</pre>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
            Select a note from the sidebar or create a new one.
          </div>
        )}
      </div>
    </div>
  );
};
