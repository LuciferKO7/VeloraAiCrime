import React from 'react';
import { Shield, Cpu, Activity, Clock } from 'lucide-react';
import { Vela } from './Vela';

export interface DynamicIslandProps {
  caseNumber?: string;
  witnessAlias?: string;
  phase?: 'Describe' | 'Recognize' | 'Refine' | 'Finalize';
  statusMessage?: string;
  provider?: string;
  model?: string;
  latencyMs?: number;
  dataMode?: 'demo' | 'real';
  routeReason?: string;
  isStreaming?: boolean;
}

/**
 * DynamicIsland
 *
 * Morphing pill at top-center of Studio per FRONTEND_DESIGN.md §6.5.
 * Shows case metadata, active phase, live request state, provider/model, and latency.
 */
export const DynamicIsland: React.FC<DynamicIslandProps> = ({
  caseNumber = 'DEMO-001',
  witnessAlias = 'W-001',
  phase = 'Describe',
  statusMessage,
  provider,
  model,
  latencyMs,
  dataMode = 'demo',
  isStreaming = false,
}) => {
  const isLocal = dataMode === 'real';

  return (
    <aside
      aria-label="Studio status console"
      className="inline-flex items-center gap-3 px-4 py-2 rounded-full glass-panel-strong border border-[rgba(255,255,255,0.14)] text-xs text-[#f4f5f7] shadow-2xl transition-all duration-300 backdrop-blur-xl"
    >
      {/* Mini-Vela */}
      <Vela
        size="mini"
        state={isStreaming ? 'sketching' : isLocal ? 'shield' : 'idle'}
      />

      {/* Case and Witness info */}
      <div className="flex items-center gap-2">
        <span className="font-mono font-medium text-white">{caseNumber}</span>
        <span className="text-[rgba(255,255,255,0.2)]">•</span>
        <span className="text-[#A9A9AA]">{witnessAlias}</span>
      </div>

      <span className="text-[rgba(255,255,255,0.2)]">|</span>

      {/* Mode / Privacy Badge */}
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium ${
          isLocal
            ? 'bg-[#2fd4a4]/20 text-[#2fd4a4] border border-[#2fd4a4]/40'
            : 'bg-[#7c8cff]/20 text-[#7c8cff] border border-[#7c8cff]/40'
        }`}
      >
        <Shield className="w-3 h-3" />
        <span>{isLocal ? 'Local-only' : 'Demo (Cloud)'}</span>
      </span>

      <span className="text-[rgba(255,255,255,0.2)]">|</span>

      {/* Active Phase Pill */}
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-[#A9A9AA]">Phase:</span>
        <span className="font-semibold text-white px-2 py-0.5 rounded-md bg-[rgba(255,255,255,0.08)]">
          {phase}
        </span>
      </div>

      {/* Live Provider & Latency */}
      {provider && (
        <div className="hidden sm:flex items-center gap-2 font-mono text-[10px] text-[#A9A9AA] pl-1">
          <span className="flex items-center gap-1 text-emerald-400">
            <Cpu className="w-3 h-3" />
            <span>{provider}{model ? `:${model.split(':')[0]}` : ''}</span>
          </span>
          {latencyMs !== undefined && (
            <span className="flex items-center gap-0.5 text-[#A9A9AA]">
              <Clock className="w-3 h-3 text-[#5ad1ff]" />
              <span>{(latencyMs / 1000).toFixed(1)}s</span>
            </span>
          )}
        </div>
      )}

      {/* Dynamic Status / Activity readout */}
      {statusMessage && (
        <span className="hidden md:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] bg-[rgba(255,255,255,0.06)] text-white animate-pulse">
          <Activity className="w-3 h-3 text-[#FF8964]" />
          <span>{statusMessage}</span>
        </span>
      )}
    </aside>
  );
};

export default DynamicIsland;
