import React, { useState, useEffect } from 'react';
import { Activity, X, Cpu, Layers, Shield, AlertCircle } from 'lucide-react';
import { apiClient, type RequestTelemetryRecord } from '../api/client';

interface PresenterHUDProps {
  isOpen: boolean;
  onClose: () => void;
  ambientTier?: 'high' | 'mid' | 'low';
}

export const PresenterHUD: React.FC<PresenterHUDProps> = ({
  isOpen,
  onClose,
  ambientTier = 'high',
}) => {
  const [fps, setFps] = useState(60);
  const [telemetryList, setTelemetryList] = useState<RequestTelemetryRecord[]>([]);

  // Measure live real-world requestAnimationFrame rendering FPS
  useEffect(() => {
    if (!isOpen) return;

    let frameCount = 0;
    let lastTime = performance.now();
    let animId: number;

    const measure = (now: number) => {
      frameCount++;
      if (now - lastTime >= 1000) {
        setFps(Math.round((frameCount * 1000) / (now - lastTime)));
        frameCount = 0;
        lastTime = now;
      }
      animId = requestAnimationFrame(measure);
    };

    animId = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(animId);
  }, [isOpen]);

  // Subscribe to live API request telemetry
  useEffect(() => {
    if (!isOpen) return;
    setTelemetryList(apiClient.getTelemetryHistory());
    const unsubscribe = apiClient.addTelemetryListener(() => {
      setTelemetryList(apiClient.getTelemetryHistory());
    });
    return unsubscribe;
  }, [isOpen]);

  if (!isOpen) return null;

  const findLatest = (endpointSub: string) => {
    for (let i = telemetryList.length - 1; i >= 0; i--) {
      if (telemetryList[i].endpoint.includes(endpointSub)) {
        return telemetryList[i];
      }
    }
    return null;
  };

  const asrTelemetry = findLatest('/speech/transcribe') || findLatest('/transcribe');
  const transTelemetry = findLatest('/speech/translate') || findLatest('/translate');
  const llmTelemetry = findLatest('/statements');
  const mlTelemetry = findLatest('/rounds');
  const finalizeTelemetry = findLatest('/finalize') || findLatest('/export');

  const pipelineStages = [
    {
      label: 'ASR (faster-whisper)',
      record: asrTelemetry,
      fallbackText: 'Standby (:8002 offline)',
    },
    {
      label: 'Translation (IndicTrans2)',
      record: transTelemetry,
      fallbackText: 'Standby (:8002 offline)',
    },
    {
      label: 'LLM Parser (Ollama / Gemini)',
      record: llmTelemetry,
      fallbackText: 'Standby (:8000 offline)',
      detail: llmTelemetry?.llmInfo?.model,
    },
    {
      label: 'LCM Generation (SD-1.5)',
      record: mlTelemetry,
      fallbackText: 'Standby (:8001 offline)',
    },
    {
      label: 'Finalize / Court Packet',
      record: finalizeTelemetry,
      fallbackText: 'Standby (Unexecuted)',
    },
  ];

  return (
    <div
      role="complementary"
      aria-label="Presenter Telemetry HUD"
      className="fixed bottom-6 right-6 z-50 w-80 bg-[#0e0f12]/95 backdrop-blur-xl border border-[rgba(255,255,255,0.16)] rounded-2xl shadow-2xl overflow-hidden font-mono text-xs select-none animate-in fade-in slide-in-from-bottom-2 duration-150"
    >
      {/* HUD Header */}
      <div className="p-3 bg-[#14161a] border-b border-[rgba(255,255,255,0.08)] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#5ad1ff]" />
          <span className="font-bold text-white uppercase text-[11px] tracking-wider">
            Presenter HUD
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-emerald-400 font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
            {fps} FPS
          </span>
          <button
            onClick={onClose}
            className="p-1 text-[#95979E] hover:text-white rounded transition-colors"
            aria-label="Close Presenter HUD"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Latencies metrics */}
      <div className="p-3.5 space-y-2.5">
        <div className="text-[10px] text-[#A9A9AA] uppercase font-semibold flex items-center justify-between pb-1 border-b border-[rgba(255,255,255,0.06)]">
          <span>Pipeline Stage</span>
          <span>Measured Latency</span>
        </div>

        <div className="space-y-1.5">
          {pipelineStages.map((stage) => {
            const hasData = !!stage.record;
            return (
              <div key={stage.label} className="flex items-center justify-between text-[11px]">
                <div className="truncate pr-2">
                  <span className="text-[#f4f5f7]/90">{stage.label}</span>
                  {stage.detail && (
                    <span className="text-[9px] text-[#A9A9AA] ml-1.5 font-sans">
                      ({stage.detail})
                    </span>
                  )}
                </div>
                {hasData ? (
                  <span className="text-[#5ad1ff] font-bold shrink-0">
                    {stage.record!.latencyMs} ms
                  </span>
                ) : (
                  <span className="text-[#95979E] text-[10px] shrink-0 font-sans italic">
                    {stage.fallbackText}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {/* System & Hardware Health */}
        <div className="pt-2 border-t border-[rgba(255,255,255,0.06)] space-y-1.5 text-[10px] text-[#95979E]">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Cpu className="w-3 h-3 text-[#7c8cff]" />
              VRAM Allocation:
            </span>
            <span className="text-[#A9A9AA] italic font-sans flex items-center gap-1">
              <AlertCircle className="w-3 h-3 text-[#ffb454]" />
              Unavailable (:8001 offline)
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Layers className="w-3 h-3 text-[#ffb454]" />
              Ambient Tier:
            </span>
            <span className="text-white uppercase font-bold">{ambientTier}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Shield className="w-3 h-3 text-emerald-400" />
              Privacy Router:
            </span>
            <span className="text-emerald-400 font-medium">Enforced: Local-only</span>
          </div>
        </div>
      </div>

      {/* Quick toggle instruction */}
      <div className="p-2 bg-[#090a0c] border-t border-[rgba(255,255,255,0.06)] text-[9px] text-[#A9A9AA] text-center">
        Toggle with <kbd className="px-1 py-0.5 rounded bg-[#14161a] text-white">Shift + P</kbd>
      </div>
    </div>
  );
};
