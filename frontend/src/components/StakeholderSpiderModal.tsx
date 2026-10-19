import React, { useState, useMemo } from 'react';
import { 
  X, 
  Building2, 
  Layers, 
  Compass, 
  Search, 
  Check, 
  HelpCircle, 
  ShieldCheck, 
  TrendingDown, 
  TrendingUp, 
  VolumeX, 
  Volume2, 
  Users,
  Flame,
  Handshake,
  ArrowRight,
  Scale,
  Zap,
  AlertTriangle,
  FileText
} from 'lucide-react';
import { OrganisationAnalysis, ConsultationSession, ConsultationComment } from '../services/consultationService';

interface StakeholderSpiderModalProps {
  isOpen: boolean;
  onClose: () => void;
  organisations: OrganisationAnalysis[];
  session: ConsultationSession;
  initialSelectedOrgName?: string | null;
}

// 10 Distinct vibrant palette colors for multi-stakeholder radar overlay
const RADAR_PALETTE = [
  { stroke: '#38bdf8', fill: 'rgba(56, 189, 248, 0.22)', dot: '#38bdf8', name: 'Sky Blue' },
  { stroke: '#a855f7', fill: 'rgba(168, 85, 247, 0.22)', dot: '#a855f7', name: 'Purple' },
  { stroke: '#34d399', fill: 'rgba(52, 211, 153, 0.22)', dot: '#34d399', name: 'Emerald' },
  { stroke: '#f59e0b', fill: 'rgba(245, 158, 11, 0.22)', dot: '#f59e0b', name: 'Amber' },
  { stroke: '#f43f5e', fill: 'rgba(244, 63, 94, 0.22)', dot: '#f43f5e', name: 'Rose' },
  { stroke: '#2dd4bf', fill: 'rgba(45, 212, 191, 0.22)', dot: '#2dd4bf', name: 'Teal' },
  { stroke: '#ec4899', fill: 'rgba(236, 72, 153, 0.22)', dot: '#ec4899', name: 'Pink' },
  { stroke: '#818cf8', fill: 'rgba(129, 140, 248, 0.22)', dot: '#818cf8', name: 'Indigo' },
  { stroke: '#eab308', fill: 'rgba(234, 179, 8, 0.22)', dot: '#eab308', name: 'Yellow' },
  { stroke: '#94a3b8', fill: 'rgba(148, 163, 184, 0.22)', dot: '#94a3b8', name: 'Slate' },
];

export interface DirectionOfTravelDefinition {
  key: string;
  shortLabel: string;
  fullTitle: string;
  description: string;
  policyTheme: string;
  typicalChampions: string;
  naturalOpponents: string;
  keywords: string[];
}

