import React, { useState, useEffect } from 'react';
import {
  User,
  Car,
  ShieldAlert,
  Building,
  Navigation,
  Sparkles,
  Download,
  AlertTriangle,
  Play,
  Pause,
  RotateCcw,
  WifiOff,
} from 'lucide-react';
import { MANDATORY_DISCLAIMER } from '../pages/LandingPage';
import { Vela } from './Vela';
import { apiClient } from '../api/client';

export interface SceneEntity {
  id: string;
  kind: 'person' | 'vehicle' | 'weapon' | 'landmark' | 'other';
  label: string;
  x: number; // 0 to 1 normalized
  y: number; // 0 to 1 normalized
  heading_deg: number;
  confidence: 'sure' | 'somewhat' | 'unsure';
  is_conflicted: boolean;
  conflict_ghost?: { x: number; y: number };
}

const DEV_FIXTURE_ENTITIES: SceneEntity[] = [
  {
    id: 'ent-1',
    kind: 'person',
    label: '[DEV FIXTURE] Witness W-001 (Viewing angle)',
    x: 0.22,
    y: 0.72,
    heading_deg: 40,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-2',
    kind: 'person',
    label: '[DEV FIXTURE] Suspect Position',
    x: 0.52,
    y: 0.42,
    heading_deg: 200,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-3',
    kind: 'vehicle',
    label: '[DEV FIXTURE] Getaway Vehicle (Dark sedan)',
    x: 0.80,
    y: 0.32,
    heading_deg: 90,
    confidence: 'somewhat',
    is_conflicted: true,
    conflict_ghost: { x: 0.88, y: 0.55 },
  },
  {
    id: 'ent-4',
    kind: 'landmark',
    label: '[DEV FIXTURE] Storefront Entrance / Cash Counter',
    x: 0.48,
    y: 0.18,
    heading_deg: 0,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-5',
    kind: 'weapon',
    label: '[DEV FIXTURE] Discarded Object / Weapon',
    x: 0.62,
    y: 0.58,
    heading_deg: 15,
    confidence: 'unsure',
    is_conflicted: false,
  },
];

interface SceneEditorProps {
  sessionId?: string;
  onBackToStudio?: () => void;
}

