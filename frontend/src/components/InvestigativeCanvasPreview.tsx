import React from 'react';
import { Layers, Activity, ShieldCheck, Eye, Compass, GitBranch, Cpu, Lock } from 'lucide-react';

interface InvestigativeCanvasPreviewProps {
  className?: string;
}

/**
 * InvestigativeCanvasPreview
 *
 * Dark charcoal product preview floating in front of the aurora pool.
 * Features fine slate border, restrained iris/coral edge illumination,
 * and clear labelling as an illustrative concept preview for data integrity.
 */
export const InvestigativeCanvasPreview: React.FC<InvestigativeCanvasPreviewProps> = ({
  className = '',
}) => {
  return (
    <div
      className={`relative w-full max-w-[1140px] mx-auto rounded-2xl border border-[#4A4B50]/60 bg-[#111111]/95 shadow-[0_-18px_45px_-12px_rgba(255,137,100,0.22),0_25px_70px_rgba(0,0,0,0.95)] backdrop-blur-xl overflow-hidden text-left ${className}`}
    >
      {/* 1. Luminous Top Rim Specular Catch (Simulates aurora light hitting chassis) */}
      <div
        className="absolute top-0 inset-x-0 h-[1.5px] pointer-events-none"
        style={{
          background:
            'linear-gradient(90deg, transparent 5%, rgba(86, 131, 218, 0.45) 30%, rgba(255, 137, 100, 0.9) 55%, rgba(255, 255, 255, 0.7) 65%, rgba(86, 131, 218, 0.3) 85%, transparent 95%)',
        }}
      />

      {/* 2. Top Window Console Chrome */}
      <div className="flex flex-wrap items-center justify-between px-5 py-3 border-b border-[#4A4B50]/40 bg-[#090A0C]/85 gap-2">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-[#4A4B50]/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#4A4B50]/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#4A4B50]/60" />
          <span className="ml-3 text-[11px] font-mono uppercase tracking-wider text-[#95979E]">
            WORKSPACE CONSOLE // CASE-2026-0814A
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-[#FF8964]/15 text-[#FF8964] border border-[#FF8964]/30">
            <span className="w-1.5 h-1.5 rounded-full bg-[#FF8964] animate-pulse mr-1.5" />
            ILLUSTRATIVE CONCEPT PREVIEW
          </span>
        </div>
      </div>

      {/* 3. Main Console Workspace Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 divide-y md:divide-y-0 md:divide-x divide-[#4A4B50]/30 text-xs">
        {/* Panel 1: Witness Statements Analysis */}
        <div className="md:col-span-4 p-5 sm:p-6 space-y-4">
          <div className="flex items-center justify-between text-[#95979E]">
            <span className="flex items-center gap-1.5 font-semibold text-[#E5E5E7] tracking-tight">
              <Layers className="w-3.5 h-3.5 text-[#5683DA]" />
              Witness Statements
            </span>
            <span className="font-mono text-[10px] text-[#A9A9AA]">3 Ingested (Demo)</span>
          </div>

          <div className="space-y-3">
            <div className="p-3 rounded-xl bg-[#303236]/25 border border-[#4A4B50]/40 space-y-1.5 hover:border-[#5683DA]/50 transition-colors">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-white font-medium">Witness 01 (Store Clerk)</span>
                <span className="text-[#5683DA] font-mono text-[10px]">Audio 04:12</span>
              </div>
              <p className="text-[#95979E] text-[11px] leading-snug">
                &ldquo;Dark hooded jacket, approximately 5&apos;10&rdquo;, fled eastward toward 4th Ave.&rdquo;
              </p>
              <div className="flex items-center gap-1.5 pt-1">
                <span className="px-1.5 py-0.5 rounded text-[9px] bg-[#5683DA]/20 text-[#5683DA] border border-[#5683DA]/30">
                  High Confidence
                </span>
                <span className="px-1.5 py-0.5 rounded text-[9px] bg-white/5 text-[#A9A9AA]">
                  Natural Lux
                </span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-[#303236]/25 border border-[#4A4B50]/40 space-y-1.5 hover:border-[#FF8964]/50 transition-colors">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-white font-medium">Witness 02 (Pedestrian)</span>
                <span className="text-[#FF8964] font-mono text-[10px]">Audio 01:45</span>
              </div>
              <p className="text-[#95979E] text-[11px] leading-snug">
                &ldquo;Stature seemed shorter, maybe 5&apos;8&rdquo;, carrying dark nylon backpack.&rdquo;
              </p>
              <div className="flex items-center gap-1.5 pt-1">
                <span className="px-1.5 py-0.5 rounded text-[9px] bg-[#FF8964]/20 text-[#FF8964] border border-[#FF8964]/30">
                  Height Variance (+2&rdquo;)
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Panel 2: Scene & Spatial Alignment Graph */}
        <div className="md:col-span-5 p-5 sm:p-6 space-y-4">
          <div className="flex items-center justify-between text-[#95979E]">
            <span className="flex items-center gap-1.5 font-semibold text-[#E5E5E7] tracking-tight">
              <Compass className="w-3.5 h-3.5 text-[#FF8964]" />
              Scene Geometry & Viewpoints
            </span>
            <span className="font-mono text-[10px] text-[#A9A9AA]">Intersection 4th & Elm</span>
          </div>

          <div className="h-48 rounded-xl bg-[#090A0C] border border-[#4A4B50]/40 p-3.5 relative flex flex-col justify-between overflow-hidden shadow-inner">
            {/* Architectural Grid Lines */}
            <div className="absolute inset-0 bg-[radial-gradient(#4A4B50_1px,transparent_1px)] [background-size:16px_16px] opacity-25" />

            {/* Viewpoint Angles */}
            <div className="relative z-10 flex justify-between items-start">
              <div className="flex items-center gap-1.5 bg-[#111111]/90 px-2.5 py-1 rounded-lg border border-[#5683DA]/40 text-[10px] text-[#5683DA] shadow-sm">
                <Eye className="w-3 h-3" />
                <span>Observer A (Angle 42°)</span>
              </div>
              <div className="flex items-center gap-1.5 bg-[#111111]/90 px-2.5 py-1 rounded-lg border border-[#FF8964]/40 text-[10px] text-[#FF8964] shadow-sm">
                <Eye className="w-3 h-3" />
                <span>Observer B (Angle 115°)</span>
              </div>
            </div>

            {/* Central Convergence Indicator */}
            <div className="relative z-10 text-center py-2">
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#111111]/95 border border-[#4A4B50]/70 text-[11px] text-white shadow-md">
                <Activity className="w-3.5 h-3.5 text-[#FF8964]" />
                <span>Line of Sight Alignment: 94.2% (Simulated)</span>
              </div>
            </div>

            <div className="relative z-10 flex justify-between text-[10px] text-[#95979E] font-mono">
              <span>Ambient Lux: 280 (Dusk)</span>
              <span>Distance to Subject: 14.5m</span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] text-[#95979E] pt-1">
            <span className="flex items-center gap-1.5">
              <GitBranch className="w-3.5 h-3.5 text-[#5683DA]" />
              Multi-angle viewpoint synthesis
            </span>
            <span className="text-[#5683DA] font-mono text-[10px]">Calculated</span>
          </div>
        </div>

        {/* Panel 3: Cryptographic Audit & Statutory Notice */}
        <div className="md:col-span-3 p-5 sm:p-6 space-y-4 bg-[#090A0C]/50">
          <div className="flex items-center justify-between text-[#95979E]">
            <span className="flex items-center gap-1.5 font-semibold text-[#E5E5E7] tracking-tight">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Custody Integrity
            </span>
            <span className="font-mono text-[9px] text-emerald-400">DEMO RECORD</span>
          </div>

          <div className="space-y-2.5">
            <div className="p-2.5 rounded-lg bg-[#111111] border border-[#4A4B50]/40 space-y-1">
              <div className="flex items-center justify-between text-[10px] font-mono text-[#95979E]">
                <span>SAMPLE HASH</span>
                <Lock className="w-3 h-3 text-[#5683DA]" />
              </div>
              <div className="text-[10px] font-mono text-[#E5E5E7] truncate">
                sha256:8f2a49b...c04e
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-[#111111] border border-[#4A4B50]/40 space-y-1">
              <div className="text-[10px] font-mono text-[#95979E]">TRACEABILITY</div>
              <div className="text-[11px] text-[#E5E5E7]">
                3 operations logged by Investigator ID #7802
              </div>
            </div>

            {/* Mandatory Legal Guardrail Banner inside console */}
            <div className="p-3 rounded-lg bg-[#5A250A]/40 border border-[#FF8964]/40 text-[10px] text-[#FF8964] leading-relaxed shadow-sm">
              <div className="flex items-center gap-1 font-semibold mb-0.5">
                <Cpu className="w-3 h-3 text-[#FF8964]" />
                STATUTORY SAFEGUARD
              </div>
              AI investigative aid — not a photograph, not evidence of identity.
            </div>
          </div>
        </div>
      </div>

      {/* 4. Bottom Status Rail */}
      <div className="flex flex-wrap items-center justify-between px-5 py-2.5 bg-[#090A0C]/90 border-t border-[#4A4B50]/30 text-[11px] text-[#95979E]">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            Local Model Encrypted
          </span>
          <span className="hidden sm:inline text-[#4A4B50]">•</span>
          <span className="hidden sm:inline">Zero external training telemetry</span>
        </div>
        <div className="font-mono text-[10px] text-[#A9A9AA]">
          VELORA v1.1.0-STABLE • CONCEPT SHELL
        </div>
      </div>
    </div>
  );
};

export default InvestigativeCanvasPreview;
