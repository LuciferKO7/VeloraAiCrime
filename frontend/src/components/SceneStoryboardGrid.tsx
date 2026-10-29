import React, { useState } from 'react';
import { DEMO_STORYBOARD_PANELS } from '../store/demoData';
import { Camera, Clock, AlertTriangle, Layers, Maximize2 } from 'lucide-react';
import { MANDATORY_DISCLAIMER } from '../pages/LandingPage';

/**
 * SceneStoryboardGrid
 *
 * 9-Panel Forensic Scene Reconstruction Storyboard.
 * Follows the 9-panel vehicle incident composition specified in requirements:
 * 1. Establishing storefront view
 * 2. Vehicle approach
 * 3. Sedan lateral profile
 * 4. Vehicle passing witnesses
 * 5. Witnesses stationary observation
 * 6. Vehicle detail: rear quarter
 * 7. Vehicle detail: front quarter
 * 8. Vehicle departure
 * 9. Return to scene tranquility with reconstructed vectors
 *
 * Clearly labeled as FICTIONAL SCENE RECONSTRUCTION — NOT CCTV FOOTAGE.
 */
export const SceneStoryboardGrid: React.FC = () => {
  const [activePanelIdx, setActivePanelIdx] = useState<number | null>(null);

  return (
    <div className="space-y-6">
      {/* Top Banner Notice */}
      <div className="p-4 rounded-2xl bg-[#14161a] border border-[rgba(255,255,255,0.1)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#5ad1ff]/10 border border-[#5ad1ff]/30 flex items-center justify-center text-[#5ad1ff]">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40">
                FICTIONAL SCENE RECONSTRUCTION
              </span>
              <span className="text-xs font-mono text-[#95979E]">CASE: DEMO-2026-041</span>
            </div>
            <h3 className="text-sm font-bold text-white mt-0.5">
              9-Panel Sequential Vehicle Trajectory Storyboard
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-mono text-[#ffb454] bg-[#5A250A]/40 border border-[#FF8964]/40 px-3 py-1.5 rounded-xl">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-[#FF8964]" />
          <span>SIMULATED NARRATIVE RECONSTRUCTION — NOT SURVEILLANCE / CCTV</span>
        </div>
      </div>

      {/* 9-Panel Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {DEMO_STORYBOARD_PANELS.map((panel, idx) => {
          const isSelected = activePanelIdx === idx;

          return (
            <div
              key={panel.step}
              onClick={() => setActivePanelIdx(isSelected ? null : idx)}
              className={`group rounded-2xl overflow-hidden glass-panel border transition-all duration-200 cursor-pointer flex flex-col justify-between ${
                isSelected
                  ? 'border-[#5ad1ff] ring-1 ring-[#5ad1ff]/50 shadow-[0_0_25px_rgba(90,209,255,0.2)]'
                  : 'border-[rgba(255,255,255,0.08)] hover:border-[rgba(255,255,255,0.2)] hover:bg-[#14161a]'
              }`}
            >
              {/* Panel Graphical Vector Canvas */}
              <div className="relative aspect-[16/10] bg-[#07080a] border-b border-[rgba(255,255,255,0.06)] overflow-hidden flex items-center justify-center">
                {/* Panel Scene Illustration SVG */}
                <svg viewBox="0 0 320 200" className="w-full h-full">
                  {/* Subtle Grid Blueprint Ground */}
                  <line x1="0" y1="140" x2="320" y2="140" stroke="#2a2e36" strokeWidth="1.5" />
                  <line x1="0" y1="175" x2="320" y2="175" stroke="#1f232b" strokeWidth="1" strokeDasharray="6 4" />

                  {/* Storefront Architecture (Consistent across all panels) */}
                  <rect x="25" y="45" width="110" height="95" fill="#14171d" stroke="#3b4252" strokeWidth="1.5" />
                  <rect x="40" y="65" width="40" height="50" fill="#1b2029" stroke="#4c566a" strokeWidth="1" />
                  <rect x="90" y="75" width="35" height="65" fill="#101318" stroke="#4c566a" strokeWidth="1" />
                  <text x="45" y="58" fill="#5ad1ff" fontSize="7" fontFamily="monospace">STOREFRONT</text>

                  {/* Sidewalk Curb */}
                  <rect x="0" y="138" width="320" height="6" fill="#1a1c22" stroke="#2e3440" strokeWidth="0.5" />

                  {/* Specific Panel Content by Step */}
                  {panel.step === 1 && (
                    /* Establishing View: Clean street, static witnesses at door */
                    <g>
                      <circle cx="55" cy="132" r="4" fill="#7c8cff" />
                      <text x="50" y="124" fill="#a9b1d6" fontSize="6" fontFamily="monospace">W-1</text>
                      <circle cx="108" cy="134" r="4" fill="#7c8cff" />
                      <text x="103" y="126" fill="#a9b1d6" fontSize="6" fontFamily="monospace">W-3</text>
                      <circle cx="45" cy="158" r="4" fill="#7c8cff" />
                      <text x="40" y="152" fill="#a9b1d6" fontSize="6" fontFamily="monospace">W-2</text>
                      <text x="180" y="160" fill="#4c566a" fontSize="8" fontFamily="monospace">EASTBOUND ROADWAY</text>
                    </g>
                  )}

                  {panel.step === 2 && (
                    /* Vehicle Approach: Sedan entering from left */
                    <g>
                      <circle cx="55" cy="132" r="4" fill="#7c8cff" />
                      <circle cx="108" cy="134" r="4" fill="#7c8cff" />
                      {/* Approaching Dark Sedan */}
                      <path d="M 0 162 L 65 162 L 60 152 L 40 150 L 25 152 L 0 155 Z" fill="#2e3440" stroke="#5ad1ff" strokeWidth="1.2" />
                      <line x1="65" y1="162" x2="90" y2="162" stroke="#ffb454" strokeWidth="1.5" strokeDasharray="3 3" />
                      <text x="80" y="150" fill="#ffb454" fontSize="6" fontFamily="monospace">DECEL (~20 km/h)</text>
                    </g>
                  )}

                  {panel.step === 3 && (
                    /* Sedan Lateral Profile: Detailed side view at curb */
                    <g>
                      {/* Four-door Sedan Side Elevation */}
                      <path d="M 120 162 L 235 162 L 230 148 L 195 146 L 165 146 L 140 150 L 120 154 Z" fill="#1b2029" stroke="#7c8cff" strokeWidth="1.6" />
                      {/* Windows & Pillars */}
                      <path d="M 148 150 L 165 148 L 165 156 L 144 156 Z" fill="#0d1117" stroke="#4c566a" strokeWidth="0.8" />
                      <path d="M 170 148 L 192 148 L 198 156 L 170 156 Z" fill="#0d1117" stroke="#4c566a" strokeWidth="0.8" />
                      {/* Wheels */}
                      <circle cx="145" cy="164" r="7" fill="#090a0c" stroke="#4c566a" strokeWidth="1.2" />
                      <circle cx="210" cy="164" r="7" fill="#090a0c" stroke="#4c566a" strokeWidth="1.2" />
                      <text x="135" y="138" fill="#7c8cff" fontSize="7" fontFamily="monospace">DARK 4-DOOR SEDAN</text>
                    </g>
                  )}

                  {panel.step === 4 && (
                    /* Vehicle Passing Witnesses */
                    <g>
                      <circle cx="55" cy="132" r="4" fill="#7c8cff" />
                      <circle cx="108" cy="134" r="4" fill="#7c8cff" />
                      {/* Lines of Sight */}
                      <line x1="55" y1="132" x2="160" y2="160" stroke="#7c8cff" strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />
                      <line x1="108" y1="134" x2="160" y2="160" stroke="#7c8cff" strokeWidth="1" strokeDasharray="2 2" opacity="0.6" />
                      {/* Sedan passing */}
                      <rect x="135" y="152" width="70" height="15" rx="3" fill="#242933" stroke="#5ad1ff" strokeWidth="1.2" />
                      <text x="140" y="146" fill="#5ad1ff" fontSize="6" fontFamily="monospace">OBSERVED TRAVERSAL</text>
                    </g>
                  )}

                  {panel.step === 5 && (
                    /* Witnesses Stationary Vantage */
                    <g>
                      <rect x="35" y="115" width="95" height="30" fill="#14171f" stroke="#ffb454" strokeWidth="1" strokeDasharray="3 3" />
                      <circle cx="55" cy="130" r="5" fill="#7c8cff" stroke="#fff" strokeWidth="1" />
                      <circle cx="85" cy="130" r="5" fill="#7c8cff" stroke="#fff" strokeWidth="1" />
                      <circle cx="115" cy="130" r="5" fill="#7c8cff" stroke="#fff" strokeWidth="1" />
                      <text x="42" y="108" fill="#ffb454" fontSize="6.5" fontFamily="monospace">STATIONARY OBSERVERS (W1, W2, W3)</text>
                    </g>
                  )}

                  {panel.step === 6 && (
                    /* Close-up: Rear Quarter & C-Pillar Detail */
                    <g>
                      <path d="M 80 165 L 240 165 L 210 110 L 140 110 Z" fill="#191d24" stroke="#7c8cff" strokeWidth="1.8" />
                      <path d="M 145 115 L 202 115 L 180 145 L 145 145 Z" fill="#0d1017" stroke="#3b4252" strokeWidth="1" />
                      <rect x="225" y="130" width="12" height="6" fill="#e78284" opacity="0.8" />
                      <circle cx="130" cy="165" r="14" fill="#090a0c" stroke="#4c566a" strokeWidth="2" />
                      <text x="90" y="98" fill="#a9b1d6" fontSize="7" fontFamily="monospace">DETAIL A: C-PILLAR & TAILLIGHT PROFILE</text>
                    </g>
                  )}

                  {panel.step === 7 && (
                    /* Close-up: Front Quarter & Wheel Arch */
                    <g>
                      <path d="M 60 165 L 230 165 L 225 135 L 140 135 L 90 148 L 60 155 Z" fill="#191d24" stroke="#5ad1ff" strokeWidth="1.8" />
                      <circle cx="115" cy="165" r="16" fill="#090a0c" stroke="#5ad1ff" strokeWidth="1.5" />
                      <circle cx="115" cy="165" r="8" fill="#1f232a" stroke="#4c566a" strokeWidth="1" />
                      <text x="80" y="115" fill="#5ad1ff" fontSize="7" fontFamily="monospace">DETAIL B: FRONT FENDER & HOOD CONTOUR</text>
                    </g>
                  )}

                  {panel.step === 8 && (
                    /* Vehicle Departure Eastbound */
                    <g>
                      {/* Accelerating Sedan exiting right */}
                      <path d="M 230 160 L 315 160 L 310 148 L 285 146 L 260 146 L 245 150 Z" fill="#242933" stroke="#ffb454" strokeWidth="1.4" />
                      <line x1="200" y1="160" x2="225" y2="160" stroke="#ffb454" strokeWidth="2" />
                      <line x1="180" y1="160" x2="195" y2="160" stroke="#ffb454" strokeWidth="1.5" />
                      <text x="210" y="140" fill="#ffb454" fontSize="6.5" fontFamily="monospace">ACCEL EASTBOUND &gt;&gt;</text>
                    </g>
                  )}

                  {panel.step === 9 && (
                    /* Return to Scene Tranquility with Overlay Vectors */
                    <g>
                      {/* Trajectory vector arrow from west to east */}
                      <line x1="20" y1="162" x2="295" y2="162" stroke="#2fd4a4" strokeWidth="2" strokeDasharray="4 2" />
                      <polygon points="300,162 290,158 290,166" fill="#2fd4a4" />
                      {/* Stationary witness markers */}
                      <circle cx="55" cy="132" r="4" fill="#7c8cff" />
                      <circle cx="108" cy="134" r="4" fill="#7c8cff" />
                      <circle cx="45" cy="158" r="4" fill="#7c8cff" />
                      <text x="65" y="182" fill="#2fd4a4" fontSize="6.5" fontFamily="monospace">RECONSTRUCTED EASTBOUND TRAJECTORY ARROW</text>
                    </g>
                  )}
                </svg>

                {/* Panel Step Number Badge */}
                <span className="absolute top-2.5 left-2.5 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-md text-[10px] font-mono font-bold text-white border border-white/10">
                  {panel.step}/9
                </span>

                {/* Time Indicator */}
                <span className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-md bg-black/70 backdrop-blur-md text-[9px] font-mono text-[#5ad1ff] flex items-center gap-1 border border-white/10">
                  <Clock className="w-2.5 h-2.5" />
                  <span>{panel.timeLabel}</span>
                </span>
              </div>

              {/* Panel Description Card */}
              <div className="p-3.5 space-y-2 flex-1 flex flex-col justify-between">
                <div>
                  <h4 className="text-xs font-bold text-white group-hover:text-[#5ad1ff] transition-colors">
                    {panel.title}
                  </h4>
                  <p className="text-[11px] text-[#A9A9AA] mt-1 leading-snug">
                    {panel.description}
                  </p>
                </div>

                <div className="pt-2 border-t border-[rgba(255,255,255,0.06)] flex items-center justify-between text-[10px] text-[#95979E] font-mono">
                  <span className="flex items-center gap-1">
                    <Camera className="w-3 h-3 text-[#5ad1ff]" />
                    <span className="truncate max-w-[130px]">{panel.camera}</span>
                  </span>
                  <span className="text-[#5ad1ff] group-hover:underline flex items-center gap-0.5">
                    <span>Inspect</span>
                    <Maximize2 className="w-2.5 h-2.5" />
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Statutory Footer Disclaimer */}
      <div className="p-3 rounded-xl bg-[#5A250A]/40 border border-[#FF8964]/40 text-center text-[10px] font-mono text-[#FFC1AD]">
        {MANDATORY_DISCLAIMER} — RECONSTRUCTED FICTIONAL STORYBOARD ONLY
      </div>
    </div>
  );
};
