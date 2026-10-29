import React, { useState, useEffect } from 'react';
import {
  FolderKanban,
  Plus,
  Shield,
  MapPin,
  ChevronRight,
  X,
  Play,
  WifiOff,
} from 'lucide-react';
import { Vela } from '../components/Vela';
import { ConsensusHeatmap } from '../components/ConsensusHeatmap';
import { setCasePurpose, getCasePurpose } from '../api/purpose';
import { apiClient } from '../api/client';

export interface CaseItem {
  id: string;
  case_number: string;
  title: string;
  station: string;
  status: 'active' | 'closed' | 'archived';
  data_mode: 'demo' | 'real';
  default_appearance_group: string;
  updated_at: string;
}

const DEV_FIXTURE_CASES: CaseItem[] = [
  {
    id: 'case-demo-001',
    case_number: '[DEV FIXTURE] DEMO-001',
    title: 'Commercial District Armed Robbery',
    station: 'Central Division Precinct 4',
    status: 'active',
    data_mode: 'demo',
    default_appearance_group: 'unspecified',
    updated_at: '2026-10-28T19:30:00.000Z',
  },
  {
    id: 'case-local-002',
    case_number: '[DEV FIXTURE] LOCAL-SIM-001',
    title: 'Station Metro Station Witness Intake',
    station: 'South Precinct Cyber Cell',
    status: 'active',
    data_mode: 'real',
    default_appearance_group: 'unspecified',
    updated_at: '2026-10-28T20:15:00.000Z',
  },
];

interface CommandCenterPageProps {
  onOpenStudioSession: (sessionId: string, caseItem: CaseItem, initialMode?: 'composite' | 'scene') => void;
  onSetGlobalDataMode: (mode: 'demo' | 'real' | 'alert') => void;
}

