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
  Trash,
  User,
  Clock,
  Sparkles,
  ShieldCheck,
  Calendar
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
  embedNote,
  generateNoteKeywords
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
  const [newType, setNewType] = useState('project_note');
  const [newProject, setNewProject] = useState('');
  const [newCreatedBy, setNewCreatedBy] = useState('');
  const [isIndefinite, setIsIndefinite] = useState(true);
  const [newExpiresAt, setNewExpiresAt] = useState('');
  const [newKeywords, setNewKeywords] = useState('');
  const [newTags, setNewTags] = useState('');
  const [isGeneratingKeywords, setIsGeneratingKeywords] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const [newSections, setNewSections] = useState<NoteSectionInput[]>([
    { heading: 'Key Provisions & Observations', content: '' }
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
    if (!confirm('Are you sure you want to delete this note from the knowledge base?')) return;
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

  const handleAutoGenerateKeywords = async () => {
    if (!newTitle.trim() && newSections.every(s => !s.content.trim())) {
      alert('Please enter a note title or section content first to extract keywords.');
      return;
    }

    setIsGeneratingKeywords(true);
    try {
      const kws = await generateNoteKeywords({
        title: newTitle.trim(),
        project: newProject.trim() || undefined,
        sections: newSections,
      }, settings);
      
      if (kws && kws.length > 0) {
        setNewKeywords(kws.join(', '));
      } else {
        alert('No keywords could be extracted.');
      }
    } catch (err: any) {
      alert(`Keyword generation note: ${err.message}`);
    } finally {
      setIsGeneratingKeywords(false);
    }
  };

  const handleCreateSubmit = async () => {
    if (!newTitle.trim()) {
      alert('Title is required');
      return;
    }

    const cleanCreator = newCreatedBy.trim();
    if (!cleanCreator) {
      alert("Creator ('Who created it') is required to ensure knowledge base governance and auditability.");
      return;
    }

    if (!isIndefinite && !newExpiresAt) {
      alert('Please select an expiration date, or choose "Indefinite Validity".');
      return;
    }
    
    setIsSubmitting(true);
    try {
      const parsedKeywords = newKeywords.split(',').map(k => k.trim()).filter(Boolean);
      const parsedTags = newTags.split(',').map(t => t.trim()).filter(Boolean);

      const req: CreateNoteRequest = {
        title: newTitle.trim(),
        note_type: newType.trim(),
        project: newProject.trim() || undefined,
        created_by: cleanCreator,
        author: cleanCreator,
        is_indefinite: isIndefinite,
        expires_at: !isIndefinite && newExpiresAt ? newExpiresAt : null,
        keywords: parsedKeywords,
        tags: parsedTags,
        auto_embed: true,
        sections: newSections.filter(s => s.heading.trim() || s.content.trim())
      };
      await createNote(req, settings);
      setIsCreating(false);
      setNewTitle('');
      setNewProject('');
      setNewKeywords('');
      setNewTags('');
      setIsIndefinite(true);
      setNewExpiresAt('');
      setNewSections([{ heading: 'Key Provisions & Observations', content: '' }]);
      await fetchNotes();
    } catch (err: any) {
      alert(`Error creating note: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredNotes = notes.filter(n => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      n.title.toLowerCase().includes(q) ||
      (n.created_by && n.created_by.toLowerCase().includes(q)) ||
      (n.project && n.project.toLowerCase().includes(q)) ||
      (n.keywords && n.keywords.some(k => k.toLowerCase().includes(q))) ||
      (n.tags && n.tags.some(t => t.toLowerCase().includes(q)))
    );
  });

  return (
    <div className="flex flex-col md:flex-row h-full">
      {/* Sidebar: List of Notes */}
      <div className="w-full md:w-88 border-r border-slate-800 bg-slate-900/50 flex flex-col h-full overflow-hidden shrink-0">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-amber-400" />
              Organizational Knowledge
            </h2>
            <div className="text-[11px] text-slate-500 mt-0.5">Informal Knowledge Base ({notes.length})</div>
          </div>
          <button
            onClick={() => {
              setIsCreating(true);
              setSelectedNote(null);
            }}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white rounded-md shadow-sm transition-colors cursor-pointer"
            title="Create New Note"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Note</span>
          </button>
        </div>

        {/* Filter Search Input */}
        <div className="p-2 border-b border-slate-800/80 bg-slate-950/40">
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 pointer-events-none" />
            <input
              type="text"
              value={searchFilter}
              onChange={e => setSearchFilter(e.target.value)}
              placeholder="Search notes, creators, keywords..."
              className="w-full bg-slate-900/90 border border-slate-800 rounded-md pl-8 pr-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {loading && !notes.length ? (
            <div className="text-center p-6 text-slate-500 text-xs">Loading notes...</div>
          ) : filteredNotes.length === 0 ? (
            <div className="text-center p-6 text-slate-500 text-xs">
              {notes.length === 0 ? 'No notes in knowledge base yet. Click "Add Note" to create one.' : 'No notes match your search.'}
            </div>
          ) : (
            filteredNotes.map(note => (
              <div 
                key={note.document_id}
                onClick={() => handleSelectNote(note.document_id)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  selectedNote?.document_id === note.document_id
                    ? 'bg-slate-800/90 border-amber-500/60 shadow-md ring-1 ring-amber-500/30'
                    : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-800/60 hover:border-slate-700'
                }`}
              >
                <div className="flex justify-between items-start gap-2 mb-1.5">
                  <h3 className="text-xs font-semibold text-slate-100 line-clamp-1 flex-1">{note.title}</h3>
                  <button 
                    onClick={(e) => handleDeleteNote(note.document_id, e)}
                    className="text-slate-500 hover:text-rose-400 p-0.5 rounded transition-colors shrink-0"
                    title="Delete note"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Creator & Date */}
                <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mb-1.5">
                  <User className="w-3 h-3 text-sky-400 shrink-0" />
                  <span className="font-medium text-slate-300 truncate">{note.created_by || note.author}</span>
                  <span className="text-slate-600">·</span>
                  <span className="text-[10px] text-slate-500">{note.date}</span>
                </div>

                {/* Badges: Validity & Type */}
                <div className="flex flex-wrap items-center gap-1.5 mb-2">
                  <span className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-400 uppercase font-mono">
                    {note.note_type.replace('_', ' ')}
                  </span>
                  
                  {note.is_indefinite ? (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/70 text-[10px] text-emerald-300 font-medium">
                      Indefinite
                    </span>
                  ) : note.is_expired ? (
                    <span className="px-1.5 py-0.5 rounded bg-rose-950/60 border border-rose-800/70 text-[10px] text-rose-300 font-medium">
                      Expired ({note.expires_at})
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded bg-amber-950/60 border border-amber-800/70 text-[10px] text-amber-300 font-medium">
                      Expires: {note.expires_at}
                    </span>
                  )}

                  {note.project && (
                    <span className="px-1.5 py-0.5 rounded bg-sky-950/50 border border-sky-800/50 text-[10px] text-sky-300 truncate max-w-[120px]">
                      {note.project}
                    </span>
                  )}

                  {note.is_embedded && (
                    <span title="Vector Embedded in FAISS" className="ml-auto flex items-center">
                      <Database className="w-3 h-3 text-emerald-400" />
                    </span>
                  )}
                </div>

                {/* Keywords preview */}
                {note.keywords && note.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {note.keywords.slice(0, 3).map((kw, i) => (
                      <span key={i} className="px-1.5 py-0.2 bg-slate-800/80 border border-slate-700/60 rounded text-[9px] text-slate-300 truncate max-w-[130px]">
                        #{kw}
                      </span>
                    ))}
                    {note.keywords.length > 3 && (
                      <span className="text-[9px] text-slate-500 font-mono">+{note.keywords.length - 3}</span>
                    )}
                  </div>
                )}
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
                <div>
                  <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                    <BookOpen className="w-5 h-5 text-amber-400" />
                    Record Knowledge Base Note
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Forms organizational knowledge. Captures author governance, expiration policy, and AI-extracted keywords.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button 
                    onClick={() => setIsCreating(false)}
                    className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 rounded border border-slate-700 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button 
                    onClick={handleCreateSubmit}
                    disabled={isSubmitting}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-amber-600 hover:bg-amber-500 text-white rounded border border-amber-500 transition-colors disabled:opacity-50 cursor-pointer shadow-sm"
                  >
                    {isSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                    Save & Index Note
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Title */}
                <div className="space-y-1.5 sm:col-span-2">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1">
                    <span>Note Title</span>
                    <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={e => setNewTitle(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 focus:border-amber-500 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
                    placeholder="E.g., SMR & A-SMGCS Operational Limitations during LVP"
                  />
                </div>

                {/* Who Created It (Enforced) */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1">
                    <User className="w-3.5 h-3.5 text-sky-400" />
                    <span>Who Created It (Author / Role)</span>
                    <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={newCreatedBy}
                    onChange={e => setNewCreatedBy(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 focus:border-amber-500 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
                    placeholder="E.g., Capt. John Miller (Safety Manager)"
                  />
                  <div className="text-[10px] text-slate-500">Enforced for internal auditability and knowledge source governance.</div>
                </div>

                {/* Note Type */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300">Note Type</label>
                  <select
                    value={newType}
                    onChange={e => setNewType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 focus:border-amber-500 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none"
                  >
                    <option value="project_note">Project Note</option>
                    <option value="meeting_minutes">Meeting Minutes</option>
                    <option value="daily_journal">Daily Journal</option>
                    <option value="safety_observation">Safety Observation</option>
                    <option value="general_note">General Note</option>
                  </select>
                </div>

                {/* Project / Topic */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300">Project / Topic (Optional)</label>
                  <input
                    type="text"
                    value={newProject}
                    onChange={e => setNewProject(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 focus:border-amber-500 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
                    placeholder="E.g., Aerodrome Safety Review"
                  />
                </div>

                {/* Validity / Expiration Policy */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-amber-400" />
                    <span>Validity & Expiration Policy</span>
                  </label>
                  <div className="flex items-center gap-4 bg-slate-900 border border-slate-700 rounded-lg p-2 text-xs">
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                      <input
                        type="radio"
                        name="validity_policy"
                        checked={isIndefinite}
                        onChange={() => setIsIndefinite(true)}
                        className="accent-amber-500"
                      />
                      <span>Indefinite</span>
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                      <input
                        type="radio"
                        name="validity_policy"
                        checked={!isIndefinite}
                        onChange={() => setIsIndefinite(false)}
                        className="accent-amber-500"
                      />
                      <span>Expires on</span>
                    </label>
                    {!isIndefinite && (
                      <input
                        type="date"
                        value={newExpiresAt}
                        onChange={e => setNewExpiresAt(e.target.value)}
                        className="bg-slate-950 border border-slate-700 rounded px-2 py-0.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
                      />
                    )}
                  </div>
                </div>

                {/* Keywords with AI Auto-Generation */}
                <div className="space-y-1.5 sm:col-span-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                      <span>Associated Keywords (Aviation Terms & Acronyms)</span>
                    </label>
                    <button
                      type="button"
                      onClick={handleAutoGenerateKeywords}
                      disabled={isGeneratingKeywords}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-amber-950/80 border border-amber-800/80 text-amber-300 hover:bg-amber-900/90 rounded-md transition-colors cursor-pointer disabled:opacity-50"
                      title="Use the local LLM to extract domain keywords automatically"
                    >
                      {isGeneratingKeywords ? (
                        <>
                          <RefreshCw className="w-3 h-3 animate-spin" />
                          <span>Extracting...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3 h-3 text-amber-400" />
                          <span>Auto-Generate via AI</span>
                        </>
                      )}
                    </button>
                  </div>
                  <input
                    type="text"
                    value={newKeywords}
                    onChange={e => setNewKeywords(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 focus:border-amber-500 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
                    placeholder="E.g. SMR, Low Visibility Procedures, Part-ADR.OPS, Surface Radar (comma-separated)"
                  />
                  <div className="text-[10px] text-slate-500">
                    Used to associate the note with relevant regulatory queries, search filters, and knowledge domains.
                  </div>
                </div>

                {/* Tags (Comma separated) */}
                <div className="space-y-1.5 sm:col-span-2">
                  <label className="text-xs font-semibold text-slate-300">Tags (Internal classification)</label>
                  <input
                    type="text"
                    value={newTags}
                    onChange={e => setNewTags(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-500"
                    placeholder="planning, design, urgent (comma-separated)"
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
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="px-2 py-0.5 rounded bg-amber-900/30 border border-amber-800/50 text-amber-400 text-[10px] uppercase font-bold tracking-wider">
                      {selectedNote.note_type?.replace('_', ' ')}
                    </span>
                    
                    {selectedNote.is_indefinite ? (
                      <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/70 text-emerald-300 text-[10px] font-semibold flex items-center gap-1">
                        <Clock className="w-3 h-3 text-emerald-400" />
                        Indefinite Validity
                      </span>
                    ) : selectedNote.is_expired ? (
                      <span className="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-800/70 text-rose-300 text-[10px] font-semibold flex items-center gap-1">
                        <Clock className="w-3 h-3 text-rose-400" />
                        Expired ({selectedNote.expires_at})
                      </span>
                    ) : selectedNote.expires_at ? (
                      <span className="px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/70 text-amber-300 text-[10px] font-semibold flex items-center gap-1">
                        <Clock className="w-3 h-3 text-amber-400" />
                        Valid until {selectedNote.expires_at}
                      </span>
                    ) : null}

                    <span className="text-xs text-slate-500 font-mono ml-1">{selectedNote.document_id}</span>
                  </div>
                  
                  <h2 className="text-2xl font-bold text-slate-100">{selectedNote.title}</h2>
                  
                  <div className="flex flex-wrap items-center gap-4 mt-3 text-xs text-slate-400">
                    <div className="flex items-center gap-1 text-slate-300 font-medium">
                      <User className="w-3.5 h-3.5 text-sky-400" />
                      <span>{selectedNote.created_by || selectedNote.author || 'Unknown'}</span>
                    </div>
                    {selectedNote.project && <span>Project: <strong className="text-slate-300 font-medium">{selectedNote.project}</strong></span>}
                    <span>Date: {new Date(selectedNote.date).toLocaleDateString()}</span>
                  </div>

                  {/* Associated Keywords */}
                  {selectedNote.keywords && selectedNote.keywords.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-3 pt-3 border-t border-slate-800/60">
                      <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1 mr-1">
                        <Sparkles className="w-3 h-3 text-amber-400" />
                        Keywords:
                      </span>
                      {selectedNote.keywords.map((kw, i) => (
                        <span 
                          key={i} 
                          className="px-2 py-0.5 bg-slate-800/90 border border-slate-700/70 rounded-full text-xs text-amber-300/90 font-medium"
                        >
                          #{kw}
                        </span>
                      ))}
                    </div>
                  )}
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
