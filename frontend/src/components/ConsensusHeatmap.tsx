import React, { useState } from 'react';
import {
  Users,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Sparkles,
  Search,
  ChevronRight,
  WifiOff,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { DEMO_POSSIBLE_LEADS } from '../store/demoData';

export interface WitnessSessionSummary {
  id: string;
  witnessAlias: string;
  language: string;
  features: {
    jawline: { value: string; confidence: 'sure' | 'somewhat' | 'unsure' };
    eyebrows: { value: string; confidence: 'sure' | 'somewhat' | 'unsure' };
    eyeShape: { value: string; confidence: 'sure' | 'somewhat' | 'unsure' };
    hairStyle: { value: string; confidence: 'sure' | 'somewhat' | 'unsure' };
    noseShape: { value: string; confidence: 'sure' | 'somewhat' | 'unsure' };
    ageEstimate: { value: string; confidence: 'sure' | 'somewhat' | 'unsure' };
  };
}

const SAMPLE_WITNESSES: WitnessSessionSummary[] = [
  {
    id: 'ses-w1',
    witnessAlias: 'Witness W-001 (Victim)',
    language: 'Tamil (தமிழ்)',
    features: {
      jawline: { value: 'sharp angular', confidence: 'sure' },
      eyebrows: { value: 'thick arched', confidence: 'sure' },
      eyeShape: { value: 'deep-set almond', confidence: 'somewhat' },
      hairStyle: { value: 'short cropped black', confidence: 'sure' },
      noseShape: { value: 'straight bridge', confidence: 'somewhat' },
      ageEstimate: { value: '28-32 years', confidence: 'sure' },
    },
  },
  {
    id: 'ses-w2',
    witnessAlias: 'Witness W-002 (Bystander)',
    language: 'English',
    features: {
      jawline: { value: 'sharp square', confidence: 'somewhat' },
      eyebrows: { value: 'thick dark', confidence: 'sure' },
      eyeShape: { value: 'almond', confidence: 'somewhat' },
      hairStyle: { value: 'wavy black parted', confidence: 'somewhat' },
      noseShape: { value: 'straight narrow', confidence: 'somewhat' },
      ageEstimate: { value: '30-35 years', confidence: 'somewhat' },
    },
  },
  {
    id: 'ses-w3',
    witnessAlias: 'Witness W-003 (Shopkeeper)',
    language: 'Hindi (हिन्दी)',
    features: {
      jawline: { value: 'medium rounded', confidence: 'unsure' }, // Disputed!
      eyebrows: { value: 'thick arched', confidence: 'sure' },
      eyeShape: { value: 'deep-set', confidence: 'somewhat' },
      hairStyle: { value: 'dark covered by cap', confidence: 'sure' }, // Disputed!
      noseShape: { value: 'prominent bridge', confidence: 'unsure' },
      ageEstimate: { value: '28-30 years', confidence: 'sure' },
    },
  },
];

interface FeatureRow {
  key: keyof WitnessSessionSummary['features'];
  name: string;
  agreementStatus: 'high' | 'medium' | 'disputed';
  disputeNote?: string;
}

const FEATURE_ROWS: FeatureRow[] = [
  { key: 'eyebrows', name: 'Eyebrow Density & Arch', agreementStatus: 'high' },
  { key: 'ageEstimate', name: 'Estimated Age Band', agreementStatus: 'high' },
  { key: 'eyeShape', name: 'Eye Shape & Orbit Depth', agreementStatus: 'medium' },
  { key: 'noseShape', name: 'Nose Bridge & Width', agreementStatus: 'medium' },
  {
    key: 'jawline',
    name: 'Jawline & Chin Geometry',
    agreementStatus: 'disputed',
    disputeNote: 'W-001 & W-002 report sharp angular chin; W-003 reports softer rounded jawline.',
  },
  {
    key: 'hairStyle',
    name: 'Hair Style & Coverage',
    agreementStatus: 'disputed',
    disputeNote: 'W-001 & W-002 saw short cropped hair; W-003 reports headwear/cap present.',
  },
];

export const ConsensusHeatmap: React.FC = () => {
  const [selectedFeature, setSelectedFeature] = useState<FeatureRow | null>(FEATURE_ROWS[4]);
  const [isGeneratingAlternates, setIsGeneratingAlternates] = useState(false);
  const [alternateSuccess, setAlternateSuccess] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [showPossibleLeads, setShowPossibleLeads] = useState(false);

  const handleGenerateAlternates = async () => {
    setIsGeneratingAlternates(true);
    setAlternateSuccess(false);
    setGenerationError(null);

    try {
      await apiClient.post('/sessions/ses-w1/rounds/edit', {
        feature: selectedFeature?.key,
        dispute: selectedFeature?.disputeNote,
        instruction: 'Branch alternate composite variants based on witness dispute',
      });
      setAlternateSuccess(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Backend offline on port 8000';
      setGenerationError(
        `Backend service offline (:8000): ${msg}. Remote alternate generation cannot be triggered.`
      );
    } finally {
      setIsGeneratingAlternates(false);
    }
  };

  const handleSimulateFixtureAlternates = () => {
    setGenerationError(null);
    setAlternateSuccess(true);
  };

  return (
    <div className="space-y-6">
      {/* Overview Card */}
      <div className="p-5 rounded-2xl glass-panel space-y-3">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/40">
                [DEV FIXTURE]
              </span>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Users className="w-5 h-5 text-[#7c8cff]" />
                Multi-Witness Consensus Matrix (Simulation Baseline)
              </h3>
            </div>
            <p className="text-xs text-[#95979E] mt-1">
              Correlating 3 independent witness sessions across facial feature vectors.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowPossibleLeads(!showPossibleLeads)}
              className="px-3 py-1.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-xs text-[#5ad1ff] hover:text-white flex items-center gap-1.5 transition-colors"
            >
              <Search className="w-3.5 h-3.5" />
              <span>{showPossibleLeads ? 'Hide Possible Leads' : 'Possible Leads (Top-K)'}</span>
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-[11px] pt-2 border-t border-[rgba(255,255,255,0.06)] font-mono">
          <span className="text-[#95979E]">Agreement:</span>
          <span className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            Consensus (≥80%)
          </span>
          <span className="flex items-center gap-1.5 text-[#5ad1ff]">
            <span className="w-2 h-2 rounded-full bg-[#5ad1ff]" />
            Moderate (50-79%)
          </span>
          <span className="flex items-center gap-1.5 text-[#ffb454]">
            <span className="w-2 h-2 rounded-full bg-[#ffb454]" />
            Disputed (&lt;50%)
          </span>
        </div>
      </div>

      {/* Heatmap Matrix Table */}
      <div className="rounded-2xl glass-panel overflow-hidden border border-[rgba(255,255,255,0.08)] shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#0e0f12] text-[#A9A9AA] border-b border-[rgba(255,255,255,0.08)]">
                <th className="py-3 px-4 font-semibold uppercase text-[10px] tracking-wider">
                  Facial Feature
                </th>
                <th className="py-3 px-4 font-semibold uppercase text-[10px] tracking-wider text-center">
                  Consensus Status
                </th>
                {SAMPLE_WITNESSES.map((w) => (
                  <th
                    key={w.id}
                    className="py-3 px-4 font-semibold uppercase text-[10px] tracking-wider"
                  >
                    <div>{w.witnessAlias}</div>
                    <div className="text-[9px] text-[#95979E] font-normal font-mono">
                      {w.language}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgba(255,255,255,0.04)]">
              {FEATURE_ROWS.map((row) => {
                const isSelected = selectedFeature?.key === row.key;
                return (
                  <tr
                    key={row.key}
                    onClick={() => setSelectedFeature(row)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-[#7c8cff]/10' : 'hover:bg-white/[0.02]'
                    }`}
                  >
                    <td className="py-3.5 px-4 font-medium text-white flex items-center justify-between">
                      <span>{row.name}</span>
                      <ChevronRight className="w-3.5 h-3.5 text-[#95979E]" />
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                          row.agreementStatus === 'high'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : row.agreementStatus === 'medium'
                            ? 'bg-[#5ad1ff]/10 text-[#5ad1ff] border border-[#5ad1ff]/20'
                            : 'bg-[#ffb454]/10 text-[#ffb454] border border-[#ffb454]/20'
                        }`}
                      >
                        {row.agreementStatus === 'high' ? (
                          <CheckCircle2 className="w-3 h-3" />
                        ) : row.agreementStatus === 'medium' ? (
                          <HelpCircle className="w-3 h-3" />
                        ) : (
                          <AlertCircle className="w-3 h-3" />
                        )}
                        {row.agreementStatus}
                      </span>
                    </td>
                    {SAMPLE_WITNESSES.map((w) => {
                      const feat = w.features[row.key];
                      return (
                        <td key={w.id} className="py-3.5 px-4">
                          <div className="text-white/90 font-medium">{feat.value}</div>
                          <div className="text-[10px] text-[#A9A9AA] font-mono">
                            Conf: {feat.confidence}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Disputed Feature Action Box */}
      {selectedFeature && (
        <div className="p-5 rounded-2xl glass-panel border border-[rgba(255,255,255,0.12)] space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div>
              <span className="text-[10px] uppercase font-mono text-[#5ad1ff] tracking-wider block">
                Selected Disputed Feature Analysis
              </span>
              <h4 className="text-sm font-bold text-white">{selectedFeature.name}</h4>
            </div>

            {selectedFeature.agreementStatus === 'disputed' && (
              <button
                onClick={handleGenerateAlternates}
                disabled={isGeneratingAlternates}
                className="btn-primary-glow px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-2"
              >
                {isGeneratingAlternates ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-[#090a0c] border-t-transparent rounded-full animate-spin" />
                    <span>Branching Alternate Variants...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Generate Alternates For Disputed Features</span>
                  </>
                )}
              </button>
            )}
          </div>

          {selectedFeature.disputeNote && (
            <div className="p-3.5 rounded-xl bg-[#ffb454]/10 border border-[#ffb454]/30 text-xs text-[#ffb454]">
              <span className="font-semibold block mb-0.5">Discrepancy Note:</span>
              <p className="text-[#ffb454]/90 text-[11px] leading-relaxed">
                {selectedFeature.disputeNote}
              </p>
            </div>
          )}

          {generationError && (
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 space-y-2">
              <div className="flex items-center gap-1.5 font-semibold text-amber-300">
                <WifiOff className="w-4 h-4 shrink-0" />
                <span>Backend Branching Service Offline (:8000)</span>
              </div>
              <p className="text-[11px] text-amber-200/90 leading-relaxed">
                {generationError}
              </p>
              <div className="pt-1">
                <button
                  type="button"
                  onClick={handleSimulateFixtureAlternates}
                  className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                >
                  <span>[DEV FIXTURE] Simulate Alternate Variants for UI Verification</span>
                </button>
              </div>
            </div>
          )}

          {alternateSuccess && (
            <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-400 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              <span>
                Generated 2 alternate branches (sharp jaw vs rounded jaw). Available in Studio round filmstrip.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Possible Leads Panel (P1 - STRICT R11 Invariant: NEVER says "identified") */}
      {showPossibleLeads && (
        <div className="p-5 rounded-2xl glass-panel space-y-4 border border-[rgba(255,255,255,0.12)]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/40">
                [DEV FIXTURE]
              </span>
              <Search className="w-4 h-4 text-[#5ad1ff]" />
              <h4 className="text-sm font-bold text-white">Possible Leads (Top-K Matches)</h4>
            </div>
            <span className="px-2 py-0.5 rounded-full bg-[#5A250A] text-[10px] font-mono text-[#FF8964] border border-[#FF8964]/40">
              Corroborative Lead Only — Not Proof of Identity
            </span>
          </div>

          <p className="text-xs text-[#95979E]">
            [DEV FIXTURE] Static gallery embeddings baseline shown for demonstration. Human supervisor review
            is legally required before investigative action.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {DEMO_POSSIBLE_LEADS.map((lead, idx) => (
              <div
                key={lead.id}
                className="p-4 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] space-y-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-white">Lead #{idx + 1} ({lead.id})</span>
                  <span className="text-xs font-mono font-bold text-[#5ad1ff]">
                    {lead.similarityPct}% Similarity
                  </span>
                </div>
                <div className="w-full bg-[#090a0c] rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-[#7c8cff] to-[#5ad1ff] h-full rounded-full"
                    style={{ width: `${lead.similarityPct}%` }}
                  />
                </div>
                <p className="text-[11px] text-[#A9A9AA]">
                  {lead.basis}
                </p>
                <div className="pt-2 border-t border-[rgba(255,255,255,0.06)] flex items-center justify-between text-[10px]">
                  <span className="text-[#95979E]">{lead.disclaimer}</span>
                  <span className="text-[#7c8cff] cursor-pointer hover:underline">
                    Dist: {lead.vectorDistance}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
