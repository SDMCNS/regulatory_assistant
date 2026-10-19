/**
 * KnowledgeGraphExplorer.tsx
 * AeroLex Regulatory Knowledge Graph Explorer & GraphRAG Visualizer
 * Fully integrated interactive D3.js force-directed knowledge graph with Kùzu Cypher engine,
 * Dual Entry (Exact Code Matching & HyDE Semantic Discovery), Multi-Source Federation,
 * and 360° Legal Context Inspection.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
import {
  Compass, Search, Sparkles, Layers, RefreshCw, ZoomIn, ZoomOut,
  Maximize2, Shield, AlertCircle, BookOpen, ExternalLink, Copy, Check,
  X, Filter, ChevronRight, FileText, Cpu, ArrowUpRight, Radio, Eye, Send
} from 'lucide-react';
import {
  fetchGraphStats, fetchSourcesCatalog, searchGraph, executeHydeSearch,
  fetchComplianceChain, fetchBlastRadius, fetchConceptSubgraph, fetchNodeDetails,
  GraphStats, SourcesCatalog, GraphSearchResult, HydeResponse, HydeCandidate,
  D3GraphData, D3GraphNode, D3GraphLink, NodeInspectionDetails
} from '../services/graphService';

interface Props {
  apiUrl: string;
  onViewDoc?: (doc: any) => void;
  onSendToAssistant?: (prompt: string, chunkIds?: string[]) => void;
}

const NODE_COLORS: Record<string, string> = {
  IR: '#8b5cf6', // Purple - Hard Law
  CS: '#6366f1', // Indigo - Certification Spec
  AMC: '#10b981', // Emerald - Soft Law
  GM: '#f59e0b', // Amber - Guidance Material
  ANNEX: '#0284c7', // Sky Blue - Regulatory Annex
  CONCEPT: '#f43f5e', // Rose - Ontology Concept
  STAKEHOLDER: '#f97316', // Orange - Actor / Role
  DEFAULT: '#64748b' // Slate
};

const LINK_COLORS: Record<string, string> = {
  SATISFIES: '#10b981',
  EXPLAINS: '#f59e0b',
  BELONGS_TO_ANNEX: '#0284c7',
  BELONGS_TO: '#0284c7',
  GOVERNS_CONCEPT: '#f43f5e',
  APPLIES_TO: '#f97316',
  CROSS_REFERENCES: '#8b5cf6',
  COVERS_CONCEPT: '#38bdf8',
  SIMILAR_TO: '#06b6d4',
  DEFAULT: '#475569'
};

export const KnowledgeGraphExplorer: React.FC<Props> = ({
  apiUrl,
  onViewDoc,
  onSendToAssistant
}) => {
  // State: View Modes & Entry
  const [currentMode, setCurrentMode] = useState<'chain' | 'blast' | 'concept'>('chain');
  const [entryMode, setEntryMode] = useState<'exact' | 'hyde'>('exact');
  const [currentCode, setCurrentCode] = useState<string>('ORO.GEN.200');
  const [currentConcept, setCurrentConcept] = useState<string>('Fuel');

  // Multi-source Federation State
  const [activeSources, setActiveSources] = useState<string[]>(['EASA', 'EU', 'FAA', 'SKYBRARY', 'EUROCAE']);
  const [sourcesCatalog, setSourcesCatalog] = useState<SourcesCatalog | null>(null);
  const [selectedSkybraryTopics, setSelectedSkybraryTopics] = useState<string[]>([]);
  const [isSourceModalOpen, setIsSourceModalOpen] = useState(false);
  const [subtopicFilter, setSubtopicFilter] = useState('');

  // Graph Data & Metrics
  const [graphData, setGraphData] = useState<D3GraphData | null>(null);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isPhysicsFrozen, setIsPhysicsFrozen] = useState<boolean>(false);

  // Search & Suggestions
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [suggestions, setSuggestions] = useState<GraphSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [showSuggestions, setShowSuggestions] = useState<boolean>(false);

  // Selection & Details Drawer
  const [selectedNode, setSelectedNode] = useState<D3GraphNode | null>(null);
  const [nodeDetails, setNodeDetails] = useState<NodeInspectionDetails | null>(null);
  const [isDetailsLoading, setIsDetailsLoading] = useState<boolean>(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);

  // 360° Inspector Modal
  const [isInspectorOpen, setIsInspectorOpen] = useState<boolean>(false);
  const [inspectorTab, setInspectorTab] = useState<'text' | 'hierarchy' | 'similar' | 'citations' | 'impact' | 'rag'>('text');
  const [copiedText, setCopiedText] = useState<boolean>(false);

  // HyDE Candidate Discovery Modal
  const [hydeResult, setHydeResult] = useState<HydeResponse | null>(null);
  const [isHydeModalOpen, setIsHydeModalOpen] = useState<boolean>(false);
  const [isHydeLoading, setIsHydeLoading] = useState<boolean>(false);

  // D3 & DOM References
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<d3.Simulation<D3GraphNode, D3GraphLink> | null>(null);
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const gRef = useRef<d3.Selection<SVGGElement, unknown, null, undefined> | null>(null);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const skipNextSearchRef = useRef<boolean>(false);

  // Close search suggestions on click outside
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Load Initial Stats & Sources Catalog
  useEffect(() => {
    fetchGraphStats(apiUrl)
      .then(setStats)
      .catch((err) => console.warn('Failed to fetch graph stats:', err));

    fetchSourcesCatalog(apiUrl)
      .then((cat) => {
        setSourcesCatalog(cat);
      })
      .catch((err) => console.warn('Failed to fetch sources catalog:', err));
  }, [apiUrl]);

  // Load Graph Data based on currentMode and currentCode / currentConcept
  const loadGraph = useCallback(async (mode: 'chain' | 'blast' | 'concept', target: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      let data: D3GraphData;
      if (mode === 'chain') {
        data = await fetchComplianceChain(apiUrl, target);
      } else if (mode === 'blast') {
        data = await fetchBlastRadius(apiUrl, target);
      } else {
        data = await fetchConceptSubgraph(apiUrl, target);
      }
      setGraphData(data);
      // Auto-select anchor if present
      const anchor = data.nodes.find(n => n.is_anchor) || data.nodes[0] || null;
      if (anchor) {
        handleSelectNode(anchor);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load knowledge graph.');
    } finally {
      setIsLoading(false);
    }
  }, [apiUrl]);

  // Trigger initial graph load
  useEffect(() => {
    loadGraph(currentMode, currentMode === 'concept' ? currentConcept : currentCode);
  }, []); // Run on mount

  // Select and inspect a node
  const handleSelectNode = async (node: D3GraphNode) => {
    setSelectedNode(node);
    setIsDrawerOpen(true);
    setIsDetailsLoading(true);
    try {
      const targetId = node.label || node.id;
      const details = await fetchNodeDetails(apiUrl, targetId);
      setNodeDetails(details);
    } catch (e) {
      console.warn('Failed to fetch node details:', e);
      setNodeDetails(null);
    } finally {
      setIsDetailsLoading(false);
    }
  };

  // D3 Simulation and Rendering
  useEffect(() => {
    if (!svgRef.current || !graphData) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 900;
    const height = svgRef.current.clientHeight || 650;

    svg.selectAll('*').remove();

    // Defs for arrow markers
    const defs = svg.append('defs');
    Object.keys(LINK_COLORS).forEach(type => {
      defs.append('marker')
        .attr('id', `arrow-${type}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 24)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', LINK_COLORS[type] || '#475569');
    });

    // Outer container for zooming
    const g = svg.append('g').attr('class', 'graph-viewport-group');
    gRef.current = g;

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 3.5])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);
    zoomBehaviorRef.current = zoom;

    // Clone nodes and links for simulation
    const nodes: D3GraphNode[] = graphData.nodes.map(d => ({ ...d }));
    const links: D3GraphLink[] = graphData.links.map(d => ({ ...d }));

    // D3 Force Simulation
    const simulation = d3.forceSimulation<D3GraphNode, D3GraphLink>(nodes)
      .force('link', d3.forceLink<D3GraphNode, D3GraphLink>(links)
        .id(d => d.id)
        .distance(d => (d.type === 'BELONGS_TO_ANNEX' ? 140 : d.type === 'SIMILAR_TO' ? 180 : 100))
      )
      .force('charge', d3.forceManyBody().strength(d => (d.is_anchor ? -600 : -280)))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(d => (d.is_anchor ? 38 : 26)).iterations(2));

    simulationRef.current = simulation;

    // Draw Links
    const linkGroup = g.append('g').attr('class', 'links');
    const link = linkGroup.selectAll('g.link')
      .data(links)
      .enter()
      .append('g')
      .attr('class', 'link');

    const linkPath = link.append('line')
      .attr('stroke', d => LINK_COLORS[d.type] || LINK_COLORS.DEFAULT)
      .attr('stroke-width', d => (d.type === 'SIMILAR_TO' ? 2 : d.type === 'SATISFIES' ? 2.5 : 1.5))
      .attr('stroke-dasharray', d => (d.type === 'SIMILAR_TO' ? '4,4' : d.type === 'CROSS_REFERENCES' ? '2,2' : 'none'))
      .attr('stroke-opacity', 0.65)
      .attr('marker-end', d => `url(#arrow-${d.type in LINK_COLORS ? d.type : 'DEFAULT'})`);

    const linkText = link.append('text')
      .attr('class', 'link-label')
      .attr('font-size', '9px')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('fill', d => LINK_COLORS[d.type] || '#64748b')
      .attr('text-anchor', 'middle')
      .attr('dy', -3)
      .text(d => d.label || d.type);

    // Draw Nodes
    const nodeGroup = g.append('g').attr('class', 'nodes');
    const node = nodeGroup.selectAll('g.node')
      .data(nodes)
      .enter()
      .append('g')
      .attr('class', d => `node ${d.is_anchor ? 'anchor-node' : ''}`)
      .attr('cursor', 'pointer')
      .call(d3.drag<SVGGElement, D3GraphNode>()
        .on('start', (event, d) => {
          if (!event.active && !isPhysicsFrozen) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active && !isPhysicsFrozen) simulation.alphaTarget(0);
          if (!isPhysicsFrozen) {
            d.fx = null;
            d.fy = null;
          }
        })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        handleSelectNode(d);
      });

    // Anchor pulsing ring
    node.filter(d => !!d.is_anchor)
      .append('circle')
      .attr('r', 32)
      .attr('fill', 'none')
      .attr('stroke', d => NODE_COLORS[d.type] || '#8b5cf6')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '3,3')
      .attr('opacity', 0.7);

    // Main Circle
    node.append('circle')
      .attr('r', d => (d.is_anchor ? 24 : d.type === 'ANNEX' ? 20 : d.type === 'CONCEPT' ? 18 : 15))
      .attr('fill', d => NODE_COLORS[d.type] || NODE_COLORS.DEFAULT)
      .attr('stroke', '#0f172a')
      .attr('stroke-width', 2.5)
      .attr('filter', 'drop-shadow(0 2px 8px rgba(0,0,0,0.5))');

    // Node Type Badge / Text
    node.append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('font-size', d => (d.is_anchor ? '10px' : '8px'))
      .attr('font-weight', '700')
      .attr('font-family', 'Inter, sans-serif')
      .attr('fill', '#ffffff')
      .text(d => d.type);

    // Node Label / Code
    node.append('text')
      .attr('dy', d => (d.is_anchor ? 38 : 30))
      .attr('text-anchor', 'middle')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('fill', '#f1f5f9')
      .text(d => d.label);

    // Node Subtitle (Truncated title)
    node.append('text')
      .attr('dy', d => (d.is_anchor ? 50 : 42))
      .attr('text-anchor', 'middle')
      .attr('font-size', '9px')
      .attr('font-family', 'Inter, sans-serif')
      .attr('fill', '#94a3b8')
      .text(d => {
        const title = d.title || '';
        return title.length > 22 ? title.slice(0, 20) + '...' : title;
      });

    // Simulation Tick
    simulation.on('tick', () => {
      linkPath
        .attr('x1', d => (d.source as D3GraphNode).x || 0)
        .attr('y1', d => (d.source as D3GraphNode).y || 0)
        .attr('x2', d => (d.target as D3GraphNode).x || 0)
        .attr('y2', d => (d.target as D3GraphNode).y || 0);

      linkText
        .attr('x', d => (((d.source as D3GraphNode).x || 0) + ((d.target as D3GraphNode).x || 0)) / 2)
        .attr('y', d => (((d.source as D3GraphNode).y || 0) + ((d.target as D3GraphNode).y || 0)) / 2);

      node.attr('transform', d => `translate(${d.x || 0},${d.y || 0})`);
    });

    // Background Click clears quick bar
    svg.on('click', () => {
      // Keep selection or dismiss? Keep selection for drawer
    });

    return () => {
      simulation.stop();
    };
  }, [graphData, isPhysicsFrozen]);

  // Viewport Control Actions
  const handleZoomIn = () => {
    if (svgRef.current && zoomBehaviorRef.current) {
      d3.select(svgRef.current).transition().duration(250).call(zoomBehaviorRef.current.scaleBy, 1.3);
    }
  };

  const handleZoomOut = () => {
    if (svgRef.current && zoomBehaviorRef.current) {
      d3.select(svgRef.current).transition().duration(250).call(zoomBehaviorRef.current.scaleBy, 0.7);
    }
  };

  const handleResetView = () => {
    if (svgRef.current && zoomBehaviorRef.current) {
      d3.select(svgRef.current).transition().duration(400).call(
        zoomBehaviorRef.current.transform,
        d3.zoomIdentity
      );
    }
  };

  const handleTogglePhysics = () => {
    setIsPhysicsFrozen(prev => {
      const next = !prev;
      if (simulationRef.current) {
        if (next) simulationRef.current.stop();
        else simulationRef.current.restart().alpha(0.2);
      }
      return next;
    });
  };

  // Center camera on a specific node
  const handlePanToNode = (targetNode: D3GraphNode) => {
    if (!svgRef.current || !zoomBehaviorRef.current || targetNode.x === undefined || targetNode.y === undefined) return;
    const width = svgRef.current.clientWidth || 900;
    const height = svgRef.current.clientHeight || 650;
    const scale = 1.4;
    const transform = d3.zoomIdentity
      .translate(width / 2 - targetNode.x * scale, height / 2 - targetNode.y * scale)
      .scale(scale);

    d3.select(svgRef.current).transition().duration(600).call(
      zoomBehaviorRef.current.transform,
      transform
    );
  };

  // Autocomplete search suggestions
  useEffect(() => {
    if (skipNextSearchRef.current) {
      skipNextSearchRef.current = false;
      return;
    }
    const q = searchQuery.trim();
    if (!q || entryMode !== 'exact') {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await searchGraph(apiUrl, q, activeSources, selectedSkybraryTopics);
        setSuggestions(res.results || []);
        setShowSuggestions(true);
      } catch (e) {
        console.warn('Search error:', e);
      } finally {
        setIsSearching(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [searchQuery, entryMode, activeSources, selectedSkybraryTopics, apiUrl]);

  // Execute HyDE Search
  const handleRunHyde = async (customQuery?: string) => {
    const q = (customQuery || searchQuery).trim();
    if (!q) return;

    setIsHydeLoading(true);
    setIsHydeModalOpen(true);
    try {
      const res = await executeHydeSearch(apiUrl, q, activeSources, selectedSkybraryTopics, 12);
      setHydeResult(res);
    } catch (err: any) {
      alert('HyDE search failed: ' + (err.message || 'Unknown error'));
      setIsHydeModalOpen(false);
    } finally {
      setIsHydeLoading(false);
    }
  };

  // Pivot graph to a new anchor rule
  const handlePivotToNode = (code: string) => {
    setCurrentCode(code);
    setCurrentMode('chain');
    loadGraph('chain', code);
    setIsInspectorOpen(false);
    setIsHydeModalOpen(false);
  };

  // Copy helper
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3.75rem)] w-full bg-slate-950 text-slate-100 overflow-hidden select-none">
      {/* ================= TOP CONTROLS BAR ================= */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-2.5 bg-slate-900/90 border-b border-slate-800/80 backdrop-blur z-20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.8)]" />
            <h1 className="text-sm font-bold tracking-tight text-slate-100 font-mono">
              Regulatory Knowledge Graph Explorer
            </h1>
          </div>
          <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60 font-mono">
            Kùzu Engine
          </span>
        </div>

        {/* Dual Entry Switcher: Exact vs HyDE */}
        <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            onClick={() => { setEntryMode('exact'); setShowSuggestions(false); }}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all ${
              entryMode === 'exact'
                ? 'bg-slate-800 text-cyan-400 shadow-sm border border-cyan-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>🎯</span> Exact Matching
          </button>
          <button
            onClick={() => { setEntryMode('hyde'); setShowSuggestions(false); }}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all ${
              entryMode === 'hyde'
                ? 'bg-slate-800 text-purple-400 shadow-sm border border-purple-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>🔮</span> HyDE Semantic Discovery
          </button>
        </div>

        {/* Search & Suggestions Input */}
        <div ref={searchContainerRef} className="relative flex-1 max-w-md min-w-[240px]">
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 focus-within:border-cyan-500/60 transition-colors">
            <Search className="w-3.5 h-3.5 text-slate-500 mr-2 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  if (entryMode === 'hyde') {
                    handleRunHyde();
                  } else if (searchQuery.trim()) {
                    skipNextSearchRef.current = true;
                    setShowSuggestions(false);
                    setSuggestions([]);
                    handlePivotToNode(searchQuery.trim());
                  }
                }
              }}
              placeholder={
                entryMode === 'exact'
                  ? 'Search code or rule title (e.g. ORO.GEN.200)...'
                  : 'Ask operational scenario via HyDE vector search...'
              }
              className="bg-transparent text-xs text-slate-100 placeholder-slate-500 outline-none w-full"
            />
            {entryMode === 'hyde' && (
              <button
                onClick={() => handleRunHyde()}
                disabled={!searchQuery.trim() || isHydeLoading}
                className="ml-2 px-2 py-0.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-[11px] font-semibold text-white rounded transition-colors flex items-center gap-1 shrink-0"
              >
                <span>Synthesize</span>
                <Sparkles className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Autocomplete Suggestions */}
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 max-h-72 overflow-y-auto bg-slate-900 border border-slate-700/80 rounded-lg shadow-2xl z-50 py-1">
              {suggestions.map((item) => (
                <div
                  key={`${item.source}-${item.id}`}
                  onClick={() => {
                    skipNextSearchRef.current = true;
                    setShowSuggestions(false);
                    setSuggestions([]);
                    handlePivotToNode(item.code);
                    setSearchQuery(item.code);
                  }}
                  className="px-3 py-2 hover:bg-slate-800/80 cursor-pointer border-b border-slate-800/40 last:border-0"
                >
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-cyan-400 font-semibold">{item.code}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                      {item.source} • {item.type}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300 truncate mt-0.5">{item.title}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Sources Federation Pill Button */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsSourceModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-lg text-xs font-medium text-slate-300 transition-colors"
          >
            <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
            <span>Sources</span>
            <span className="px-1.5 py-0.2 rounded-full bg-cyan-950 border border-cyan-800/60 text-[10px] text-cyan-300 font-mono">
              {activeSources.length} Active
            </span>
          </button>
        </div>
      </div>

      {/* Quick Presets Ribbon */}
      <div className="flex items-center gap-2 px-5 py-1.5 bg-slate-950 border-b border-slate-800/60 text-xs text-slate-400 overflow-x-auto shrink-0">
        <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider shrink-0">
          {entryMode === 'exact' ? 'Exact Presets:' : 'HyDE Scenarios:'}
        </span>
        {entryMode === 'exact' ? (
          <>
            {[
              { code: 'ORO.GEN.200', label: 'ORO.GEN.200 (SMS)', mode: 'chain' },
              { code: 'CAT.OP.MPA.180', label: 'CAT.OP.MPA.180 (Fuel)', mode: 'chain' },
              { code: '145.A.30', label: '145.A.30 (Maint)', mode: 'chain' },
              { code: 'FCL.055', label: 'FCL.055 (Aircrew)', mode: 'chain' },
              { code: 'CS 25.1309', label: 'CS 25.1309 (Cert)', mode: 'chain' },
              { code: 'ORO.GEN.200', label: 'Blast: ORO.GEN.200', mode: 'blast' }
            ].map(p => (
              <button
                key={p.label}
                onClick={() => {
                  setCurrentCode(p.code);
                  setCurrentMode(p.mode as any);
                  loadGraph(p.mode as any, p.code);
                }}
                className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors shrink-0 ${
                  currentCode === p.code && currentMode === p.mode
                    ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60'
                    : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {p.label}
              </button>
            ))}
          </>
        ) : (
          <>
            {[
              { query: 'How should an operator handle flight duty extensions during unforeseen operational delays?', label: '⏱️ FTL Delay Extensions' },
              { query: 'Accountable manager duties and safety management system hazard identification', label: '🛡️ Accountable Mgr SMS' },
              { query: 'Contingency fuel planning and minimum fuel declarations in flight', label: '⛽ In-Flight Fuel Policy' },
              { query: 'Leasing of third-country registered aircraft by an EU commercial operator', label: '✈️ Wet / Dry Aircraft Lease' }
            ].map(s => (
              <button
                key={s.label}
                onClick={() => {
                  setSearchQuery(s.query);
                  handleRunHyde(s.query);
                }}
                className="px-2 py-0.5 rounded text-[11px] bg-slate-900 text-purple-300 hover:text-purple-100 hover:bg-slate-800 border border-purple-900/40 transition-colors shrink-0"
              >
                {s.label}
              </button>
            ))}
          </>
        )}
      </div>

      {/* ================= MAIN WORKSPACE: LEFT CONTROLS + CANVAS + DRAWER ================= */}
      <div className="flex flex-1 relative overflow-hidden">
        {/* Left Controls & Legend Sidebar */}
        <aside className="w-64 bg-slate-900/80 border-r border-slate-800/80 p-3.5 flex flex-col gap-3.5 overflow-y-auto shrink-0 select-text">
          {/* Visual Mode Selector */}
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              <span>Visual Mode</span>
            </h3>
            <div className="flex flex-col gap-1">
              {[
                { id: 'chain', label: 'Compliance Chain', sub: 'IR + AMC + GM hierarchy' },
                { id: 'blast', label: 'Blast Radius', sub: 'Dependencies & citations' },
                { id: 'concept', label: 'Concept Ontology', sub: 'Cross-Annex concept mesh' }
              ].map(m => (
                <button
                  key={m.id}
                  onClick={() => {
                    setCurrentMode(m.id as any);
                    loadGraph(m.id as any, m.id === 'concept' ? currentConcept : currentCode);
                  }}
                  className={`text-left px-2.5 py-1.5 rounded-md transition-all ${
                    currentMode === m.id
                      ? 'bg-slate-800 text-cyan-400 border border-cyan-500/30'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  <div className="text-xs font-semibold">{m.label}</div>
                  <div className="text-[10px] text-slate-500">{m.sub}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Graph Legend */}
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Ontology Legend
            </h3>
            <div className="flex flex-col gap-1.5 text-[11px]">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-500" />
                  <span>Implementing Rule (IR)</span>
                </div>
                <span className="text-[9px] px-1 bg-purple-950 text-purple-300 rounded font-mono">Hard Law</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  <span>Acceptable Means (AMC)</span>
                </div>
                <span className="text-[9px] px-1 bg-emerald-950 text-emerald-300 rounded font-mono">Soft Law</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  <span>Guidance Material (GM)</span>
                </div>
                <span className="text-[9px] px-1 bg-amber-950 text-amber-300 rounded font-mono">Soft Law</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-sky-500" />
                  <span>Regulatory Annex</span>
                </div>
                <span className="text-[9px] px-1 bg-sky-950 text-sky-300 rounded font-mono">Structure</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
                  <span>Concept Node</span>
                </div>
                <span className="text-[9px] px-1 bg-rose-950 text-rose-300 rounded font-mono">Ontology</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-orange-500" />
                  <span>Stakeholder</span>
                </div>
                <span className="text-[9px] px-1 bg-orange-950 text-orange-300 rounded font-mono">Actor</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
                  <span>SIMILAR_TO</span>
                </div>
                <span className="text-[9px] px-1 bg-cyan-950 text-cyan-300 rounded font-mono">Semantic</span>
              </div>
            </div>
          </div>

          {/* Metrics */}
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Graph Topology Metrics
            </h3>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="bg-slate-900 p-1.5 rounded border border-slate-800/60">
                <div className="text-base font-bold text-cyan-400 font-mono">
                  {graphData ? graphData.nodes.length : 0}
                </div>
                <div className="text-[10px] text-slate-400">Active Nodes</div>
              </div>
              <div className="bg-slate-900 p-1.5 rounded border border-slate-800/60">
                <div className="text-base font-bold text-cyan-400 font-mono">
                  {graphData ? graphData.links.length : 0}
                </div>
                <div className="text-[10px] text-slate-400">Active Edges</div>
              </div>
              <div className="bg-slate-900 p-1.5 rounded border border-slate-800/60">
                <div className="text-base font-bold text-slate-200 font-mono">
                  {stats ? stats.total_provisions.toLocaleString() : '19,616'}
                </div>
                <div className="text-[10px] text-slate-400">Total Rules</div>
              </div>
              <div className="bg-slate-900 p-1.5 rounded border border-slate-800/60">
                <div className="text-base font-bold text-slate-200 font-mono">
                  {stats ? Object.values(stats.relationships).reduce((a, b) => a + b, 0).toLocaleString() : '110k+'}
                </div>
                <div className="text-[10px] text-slate-400">Total Edges</div>
              </div>
            </div>
          </div>

          {/* Viewport Controls */}
          <div className="bg-slate-950/70 p-2.5 rounded-lg border border-slate-800 mt-auto">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
              Viewport Controls
            </h3>
            <div className="grid grid-cols-2 gap-1.5">
              <button
                onClick={handleZoomIn}
                className="flex items-center justify-center gap-1 px-2 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded text-xs text-slate-300 transition-colors"
                title="Zoom In"
              >
                <ZoomIn className="w-3.5 h-3.5" /> Zoom In
              </button>
              <button
                onClick={handleZoomOut}
                className="flex items-center justify-center gap-1 px-2 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded text-xs text-slate-300 transition-colors"
                title="Zoom Out"
              >
                <ZoomOut className="w-3.5 h-3.5" /> Zoom Out
              </button>
              <button
                onClick={handleResetView}
                className="flex items-center justify-center gap-1 px-2 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded text-xs text-slate-300 transition-colors"
                title="Center Camera"
              >
                <Maximize2 className="w-3.5 h-3.5" /> Center
              </button>
              <button
                onClick={handleTogglePhysics}
                className={`flex items-center justify-center gap-1 px-2 py-1.5 rounded text-xs font-medium border transition-colors ${
                  isPhysicsFrozen
                    ? 'bg-amber-950/80 text-amber-300 border-amber-700/60'
                    : 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
                }`}
                title="Toggle Physics Freeze"
              >
                <Cpu className="w-3.5 h-3.5" /> {isPhysicsFrozen ? 'Unfreeze' : 'Freeze'}
              </button>
            </div>
          </div>
        </aside>

        {/* Center D3 Canvas */}
        <main className="flex-1 relative bg-slate-950 overflow-hidden flex flex-col">
          <svg ref={svgRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

          {/* Loading Overlay */}
          {isLoading && (
            <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm flex flex-col items-center justify-center gap-3 z-30">
              <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
              <div className="text-sm font-medium text-slate-300">
                Traversing Kùzu Regulatory Graph...
              </div>
            </div>
          )}

          {/* Error Banner */}
          {errorMessage && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-red-950/90 border border-red-700 text-red-200 px-4 py-2 rounded-lg shadow-xl text-xs flex items-center gap-2 z-30">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{errorMessage}</span>
              <button
                onClick={() => setErrorMessage(null)}
                className="ml-2 hover:text-white"
              >
                ✕
              </button>
            </div>
          )}

          {/* Floating Quick-Pivot Bar when a node is selected */}
          {selectedNode && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-slate-900/95 border border-slate-700/80 shadow-2xl rounded-xl px-4 py-2 flex items-center gap-3 z-20 backdrop-blur">
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded text-white font-mono"
                style={{ backgroundColor: NODE_COLORS[selectedNode.type] || '#64748b' }}
              >
                {selectedNode.type}
              </span>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-slate-100 font-mono">
                  {selectedNode.label}
                </span>
                <span className="text-[10px] text-slate-400 max-w-xs truncate">
                  {selectedNode.title || selectedNode.subject || ''}
                </span>
              </div>
              <div className="flex items-center gap-1.5 ml-2 border-l border-slate-700/60 pl-3">
                <button
                  onClick={() => handlePivotToNode(selectedNode.label)}
                  className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-semibold flex items-center gap-1 transition-colors shadow-sm"
                  title="Regenerate the entire graph view around this node as central anchor"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Regenerate View Here</span>
                </button>
                <button
                  onClick={() => {
                    setIsInspectorOpen(true);
                    if (!nodeDetails && selectedNode) {
                      handleSelectNode(selectedNode);
                    }
                  }}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs font-semibold flex items-center gap-1 transition-colors border border-slate-700"
                  title="Deep 360° legal inspection"
                >
                  <Eye className="w-3 h-3" />
                  <span>Deep Inspect</span>
                </button>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* Helper Hint */}
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-slate-900/80 border border-slate-800/80 rounded-full text-[11px] text-slate-400 backdrop-blur pointer-events-none">
            💡 <strong>Click</strong> node to inspect & regenerate • <strong>Drag</strong> to pin • <strong>Scroll</strong> to zoom
          </div>
        </main>

        {/* Right Drawer: Quick Overview */}
        {isDrawerOpen && selectedNode && (
          <aside className="w-80 bg-slate-900 border-l border-slate-800 p-4 flex flex-col gap-3 overflow-y-auto z-20 shrink-0 select-text">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <div className="flex items-center gap-2">
                <span
                  className="text-[10px] font-bold px-2 py-0.5 rounded text-white font-mono"
                  style={{ backgroundColor: NODE_COLORS[selectedNode.type] || '#64748b' }}
                >
                  {selectedNode.type}
                </span>
                <h2 className="text-sm font-bold text-slate-100 font-mono">
                  {selectedNode.label}
                </h2>
              </div>
              <button
                onClick={() => setIsDrawerOpen(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Official Title */}
            <div>
              <div className="text-[10px] uppercase font-semibold text-slate-500 mb-0.5">
                Official Title
              </div>
              <div className="text-xs font-medium text-slate-200">
                {selectedNode.title || nodeDetails?.title || 'No official title recorded'}
              </div>
            </div>

            {/* Regulatory Annex */}
            {nodeDetails?.annex && (
              <div>
                <div className="text-[10px] uppercase font-semibold text-slate-500 mb-0.5">
                  Regulatory Annex
                </div>
                <div className="inline-block px-2 py-0.5 bg-sky-950/80 border border-sky-800 text-sky-300 rounded text-xs font-mono">
                  {nodeDetails.annex.name} ({nodeDetails.annex.code})
                </div>
              </div>
            )}

            {/* Verbatim Excerpt */}
            <div>
              <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1">
                Verbatim Excerpt
              </div>
              <div className="p-2.5 bg-slate-950 rounded border border-slate-800 text-xs text-slate-300 leading-relaxed font-serif max-h-48 overflow-y-auto">
                {isDetailsLoading ? (
                  <div className="text-slate-500 italic">Fetching regulatory text...</div>
                ) : (
                  nodeDetails?.text_snippet || nodeDetails?.full_text || selectedNode.text || 'No text snippet recorded.'
                )}
              </div>
            </div>

            {/* Attached Soft Law */}
            {nodeDetails && (nodeDetails.acceptable_means_of_compliance?.length || nodeDetails.guidance_material?.length) ? (
              <div>
                <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1">
                  Attached Soft Law (AMCs & GMs)
                </div>
                <div className="flex flex-col gap-1 max-h-36 overflow-y-auto">
                  {nodeDetails.acceptable_means_of_compliance?.map(amc => (
                    <div
                      key={amc.id}
                      onClick={() => handlePivotToNode(amc.code)}
                      className="px-2 py-1 bg-slate-950 hover:bg-slate-800 border border-emerald-900/40 rounded cursor-pointer transition-colors"
                    >
                      <div className="text-[11px] font-mono text-emerald-400 font-semibold">{amc.code}</div>
                      <div className="text-[10px] text-slate-400 truncate">{amc.title}</div>
                    </div>
                  ))}
                  {nodeDetails.guidance_material?.map(gm => (
                    <div
                      key={gm.id}
                      onClick={() => handlePivotToNode(gm.code)}
                      className="px-2 py-1 bg-slate-950 hover:bg-slate-800 border border-amber-900/40 rounded cursor-pointer transition-colors"
                    >
                      <div className="text-[11px] font-mono text-amber-400 font-semibold">{gm.code}</div>
                      <div className="text-[10px] text-slate-400 truncate">{gm.title}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Semantic Parallels (SIMILAR_TO) */}
            {nodeDetails?.similar_provisions && nodeDetails.similar_provisions.length > 0 && (
              <div>
                <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1 flex items-center justify-between">
                  <span>Semantic Parallels</span>
                  <span className="text-cyan-400 font-mono">{nodeDetails.similar_provisions.length} Links</span>
                </div>
                <div className="flex flex-col gap-1 max-h-36 overflow-y-auto">
                  {nodeDetails.similar_provisions.slice(0, 5).map(sim => (
                    <div
                      key={sim.id}
                      onClick={() => handlePivotToNode(sim.code)}
                      className="p-1.5 bg-slate-950 hover:bg-slate-800 border border-cyan-900/40 rounded cursor-pointer transition-colors"
                    >
                      <div className="flex items-center justify-between text-[11px] font-mono">
                        <span className="text-cyan-300 font-semibold">{sim.code}</span>
                        <span className="text-[9px] px-1 bg-cyan-950 text-cyan-300 rounded">
                          {Math.round(sim.score * 100)}% Match
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-400 truncate">{sim.title}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Drawer Actions */}
            <div className="flex flex-col gap-2 mt-auto pt-3 border-t border-slate-800">
              <button
                onClick={() => handlePivotToNode(selectedNode.label)}
                className="w-full py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-sm"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Regenerate View Around Node</span>
              </button>
              <button
                onClick={() => {
                  setIsInspectorOpen(true);
                  if (!nodeDetails && selectedNode) {
                    handleSelectNode(selectedNode);
                  }
                }}
                className="w-full py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-md text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
              >
                <Eye className="w-3.5 h-3.5 text-cyan-400" />
                <span>Examine Full Context & Text</span>
              </button>
              <button
                onClick={() => handlePanToNode(selectedNode)}
                className="w-full py-1.5 bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded-md text-xs font-medium flex items-center justify-center gap-1.5 transition-colors"
              >
                <Compass className="w-3.5 h-3.5 text-slate-400" />
                <span>Pan Camera Here</span>
              </button>
            </div>
          </aside>
        )}
      </div>

      {/* ================= 360° NODE INSPECTOR MODAL ================= */}
      {isInspectorOpen && selectedNode && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <div className="flex items-center gap-3">
                <span
                  className="text-xs font-bold px-2.5 py-1 rounded text-white font-mono"
                  style={{ backgroundColor: NODE_COLORS[selectedNode.type] || '#64748b' }}
                >
                  {selectedNode.type}
                </span>
                <div>
                  <h2 className="text-lg font-bold text-slate-100 font-mono">
                    {selectedNode.label}
                  </h2>
                  <div className="text-xs text-slate-400">
                    {selectedNode.title || nodeDetails?.title || ''}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handlePivotToNode(selectedNode.label)}
                  className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Regenerate View Here</span>
                </button>
                <button
                  onClick={() => setIsInspectorOpen(false)}
                  className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-100 rounded-lg"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Tabs Header */}
            <div className="flex border-b border-slate-800 bg-slate-950/30 px-6 gap-2 text-xs font-medium text-slate-400">
              {[
                { id: 'text', label: '📖 Verbatim Text' },
                { id: 'hierarchy', label: '⚖️ Legal Hierarchy & Soft Law' },
                { id: 'similar', label: '🧬 Semantic Parallels (SIMILAR_TO)' },
                { id: 'citations', label: '🔗 Dependencies & Citations' },
                { id: 'impact', label: '👥 Stakeholders & Concepts' },
                { id: 'rag', label: '🤖 GraphRAG Context Export' }
              ].map(t => (
                <button
                  key={t.id}
                  onClick={() => setInspectorTab(t.id as any)}
                  className={`py-3 px-2 border-b-2 transition-colors ${
                    inspectorTab === t.id
                      ? 'border-cyan-400 text-cyan-400 font-semibold'
                      : 'border-transparent hover:text-slate-200'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Modal Tab Content Container */}
            <div className="p-6 overflow-y-auto flex-1 select-text">
              {isDetailsLoading ? (
                <div className="flex flex-col items-center justify-center py-20 gap-3">
                  <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
                  <span className="text-xs text-slate-400 font-medium">Fetching 360° regulatory details from graph...</span>
                </div>
              ) : (
                <>
                  {/* Tab 1: Verbatim Text */}
                  {inspectorTab === 'text' && (
                    <div className="flex flex-col gap-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-slate-400">
                          Official EASA Easy Access regulatory text stored in Kùzu Cypher graph
                        </span>
                        <button
                          onClick={() => handleCopy(nodeDetails?.full_text || nodeDetails?.text_snippet || nodeDetails?.text || '')}
                          className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs flex items-center gap-1"
                        >
                          {copiedText ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                          <span>{copiedText ? 'Copied' : 'Copy Text'}</span>
                        </button>
                      </div>
                      <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-sm text-slate-200 font-serif leading-relaxed whitespace-pre-wrap">
                        {nodeDetails?.full_text || nodeDetails?.text_snippet || nodeDetails?.text || selectedNode?.text || 'No text snippet found.'}
                      </div>
                    </div>
                  )}

                  {/* Tab 2: Legal Hierarchy & Soft Law */}
                  {inspectorTab === 'hierarchy' && (
                    <div className="flex flex-col gap-5">
                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Upstream Implementing Rule (Hard Law)
                        </h3>
                        {(nodeDetails?.upstream_rules?.length || nodeDetails?.upstream?.length) ? (
                          <div className="flex flex-col gap-2">
                            {(nodeDetails?.upstream_rules || nodeDetails?.upstream || []).map(u => (
                              <div
                                key={u.id}
                                onClick={() => handlePivotToNode(u.code)}
                                className="p-3 bg-slate-950 border border-purple-900/40 rounded-lg hover:border-purple-600/80 cursor-pointer transition-colors"
                              >
                                <span className="text-xs font-mono font-bold text-purple-400">{u.code}</span>
                                <div className="text-xs text-slate-300 mt-0.5">{u.title}</div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-slate-500 italic">This node is the root hard law implementing rule.</div>
                        )}
                      </div>

                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Downstream Acceptable Means of Compliance (AMC)
                        </h3>
                        {((nodeDetails?.acceptable_means_of_compliance?.length || 0) > 0 || (nodeDetails?.downstream_amcs?.length || 0) > 0) ? (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {(nodeDetails?.acceptable_means_of_compliance || nodeDetails?.downstream_amcs || []).map(amc => (
                              <div
                                key={amc.id}
                                onClick={() => handlePivotToNode(amc.code)}
                                className="p-2.5 bg-slate-950 border border-emerald-900/40 rounded-lg hover:border-emerald-600/80 cursor-pointer transition-colors"
                              >
                                <span className="text-xs font-mono font-bold text-emerald-400">{amc.code}</span>
                                <div className="text-xs text-slate-300 truncate mt-0.5">{amc.title}</div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-slate-500 italic">No associated Acceptable Means of Compliance (AMC).</div>
                        )}
                      </div>

                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Downstream Guidance Material (GM)
                        </h3>
                        {((nodeDetails?.guidance_material?.length || 0) > 0 || (nodeDetails?.downstream_gms?.length || 0) > 0) ? (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {(nodeDetails?.guidance_material || nodeDetails?.downstream_gms || []).map(gm => (
                              <div
                                key={gm.id}
                                onClick={() => handlePivotToNode(gm.code)}
                                className="p-2.5 bg-slate-950 border border-amber-900/40 rounded-lg hover:border-amber-600/80 cursor-pointer transition-colors"
                              >
                                <span className="text-xs font-mono font-bold text-amber-400">{gm.code}</span>
                                <div className="text-xs text-slate-300 truncate mt-0.5">{gm.title}</div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-slate-500 italic">No associated Guidance Material (GM).</div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Tab 3: Semantic Parallels */}
                  {inspectorTab === 'similar' && (
                    <div className="flex flex-col gap-3">
                      <div className="text-xs text-slate-400 mb-1">
                        Provisions sharing dense semantic embedding equivalence across Air Operations, Continuing Airworthiness, and Certification.
                      </div>
                      {nodeDetails?.similar_provisions?.length ? (
                        nodeDetails.similar_provisions.map(sim => (
                          <div
                            key={sim.id}
                            className="p-3 bg-slate-950 border border-cyan-900/40 rounded-xl flex items-start justify-between gap-4"
                          >
                            <div className="flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-mono font-bold text-cyan-400">{sim.code}</span>
                                <span className="text-[10px] px-1.5 py-0.2 bg-slate-800 text-slate-400 rounded">
                                  {sim.annex}
                                </span>
                                <span className="text-[10px] px-1.5 py-0.2 bg-cyan-950 text-cyan-300 rounded font-mono">
                                  {Math.round(sim.score * 100)}% Equivalence
                                </span>
                              </div>
                              <div className="text-xs font-medium text-slate-200 mt-1">{sim.title}</div>
                              {sim.reason && (
                                <div className="text-xs text-slate-400 mt-1 italic font-serif">
                                  "{sim.reason}"
                                </div>
                              )}
                            </div>
                            <button
                              onClick={() => handlePivotToNode(sim.code)}
                              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-cyan-400 rounded text-xs font-medium transition-colors shrink-0 flex items-center gap-1"
                            >
                              <span>Pivot Here</span>
                              <ArrowUpRight className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-slate-500 italic">No semantic parallels recorded for this provision.</div>
                      )}
                    </div>
                  )}

                  {/* Tab 4: Dependencies & Citations */}
                  {inspectorTab === 'citations' && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Rules Citing This Provision (Blast Impact)
                        </h3>
                        <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto">
                          {nodeDetails?.incoming_citations?.length ? (
                            nodeDetails.incoming_citations.map(c => (
                              <div
                                key={c.code}
                                onClick={() => handlePivotToNode(c.code)}
                                className="p-2 bg-slate-950 border border-slate-800 rounded hover:border-slate-700 cursor-pointer"
                              >
                                <span className="text-xs font-mono font-bold text-purple-400">{c.code}</span>
                                <div className="text-[11px] text-slate-400 truncate">{c.title}</div>
                              </div>
                            ))
                          ) : (
                            <div className="text-xs text-slate-500 italic">No incoming citations recorded.</div>
                          )}
                        </div>
                      </div>

                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Outgoing Citations (Referenced Rules)
                        </h3>
                        <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto">
                          {nodeDetails?.outgoing_citations?.length ? (
                            nodeDetails.outgoing_citations.map(c => (
                              <div
                                key={c.code}
                                onClick={() => handlePivotToNode(c.code)}
                                className="p-2 bg-slate-950 border border-slate-800 rounded hover:border-slate-700 cursor-pointer"
                              >
                                <span className="text-xs font-mono font-bold text-sky-400">{c.code}</span>
                                <div className="text-[11px] text-slate-400 truncate">{c.title}</div>
                              </div>
                            ))
                          ) : (
                            <div className="text-xs text-slate-500 italic">No outgoing cross-references recorded.</div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Tab 5: Stakeholders & Concepts */}
                  {inspectorTab === 'impact' && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Governed Stakeholder Roles
                        </h3>
                        {nodeDetails?.stakeholders?.length ? (
                          <div className="flex flex-col gap-2">
                            {nodeDetails.stakeholders.map(s => (
                              <div key={s.name} className="p-2.5 bg-slate-950 border border-orange-900/40 rounded-lg">
                                <span className="text-xs font-bold text-orange-400">{s.name}</span>
                                <span className="ml-2 text-[10px] px-1 bg-orange-950 text-orange-300 rounded font-mono">
                                  {s.role_type}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-slate-500 italic">No explicit stakeholder links mapped.</div>
                        )}
                      </div>

                      <div>
                        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                          Governed Aviation Concepts
                        </h3>
                        {nodeDetails?.concepts?.length ? (
                          <div className="flex flex-col gap-2">
                            {nodeDetails.concepts.map(c => (
                              <div key={c.name} className="p-2.5 bg-slate-950 border border-rose-900/40 rounded-lg">
                                <span className="text-xs font-bold text-rose-400">{c.name}</span>
                                <span className="ml-2 text-[10px] px-1 bg-rose-950 text-rose-300 rounded font-mono">
                                  {c.category}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-slate-500 italic">No operational concepts directly mapped.</div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Tab 6: GraphRAG Context Export */}
                  {inspectorTab === 'rag' && (
                    <div className="flex flex-col gap-4">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-slate-400">
                          Synthesized GraphRAG context with complete legal hierarchy, soft law, and citations ready for LLM prompts.
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleCopy(nodeDetails?.graphrag_context || nodeDetails?.graph_rag_markdown || '')}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs flex items-center gap-1"
                          >
                            {copiedText ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                            <span>{copiedText ? 'Copied' : 'Copy Prompt Context'}</span>
                          </button>
                          {onSendToAssistant && (
                            <button
                              onClick={() => {
                                const ragText = nodeDetails?.graphrag_context || nodeDetails?.graph_rag_markdown;
                                if (ragText) {
                                  onSendToAssistant(
                                    `Regarding regulatory provision ${selectedNode.label}:\n\n` + ragText
                                  );
                                  setIsInspectorOpen(false);
                                }
                              }}
                              className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-semibold flex items-center gap-1 shadow-sm"
                            >
                              <Send className="w-3 h-3" />
                              <span>Send to Assistant</span>
                            </button>
                          )}
                        </div>
                      </div>
                      <pre className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-300 font-mono leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
                        {nodeDetails?.graphrag_context || nodeDetails?.graph_rag_markdown || 'Generating GraphRAG context...'}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ================= HYDE DISCOVERY CANDIDATES MODAL ================= */}
      {isHydeModalOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-purple-700/80 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-5 h-5 text-purple-400" />
                <h2 className="text-base font-bold text-slate-100">
                  HyDE Semantic Discovery & Candidate Provisions
                </h2>
              </div>
              <button
                onClick={() => setIsHydeModalOpen(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-100 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 flex flex-col gap-5 select-text">
              {isHydeLoading ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <RefreshCw className="w-8 h-8 text-purple-400 animate-spin" />
                  <div className="text-sm text-slate-300 font-medium">
                    Synthesizing hypothetical EASA regulatory excerpt & searching vector space...
                  </div>
                </div>
              ) : hydeResult ? (
                <>
                  {/* Synthesized Excerpt Box */}
                  <div className="p-4 bg-purple-950/30 border border-purple-800/60 rounded-xl">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-purple-300 font-mono">
                        Synthesized Hypothetical EASA Regulation Anchor
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-purple-900/60 text-purple-200 font-mono">
                        AI-Generated Vector Anchor
                      </span>
                    </div>
                    <p className="text-xs text-purple-100/90 font-serif leading-relaxed italic">
                      "{hydeResult.hypothetical_document}"
                    </p>
                  </div>

                  {/* Ranked Candidates */}
                  <div>
                    <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">
                      Top Ranked Candidate Provisions ({(hydeResult.candidates || []).length} Discovered)
                    </h3>
                    <div className="flex flex-col gap-2">
                      {(hydeResult.candidates || []).map(c => (
                        <div
                          key={`${c.source}-${c.id}`}
                          className="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-between gap-4 hover:border-slate-700 transition-colors"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-mono font-bold text-cyan-400">{c.code}</span>
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                                {c.source} • {c.type}
                              </span>
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-950 text-cyan-300 font-mono">
                                {c.match_percentage}% Match
                              </span>
                            </div>
                            <div className="text-xs font-semibold text-slate-200 mt-1">{c.title}</div>
                            <p className="text-xs text-slate-400 line-clamp-2 mt-1 font-serif">
                              {c.text_snippet}
                            </p>
                          </div>
                          <button
                            onClick={() => handlePivotToNode(c.code)}
                            className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors shrink-0 shadow-sm"
                          >
                            <span>Explore in Graph</span>
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* ================= SOURCES FEDERATION CONFIG MODAL ================= */}
      {isSourceModalOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
              <div className="flex items-center gap-2.5">
                <BookOpen className="w-5 h-5 text-cyan-400" />
                <h2 className="text-base font-bold text-slate-100">
                  Federated Regulatory & Knowledge Sources
                </h2>
              </div>
              <button
                onClick={() => setIsSourceModalOpen(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-100 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 flex flex-col gap-4 select-text">
              <div className="text-xs text-slate-400">
                Configure knowledge bases included in federated search, cross-reference discovery, and HyDE matching.
              </div>

              {/* Source Cards */}
              <div className="flex flex-col gap-2">
                {[
                  { id: 'EASA', name: 'EASA Easy Access Rules', desc: 'Core European Union Aviation Safety Agency regulations and soft law', records: '19,616 provisions' },
                  { id: 'EU', name: 'EU Formex Regulations', desc: 'EUR-Lex Official Journal regulations and acts', records: '1,420 articles' },
                  { id: 'FAA', name: 'FAA Title 14 CFR', desc: 'Federal Aviation Regulations (e.g. Part 25, 91, 121, 135)', records: '12,500 sections' },
                  { id: 'EUROCAE', name: 'EUROCAE Standards', desc: 'European civil aviation electronics and avionics technical standards', records: '3,200 requirements' },
                  { id: 'SKYBRARY', name: 'Skybrary Aviation Safety Knowledge', desc: 'Operational safety portal curated by EUROCONTROL and Flight Safety Foundation', records: '1,850 articles' }
                ].map(s => {
                  const isActive = activeSources.includes(s.id);
                  return (
                    <div
                      key={s.id}
                      onClick={() => {
                        setActiveSources(prev =>
                          prev.includes(s.id)
                            ? (prev.length > 1 ? prev.filter(x => x !== s.id) : prev)
                            : [...prev, s.id]
                        );
                      }}
                      className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                        isActive
                          ? 'bg-slate-950 border-cyan-800/80 text-slate-100'
                          : 'bg-slate-950/40 border-slate-800/80 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold font-mono">{s.name}</span>
                          <span className="text-[10px] px-1.5 py-0.2 bg-slate-800 rounded text-slate-400">
                            {s.records}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">{s.desc}</div>
                      </div>
                      <div className={`w-5 h-5 rounded-md flex items-center justify-center border text-xs ${
                        isActive ? 'bg-cyan-600 border-cyan-500 text-white' : 'border-slate-700 bg-slate-900'
                      }`}>
                        {isActive && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Skybrary Subtopics */}
              {activeSources.includes('SKYBRARY') && sourcesCatalog?.skybrary_categories && (
                <div className="mt-2 p-3 bg-slate-950 rounded-xl border border-slate-800 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-200">
                      Skybrary Domain Sub-Topics Filter ({selectedSkybraryTopics.length ? `${selectedSkybraryTopics.length} Selected` : 'All Topics Active'})
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setSelectedSkybraryTopics([])}
                        className="text-[10px] px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded"
                      >
                        Reset / All
                      </button>
                    </div>
                  </div>
                  <input
                    type="text"
                    value={subtopicFilter}
                    onChange={(e) => setSubtopicFilter(e.target.value)}
                    placeholder="Filter sub-topics (e.g. Fuel, ATM, Human Factors)..."
                    className="bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 outline-none"
                  />
                  <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto pt-1">
                    {sourcesCatalog.skybrary_categories
                      .filter(c => !subtopicFilter || c.name.toLowerCase().includes(subtopicFilter.toLowerCase()))
                      .map(c => {
                        const isSelected = selectedSkybraryTopics.includes(c.name);
                        return (
                          <button
                            key={c.name}
                            onClick={() => {
                              setSelectedSkybraryTopics(prev =>
                                prev.includes(c.name)
                                  ? prev.filter(x => x !== c.name)
                                  : [...prev, c.name]
                              );
                            }}
                            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                              isSelected
                                ? 'bg-cyan-950 text-cyan-300 border border-cyan-700'
                                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                            }`}
                          >
                            <span>{c.name}</span>
                            <span className="ml-1 text-[9px] text-slate-500">({c.count})</span>
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex justify-end">
              <button
                onClick={() => setIsSourceModalOpen(false)}
                className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold transition-colors"
              >
                Apply Sources
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