// Canonical directions of travel taxonomy in aviation & public consultation governance
export const CANONICAL_DIRECTIONS: DirectionOfTravelDefinition[] = [
  {
    key: 'Timeline Extension & Transitional Phasing',
    shortLabel: 'Timeline Extension',
    fullTitle: 'Timeline Extension & Transitional Phasing',
    description: 'Advocating for extended transitional deadlines, phased implementation, or multi-year grace periods.',
    policyTheme: 'Implementation Feasibility',
    typicalChampions: 'Commercial Airlines, Air Operators, Ground Handlers',
    naturalOpponents: 'National Aviation Authorities, Safety Oversight Boards, Passenger Advocates',
    keywords: ['timeline', 'transition', 'delay', 'grace period', 'months', 'years', 'postpone', 'phased']
  },
  {
    key: 'Proportionality Relief & Scope Exemptions for Non-Complex Entities',
    shortLabel: 'Proportionality & Scope',
    fullTitle: 'Proportionality Relief & Scope Exemptions',
    description: 'Demanding tiered obligations, tailored thresholds, or exclusions for SMEs, General Aviation, and non-complex entities.',
    policyTheme: 'Regulatory Burden Reduction',
    typicalChampions: 'General Aviation, Flying Clubs, Regional Small Operators, UAV Startups',
    naturalOpponents: 'Large Network Carriers, European Regulatory Bodies (urging level playing fields)',
    keywords: ['proportional', 'small operator', 'sme', 'general aviation', 'glider', 'exclude', 'exemption', 'non-complex']
  },
  {
    key: 'Flexibility via Non-Binding Guidance (AMC/GM) rather than Hard Rules',
    shortLabel: 'Flexibility via AMC/GM',
    fullTitle: 'Flexibility via Non-Binding Guidance (AMC/GM)',
    description: 'Recommending that prescriptive requirements be shifted from hard Implementing Rules into flexible soft-law AMC or Guidance Material.',
    policyTheme: 'Operational Flexibility',
    typicalChampions: 'Aerospace Manufacturers, Engineering Design Organisations, Airlines',
    naturalOpponents: 'Enforcement Bodies and Legal Auditors (seeking binding clarity)',
    keywords: ['amc', 'gm', 'guidance material', 'acceptable means', 'criteria', 'clarify', 'guidance', 'soft law']
  },
  {
    key: 'Mitigation of Compliance Costs & Resourcing Burdens',
    shortLabel: 'Cost Mitigation',
    fullTitle: 'Mitigation of Compliance Costs & Resourcing Burdens',
    description: 'Prioritizing reduction of CAPEX/OPEX, equipment retrofit expenses, administrative fees, and training burdens.',
    policyTheme: 'Economic Proportionality',
    typicalChampions: 'Airline Associations (IATA, A4E), Airport Operators, MRO Facilities',
    naturalOpponents: 'Safety regulators requiring uncompromising risk mitigations',
    keywords: ['cost', 'budget', 'procurement', 'fee', 'financial burden', 'capex', 'opex', 'expensive']
  },
  {
    key: 'Enhancement of Risk Mitigation & Operational Safety Margins',
    shortLabel: 'Safety Margins & Oversight',
    fullTitle: 'Enhancement of Risk Mitigation & Operational Safety Margins',
    description: 'Strengthening defensive barriers, mandatory safety management systems (SMS), oversight audits, and safety margins.',
    policyTheme: 'Risk Prevention & Standard Setting',
    typicalChampions: 'National Civil Aviation Authorities, Flight Safety Foundations, Pilot Associations (ECA, BALPA)',
    naturalOpponents: 'Cost-sensitive commercial operators, de-regulation advocates',
    keywords: ['safety', 'hazard', 'risk', 'mitigation', 'sms', 'oversight', 'audit', 'defense', 'mandatory']
  },
  {
    key: 'International Standardization & ICAO Harmonization',
    shortLabel: 'ICAO / Global Alignment',
    fullTitle: 'International Standardization & ICAO Harmonization',
    description: 'Demanding strict consistency with ICAO Annexes, FAA FAR regulations, and bilateral aviation safety agreements (BASA).',
    policyTheme: 'Global Interoperability',
    typicalChampions: 'OEM Manufacturers (Airbus, Boeing), Global Alliances, Cargo Carriers',
    naturalOpponents: 'Regional purists, local environmental or unilateral standard-setters',
    keywords: ['icao', 'faa', 'harmonization', 'harmonisation', 'annex 13', 'bilateral', 'international', 'global']
  },
  {
    key: 'Strengthening Reporter Confidentiality & Just Culture Protections',
    shortLabel: 'Just Culture & Confidentiality',
    fullTitle: 'Strengthening Reporter Confidentiality & Just Culture Protections',
    description: 'Protecting occurrence reporters from self-incrimination, legal discovery, employer reprisals, and public disclosures.',
    policyTheme: 'Human Factors & Safety Reporting',
    typicalChampions: 'Pilot Associations, Air Traffic Controllers (IFATCA), Whistleblower Advocates',
    naturalOpponents: 'Judicial authorities, FOI litigators, strict public disclosure mandates',
    keywords: ['cyber', 'part-is', 'pseudonym', 'anonym', 'confidential', 'reporter identity', 'just culture', 'disclosure', 'protection']
  },
  {
    key: 'Operational Simplicity & Single-Window Harmonization',
    shortLabel: 'Single Window Simplicity',
    fullTitle: 'Operational Simplicity & Single-Window Harmonization',
    description: 'Eliminating duplicate national reporting portals in favor of unified digital platforms and streamlined administrative filings.',
    policyTheme: 'Digital Administrative Efficiency',
    typicalChampions: 'Cross-Border Operators, Business Aviation (EBAA), Air Navigation Service Providers',
    naturalOpponents: 'Fragmented national agencies wishing to preserve distinct legacy IT portals',
    keywords: ['single window', 'single portal', 'unified', 'standardized form', 'fragmented', 'portal', 'simplification']
  }
];

