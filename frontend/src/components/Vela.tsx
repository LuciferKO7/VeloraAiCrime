import React from 'react';

export type VelaState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'sketching'
  | 'curious'
  | 'shield'
  | 'proud'
  | 'wince'
  | 'alarm'
  | 'sleepy';

export type VelaSize = 'hero' | 'companion' | 'mini';

interface VelaProps {
  state?: VelaState;
  size?: VelaSize;
  speechText?: string;
  speechBubble?: string;
  subText?: string;
  className?: string;
}

/**
 * Vela
 *
 * Original code-drawn SVG companion character per FRONTEND_DESIGN.md §5.
 * A luminous sketching spirit with a rounded orb body, expressive eyes,
 * a pencil-tip tail, and an ambient aura driven by real system events.
 */
export const Vela: React.FC<VelaProps> = ({
  state = 'idle',
  size = 'companion',
  speechText,
  speechBubble,
  subText,
  className = '',
}) => {
  const activeSpeech = speechText || speechBubble;
  // Dimensions per spec
  const pixelSize = size === 'hero' ? 220 : size === 'companion' ? 64 : 24;

  // State-driven color / aura
  const isTeal = state === 'shield';
  const isAlarm = state === 'alarm';
  const isWince = state === 'wince';

  const auraColor = isAlarm
    ? '#ff6b6b'
    : isWince
    ? '#ffb454'
    : isTeal
    ? '#2fd4a4'
    : 'var(--a1)';

  return (
    <div
      className={`relative inline-flex flex-col items-center select-none ${className}`}
      data-testid="vela-character"
      data-state={state}
    >
      {/* Speech Bubble (when text provided) */}
      {activeSpeech && size !== 'mini' && (
        <div className="mb-3 max-w-[280px] p-3 rounded-2xl glass-panel text-left text-xs text-[#f4f5f7] shadow-xl animate-hero-eyebrow relative z-20">
          <p className="font-medium leading-snug">{activeSpeech}</p>
          {subText && <p className="text-[10px] text-[#A9A9AA] mt-1">{subText}</p>}
          <div className="absolute -bottom-1.5 left-6 w-3 h-3 bg-[#14161a] border-r border-b border-[rgba(255,255,255,0.08)] transform rotate-45" />
        </div>
      )}

      {/* Code-Drawn SVG Character */}
      <div
        className="relative flex items-center justify-center"
        style={{
          width: pixelSize,
          height: pixelSize,
          filter: `drop-shadow(0 0 ${pixelSize * 0.15}px ${auraColor})`,
        }}
      >
        <svg
          viewBox="0 0 100 100"
          className="w-full h-full overflow-visible"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* Luminous Body Gradient */}
            <linearGradient id="velaBodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
              <stop offset="60%" stopColor={auraColor} stopOpacity="0.9" />
              <stop offset="100%" stopColor="var(--a2)" stopOpacity="0.85" />
            </linearGradient>

            {/* Shield Aura Gradient */}
            <linearGradient id="shieldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#2fd4a4" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#5ad1ff" stopOpacity="0.3" />
            </linearGradient>
          </defs>

          {/* 1. Tail Pencil Tip */}
          <path
            d="M 68,68 Q 82,78 88,90 Q 78,82 66,74 Z"
            fill="url(#velaBodyGrad)"
            opacity="0.9"
          />
          <polygon points="88,90 92,94 85,92" fill="#FF8964" />

          {/* 2. Main Orb Body */}
          <circle
            cx="50"
            cy="50"
            r="32"
            fill="url(#velaBodyGrad)"
            className={
              state === 'thinking'
                ? 'animate-pulse'
                : state === 'listening'
                ? 'scale-105'
                : ''
            }
          />

          {/* 3. Orbiting Thinking Dots */}
          {state === 'thinking' && (
            <g className="animate-spin" style={{ transformOrigin: '50px 50px' }}>
              <circle cx="50" cy="12" r="3" fill="#5ad1ff" />
              <circle cx="88" cy="50" r="2.5" fill="#FF8964" />
              <circle cx="50" cy="88" r="2.5" fill="#7be0c3" />
            </g>
          )}

          {/* 4. Listening Sound Wave Ring */}
          {state === 'listening' && (
            <circle
              cx="50"
              cy="50"
              r="40"
              fill="none"
              stroke="var(--a1)"
              strokeWidth="2"
              strokeDasharray="4 4"
              className="animate-spin"
              style={{ transformOrigin: '50px 50px' }}
            />
          )}

          {/* 5. Translucent Protective Shield for Local Mode */}
          {state === 'shield' && (
            <path
              d="M 30,30 L 70,30 Q 75,55 50,75 Q 25,55 30,30 Z"
              fill="url(#shieldGrad)"
              stroke="#2fd4a4"
              strokeWidth="1.5"
              opacity="0.85"
            />
          )}

          {/* 6. Expressive Eyes */}
          {state === 'wince' ? (
            /* Squinting Eyes */
            <g stroke="#090a0c" strokeWidth="3" strokeLinecap="round">
              <line x1="38" y1="46" x2="46" y2="48" />
              <line x1="46" y1="48" x2="38" y2="50" />
              <line x1="62" y1="46" x2="54" y2="48" />
              <line x1="54" y1="48" x2="62" y2="50" />
            </g>
          ) : state === 'sleepy' ? (
            /* Half-closed Sleeping Eyes */
            <g stroke="#090a0c" strokeWidth="2.5" strokeLinecap="round" fill="none">
              <path d="M 38,48 Q 42,53 46,48" />
              <path d="M 54,48 Q 58,53 62,48" />
            </g>
          ) : state === 'alarm' ? (
            /* Wide Alert Eyes */
            <g fill="#090a0c">
              <circle cx="42" cy="46" r="5" />
              <circle cx="58" cy="46" r="5" />
              <circle cx="43" cy="45" r="1.5" fill="#ffffff" />
              <circle cx="59" cy="45" r="1.5" fill="#ffffff" />
            </g>
          ) : (
            /* Normal Calm Expressive Eyes */
            <g fill="#090a0c">
              <ellipse cx="43" cy="47" rx="3.5" ry="4.5" />
              <ellipse cx="57" cy="47" rx="3.5" ry="4.5" />
              <circle cx="44" cy="45" r="1.5" fill="#ffffff" />
              <circle cx="58" cy="45" r="1.5" fill="#ffffff" />
            </g>
          )}

          {/* 7. Subtle Facial Blush / Smile */}
          {state === 'proud' && (
            <path
              d="M 44,56 Q 50,61 56,56"
              fill="none"
              stroke="#090a0c"
              strokeWidth="2"
              strokeLinecap="round"
            />
          )}
        </svg>
      </div>

      {/* Local Shield Badge Tag */}
      {state === 'shield' && size !== 'mini' && (
        <span className="mt-1 px-2 py-0.5 rounded-full text-[9px] font-mono font-medium bg-[#2fd4a4]/20 text-[#2fd4a4] border border-[#2fd4a4]/40">
          LOCAL-ONLY
        </span>
      )}
    </div>
  );
};

export default Vela;
