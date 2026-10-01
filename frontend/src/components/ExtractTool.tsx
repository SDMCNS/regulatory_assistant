/**
 * ExtractTool Component
 * Clean frontend for FastAPI POST /llm/extract
 * Extracts structured JSON according to user-defined JSON schema
 */

import React, { useState } from 'react';
import { 
  FileCode, Play, Copy, Check, RefreshCw, AlertCircle, 
  Code, FileText 
} from 'lucide-react';
import { AppSettings } from '../types';
import { extractStructuredData } from '../services/apiClient';
import { recordQuery } from '../services/memoryService';

interface ExtractToolProps {
  settings: AppSettings;
}

const SCHEMA_TEMPLATES = [
  {
    name: 'Compliance Checklist',
    description: 'Extracts primary regulatory requirements, applicable entities, and mandatory actions',
    schema: {
      type: 'object',
      properties: {
        regulation_title: { type: 'string', description: 'Formal regulation title or article number' },
        responsible_parties: { type: 'array', items: { type: 'string' } },
        mandatory_requirements: { type: 'array', items: { type: 'string' } },
        exceptions_or_discretions: { type: 'array', items: { type: 'string' } }
      },
      required: ['regulation_title', 'mandatory_requirements']
    }
  },
  {
    name: 'Operational Limits & Metrics',
    description: 'Extracts exact quantitative limits, altitudes, duty durations, and distances',
    schema: {
      type: 'object',
      properties: {
        domain: { type: 'string' },
        maximum_altitude_meters: { type: 'number' },
        maximum_mass_kg: { type: 'number' },
        line_of_sight_required: { type: 'boolean' },
        operational_subcategories: { type: 'array', items: { type: 'string' } }
      },
      required: ['maximum_altitude_meters', 'line_of_sight_required']
    }
  },
  {
    name: 'Licensing & Qualifications',
    description: 'Extracts ratings, re-evaluation intervals, and qualification conditions',
    schema: {
      type: 'object',
      properties: {
        endorsement_type: { type: 'string' },
        applicable_aircraft: { type: 'array', items: { type: 'string' } },
        level_validity_years: { 
          type: 'object',
          properties: {
            level_4_operational: { type: 'number' },
            level_5_extended: { type: 'number' },
            level_6_expert: { type: 'string' }
          }
        }
      },
      required: ['endorsement_type', 'applicable_aircraft']
    }
  }
];