export const CommandCenterPage: React.FC<CommandCenterPageProps> = ({
  onOpenStudioSession,
  onSetGlobalDataMode,
}) => {
  // Cases state (persisted or populated from active investigations)
  const [cases, setCases] = useState<CaseItem[]>(DEV_FIXTURE_CASES);
  const [isBackendOffline, setIsBackendOffline] = useState(false);

  useEffect(() => {
    let active = true;
    const fetchLiveCases = async () => {
      try {
        const liveCases = await apiClient.get<CaseItem[]>('/cases');
        if (active && Array.isArray(liveCases) && liveCases.length > 0) {
          setCases(liveCases);
          setIsBackendOffline(false);
        }
      } catch {
        if (active) {
          setIsBackendOffline(true);
        }
      }
    };
    fetchLiveCases();
    return () => {
      active = false;
    };
  }, []);

  const [selectedCase, setSelectedCase] = useState<CaseItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<'witnesses' | 'sessions' | 'consensus' | 'access'>('sessions');

  // Purpose modal state
  const [showPurposeSheet, setShowPurposeSheet] = useState(false);
  const [pendingCase, setPendingCase] = useState<CaseItem | null>(null);
  const [purposeText, setPurposeText] = useState('Witness interview');

  // New Case sheet state
  const [showNewCaseSheet, setShowNewCaseSheet] = useState(false);
  const [newCaseNumber, setNewCaseNumber] = useState('');
  const [newCaseTitle, setNewCaseTitle] = useState('');
  const [newCaseMode, setNewCaseMode] = useState<'demo' | 'real'>('demo');
  const [newCaseAppearance, setNewCaseAppearance] = useState('unspecified');

  const handleOpenCase = (c: CaseItem) => {
    // Check if purpose is already stored in memory
    const existingPurpose = getCasePurpose(c.id);
    if (!existingPurpose) {
      setPendingCase(c);
      setShowPurposeSheet(true);
    } else {
      activateCase(c);
    }
  };

  const activateCase = (c: CaseItem) => {
    setSelectedCase(c);
    setDrawerOpen(true);
    onSetGlobalDataMode(c.data_mode);
  };

  const handleConfirmPurpose = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingCase || purposeText.trim().length < 5) return;
    setCasePurpose(pendingCase.id, purposeText.trim());
    setShowPurposeSheet(false);
    activateCase(pendingCase);
    setPendingCase(null);
  };

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCaseNumber.trim() || !newCaseTitle.trim()) return;

    try {
      const created = await apiClient.post<CaseItem>('/cases', {
        case_number: newCaseNumber.trim(),
        title: newCaseTitle.trim(),
        data_mode: newCaseMode,
        default_appearance_group: newCaseAppearance,
      });

      setCases((prev) => [created, ...prev]);
      setShowNewCaseSheet(false);
      setNewCaseNumber('');
      setNewCaseTitle('');
      activateCase(created);
    } catch {
      // Backend offline fallback - explicitly labeled as dev fixture
      const localFixture: CaseItem = {
        id: `case-${Date.now()}`,
        case_number: `[DEV FIXTURE] ${newCaseNumber.trim()}`,
        title: newCaseTitle.trim(),
        station: 'Central Investigation Hub (Local Offline)',
        status: 'active',
        data_mode: newCaseMode,
        default_appearance_group: newCaseAppearance,
        updated_at: new Date().toISOString(),
      };

      setCases((prev) => [localFixture, ...prev]);
      setShowNewCaseSheet(false);
      setNewCaseNumber('');
      setNewCaseTitle('');
      activateCase(localFixture);
    }
  };

  return (
    <div className="max-w-[1240px] mx-auto px-6 py-8 relative">
      {/* Honest Backend Service Offline Notice */}
      {isBackendOffline && (
        <div className="mb-6 p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <WifiOff className="w-4 h-4 text-amber-400 shrink-0" />
            <div>
              <span className="font-semibold text-amber-300">Backend Case Registry Offline (:8000)</span>
              <p className="text-[11px] text-amber-200/80 mt-0.5">
                The centralized case store is unreachable. Showing clearly labeled <code className="px-1 py-0.5 rounded bg-black/40 font-mono text-[10px]">[DEV FIXTURE]</code> demonstration cases.
              </p>
            </div>
          </div>
          <span className="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-300 font-mono text-[10px] shrink-0">
            OFFLINE FIXTURE MODE
          </span>
        </div>
      )}

      {/* 1. Greeting Row with Vela Companion */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-8 border-b border-[rgba(255,255,255,0.08)]">
        <div className="flex items-center gap-4">
          <Vela size="companion" state="idle" />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-white">
                Command Center
              </h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-[#7c8cff]/15 text-[#7c8cff] border border-[#7c8cff]/30">
                OFFICER ACTIVE
              </span>
            </div>
            <p className="text-sm text-[#95979E] mt-0.5">
              Active case docket and witness intake operations
            </p>
          </div>
        </div>

        {/* Action button */}
        <button
          onClick={() => {
            setShowNewCaseSheet(true);
            setNewCaseNumber(`CASE-${Math.floor(1000 + Math.random() * 9000)}`);
          }}
          className="btn-primary-glow inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-xs sm:text-sm font-semibold self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Investigation Case</span>
        </button>
      </div>

      {/* 2. Cases Grid */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold tracking-wider text-[#A9A9AA] uppercase">
            Registered Cases ({cases.length})
          </h2>
          <span className="text-xs text-[#95979E]">Click case card to open operations drawer</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {cases.map((c) => {
            const isLocal = c.data_mode === 'real';
            return (
              <div
                key={c.id}
                onClick={() => handleOpenCase(c)}
                className="group cursor-pointer rounded-2xl glass-panel p-6 hover:border-[rgba(255,255,255,0.22)] transition-all hover:-translate-y-1 relative overflow-hidden"
              >
                {/* Mode top accent bar */}
                <div
                  className={`absolute top-0 inset-x-0 h-1 ${
                    isLocal ? 'bg-[#2fd4a4]' : 'bg-[#7c8cff]'
                  }`}
                />

                <div className="flex items-center justify-between mb-3">
                  <span className="font-mono text-xs font-semibold text-white">
                    {c.case_number}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium ${
                      isLocal
                        ? 'bg-[#2fd4a4]/20 text-[#2fd4a4] border border-[#2fd4a4]/40'
                        : 'bg-[#7c8cff]/20 text-[#7c8cff] border border-[#7c8cff]/40'
                    }`}
                  >
                    <Shield className="w-2.5 h-2.5" />
                    <span>{isLocal ? 'Local-only' : 'Demo (Cloud)'}</span>
                  </span>
                </div>

                <h3 className="text-base font-semibold text-white group-hover:text-[#5ad1ff] transition-colors leading-snug">
                  {c.title}
                </h3>

                <div className="mt-4 pt-3 border-t border-[rgba(255,255,255,0.06)] flex items-center justify-between text-xs text-[#95979E]">
                  <span className="flex items-center gap-1.5 truncate max-w-[180px]">
                    <MapPin className="w-3.5 h-3.5 shrink-0 text-[#A9A9AA]" />
                    <span className="truncate">{c.station}</span>
                  </span>
                  <ChevronRight className="w-4 h-4 text-[#A9A9AA] group-hover:translate-x-1 transition-transform" />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Case Operations Drawer (Right-side 520px per §6.4) */}
      {drawerOpen && selectedCase && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />

          {/* Drawer content */}
          <aside
            aria-label="Case details drawer"
            className="relative w-full max-w-[520px] bg-[#0e0f12] border-l border-[rgba(255,255,255,0.12)] h-full p-6 flex flex-col justify-between shadow-2xl z-10 overflow-y-auto"
          >
            <div>
              {/* Drawer Header */}
              <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)]">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-[#5ad1ff]">
                      {selectedCase.case_number}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[9px] font-mono ${
                        selectedCase.data_mode === 'real'
                          ? 'bg-[#2fd4a4]/20 text-[#2fd4a4]'
                          : 'bg-[#7c8cff]/20 text-[#7c8cff]'
                      }`}
                    >
                      {selectedCase.data_mode === 'real' ? 'LOCAL' : 'DEMO'}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-white mt-1">
                    {selectedCase.title}
                  </h3>
                </div>
                <button
                  onClick={() => setDrawerOpen(false)}
                  className="p-2 rounded-lg text-[#A9A9AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)]"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Drawer Tabs */}
              <div className="flex items-center gap-2 border-b border-[rgba(255,255,255,0.08)] py-3 text-xs">
                {(['sessions', 'witnesses', 'consensus', 'access'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setDrawerTab(tab)}
                    className={`capitalize px-3 py-1.5 rounded-lg font-medium transition-all ${
                      drawerTab === tab
                        ? 'bg-[rgba(255,255,255,0.12)] text-white'
                        : 'text-[#A9A9AA] hover:text-white'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Tab Contents */}
              <div className="py-6">
                {drawerTab === 'sessions' && (
                  <div className="space-y-4">
                    <div className="p-4 rounded-xl glass-panel space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-semibold text-white">
                          SESSION // SES-2026-0814
                        </span>
                        <span className="text-[10px] text-emerald-400 font-mono">READY</span>
                      </div>
                      <p className="text-xs text-[#95979E]">
                        Primary witness interview and facial composite generation session.
                      </p>
                      <button
                        onClick={() => {
                          setDrawerOpen(false);
                          onOpenStudioSession('ses-2026-0814', selectedCase);
                        }}
                        className="btn-primary-glow w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-semibold"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Launch Studio Session</span>
                      </button>
                    </div>

                    <div className="p-4 rounded-xl glass-panel space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-semibold text-white">
                          SCENE // SCN-2026-0814
                        </span>
                        <span className="text-[10px] text-[#5ad1ff] font-mono">READY</span>
                      </div>
                      <p className="text-xs text-[#95979E]">
                        Crime scene spatial layout and suspect approach/egress diagram.
                      </p>
                      <button
                        onClick={() => {
                          setDrawerOpen(false);
                          onOpenStudioSession('ses-2026-0814', selectedCase, 'scene');
                        }}
                        className="w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-semibold bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-white hover:bg-white/5 transition-colors"
                      >
                        <Play className="w-3.5 h-3.5 fill-current text-[#5ad1ff]" />
                        <span>Launch Scene Diagram</span>
                      </button>
                    </div>
                  </div>
                )}

                {drawerTab === 'witnesses' && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] flex items-center justify-between text-xs">
                      <div>
                        <span className="font-medium text-white">Witness 01 (Store Clerk)</span>
                        <div className="flex items-center gap-2 text-[10px] text-[#95979E] mt-0.5">
                          <span>Alias: W-001</span>
                          <span>•</span>
                          <span>Language: தமிழ் (Tamil)</span>
                        </div>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] bg-[#5ad1ff]/15 text-[#5ad1ff]">
                        Assigned
                      </span>
                    </div>

                    <div className="p-3 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] flex items-center justify-between text-xs">
                      <div>
                        <span className="font-medium text-white">Witness 02 (Pedestrian)</span>
                        <div className="flex items-center gap-2 text-[10px] text-[#95979E] mt-0.5">
                          <span>Alias: W-002</span>
                          <span>•</span>
                          <span>Language: English</span>
                        </div>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] bg-[rgba(255,255,255,0.06)] text-[#A9A9AA]">
                        Pending
                      </span>
                    </div>
                  </div>
                )}

                {drawerTab === 'consensus' && (
                  <div className="space-y-4">
                    <ConsensusHeatmap />
                  </div>
                )}

                {drawerTab === 'access' && (
                  <div className="space-y-3 text-xs">
                    <div className="p-3 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)]">
                      <span className="font-medium text-white">Lead Investigator</span>
                      <p className="text-[11px] text-[#A9A9AA] mt-0.5">ID: #7802 (Full Edit & Export)</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="pt-4 border-t border-[rgba(255,255,255,0.08)] text-[11px] text-[#95979E] flex items-center justify-between">
              <span>Custody Ledger: Hash #8f2a...c04e</span>
              <span className="text-emerald-400 font-mono">VERIFIED</span>
            </div>
          </aside>
        </div>
      )}

      {/* 4. Purpose-of-Access Sheet (Face-ID style modal per §6.3) */}
      {showPurposeSheet && pendingCase && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-md" />
          <div className="relative w-full max-w-md rounded-2xl glass-panel-strong p-6 shadow-2xl z-10 text-left">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-[#7c8cff]/15 border border-[#7c8cff]/30 flex items-center justify-center text-[#7c8cff]">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">
                  Purpose of Access Declaration
                </h3>
                <span className="font-mono text-xs text-[#A9A9AA]">
                  {pendingCase.case_number}
                </span>
              </div>
            </div>

            <p className="text-xs text-[#95979E] mb-4 leading-relaxed">
              Section 6.3 mandate: Every case-scoped request writes a tamper-evident audit record.
              Please declare your purpose of access (minimum 5 characters).
            </p>

            {/* Quick chips */}
            <div className="flex flex-wrap gap-2 mb-4">
              {['Witness interview', 'Case review', 'Forensic supervision', 'Composite generation'].map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => setPurposeText(chip)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                    purposeText === chip
                      ? 'bg-[#7c8cff] text-[#090a0c]'
                      : 'bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[#A9A9AA] hover:text-white'
                  }`}
                >
                  {chip}
                </button>
              ))}
            </div>

            <form onSubmit={handleConfirmPurpose} className="space-y-4">
              <input
                type="text"
                value={purposeText}
                onChange={(e) => setPurposeText(e.target.value)}
                placeholder="Enter access purpose..."
                className="w-full px-4 py-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white placeholder-[#95979E] focus:outline-none focus:ring-2 focus:ring-[#7c8cff]"
                required
                minLength={5}
              />

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowPurposeSheet(false)}
                  className="px-4 py-2 rounded-xl text-xs text-[#A9A9AA] hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={purposeText.trim().length < 5}
                  className="btn-primary-glow px-5 py-2 rounded-xl text-xs font-semibold disabled:opacity-40"
                >
                  Authorize & Open Case
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 5. New Case Sheet Modal */}
      {showNewCaseSheet && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-md"
            onClick={() => setShowNewCaseSheet(false)}
          />
          <div className="relative w-full max-w-lg rounded-2xl glass-panel-strong p-6 shadow-2xl z-10 text-left">
            <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)] mb-6">
              <div className="flex items-center gap-2">
                <FolderKanban className="w-5 h-5 text-[#5ad1ff]" />
                <h3 className="text-base font-bold text-white">Create New Investigation Case</h3>
              </div>
              <button
                onClick={() => setShowNewCaseSheet(false)}
                className="p-1 rounded text-[#A9A9AA] hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCase} className="space-y-5">
              {/* Step 1: Number & Title */}
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-[#A9A9AA] mb-1">
                    Case Identifier Number
                  </label>
                  <input
                    type="text"
                    value={newCaseNumber}
                    onChange={(e) => setNewCaseNumber(e.target.value)}
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white font-mono focus:ring-2 focus:ring-[#5ad1ff] outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-[#A9A9AA] mb-1">
                    Investigation Case Title
                  </label>
                  <input
                    type="text"
                    value={newCaseTitle}
                    onChange={(e) => setNewCaseTitle(e.target.value)}
                    placeholder="e.g. Armed robbery downtown storefront"
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white focus:ring-2 focus:ring-[#5ad1ff] outline-none"
                  />
                </div>
              </div>

              {/* Step 2: Privacy Mode Selection */}
              <div>
                <label className="block text-xs font-medium text-[#A9A9AA] mb-1.5">
                  Privacy & Data Mode
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setNewCaseMode('demo')}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      newCaseMode === 'demo'
                        ? 'bg-[#7c8cff]/15 border-[#7c8cff] text-white shadow-sm'
                        : 'bg-[#14161a] border-[rgba(255,255,255,0.08)] text-[#95979E]'
                    }`}
                  >
                    <div className="font-semibold text-xs text-white">Demo Mode</div>
                    <p className="text-[10px] text-[#A9A9AA] mt-1">
                      May use cloud LLMs (Gemini Free Tier).
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => setNewCaseMode('real')}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      newCaseMode === 'real'
                        ? 'bg-[#2fd4a4]/15 border-[#2fd4a4] text-white shadow-sm'
                        : 'bg-[#14161a] border-[rgba(255,255,255,0.08)] text-[#95979E]'
                    }`}
                  >
                    <div className="font-semibold text-xs text-[#2fd4a4]">Real (Local-Only)</div>
                    <p className="text-[10px] text-[#A9A9AA] mt-1">
                      Never calls cloud. Strict Ollama & local models only.
                    </p>
                  </button>
                </div>
              </div>

              {/* Step 3: Default appearance group (human set only per R11) */}
              <div>
                <label className="block text-xs font-medium text-[#A9A9AA] mb-1">
                  Default Appearance Group (Officer Set Only)
                </label>
                <select
                  value={newCaseAppearance}
                  onChange={(e) => setNewCaseAppearance(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white focus:ring-2 focus:ring-[#5ad1ff] outline-none"
                >
                  <option value="unspecified">Unspecified (Sample across variants)</option>
                  <option value="south_asian">South Asian</option>
                  <option value="east_asian">East Asian</option>
                  <option value="caucasian">Caucasian</option>
                  <option value="african">African</option>
                  <option value="other">Other / Multi-ethnic</option>
                </select>
                <p className="text-[10px] text-[#95979E] mt-1">
                  R11 Responsible AI rule: The AI never guesses this attribute.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-[rgba(255,255,255,0.08)]">
                <button
                  type="button"
                  onClick={() => setShowNewCaseSheet(false)}
                  className="px-4 py-2 text-xs text-[#A9A9AA] hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary-glow px-6 py-2.5 rounded-xl text-xs font-semibold"
                >
                  Initialize Case
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CommandCenterPage;
