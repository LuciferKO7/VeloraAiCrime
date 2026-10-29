import React from 'react';

interface ForensicGraphiteSketchProps {
  view?: 'frontal' | 'profile' | 'three-quarter';
  hasBeard?: boolean;
  hasCap?: boolean;
  isMature?: boolean;
  jawStyle?: 'sharp' | 'rounded';
  className?: string;
  showMetadata?: boolean;
  scale?: number;
}

/**
 * ForensicGraphiteSketch
 *
 * Traditional forensic-artist graphite drawing component.
 * Delivers natural anatomical proportions, subtle facial asymmetry,
 * pencil cross-hatching, graphite grain, and documentary scanned sheet presentation.
 * STRICT R11 Invariant: Always includes mandatory statutory disclaimer.
 */
export const ForensicGraphiteSketch: React.FC<ForensicGraphiteSketchProps> = ({
  view = 'frontal',
  hasBeard = false,
  hasCap = false,
  isMature = false,
  jawStyle = 'sharp',
  className = '',
  showMetadata = true,
}) => {
  return (
    <div
      className={`relative rounded-xl overflow-hidden border border-[#d2cbbe] shadow-inner select-none ${className}`}
      style={{
        backgroundColor: '#f5f0e6',
        backgroundImage: 'radial-gradient(#e5dfd3 1px, transparent 1px)',
        backgroundSize: '12px 12px',
      }}
    >
      {/* Scanned Paper Texture Overlay */}
      <div className="absolute inset-0 pointer-events-none opacity-40 mix-blend-multiply bg-gradient-to-b from-[#e8e1d3] via-transparent to-[#ded6c5]" />

      {/* Scanned Forensic Composite Sheet Top Header */}
      {showMetadata && (
        <div className="px-3 pt-2 pb-1 border-b border-[#d8d0c2] flex items-center justify-between text-[9px] font-mono text-[#5a5448]">
          <span className="font-bold tracking-wider">VELORA FORENSIC RECONSTRUCTION</span>
          <span className="bg-[#e4ddce] px-1.5 py-0.5 rounded">CASE: DEMO-2026-041</span>
        </div>
      )}

      {/* Main Graphite Drawing SVG */}
      <div className="p-3 flex items-center justify-center">
        {view === 'profile' ? (
          /* Profile Lateral Graphite Drawing */
          <svg viewBox="0 0 200 240" className="w-full h-full max-h-[300px]">
            <defs>
              <filter id="pencil-profile" x="-10%" y="-10%" width="120%" height="120%">
                <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="4" result="noise" />
                <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.5" />
              </filter>
            </defs>

            <g filter="url(#pencil-profile)" stroke="#2a2723" fill="none">
              {/* Paper Grid Aligners */}
              <line x1="30" y1="20" x2="30" y2="220" stroke="#d5cebf" strokeWidth="0.5" strokeDasharray="2 4" />
              <line x1="170" y1="20" x2="170" y2="220" stroke="#d5cebf" strokeWidth="0.5" strokeDasharray="2 4" />
              <line x1="20" y1="120" x2="180" y2="120" stroke="#d5cebf" strokeWidth="0.5" strokeDasharray="2 4" />

              {/* Head Silhouette Contour (Profile) */}
              <path
                d="M 120 30 C 95 30 75 45 70 70 C 65 78 60 85 58 92 L 52 108 L 46 114 L 56 122 L 50 134 C 48 138 52 144 56 144 L 52 152 C 54 165 65 174 80 180 L 105 186 C 110 196 115 210 125 220"
                strokeWidth="2.2"
                strokeLinecap="round"
              />

              {/* Forehead & Cranium Hatching */}
              <path d="M 85 45 Q 115 48 130 65" strokeWidth="0.8" opacity="0.6" />
              <path d="M 82 52 Q 112 55 128 72" strokeWidth="0.8" opacity="0.6" />
              <path d="M 80 60 Q 110 63 125 80" strokeWidth="0.8" opacity="0.5" />

              {/* Eye Socket & Brow (Profile) */}
              <path d="M 60 92 Q 68 90 74 94" strokeWidth="2.5" strokeLinecap="round" />
              <ellipse cx="66" cy="98" rx="5" ry="3.5" strokeWidth="1.2" fill="#3a3630" />
              <path d="M 64 96 L 70 100" strokeWidth="1" />

              {/* Nose Bridge & Nostril Detail */}
              <path d="M 52 108 L 46 114 L 56 120" strokeWidth="1.8" />
              <ellipse cx="58" cy="120" rx="3" ry="2" strokeWidth="1" fill="#443f38" opacity="0.8" />

              {/* Lips & Philtrum Profile */}
              <path d="M 50 132 Q 56 134 50 136" strokeWidth="1.8" />
              <path d="M 52 140 Q 58 142 54 146" strokeWidth="1.5" />

              {/* Chin & Jawline Contour */}
              {jawStyle === 'sharp' ? (
                <path d="M 54 150 L 52 158 L 68 170 L 98 166 L 120 148" strokeWidth="2.2" />
              ) : (
                <path d="M 54 150 Q 56 164 74 168 Q 98 168 118 148" strokeWidth="2.2" />
              )}

              {/* Ear Morphology (Profile) */}
              <path d="M 115 105 C 112 95 125 90 128 100 C 132 110 130 125 125 132 C 122 136 116 134 116 128 C 116 120 122 115 122 108" strokeWidth="1.8" />
              <path d="M 120 106 Q 124 112 120 118" strokeWidth="1" opacity="0.7" />

              {/* Hair Texture (Short Cropped vs Cap) */}
              {hasCap ? (
                <g>
                  <path d="M 40 85 C 38 78 70 60 135 62 L 145 74 L 130 78 C 80 78 50 88 40 85 Z" fill="#2d2924" strokeWidth="2" />
                  <path d="M 28 88 L 48 83" strokeWidth="3" strokeLinecap="round" />
                </g>
              ) : (
                <g strokeWidth="1.2" opacity="0.85">
                  <path d="M 70 70 C 75 55 90 38 120 36 C 145 36 155 55 152 80 C 150 95 142 115 138 125" strokeWidth="2" />
                  <path d="M 78 62 L 85 52 M 88 56 L 96 46 M 98 50 L 108 40 M 110 48 L 122 38" />
                  <path d="M 125 46 L 136 40 M 135 55 L 146 50 M 140 68 L 148 65" />
                </g>
              )}

              {/* Speculative Beard Shading */}
              {hasBeard && (
                <g stroke="#26231f" strokeWidth="0.8" opacity="0.85">
                  <path d="M 52 148 Q 56 166 75 174 L 98 170 L 115 150" strokeWidth="2" />
                  <path d="M 56 152 L 62 160 M 60 156 L 68 164 M 68 160 L 76 168 M 78 164 L 88 168" />
                  <path d="M 85 165 L 94 167 M 95 163 L 105 160 M 105 155 L 112 148" />
                </g>
              )}

              {/* Mature Ageing Hatching */}
              {isMature && (
                <g strokeWidth="0.7" opacity="0.6">
                  <path d="M 58 125 Q 64 135 62 145" />
                  <path d="M 70 102 Q 74 108 72 114" />
                  <path d="M 80 62 Q 95 64 110 65" />
                </g>
              )}
            </g>
          </svg>
        ) : (
          /* Frontal / Three-Quarter Graphite Drawing */
          <svg viewBox="0 0 200 240" className="w-full h-full max-h-[300px]">
            <defs>
              <filter id="pencil-frontal" x="-10%" y="-10%" width="120%" height="120%">
                <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="4" result="noise" />
                <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.4" />
              </filter>
            </defs>

            <g filter="url(#pencil-frontal)" stroke="#282521" fill="none">
              {/* Proportional Forensic Grid Lines */}
              <line x1="100" y1="20" x2="100" y2="225" stroke="#d5cebf" strokeWidth="0.6" strokeDasharray="3 4" />
              <line x1="30" y1="105" x2="170" y2="105" stroke="#d5cebf" strokeWidth="0.6" strokeDasharray="3 4" />
              <line x1="45" y1="140" x2="155" y2="140" stroke="#d5cebf" strokeWidth="0.5" strokeDasharray="2 4" />
              <line x1="55" y1="170" x2="145" y2="170" stroke="#d5cebf" strokeWidth="0.5" strokeDasharray="2 4" />

              {/* Head Contour Outline */}
              {jawStyle === 'sharp' ? (
                <path
                  d="M 52 75 C 50 115 52 145 68 178 L 100 200 L 132 178 C 148 145 150 115 148 75 C 145 42 125 32 100 32 C 75 32 55 42 52 75 Z"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                />
              ) : (
                <path
                  d="M 54 75 C 52 115 56 148 74 176 Q 100 198 126 176 C 144 148 148 115 146 75 C 143 42 125 32 100 32 C 75 32 57 42 54 75 Z"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                />
              )}

              {/* Thick Dark Arched Eyebrows (Both Eyewitnesses Corroborated) */}
              <path
                d="M 64 96 Q 78 90 92 95"
                strokeWidth="3.2"
                strokeLinecap="round"
                stroke="#221f1b"
              />
              <path
                d="M 108 95 Q 122 90 136 96"
                strokeWidth="3.2"
                strokeLinecap="round"
                stroke="#221f1b"
              />

              {/* Eye Orbits & Deep-Set Shading */}
              <g strokeWidth="1.4">
                {/* Left Eye */}
                <path d="M 66 106 Q 78 100 90 106 Q 78 112 66 106 Z" strokeWidth="1.6" />
                <ellipse cx="78" cy="106" rx="4.5" ry="4" fill="#302c26" />
                <circle cx="79.5" cy="104.5" r="1" fill="#f5f0e6" />
                <path d="M 68 100 Q 78 98 88 100" strokeWidth="0.8" opacity="0.6" />

                {/* Right Eye */}
                <path d="M 110 106 Q 122 100 134 106 Q 122 112 110 106 Z" strokeWidth="1.6" />
                <ellipse cx="122" cy="106" rx="4.5" ry="4" fill="#302c26" />
                <circle cx="123.5" cy="104.5" r="1" fill="#f5f0e6" />
                <path d="M 112 100 Q 122 98 132 100" strokeWidth="0.8" opacity="0.6" />
              </g>

              {/* Nasal Bridge & Cartilage Definition */}
              <path d="M 94 98 L 93 132 L 88 140 Q 100 144 112 140 L 107 132 L 106 98" strokeWidth="1.4" />
              <path d="M 92 138 Q 100 142 108 138" strokeWidth="1.8" />
              <ellipse cx="92" cy="138" rx="2" ry="1.5" fill="#3a352e" />
              <ellipse cx="108" cy="138" rx="2" ry="1.5" fill="#3a352e" />

              {/* Lips, Vermilion Border & Philtrum */}
              <path d="M 97 146 L 97 154 M 103 146 L 103 154" strokeWidth="0.8" opacity="0.6" />
              <path d="M 82 162 Q 100 159 118 162 Q 100 166 82 162 Z" strokeWidth="1.8" fill="#e8dfce" />
              <path d="M 88 168 Q 100 173 112 168" strokeWidth="1.5" />

              {/* Ears */}
              <path d="M 52 98 C 45 95 44 125 54 135" strokeWidth="1.6" />
              <path d="M 148 98 C 155 95 156 125 146 135" strokeWidth="1.6" />

              {/* Hair Texture or Cap Variant */}
              {hasCap ? (
                <g>
                  <path d="M 46 84 C 45 45 155 45 154 84 Z" fill="#2a2622" strokeWidth="2.2" />
                  <path d="M 40 86 Q 100 75 160 86" strokeWidth="3" strokeLinecap="round" />
                  {/* Visor Shadow */}
                  <path d="M 50 88 Q 100 96 150 88 L 148 98 Q 100 102 52 98 Z" fill="#3a352f" opacity="0.3" />
                </g>
              ) : (
                <g strokeWidth="1.2">
                  <path d="M 52 75 C 50 40 70 25 100 24 C 130 25 150 40 148 75 C 145 68 135 56 120 56 C 105 56 95 58 85 54 C 70 54 58 64 52 75 Z" fill="#2d2925" />
                  <path d="M 68 45 L 75 35 M 82 38 L 88 28 M 98 34 L 102 24 M 115 36 L 120 26 M 130 42 L 138 32" opacity="0.8" />
                  <path d="M 56 70 L 62 60 M 144 70 L 138 60" opacity="0.7" />
                </g>
              )}

              {/* Speculative Beard Shading */}
              {hasBeard && (
                <g stroke="#26231f" strokeWidth="1" opacity="0.85">
                  <path d="M 72 172 Q 100 188 128 172 Q 100 202 72 172 Z" fill="#302c26" opacity="0.4" />
                  <path d="M 84 158 Q 100 154 116 158" strokeWidth="1.6" />
                  <path d="M 80 176 L 86 186 M 92 180 L 98 192 M 104 180 L 102 192 M 114 176 L 110 188" />
                </g>
              )}

              {/* Mature Ageing Hatching (Nasolabial Folds & Forehead) */}
              {isMature && (
                <g strokeWidth="0.8" opacity="0.6">
                  <path d="M 82 135 Q 76 152 72 165" />
                  <path d="M 118 135 Q 124 152 128 165" />
                  <path d="M 68 82 Q 100 80 132 82" />
                  <path d="M 72 74 Q 100 72 128 74" />
                </g>
              )}

              {/* Neck & Trapezius Outlines */}
              <path d="M 70 184 L 62 225" strokeWidth="1.8" />
              <path d="M 130 184 L 138 225" strokeWidth="1.8" />
              <path d="M 62 225 Q 100 230 138 225" strokeWidth="1.4" strokeDasharray="3 3" />
            </g>
          </svg>
        )}
      </div>

      {/* Forensic Document Statutory Seal Footer (R11 Invariant) */}
      <div className="px-3 py-1.5 bg-[#eae2d3] border-t border-[#d8d0c2] text-center">
        <p className="text-[8px] font-mono text-[#8a3b14] font-semibold uppercase tracking-wider">
          AI-generated investigative aid — not a photograph, not evidence of identity.
        </p>
      </div>
    </div>
  );
};