export const ExtractTool: React.FC<ExtractToolProps> = ({ settings }) => {
  const [selectedTemplateIndex, setSelectedTemplateIndex] = useState(0);
  const [rawText, setRawText] = useState('');
  const [schemaJson, setSchemaJson] = useState(JSON.stringify(SCHEMA_TEMPLATES[0].schema, null, 2));
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [extractedData, setExtractedData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleSelectTemplate = (index: number) => {
    setSelectedTemplateIndex(index);
    setSchemaJson(JSON.stringify(SCHEMA_TEMPLATES[index].schema, null, 2));
    setSchemaError(null);
  };

  const handleRunExtract = async () => {
    setError(null);
    setSchemaError(null);

    let parsedSchema: Record<string, any>;
    try {
      parsedSchema = JSON.parse(schemaJson);
    } catch (e: any) {
      setSchemaError('Invalid JSON schema syntax: ' + e.message);
      return;
    }

    if (!rawText.trim()) {
      setError('Please enter or paste the regulatory text you want to extract structured data from.');
      return;
    }

    setLoading(true);
    try {
      const result = await extractStructuredData(rawText, parsedSchema, settings);
      setExtractedData(result);

      // Record in Query Memory
      recordQuery({
        query: `Extracted structured schema for: "${rawText.slice(0, 50)}..."`,
        type: 'extract',
        origin: settings.defaultOrigin,
        answerSnippet: JSON.stringify(result).slice(0, 160) + '...',
        fullAnswer: JSON.stringify(result, null, 2),
        isPinned: false,
        isActiveInContext: false,
      });
    } catch (err: any) {
      setError(err.message || 'Error communicating with /llm/extract endpoint');
      setExtractedData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyOutput = () => {
    if (!extractedData) return;
    navigator.clipboard.writeText(JSON.stringify(extractedData, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-61px)] bg-slate-950 overflow-y-auto">
      {/* Header */}
      <div className="p-6 bg-slate-900/60 border-b border-slate-800/80 shrink-0">
        <div className="max-w-6xl mx-auto space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-bold text-slate-100 tracking-tight flex items-center gap-2">
                <FileCode className="w-5 h-5 text-sky-400" />
                <span>Structured Regulatory Schema Extractor</span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Send text and a JSON Schema to FastAPI (`POST /llm/extract`) for schema-guaranteed extraction
              </p>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              <span className="text-xs text-slate-500 mr-1">Schema Template:</span>
              {SCHEMA_TEMPLATES.map((tpl, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectTemplate(idx)}
                  className={`px-2.5 py-1 text-xs rounded-lg transition-colors ${
                    selectedTemplateIndex === idx
                      ? 'bg-sky-950 text-sky-400 border border-sky-800/80 font-medium'
                      : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  {tpl.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid View */}
      <div className="flex-1 p-6 max-w-6xl mx-auto w-full space-y-6">
        {error && (
          <div className="p-3 bg-rose-950/30 border border-rose-800/50 rounded-lg text-xs text-rose-300 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
            <div>
              <span className="font-semibold">API Error:</span> {error}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Column: Input Text & JSON Schema Editor */}
          <div className="space-y-4">
            {/* Input Regulatory Text */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-sky-400" />
                  <span>Regulatory Text Source (`text`)</span>
                </label>
                <span className="text-[11px] text-slate-500 font-mono">
                  {rawText.length} characters
                </span>
              </div>
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={7}
                placeholder="Paste the regulation text, article, or chunk to extract structured fields from..."
                className="w-full p-3 bg-slate-900 border border-slate-800 focus:border-sky-500 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none font-sans leading-relaxed resize-y"
              />
            </div>

            {/* Schema Definition */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <Code className="w-3.5 h-3.5 text-sky-400" />
                  <span>Target JSON Schema (`json_schema`)</span>
                </label>
                {schemaError && (
                  <span className="text-[11px] text-rose-400 font-medium">
                    Schema Syntax Error
                  </span>
                )}
              </div>
              <textarea
                value={schemaJson}
                onChange={(e) => {
                  setSchemaJson(e.target.value);
                  setSchemaError(null);
                }}
                rows={10}
                className="w-full p-3 bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-lg text-xs text-sky-300 font-mono leading-relaxed resize-y"
              />
              {schemaError && (
                <div className="text-xs text-rose-400 bg-rose-950/40 p-2 rounded border border-rose-900/60">
                  {schemaError}
                </div>
              )}
            </div>

            {/* Run Button */}
            <button
              type="button"
              onClick={handleRunExtract}
              disabled={loading || !rawText.trim()}
              className="w-full py-2.5 px-4 bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50 shadow-md"
            >
              <Play className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>{loading ? 'Calling POST /llm/extract...' : 'Extract Structured JSON'}</span>
            </button>
          </div>

          {/* Right Column: Output JSON Preview */}
          <div className="flex flex-col bg-slate-900 border border-slate-800 rounded-xl overflow-hidden min-h-[420px]">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-950/60">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${extractedData ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Extracted JSON Result
                </span>
              </div>

              {extractedData && (
                <button
                  type="button"
                  onClick={handleCopyOutput}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 rounded transition-colors"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? 'Copied' : 'Copy JSON'}</span>
                </button>
              )}
            </div>

            <div className="flex-1 p-4 bg-slate-950 overflow-auto font-mono text-xs text-slate-200">
              {loading ? (
                <div className="h-full flex items-center justify-center text-slate-500 space-x-2">
                  <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
                  <span>Executing /llm/extract on local backend...</span>
                </div>
              ) : extractedData ? (
                <pre className="text-emerald-400 whitespace-pre-wrap leading-relaxed">
                  {JSON.stringify(extractedData, null, 2)}
                </pre>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 text-center space-y-2 p-6">
                  <FileCode className="w-8 h-8 text-slate-700" />
                  <p className="text-xs max-w-sm">
                    Paste regulatory text in the left panel and click <strong>Extract Structured JSON</strong> to invoke <code className="text-sky-400 font-mono">POST /llm/extract</code>.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