export const SceneEditor: React.FC<SceneEditorProps> = ({
  sessionId = 'SES-2026-0814',
  onBackToStudio,
}) => {
  const [entities, setEntities] = useState<SceneEntity[]>(DEV_FIXTURE_ENTITIES);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>('ent-2');
  const [timelineProgress, setTimelineProgress] = useState(30);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState<string | null>(null);
  const [isBackendOffline, setIsBackendOffline] = useState(false);
  const [narrativeInput, setNarrativeInput] = useState(
    'The suspect approached from the commercial storefront, confronted the cashier, and fled towards the dark sedan parked at the east curb.'
  );

  useEffect(() => {
    let active = true;
    const fetchScene = async () => {
      try {
        interface SceneApiResponse {
          scene?: {
            entities?: SceneEntity[];
          };
        }
        const data = await apiClient.get<SceneApiResponse>(
          `/sessions/${sessionId}/scene`,
          { purpose: 'Scene diagram inspection' }
        );
        if (active && data?.scene?.entities && data.scene.entities.length > 0) {
          setEntities(data.scene.entities);
          setIsBackendOffline(false);
        }
      } catch {
        if (active) {
          setIsBackendOffline(true);
        }
      }
    };
    fetchScene();
    return () => {
      active = false;
    };
  }, [sessionId]);

  const selectedEntity = entities.find((e) => e.id === selectedEntityId);

  const handleEntityDrag = (id: string, e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.parentElement?.getBoundingClientRect();
    if (!rect) return;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const newX = Math.max(0.05, Math.min(0.95, (moveEvent.clientX - rect.left) / rect.width));
      const newY = Math.max(0.05, Math.min(0.95, (moveEvent.clientY - rect.top) / rect.height));

      setEntities((prev) =>
        prev.map((item) => (item.id === id ? { ...item, x: newX, y: newY } : item))
      );
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleExtractFromNarrative = async () => {
    setIsExtracting(true);
    setExtractionError(null);

    try {
      interface ExtractResponse {
        entities?: SceneEntity[];
      }
      const res = await apiClient.post<ExtractResponse>(
        `/sessions/${sessionId}/scene/extract`,
        { narrative: narrativeInput },
        { purpose: 'Spatial narrative entity extraction' }
      );
      if (res?.entities && res.entities.length > 0) {
        setEntities((prev) => [...prev, ...res.entities!]);
      } else {
        throw new Error('No new entities returned from narrative parser');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Backend offline on port 8000';
      setExtractionError(
        `Scene extraction service offline (:8000): ${msg}. Backend spatial parser is unreachable.`
      );
    } finally {
      setIsExtracting(false);
    }
  };

  const handleAddFixtureEntity = () => {
    setExtractionError(null);
    setEntities((prev) => [
      ...prev,
      {
        id: `ent-${Date.now()}`,
        kind: 'other',
        label: '[DEV FIXTURE] Cashier Counter (Parsed)',
        x: 0.40,
        y: 0.35,
        heading_deg: 0,
        confidence: 'sure',
        is_conflicted: false,
      },
    ]);
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
      {/* Top Banner & Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-[rgba(255,255,255,0.08)]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full bg-[#7c8cff]/10 text-[#7c8cff] text-[10px] font-mono font-semibold uppercase">
              BNSS §176(3) Forensic Scene Mode
            </span>
            <span className="text-xs text-[#95979E]">Session: {sessionId}</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
            Spatial Crime Scene Diagram & Trajectory
          </h1>
        </div>

        <div className="flex items-center gap-3">
          {onBackToStudio && (
            <button
              onClick={onBackToStudio}
              className="px-3.5 py-1.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-xs text-[#f4f5f7] hover:text-white transition-colors"
            >
              ← Back to Studio
            </button>
          )}
          <button
            onClick={() => {
              const svgData = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" style="background:#090a0c;">
  <text x="20" y="30" fill="#FFC1AD" font-size="12">${MANDATORY_DISCLAIMER}</text>
  <text x="20" y="60" fill="#ffffff" font-size="16" font-weight="bold">SCENE DIAGRAM - ${sessionId}</text>
  ${entities
    .map(
      (e) =>
        `<circle cx="${e.x * 800}" cy="${e.y * 600}" r="12" fill="#7c8cff" />
         <text x="${e.x * 800 + 16}" y="${e.y * 600 + 4}" fill="#ffffff" font-size="12">${e.label}</text>`
    )
    .join('\n  ')}
</svg>`;
              const blob = new Blob([svgData], { type: 'image/svg+xml' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `VELORA_SCENE_${sessionId}.svg`;
              a.click();
            }}
            className="btn-primary-glow px-4 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-2"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export SVG Diagram</span>
          </button>
        </div>
      </div>

      {/* Honest Backend Service Offline Notice */}
      {isBackendOffline && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <WifiOff className="w-4 h-4 text-amber-400 shrink-0" />
            <div>
              <span className="font-semibold text-amber-300">Backend Scene Service Offline (:8000)</span>
              <p className="text-[11px] text-amber-200/80 mt-0.5">
                The centralized scene persistence service is unreachable. Showing clearly labeled <code className="px-1 py-0.5 rounded bg-black/40 font-mono text-[10px]">[DEV FIXTURE]</code> demonstrator layout.
              </p>
            </div>
          </div>
          <span className="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-300 font-mono text-[10px] shrink-0">
            OFFLINE FIXTURE MODE
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Interactive Canvas Grid */}
        <div className="lg:col-span-8 flex flex-col space-y-4">
          <div className="relative w-full h-[540px] rounded-2xl bg-[#090a0c] border border-[rgba(255,255,255,0.12)] overflow-hidden shadow-2xl select-none">
            {/* Perspective / Soft Grid lines */}
            <div
              className="absolute inset-0 pointer-events-none opacity-20"
              style={{
                backgroundImage:
                  'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.3) 1px, transparent 0)',
                backgroundSize: '32px 32px',
              }}
            />

            {/* Scale Unknown Mandatory Notice Badge */}
            <div className="absolute top-4 left-4 z-20 px-3 py-1 rounded-full bg-[#14161a]/90 backdrop-blur-md border border-[rgba(255,255,255,0.12)] text-[10px] text-[#ffb454] font-medium flex items-center gap-1.5 shadow">
              <AlertTriangle className="w-3.5 h-3.5 text-[#ffb454]" />
              <span>Scale unknown — diagram not to exact metric scale</span>
            </div>

            {/* Compass Heading Indicator */}
            <div className="absolute top-4 right-4 z-20 w-8 h-8 rounded-full bg-[#14161a]/90 border border-[rgba(255,255,255,0.12)] flex items-center justify-center text-[10px] font-mono text-[#5ad1ff] shadow">
              N ↑
            </div>

            {/* Conflicted positions dashed connection line */}
            {entities.map((ent) => {
              if (ent.is_conflicted && ent.conflict_ghost) {
                return (
                  <svg
                    key={`line-${ent.id}`}
                    className="absolute inset-0 w-full h-full pointer-events-none z-10"
                  >
                    <line
                      x1={`${ent.x * 100}%`}
                      y1={`${ent.y * 100}%`}
                      x2={`${ent.conflict_ghost.x * 100}%`}
                      y2={`${ent.conflict_ghost.y * 100}%`}
                      stroke="#ffb454"
                      strokeWidth="2"
                      strokeDasharray="4 4"
                    />
                  </svg>
                );
              }
              return null;
            })}

            {/* Render Conflict Ghost Markers */}
            {entities.map((ent) => {
              if (ent.is_conflicted && ent.conflict_ghost) {
                return (
                  <div
                    key={`ghost-${ent.id}`}
                    style={{
                      left: `${ent.conflict_ghost.x * 100}%`,
                      top: `${ent.conflict_ghost.y * 100}%`,
                    }}
                    className="absolute -translate-x-1/2 -translate-y-1/2 z-10 px-2 py-1 rounded-lg border border-dashed border-[#ffb454] bg-[#ffb454]/10 text-[#ffb454] text-[10px] font-mono pointer-events-none opacity-75"
                  >
                    Ghost Marker (Witness 2 contested)
                  </div>
                );
              }
              return null;
            })}

            {/* Render Interactive Entity Nodes */}
            {entities.map((ent) => {
              const isSelected = selectedEntityId === ent.id;
              const isUnsure = ent.confidence === 'unsure';

              let IconComponent = User;
              if (ent.kind === 'vehicle') IconComponent = Car;
              else if (ent.kind === 'weapon') IconComponent = ShieldAlert;
              else if (ent.kind === 'landmark') IconComponent = Building;

              return (
                <div
                  key={ent.id}
                  style={{
                    left: `${ent.x * 100}%`,
                    top: `${ent.y * 100}%`,
                  }}
                  onMouseDown={(e) => {
                    setSelectedEntityId(ent.id);
                    handleEntityDrag(ent.id, e);
                  }}
                  className={`absolute -translate-x-1/2 -translate-y-1/2 z-20 cursor-grab active:cursor-grabbing transition-transform ${
                    isSelected ? 'scale-110 z-30' : ''
                  }`}
                >
                  <div
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full backdrop-blur-md transition-all shadow-lg ${
                      isUnsure
                        ? 'border border-dashed border-[rgba(255,255,255,0.4)] opacity-60 bg-[#14161a]/60 text-white'
                        : isSelected
                        ? 'border-2 border-[#5ad1ff] bg-[#14161a] text-white shadow-[#5ad1ff]/20'
                        : 'border border-[rgba(255,255,255,0.12)] bg-[#14161a]/90 text-white/90 hover:border-white/30'
                    }`}
                  >
                    <IconComponent
                      className={`w-3.5 h-3.5 ${
                        isSelected ? 'text-[#5ad1ff]' : ent.is_conflicted ? 'text-[#ffb454]' : 'text-[#7c8cff]'
                      }`}
                    />
                    <span className="text-xs font-medium whitespace-nowrap">{ent.label}</span>
                    <span
                      style={{ transform: `rotate(${ent.heading_deg}deg)` }}
                      className="text-[10px] text-[#A9A9AA] inline-block font-mono"
                    >
                      ↑
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Timeline Animation Scrubber */}
          <div className="p-4 rounded-2xl glass-panel flex items-center gap-4 text-xs">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className="p-2 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.1)] text-white hover:bg-white/10 transition-colors"
              aria-label={isPlaying ? 'Pause timeline playback' : 'Play timeline playback'}
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 text-emerald-400" />}
            </button>
            <button
              onClick={() => setTimelineProgress(0)}
              className="p-2 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.1)] text-[#95979E] hover:text-white transition-colors"
              aria-label="Reset timeline scrubber"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <div className="flex-1 flex flex-col gap-1">
              <div className="flex justify-between text-[10px] text-[#A9A9AA] font-mono">
                <span>T-00:00 (Incident start)</span>
                <span>T+00:{String(Math.floor((timelineProgress / 100) * 45)).padStart(2, '0')}</span>
                <span>T+00:45 (Suspect egress)</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={timelineProgress}
                onChange={(e) => setTimelineProgress(Number(e.target.value))}
                className="w-full accent-[#7c8cff] h-1.5 bg-[#14161a] rounded-lg cursor-pointer"
              />
            </div>
          </div>
        </div>

        {/* Right Sidebar: Narrative Extraction & Entity Properties */}
        <div className="lg:col-span-4 space-y-5">
          {/* Extract from Narrative Panel */}
          <div className="p-5 rounded-2xl glass-panel space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[#7c8cff]" />
                Extract From Narrative
              </span>
              <span className="text-[10px] text-[#5ad1ff] font-mono">LLM spatial</span>
            </div>

            <textarea
              rows={3}
              value={narrativeInput}
              onChange={(e) => setNarrativeInput(e.target.value)}
              className="w-full p-2.5 rounded-xl bg-[#090a0c] border border-[rgba(255,255,255,0.12)] text-xs text-white placeholder-[#95979E] focus:outline-none focus:border-[#7c8cff] resize-none"
              placeholder="Paste or type witness spatial statement..."
            />

            <button
              onClick={handleExtractFromNarrative}
              disabled={isExtracting}
              className="w-full btn-primary-glow py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-2"
            >
              {isExtracting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-[#090a0c] border-t-transparent rounded-full animate-spin" />
                  <span>Parsing Spatial Graph...</span>
                </>
              ) : (
                <>
                  <Navigation className="w-3.5 h-3.5" />
                  <span>Update Scene Layout</span>
                </>
              )}
            </button>

            {extractionError && (
              <div className="mt-3 p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 space-y-2">
                <div className="flex items-center gap-1.5 font-semibold text-amber-300">
                  <WifiOff className="w-3.5 h-3.5 shrink-0" />
                  <span>Parser Offline (:8000)</span>
                </div>
                <p className="text-[11px] text-amber-200/90 leading-relaxed">
                  {extractionError}
                </p>
                <button
                  type="button"
                  onClick={handleAddFixtureEntity}
                  className="w-full py-1.5 px-2.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 text-xs font-semibold flex items-center justify-center gap-1 transition-colors"
                >
                  <span>[DEV FIXTURE] Add Extracted Counter Entity</span>
                </button>
              </div>
            )}
          </div>

          {/* Selected Entity Inspector */}
          {selectedEntity ? (
            <div className="p-5 rounded-2xl glass-panel space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-[rgba(255,255,255,0.08)]">
                <span className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
                  Entity Inspector
                </span>
                <span className="text-[10px] text-[#7c8cff] font-mono">{selectedEntity.id}</span>
              </div>

              <div>
                <label className="text-[10px] text-[#A9A9AA] font-mono uppercase block mb-1">
                  Label
                </label>
                <input
                  type="text"
                  value={selectedEntity.label}
                  onChange={(e) => {
                    const val = e.target.value;
                    setEntities((prev) =>
                      prev.map((item) =>
                        item.id === selectedEntity.id ? { ...item, label: val } : item
                      )
                    );
                  }}
                  className="w-full px-3 py-1.5 rounded-lg bg-[#090a0c] border border-[rgba(255,255,255,0.12)] text-xs text-white focus:outline-none focus:border-[#7c8cff]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-[10px] text-[#A9A9AA] font-mono uppercase block mb-1">
                    Confidence
                  </span>
                  <select
                    value={selectedEntity.confidence}
                    onChange={(e) => {
                      const val = e.target.value as any;
                      setEntities((prev) =>
                        prev.map((item) =>
                          item.id === selectedEntity.id ? { ...item, confidence: val } : item
                        )
                      );
                    }}
                    className="w-full px-2 py-1.5 rounded-lg bg-[#090a0c] border border-[rgba(255,255,255,0.12)] text-xs text-white"
                  >
                    <option value="sure">Sure (Solid)</option>
                    <option value="somewhat">Somewhat</option>
                    <option value="unsure">Unsure (Dashed)</option>
                  </select>
                </div>

                <div>
                  <span className="text-[10px] text-[#A9A9AA] font-mono uppercase block mb-1">
                    Heading
                  </span>
                  <div className="flex items-center gap-2">
                    <input
                      type="range"
                      min="0"
                      max="360"
                      value={selectedEntity.heading_deg}
                      onChange={(e) => {
                        const val = Number(e.target.value);
                        setEntities((prev) =>
                          prev.map((item) =>
                            item.id === selectedEntity.id ? { ...item, heading_deg: val } : item
                          )
                        );
                      }}
                      className="w-full accent-[#7c8cff]"
                    />
                    <span className="text-[11px] font-mono text-white w-8">
                      {selectedEntity.heading_deg}°
                    </span>
                  </div>
                </div>
              </div>

              {selectedEntity.is_conflicted && (
                <div className="p-3 rounded-xl bg-[#ffb454]/10 border border-[#ffb454]/30 text-xs text-[#ffb454]">
                  <span className="font-semibold block mb-0.5">Contested Position Detected</span>
                  <p className="text-[10px] text-[#ffb454]/80 leading-relaxed">
                    Witness W-002 placed this vehicle 12 meters further east. Both versions are
                    preserved in the audit trail.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="p-5 rounded-2xl glass-panel text-center text-xs text-[#95979E]">
              Click any entity on the canvas to inspect coordinates and confidence.
            </div>
          )}

          {/* Assistant Companion Preview */}
          <div className="p-4 rounded-2xl bg-[#14161a] border border-[rgba(255,255,255,0.06)] flex items-center gap-3">
            <Vela state={isExtracting ? 'sketching' : 'idle'} size="companion" />
            <div className="text-xs">
              <span className="text-white font-medium block">Vela Spatial Guide</span>
              <p className="text-[11px] text-[#95979E]">
                Drag entities to refine positions. Contested placements are highlighted with dashed
                bridges.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