export const StakeholderSpiderModal: React.FC<StakeholderSpiderModalProps> = ({
  isOpen,
  onClose,
  organisations,
  session,
  initialSelectedOrgName
}) => {
  const [activeTab, setActiveTab] = useState<'spider' | 'tensions' | 'silence' | 'profiles'>('spider');
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [hoveredPoint, setHoveredPoint] = useState<{
    orgName: string;
    directionKey: string;
    directionLabel: string;
    description: string;
    score: number;
    status: string;
    directCount: number;
    x: number;
    y: number;
  } | null>(null);

  // Selected stakeholder organisation names (multi-select)
  const [selectedOrgs, setSelectedOrgs] = useState<string[]>(() => {
    if (initialSelectedOrgName && organisations.some(o => o.organisation_name === initialSelectedOrgName)) {
      return [initialSelectedOrgName];
    }
    // Default to top 3 organisations by comment volume
    const sorted = [...organisations].sort((a, b) => (b.total_comments || 0) - (a.total_comments || 0));
    return sorted.slice(0, 3).map(o => o.organisation_name);
  });

  // Dynamically determine the active directions of travel for this consultation session
  const activeDirections = useMemo(() => {
    // Collect all direction keys from session metrics and canonical definitions
    const sessionDirKeys = Object.keys(session.metrics.direction_of_travel_distribution || {});
    
    // Find canonical matches or create entries for any custom session directions
    const matched: DirectionOfTravelDefinition[] = [];
    const usedKeys = new Set<string>();

    CANONICAL_DIRECTIONS.forEach(def => {
      matched.push(def);
      usedKeys.add(def.key);
    });

    // If session has any unique custom direction not in canonical list, add it
    sessionDirKeys.forEach(key => {
      if (!usedKeys.has(key) && key.trim()) {
        matched.push({
          key,
          shortLabel: key.length > 25 ? `${key.substring(0, 22)}...` : key,
          fullTitle: key,
          description: `Consultation-specific direction of travel identified from stakeholder feedback.`,
          policyTheme: 'Specific Regulatory Issue',
          typicalChampions: 'Participating Stakeholders',
          naturalOpponents: 'Counterpart Sector Entities',
          keywords: key.toLowerCase().split(' ')
        });
        usedKeys.add(key);
      }
    });

    // Return the top 6 to 8 directions
    return matched.slice(0, 8);
  }, [session]);

  // Compute multi-vector scores (0-100) for an organisation across all directions of travel
  const computeOrgDirectionScores = useMemo(() => {
    const scoresMap = new Map<string, Record<string, number>>();

    organisations.forEach(org => {
      // 1. If the organisation already has precomputed direction_scores from backend, use it
      if (org.direction_scores && Object.keys(org.direction_scores).length > 0) {
        scoresMap.set(org.organisation_name, org.direction_scores);
        return;
      }

      // 2. Otherwise calculate dynamically based on comments submitted by this organisation
      const orgComments = session.comments.filter(
        c => (c.organisation_name || c.stakeholder_name) === org.organisation_name
      );

      const calculated: Record<string, number> = {};
      const primaryDir = org.direction_of_travel || org.primary_direction_of_travel;

      activeDirections.forEach(def => {
        // Direct comments explicitly under this direction
        const directComments = orgComments.filter(c => {
          const dir = c.direction_of_travel || '';
          return dir.toLowerCase() === def.key.toLowerCase();
        });

        if (directComments.length > 0) {
          // Strong advocacy
          let base = 75 + Math.min(18, directComments.length * 4);
          if (def.key === primaryDir) base += 5;
          if (directComments.some(c => c.importance === 'Critical' || c.importance === 'High')) {
            base += 4;
          }
          calculated[def.key] = Math.round(Math.min(98, base));
        } else {
          // Check text keyword mentions in comment texts and proposed texts
          let kwMatches = 0;
          orgComments.forEach(c => {
            const comb = `${c.comment_text} ${c.rationale || ''} ${c.proposed_text || ''}`.toLowerCase();
            if (def.keywords.some(k => comb.includes(k))) {
              kwMatches++;
            }
          });

          if (kwMatches > 0) {
            calculated[def.key] = Math.round(Math.min(70, 42 + kwMatches * 9));
          } else {
            // Check for natural regulatory tensions
            const isCostChampion = (calculated['Mitigation of Compliance Costs & Resourcing Burdens'] || 0) > 75;
            const isRegulator = /authority|regulator|oversight|caa/i.test(org.stakeholder_category);

            if (def.key === 'Enhancement of Risk Mitigation & Operational Safety Margins' && isCostChampion) {
              calculated[def.key] = 18; // In tension with heavy cost cuts
            } else if (def.key === 'Timeline Extension & Transitional Phasing' && isRegulator) {
              calculated[def.key] = 20; // Authorities resist deferrals
            } else if (def.key === primaryDir) {
              calculated[def.key] = 85;
            } else {
              calculated[def.key] = 25; // Neutral baseline / low priority
            }
          }
        }
      });

      scoresMap.set(org.organisation_name, calculated);
    });

    return scoresMap;
  }, [organisations, session.comments, activeDirections]);

  // Categories list
  const categories = useMemo(() => {
    const cats = new Set(organisations.map(o => o.stakeholder_category).filter(Boolean));
    return Array.from(cats);
  }, [organisations]);

  // Filtered organisations for sidebar
  const filteredOrganisations = useMemo(() => {
    return organisations.filter(o => {
      const matchesSearch = !searchTerm || o.organisation_name.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCat = categoryFilter === 'all' || o.stakeholder_category === categoryFilter;
      return matchesSearch && matchesCat;
    });
  }, [organisations, searchTerm, categoryFilter]);

  // Selected organisation analysis objects with assigned palette colors
  const selectedOrgData = useMemo(() => {
    return selectedOrgs.map((orgName, index) => {
      const org = organisations.find(o => o.organisation_name === orgName);
      const color = RADAR_PALETTE[index % RADAR_PALETTE.length];
      const scores = org ? computeOrgDirectionScores.get(org.organisation_name) || {} : {};
      return { org, color, scores };
    }).filter((item): item is { org: OrganisationAnalysis; color: typeof RADAR_PALETTE[0]; scores: Record<string, number> } => Boolean(item.org));
  }, [selectedOrgs, organisations, computeOrgDirectionScores]);

  // Inter-Stakeholder Tension Calculations
  const tensionAnalysis = useMemo(() => {
    if (selectedOrgData.length < 2) return null;

    // 1. Calculate spread (max - min) and pairwise variance per direction
    const directionTensions = activeDirections.map(def => {
      const scores = selectedOrgData.map(d => ({
        orgName: d.org.organisation_name,
        color: d.color,
        score: d.scores[def.key] ?? 25
      }));

      scores.sort((a, b) => b.score - a.score);
      const highest = scores[0];
      const lowest = scores[scores.length - 1];
      const spread = highest.score - lowest.score;

      return {
        direction: def,
        spread,
        highest,
        lowest,
        scores
      };
    });

    // Sort by spread descending to find the primary battleground
    directionTensions.sort((a, b) => b.spread - a.spread);

    const primaryTension = directionTensions[0];
    const commonGround = [...directionTensions].sort((a, b) => a.spread - b.spread)[0];

    // Compute overall tension index (average spread across all directions)
    const avgSpread = Math.round(
      directionTensions.reduce((sum, item) => sum + item.spread, 0) / directionTensions.length
    );

    return {
      directionTensions,
      primaryTension,
      commonGround,
      avgSpread
    };
  }, [selectedOrgData, activeDirections]);

  // Toggle stakeholder selection
  const handleToggleOrg = (orgName: string) => {
    if (selectedOrgs.includes(orgName)) {
      if (selectedOrgs.length > 1) {
        setSelectedOrgs(selectedOrgs.filter(name => name !== orgName));
      }
    } else {
      if (selectedOrgs.length >= 8) {
        alert('You can compare up to 8 stakeholders simultaneously on the spider diagram.');
        return;
      }
      setSelectedOrgs([...selectedOrgs, orgName]);
    }
  };

  const handleSelectTop3 = () => {
    const sorted = [...organisations].sort((a, b) => (b.total_comments || 0) - (a.total_comments || 0));
    setSelectedOrgs(sorted.slice(0, 3).map(o => o.organisation_name));
  };

  const handleSelectAllInFiltered = () => {
    const toSelect = filteredOrganisations.slice(0, 6).map(o => o.organisation_name);
    setSelectedOrgs(toSelect);
  };

  // SVG Geometry for Radar Web
  const cx = 270;
  const cy = 250;
  const radius = 175;
  const numAxes = activeDirections.length;
  const levels = [0.2, 0.4, 0.6, 0.8, 1.0];

  // Helper to get coordinates for axis index and percentage value (0-100)
  const getCoordinates = (axisIndex: number, valuePct: number) => {
    const angle = -Math.PI / 2 + (axisIndex * (2 * Math.PI / numAxes));
    const r = radius * (Math.max(5, Math.min(100, valuePct)) / 100);
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle)
    };
  };

  // Clauses with silence data for the Silence Tab
  const clausesWithSilence = useMemo(() => {
    const clauseMap = new Map<string, {
      clause: string;
      objectors: string[];
      defenders: string[];
      silent: string[];
      silenceRate: number;
    }>();

    session.comments.forEach(c => {
      const sec = c.chapter_section || c.target_section || 'General';
      if (!clauseMap.has(sec)) {
        const net = c.support_network;
        clauseMap.set(sec, {
          clause: sec,
          objectors: net?.co_objectors || [],
          defenders: net?.defenders || [],
          silent: net?.silent_organisations || [],
          silenceRate: net?.silence_rate_pct || 0
        });
      } else {
        const existing = clauseMap.get(sec)!;
        if (c.support_network?.co_objectors) {
          c.support_network.co_objectors.forEach(o => {
            if (!existing.objectors.includes(o)) existing.objectors.push(o);
          });
        }
      }
    });

    return Array.from(clauseMap.values()).sort((a, b) => b.silenceRate - a.silenceRate);
  }, [session.comments]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-150">
      <div 
        className="w-full max-w-7xl h-[92vh] bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl flex flex-col overflow-hidden text-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-purple-950 border border-purple-800 flex items-center justify-center text-purple-400 shadow-md shadow-purple-950/50">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white">Stakeholder Direction of Travel Spider Mapping</h2>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-purple-950 text-purple-300 border border-purple-800">
                  Inter-Stakeholder Tensions Engine
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Visualizing stakeholder affinity across all possible directions of travel to expose policy tensions, coalitions, and trade-offs.
              </p>
            </div>
          </div>

          {/* Tab Switcher */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setActiveTab('spider')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'spider'
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Direction Spider Web</span>
            </button>
            <button
              onClick={() => setActiveTab('tensions')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'tensions'
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Flame className="w-3.5 h-3.5 text-amber-400" />
              <span>Tension Matrix</span>
            </button>
            <button
              onClick={() => setActiveTab('silence')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'silence'
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <VolumeX className="w-3.5 h-3.5 text-cyan-400" />
              <span>Silence Matrix</span>
            </button>
            <button
              onClick={() => setActiveTab('profiles')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'profiles'
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>Stance Profiles</span>
            </button>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* TAB 1: DIRECTION OF TRAVEL SPIDER WEB & TENSION MATRIX */}
          {activeTab === 'spider' && (
            <div className="flex-1 flex overflow-hidden">
              
              {/* Left Sidebar: Selectable Stakeholders */}
              <div className="w-80 border-r border-slate-800 bg-slate-950/60 p-4 flex flex-col gap-3 shrink-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-purple-400" />
                    Select Stakeholders ({selectedOrgs.length}/8)
                  </span>
                  <button
                    type="button"
                    onClick={() => setSelectedOrgs([])}
                    className="text-[11px] text-slate-400 hover:text-slate-200"
                  >
                    Clear All
                  </button>
                </div>

                {/* Search */}
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="Filter organisation..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  />
                </div>

                {/* Category Dropdown */}
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-purple-500"
                >
                  <option value="all">All Stakeholder Categories</option>
                  {categories.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>

                {/* Quick Presets */}
                <div className="flex items-center justify-between text-xs text-slate-400 pb-1 border-b border-slate-800/80">
                  <span>Presets:</span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={handleSelectTop3}
                      className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[10px] font-semibold transition-colors"
                    >
                      Top 3 Active
                    </button>
                    <button
                      type="button"
                      onClick={handleSelectAllInFiltered}
                      className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[10px] font-semibold transition-colors"
                    >
                      Select Top 6
                    </button>
                  </div>
                </div>

                {/* Stakeholder List */}
                <div className="flex-1 overflow-y-auto space-y-1.5 pr-1 scrollbar-thin">
                  {filteredOrganisations.map((org) => {
                    const isSelected = selectedOrgs.includes(org.organisation_name);
                    const colorIndex = selectedOrgs.indexOf(org.organisation_name);
                    const paletteItem = colorIndex >= 0 ? RADAR_PALETTE[colorIndex % RADAR_PALETTE.length] : null;
                    const primaryDir = org.primary_direction_of_travel || org.direction_of_travel;

                    return (
                      <div
                        key={org.organisation_name}
                        onClick={() => handleToggleOrg(org.organisation_name)}
                        className={`p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between gap-2 text-left ${
                          isSelected
                            ? 'bg-slate-900/90 border-slate-700 shadow-xs'
                            : 'bg-slate-950/40 border-slate-900 hover:border-slate-800 opacity-70 hover:opacity-100'
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {paletteItem ? (
                            <span 
                              className="w-3.5 h-3.5 rounded-full shrink-0 shadow-sm ring-2 ring-slate-800"
                              style={{ backgroundColor: paletteItem.stroke }}
                            />
                          ) : (
                            <span className="w-3.5 h-3.5 rounded-full border border-slate-700 shrink-0" />
                          )}

                          <div className="min-w-0">
                            <span className="text-xs font-semibold text-white block truncate">
                              {org.organisation_name}
                            </span>
                            <span className="text-[10px] text-purple-300 block truncate font-medium">
                              {primaryDir}
                            </span>
                            <span className="text-[10px] text-slate-400 block truncate">
                              {org.stakeholder_category} • {org.total_comments} comments
                            </span>
                          </div>
                        </div>

                        <span className="px-1.5 py-0.5 rounded font-mono text-[10px] font-bold shrink-0 bg-slate-800 text-slate-300">
                          {org.total_comments}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Center / Right: Interactive Spider Diagram & Tension Cards */}
              <div className="flex-1 flex flex-col bg-slate-950 p-6 overflow-y-auto space-y-5">
                
                {/* Active Legends Bar */}
                <div className="flex items-center justify-between gap-2 flex-wrap pb-3 border-b border-slate-800/80 shrink-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-slate-400">Comparing Stakeholders:</span>
                    {selectedOrgData.map(({ org, color }) => (
                      <span
                        key={org.organisation_name}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border shadow-xs"
                        style={{
                          backgroundColor: `${color.stroke}15`,
                          borderColor: `${color.stroke}50`,
                          color: color.stroke
                        }}
                      >
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color.stroke }} />
                        <span>{org.organisation_name}</span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleOrg(org.organisation_name);
                          }}
                          className="hover:opacity-100 opacity-60 ml-0.5"
                          title="Remove from spider diagram"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>

                  <span className="text-[11px] text-slate-400 font-mono flex items-center gap-1">
                    <Compass className="w-3.5 h-3.5 text-purple-400" />
                    Axes = Possible Directions of Travel (0-100% Affinity)
                  </span>
                </div>

                {/* SVG Spider Chart Container */}
                <div className="flex items-center justify-center relative min-h-[460px] bg-slate-900/30 rounded-2xl border border-slate-800/60 p-4">
                  <svg 
                    viewBox="0 0 540 500" 
                    className="w-full max-w-[560px] h-auto select-none overflow-visible"
                  >
                    {/* Concentric Web Rings (20%, 40%, 60%, 80%, 100%) */}
                    {levels.map((level, lvlIdx) => {
                      const ringPoints = activeDirections.map((_, i) => {
                        const { x, y } = getCoordinates(i, level * 100);
                        return `${x},${y}`;
                      }).join(' ');

                      return (
                        <g key={lvlIdx}>
                          <polygon
                            points={ringPoints}
                            fill={lvlIdx === levels.length - 1 ? 'rgba(30, 41, 59, 0.18)' : 'none'}
                            stroke="rgba(148, 163, 184, 0.18)"
                            strokeWidth="1"
                            strokeDasharray={lvlIdx < levels.length - 1 ? '3 3' : undefined}
                          />
                          {/* Percentage label on the vertical top axis */}
                          <text
                            x={cx + 4}
                            y={cy - radius * level - 2}
                            fill="rgba(148, 163, 184, 0.45)"
                            fontSize="9"
                            fontFamily="monospace"
                          >
                            {Math.round(level * 100)}%
                          </text>
                        </g>
                      );
                    })}

                    {/* Spoke Lines from Center to Each Direction Vertex */}
                    {activeDirections.map((def, i) => {
                      const { x, y } = getCoordinates(i, 100);
                      const angle = -Math.PI / 2 + (i * (2 * Math.PI / numAxes));
                      
                      // Label coordinates slightly outside the 100% boundary
                      const labelDistance = radius + 28;
                      const lx = cx + labelDistance * Math.cos(angle);
                      const ly = cy + labelDistance * Math.sin(angle);
                      
                      // Alignment based on angle position
                      let textAnchor = 'middle';
                      if (Math.cos(angle) > 0.2) textAnchor = 'start';
                      else if (Math.cos(angle) < -0.2) textAnchor = 'end';

                      return (
                        <g key={def.key}>
                          <line
                            x1={cx}
                            y1={cy}
                            x2={x}
                            y2={y}
                            stroke="rgba(148, 163, 184, 0.28)"
                            strokeWidth="1.2"
                          />
                          {/* Direction Title on spoke */}
                          <text
                            x={lx}
                            y={ly}
                            textAnchor={textAnchor}
                            fill="#e2e8f0"
                            fontSize="11"
                            fontWeight="600"
                            className="cursor-default"
                          >
                            {def.shortLabel}
                          </text>
                        </g>
                      );
                    })}

                    {/* Stakeholder Polygons & Points */}
                    {selectedOrgData.map(({ org, color, scores }) => {
                      const polyPoints = activeDirections.map((def, i) => {
                        const val = scores[def.key] ?? 25;
                        const { x, y } = getCoordinates(i, val);
                        return `${x},${y}`;
                      }).join(' ');

                      return (
                        <g key={org.organisation_name} className="transition-all duration-300">
                          {/* Polygons */}
                          <polygon
                            points={polyPoints}
                            fill={color.fill}
                            stroke={color.stroke}
                            strokeWidth="2.5"
                            className="transition-all duration-300"
                          />

                          {/* Dots at vertices */}
                          {activeDirections.map((def, i) => {
                            const val = scores[def.key] ?? 25;
                            const { x, y } = getCoordinates(i, val);
                            const orgComments = session.comments.filter(
                              c => (c.organisation_name || c.stakeholder_name) === org.organisation_name &&
                                   (c.direction_of_travel || '').toLowerCase() === def.key.toLowerCase()
                            );

                            return (
                              <circle
                                key={def.key}
                                cx={x}
                                cy={y}
                                r="4.5"
                                fill={color.stroke}
                                stroke="#0f172a"
                                strokeWidth="1.5"
                                className="cursor-pointer hover:r-6 transition-all"
                                onMouseEnter={() => {
                                  setHoveredPoint({
                                    orgName: org.organisation_name,
                                    directionKey: def.key,
                                    directionLabel: def.fullTitle,
                                    description: def.description,
                                    score: val,
                                    status: val >= 75 ? 'Primary Champion' : val >= 50 ? 'Constructive Alignment' : 'Low Priority / Tension',
                                    directCount: orgComments.length,
                                    x,
                                    y
                                  });
                                }}
                                onMouseLeave={() => setHoveredPoint(null)}
                              />
                            );
                          })}
                        </g>
                      );
                    })}
                  </svg>

                  {/* Tooltip Overlay */}
                  {hoveredPoint && (
                    <div 
                      className="absolute z-20 pointer-events-none bg-slate-900 border border-slate-700 rounded-xl p-3 shadow-2xl text-xs max-w-xs space-y-1.5 animate-in fade-in zoom-in-95 duration-100"
                      style={{
                        left: `${hoveredPoint.x + 12}px`,
                        top: `${hoveredPoint.y - 50}px`
                      }}
                    >
                      <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-1">
                        <span className="font-bold text-white truncate">{hoveredPoint.orgName}</span>
                        <span className={`px-1.5 py-0.2 rounded font-mono text-[10px] font-bold ${
                          hoveredPoint.score >= 75
                            ? 'bg-purple-950 text-purple-300 border border-purple-800'
                            : hoveredPoint.score >= 50
                            ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                            : 'bg-slate-800 text-slate-400'
                        }`}>
                          {hoveredPoint.score}%
                        </span>
                      </div>
                      <div>
                        <span className="text-[11px] font-semibold text-purple-300 block">{hoveredPoint.directionLabel}</span>
                        <p className="text-[10px] text-slate-400 leading-snug mt-0.5">{hoveredPoint.description}</p>
                      </div>
                      <div className="flex items-center justify-between pt-1 border-t border-slate-800 text-[10px] text-slate-400">
                        <span>Affinity: <strong className="text-white">{hoveredPoint.status}</strong></span>
                        <span>{hoveredPoint.directCount} direct comment(s)</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Inter-Stakeholder Tension & Coalitions Summary Banner */}
                {tensionAnalysis && (
                  <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-2xl space-y-4">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-amber-950 border border-amber-800 flex items-center justify-center text-amber-400">
                          <Flame className="w-4 h-4" />
                        </div>
                        <div>
                          <h3 className="text-xs font-bold text-white">Inter-Stakeholder Tension & Trade-Off Diagnostics</h3>
                          <p className="text-[11px] text-slate-400">
                            Quantifying polarization across the {selectedOrgData.length} selected stakeholders to identify battlegrounds and consensus areas.
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-400">Inter-Stakeholder Divergence Index:</span>
                        <span className={`px-2.5 py-1 rounded-xl text-xs font-mono font-bold border ${
                          tensionAnalysis.avgSpread >= 50
                            ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                            : tensionAnalysis.avgSpread >= 30
                            ? 'bg-amber-950/80 text-amber-300 border-amber-800'
                            : 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
                        }`}>
                          {tensionAnalysis.avgSpread}% Divergence
                        </span>
                      </div>
                    </div>

                    {/* Peak Battleground and Shared Ground Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                      {/* Critical Tension Point */}
                      <div className="p-3 bg-rose-950/30 border border-rose-900/60 rounded-xl space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-rose-300 flex items-center gap-1.5">
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                            Primary Tension Battleground: {tensionAnalysis.primaryTension.direction.shortLabel}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-900/60 text-rose-200">
                            {tensionAnalysis.primaryTension.spread}% Spread
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-300 leading-snug">
                          <strong>{tensionAnalysis.primaryTension.highest.orgName}</strong> champions this direction ({tensionAnalysis.primaryTension.highest.score}%), whereas <strong>{tensionAnalysis.primaryTension.lowest.orgName}</strong> strongly opposes or deprioritizes it ({tensionAnalysis.primaryTension.lowest.score}%).
                        </p>
                        <p className="text-[10px] text-slate-400 italic">
                          Policy implication: Direct clash between {tensionAnalysis.primaryTension.direction.typicalChampions} and {tensionAnalysis.primaryTension.direction.naturalOpponents}.
                        </p>
                      </div>

                      {/* Shared Ground */}
                      <div className="p-3 bg-emerald-950/30 border border-emerald-900/60 rounded-xl space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-emerald-300 flex items-center gap-1.5">
                            <Handshake className="w-3.5 h-3.5 text-emerald-400" />
                            Common Ground / Coalition: {tensionAnalysis.commonGround.direction.shortLabel}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-900/60 text-emerald-200">
                            {tensionAnalysis.commonGround.spread}% Spread
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-300 leading-snug">
                          Low divergence detected across all selected parties (scores ranging from {tensionAnalysis.commonGround.lowest.score}% to {tensionAnalysis.commonGround.highest.score}%).
                        </p>
                        <p className="text-[10px] text-slate-400 italic">
                          Consensus pathway: Opportunity for regulatory drafters to anchor revisions around this mutually acceptable vector.
                        </p>
                      </div>
                    </div>

                    {/* Detailed Scoring Matrix Table */}
                    <div className="overflow-x-auto pt-2">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-slate-800 text-[11px] text-slate-400">
                            <th className="py-2 px-3">Direction of Travel Axis</th>
                            {selectedOrgData.map(({ org, color }) => (
                              <th key={org.organisation_name} className="py-2 px-3" style={{ color: color.stroke }}>
                                {org.organisation_name}
                              </th>
                            ))}
                            <th className="py-2 px-3 text-right">Tension Spread</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                          {tensionAnalysis.directionTensions.map(({ direction, spread, scores }) => (
                            <tr key={direction.key} className="hover:bg-slate-800/30 transition-colors">
                              <td className="py-2 px-3 font-sans font-medium text-slate-200">
                                <span>{direction.fullTitle}</span>
                              </td>
                              {selectedOrgData.map(({ org }) => {
                                const score = scores.find(s => s.orgName === org.organisation_name)?.score ?? 25;
                                return (
                                  <td key={org.organisation_name} className="py-2 px-3">
                                    <div className="flex items-center gap-2">
                                      <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                        <div 
                                          className="h-full bg-purple-500 rounded-full"
                                          style={{ width: `${score}%` }}
                                        />
                                      </div>
                                      <span className={score >= 70 ? 'text-purple-300 font-bold' : 'text-slate-400'}>
                                        {score}%
                                      </span>
                                    </div>
                                  </td>
                                );
                              })}
                              <td className="py-2 px-3 text-right">
                                <span className={`px-2 py-0.5 rounded font-bold ${
                                  spread >= 50
                                    ? 'bg-rose-950 text-rose-300 border border-rose-900'
                                    : spread >= 25
                                    ? 'bg-amber-950 text-amber-300 border border-amber-900'
                                    : 'bg-emerald-950 text-emerald-300 border border-emerald-900'
                                }`}>
                                  {spread}%
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

              </div>
            </div>
          )}

          {/* TAB 2: DETAILED PAIRWISE TENSION BREAKDOWN */}
          {activeTab === 'tensions' && (
            <div className="flex-1 flex flex-col p-6 overflow-y-auto space-y-6">
              <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800 flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Flame className="w-4 h-4 text-amber-400" />
                    <span>Regulatory Battleground & Policy Tensions Analysis</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Systematic analysis of policy friction between participating organisations. Where stakeholders pull in opposing directions, deliberate regulatory trade-offs must be made.
                  </p>
                </div>
                <span className="px-3 py-1.5 rounded-xl bg-purple-950 border border-purple-800 text-xs font-mono text-purple-300">
                  {selectedOrgData.length} Stakeholders Under Tension Review
                </span>
              </div>

              {selectedOrgData.length < 2 ? (
                <div className="p-12 text-center text-slate-500 bg-slate-950/40 rounded-2xl border border-slate-800">
                  <Flame className="w-10 h-10 mx-auto mb-2 opacity-30 text-amber-400" />
                  <p className="text-sm font-semibold">Select at least 2 stakeholders in the Direction Spider Web tab to analyze tensions.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {activeDirections.map(def => {
                    const sortedOrgs = [...selectedOrgData].sort((a, b) => {
                      const scoreA = a.scores[def.key] ?? 25;
                      const scoreB = b.scores[def.key] ?? 25;
                      return scoreB - scoreA;
                    });

                    const highest = sortedOrgs[0];
                    const lowest = sortedOrgs[sortedOrgs.length - 1];
                    const spread = (highest.scores[def.key] ?? 25) - (lowest.scores[def.key] ?? 25);

                    return (
                      <div key={def.key} className="p-4 bg-slate-950/80 border border-slate-800 rounded-2xl space-y-3">
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div>
                            <span className="text-xs font-bold text-white flex items-center gap-2">
                              <span>{def.fullTitle}</span>
                              <span className="text-[10px] font-normal text-slate-400">({def.policyTheme})</span>
                            </span>
                            <p className="text-[11px] text-slate-400 mt-0.5">{def.description}</p>
                          </div>

                          <span className={`px-2.5 py-1 rounded-xl text-xs font-mono font-bold border ${
                            spread >= 50
                              ? 'bg-rose-950 text-rose-300 border-rose-800'
                              : spread >= 25
                              ? 'bg-amber-950 text-amber-300 border-amber-800'
                              : 'bg-emerald-950 text-emerald-300 border-emerald-800'
                          }`}>
                            Tension Spread: {spread}%
                          </span>
                        </div>

                        {/* Visual Range Bar */}
                        <div className="p-3 bg-slate-900 rounded-xl space-y-2">
                          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
                            <span className="text-emerald-400 flex items-center gap-1">
                              <strong>Primary Advocate:</strong> {highest.org.organisation_name} ({highest.scores[def.key] ?? 25}%)
                            </span>
                            <span className="text-rose-400 flex items-center gap-1">
                              <strong>Opposing / Indifferent:</strong> {lowest.org.organisation_name} ({lowest.scores[def.key] ?? 25}%)
                            </span>
                          </div>

                          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden flex items-center relative">
                            {selectedOrgData.map(({ org, color, scores }) => {
                              const s = scores[def.key] ?? 25;
                              return (
                                <div
                                  key={org.organisation_name}
                                  className="absolute w-3 h-3 rounded-full border-2 border-white shadow-md cursor-pointer -ml-1.5"
                                  style={{ left: `${s}%`, backgroundColor: color.stroke }}
                                  title={`${org.organisation_name}: ${s}%`}
                                />
                              );
                            })}
                          </div>
                        </div>

                        {/* Trade-off Guidance for Drafters */}
                        <div className="flex items-start gap-2 text-xs bg-slate-900/60 p-2.5 rounded-lg border border-slate-800 text-slate-400">
                          <Scale className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
                          <div className="leading-snug">
                            <strong className="text-slate-300">Regulatory Deliberation Trade-Off: </strong>
                            {spread >= 50 ? (
                              <span>High risk of legal challenge or non-compliance. Accommodating <em>{highest.org.organisation_name}</em> by granting this concession directly challenges the regulatory objectives held by <em>{lowest.org.organisation_name}</em>. Consider phased AMC guidance rather than hard rule amendments.</span>
                            ) : (
                              <span>Manageable consensus zone. Parties show workable proximity; amendments to GM or standardized clauses can bridge the {spread}% gap.</span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: SILENCE & TACIT ACQUIESCENCE MATRIX */}
          {activeTab === 'silence' && (
            <div className="flex-1 flex flex-col p-6 overflow-y-auto space-y-4">
              <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800 flex items-start gap-3 shrink-0">
                <div className="w-8 h-8 rounded-lg bg-cyan-950 border border-cyan-800 flex items-center justify-center text-cyan-400 shrink-0">
                  <VolumeX className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Tacit Acquiescence & Silence Accounting</h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    In aviation regulatory deliberation, an objection from an individual submitter or airline is weighed against the collective silence of unaffected or compliant sectors. Where an organisation does not file an objection against a clause, European regulatory governance accounts for that absence of comment as <strong>tacit non-opposition or acquiescence</strong>.
                  </p>
                </div>
              </div>

              {/* Silence Matrix Table */}
              <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden flex flex-col">
                <div className="p-3 border-b border-slate-800 flex items-center justify-between text-xs font-semibold text-slate-400 bg-slate-900/50">
                  <span>Provisions Silence & Coalitions Matrix</span>
                  <span>Showing {clausesWithSilence.length} regulatory provisions</span>
                </div>

                <div className="overflow-y-auto max-h-[58vh]">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-900/80 sticky top-0 z-10 border-b border-slate-800 text-[11px] text-slate-400">
                      <tr>
                        <th className="p-3">Clause / Target Provision</th>
                        <th className="p-3">Objecting Organisations</th>
                        <th className="p-3">Defenders</th>
                        <th className="p-3">Silent Parties (Tacit Acquiescence)</th>
                        <th className="p-3 text-right">Silence Rate</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {clausesWithSilence.map((row) => (
                        <tr key={row.clause} className="hover:bg-slate-800/30 transition-colors">
                          <td className="p-3 font-mono font-semibold text-white whitespace-nowrap">
                            {row.clause}
                          </td>
                          <td className="p-3">
                            <div className="flex flex-wrap gap-1 max-w-xs">
                              {row.objectors.length > 0 ? (
                                row.objectors.map(o => (
                                  <span key={o} className="px-1.5 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-900">
                                    {o}
                                  </span>
                                ))
                              ) : (
                                <span className="text-slate-500 italic">None</span>
                              )}
                            </div>
                          </td>
                          <td className="p-3">
                            <div className="flex flex-wrap gap-1 max-w-xs">
                              {row.defenders.length > 0 ? (
                                row.defenders.map(d => (
                                  <span key={d} className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-900">
                                    {d}
                                  </span>
                                ))
                              ) : (
                                <span className="text-slate-500 italic">None</span>
                              )}
                            </div>
                          </td>
                          <td className="p-3 text-slate-400">
                            <div className="flex flex-wrap gap-1 max-w-sm">
                              {row.silent.slice(0, 3).map(s => (
                                <span key={s} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-900 text-slate-400 border border-slate-800">
                                  {s}
                                </span>
                              ))}
                              {row.silent.length > 3 && (
                                <span className="text-[10px] text-slate-500 self-center">
                                  +{row.silent.length - 3} others
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="p-3 text-right">
                            <span className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                              row.silenceRate >= 75
                                ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
                                : 'bg-slate-800 text-slate-300'
                            }`}>
                              {row.silenceRate}% silent
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: DETAILED PROFILES */}
          {activeTab === 'profiles' && (
            <div className="flex-1 p-6 overflow-y-auto space-y-4">
              <h3 className="text-xs font-bold text-white uppercase tracking-wider text-slate-400">
                Selected Stakeholder Strategy & Trajectory Profiles ({selectedOrgData.length})
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {selectedOrgData.map(({ org, color }) => (
                  <div 
                    key={org.organisation_name}
                    className="p-4 bg-slate-950 rounded-2xl border border-slate-800 space-y-3"
                  >
                    <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color.stroke }} />
                        <span className="font-bold text-white text-sm">{org.organisation_name}</span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-950 text-purple-300 border border-purple-800">
                        {org.stakeholder_category}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed">
                      {org.stance_summary}
                    </p>

                    <div className="space-y-1.5 pt-2 border-t border-slate-800/60 text-xs">
                      <div className="flex items-center justify-between text-slate-400">
                        <span>Primary Direction of Travel:</span>
                        <strong className="text-purple-300 font-semibold">{org.primary_direction_of_travel || org.direction_of_travel}</strong>
                      </div>
                      <div className="flex items-center justify-between text-slate-400">
                        <span>Total Feedback Volume:</span>
                        <span className="font-mono text-white">{org.total_comments} comments</span>
                      </div>
                      <div className="flex items-center justify-between text-slate-400">
                        <span>Targeted Clauses:</span>
                        <span className="font-mono text-white">{org.targeted_sections?.length || 0} clauses</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/90 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Direction of Travel Spider Mapping · Mapping Multi-Vector Alignment, Oppositions & Inter-Stakeholder Tensions</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
};

export default StakeholderSpiderModal;
