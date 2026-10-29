import React, { useState } from 'react';
import { Vela, type VelaState } from '../components/Vela';
import { Sparkles, ArrowLeft } from 'lucide-react';

interface VelaLabPageProps {
  onBackToApp?: () => void;
}

const ALL_STATES: Array<{
  state: VelaState;
  label: string;
  trigger: string;
  defaultSpeech: string;
}> = [
  {
    state: 'idle',
    label: 'Idle',
    trigger: 'No requests pending, normal standby',
    defaultSpeech: 'Standing by for witness description.',
  },
  {
    state: 'listening',
    label: 'Listening',
    trigger: 'Microphone recording active',
    defaultSpeech: 'Listening... (Microphone active)',
  },
  {
    state: 'thinking',
    label: 'Thinking',
    trigger: 'Statement parsing or ASR request in flight',
    defaultSpeech: 'Analyzing statement with Ollama / Qwen...',
  },
  {
    state: 'sketching',
    label: 'Sketching',
    trigger: 'Round generation in flight (LCM SD-1.5)',
    defaultSpeech: 'Generating 6 facial variants...',
  },
  {
    state: 'curious',
    label: 'Curious',
    trigger: 'Next targeted question available',
    defaultSpeech: 'Did you notice any facial hair or scars?',
  },
  {
    state: 'shield',
    label: 'Shield',
    trigger: 'Case data_mode is "real" (Local-only, teal mode)',
    defaultSpeech: 'Local-only privacy active. Real case never leaves the building.',
  },
  {
    state: 'proud',
    label: 'Proud',
    trigger: 'Finalize complete or audit verified',
    defaultSpeech: 'Composite sealed and cryptographically verified!',
  },
  {
    state: 'wince',
    label: 'Wince',
    trigger: 'Service unavailable error (ML_UNAVAILABLE / SPEECH_UNAVAILABLE)',
    defaultSpeech: 'Local model is offline — start Ollama. Cloud fallback forbidden.',
  },
  {
    state: 'alarm',
    label: 'Alarm',
    trigger: 'Audit chain tamper detected / verify invalid',
    defaultSpeech: 'Tamper alert! Block sequence mismatch detected.',
  },
  {
    state: 'sleepy',
    label: 'Sleepy',
    trigger: 'Idle timeout > 90 seconds',
    defaultSpeech: 'Zzz... Tap any key to resume.',
  },
];

export const VelaLabPage: React.FC<VelaLabPageProps> = ({ onBackToApp }) => {
  const [activeState, setActiveState] = useState<VelaState>('idle');
  const [size, setSize] = useState<'hero' | 'companion' | 'mini'>('hero');
  const [customSpeech, setCustomSpeech] = useState<string>(
    'Standing by for witness description.'
  );

  const handleSelectState = (s: typeof ALL_STATES[0]) => {
    setActiveState(s.state);
    setCustomSpeech(s.defaultSpeech);
  };

  return (
    <div className="min-h-screen bg-[#090a0c] text-[#f4f5f7] p-6 max-w-6xl mx-auto space-y-8 select-none">
      {/* Top Header */}
      <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full bg-[#7c8cff]/10 text-[#7c8cff] text-[10px] font-mono font-semibold uppercase">
              TCD8 Dev-Only Verification
            </span>
            <span className="text-xs text-[#95979E]">Vela Laboratory v1.0</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Vela State Machine & SVG Character Lab
          </h1>
        </div>

        {onBackToApp && (
          <button
            onClick={onBackToApp}
            className="px-4 py-2 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-xs text-white hover:bg-white/5 flex items-center gap-2 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Velora</span>
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Stage Preview */}
        <div className="lg:col-span-7 flex flex-col items-center space-y-6">
          <div className="w-full h-[420px] rounded-3xl bg-[#0e0f12] border border-[rgba(255,255,255,0.12)] flex flex-col items-center justify-center p-8 relative shadow-2xl overflow-hidden">
            {/* Ambient subtle backglow */}
            <div
              className={`absolute w-64 h-64 rounded-full blur-[80px] pointer-events-none transition-all duration-700 ${
                activeState === 'alarm'
                  ? 'bg-red-500/20'
                  : activeState === 'shield'
                  ? 'bg-emerald-500/20'
                  : activeState === 'proud'
                  ? 'bg-[#5ad1ff]/20'
                  : 'bg-[#7c8cff]/15'
              }`}
            />

            <Vela state={activeState} size={size} speechBubble={customSpeech} />

            {/* Stage Footer Status */}
            <div className="absolute bottom-4 inset-x-6 flex items-center justify-between text-xs text-[#95979E] font-mono border-t border-[rgba(255,255,255,0.06)] pt-3">
              <span>State: <span className="text-white font-bold">{activeState}</span></span>
              <span>Size: <span className="text-white font-bold">{size}</span></span>
            </div>
          </div>

          {/* Size controls & Custom Speech Input */}
          <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-2xl glass-panel space-y-2">
              <label className="text-xs font-semibold text-white block">Scale Preset</label>
              <div className="flex gap-2">
                {(['hero', 'companion', 'mini'] as const).map((sz) => (
                  <button
                    key={sz}
                    onClick={() => setSize(sz)}
                    className={`flex-1 py-2 rounded-xl text-xs font-mono uppercase transition-colors ${
                      size === sz
                        ? 'bg-[#7c8cff] text-[#090a0c] font-bold'
                        : 'bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[#A9A9AA]'
                    }`}
                  >
                    {sz}
                  </button>
                ))}
              </div>
            </div>

            <div className="p-4 rounded-2xl glass-panel space-y-2">
              <label className="text-xs font-semibold text-white block">Speech Bubble Text</label>
              <input
                type="text"
                value={customSpeech}
                onChange={(e) => setCustomSpeech(e.target.value)}
                className="w-full px-3 py-1.5 rounded-xl bg-[#090a0c] border border-[rgba(255,255,255,0.12)] text-xs text-white focus:outline-none focus:border-[#7c8cff]"
              />
            </div>
          </div>
        </div>

        {/* Right Column: 10 State Selector Grid */}
        <div className="lg:col-span-5 space-y-4">
          <div className="p-5 rounded-2xl glass-panel space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#7c8cff]" />
              Triggerable States (All 10 Handled)
            </h3>
            <p className="text-xs text-[#95979E]">
              Click any state to preview the live SVG reaction and speech bubble behavior.
            </p>

            <div className="space-y-2 pt-2">
              {ALL_STATES.map((s) => {
                const isSelected = activeState === s.state;
                return (
                  <button
                    key={s.state}
                    onClick={() => handleSelectState(s)}
                    className={`w-full p-3 rounded-xl border text-left transition-all ${
                      isSelected
                        ? 'bg-[#7c8cff]/15 border-[#7c8cff] text-white shadow-md'
                        : 'bg-[#14161a] border-[rgba(255,255,255,0.06)] text-[#A9A9AA] hover:border-white/20'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-xs text-white capitalize">{s.label}</span>
                      <span className="text-[10px] font-mono text-[#5ad1ff]">{s.state}</span>
                    </div>
                    <div className="text-[11px] text-[#95979E]">{s.trigger}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
