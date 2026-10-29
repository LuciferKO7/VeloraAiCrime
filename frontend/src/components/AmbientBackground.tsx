import React, { useEffect, useRef, useState } from 'react';

export type AmbientTier = 'high' | 'mid' | 'low';
export type AmbientEventMode = 'idle' | 'listening' | 'thinking' | 'sketching' | 'alert';

interface AmbientBackgroundProps {
  forcedTier?: AmbientTier;
  eventMode?: AmbientEventMode;
  className?: string;
}

/**
 * AmbientBackground
 *
 * Implements FRONTEND_DESIGN.md §4:
 * 1. Base: --bg-0 + subtle vignette
 * 2. Aurora blobs: 3 radial-gradient divs using --a1/--a2/--a3
 * 3. Line field: lightweight canvas contour ripples
 * 4. Dust particles: upward drifting celestial particles
 *
 * Performance tiers (high/mid/low) and visibility handling (document.hidden).
 */
export const AmbientBackground: React.FC<AmbientBackgroundProps> = ({
  forcedTier,
  eventMode = 'idle',
  className = '',
}) => {
  const [tier, setTier] = useState<AmbientTier>(forcedTier || 'high');
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Monitor prefers-reduced-motion and document visibility
  useEffect(() => {
    if (forcedTier) {
      setTier(forcedTier);
      return;
    }
    const isReduced =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (isReduced) {
      setTier('low');
    }
  }, [forcedTier]);

  // Canvas line field + dust particles
  useEffect(() => {
    if (tier === 'low') return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = Math.floor(window.innerWidth * 0.5));
    let height = (canvas.height = Math.floor(window.innerHeight * 0.5));

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = Math.floor(window.innerWidth * 0.5);
      height = canvas.height = Math.floor(window.innerHeight * 0.5);
    };
    window.addEventListener('resize', handleResize);

    // Particles setup
    interface Particle {
      x: number;
      y: number;
      s: number;
      vy: number;
      vx: number;
      alpha: number;
    }

    const count = tier === 'high' ? 36 : 18;
    const particles: Particle[] = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      s: Math.random() * 1.5 + 0.6,
      vy: -(Math.random() * 0.3 + 0.1),
      vx: (Math.random() - 0.5) * 0.15,
      alpha: Math.random() * 0.5 + 0.2,
    }));

    let frame = 0;
    let isHidden = document.hidden;

    const handleVisibility = () => {
      isHidden = document.hidden;
    };
    document.addEventListener('visibilitychange', handleVisibility);

    const render = () => {
      if (!isHidden) {
        frame++;
        ctx.clearRect(0, 0, width, height);

        // Layer 3: Faint contour lines (Line field)
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
        ctx.lineWidth = 1;

        const waveOffset = frame * 0.015;
        const speedMultiplier = eventMode === 'thinking' ? 2.2 : eventMode === 'sketching' ? 1.6 : 1.0;

        for (let y = height * 0.3; y < height; y += 42) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          for (let x = 0; x <= width; x += 30) {
            const dy = Math.sin((x * 0.015) + waveOffset * speedMultiplier) * 8;
            ctx.lineTo(x, y + dy);
          }
          ctx.stroke();
        }

        // Layer 4: Dust particles (tier === 'high' only)
        if (tier === 'high') {
          for (let i = 0; i < particles.length; i++) {
            const p = particles[i];
            const vBoost = eventMode === 'thinking' ? 2.5 : 1.0;
            p.y += p.vy * vBoost;
            p.x += p.vx;

            if (p.y < 0) {
              p.y = height + 10;
              p.x = Math.random() * width;
            }
            if (p.x < 0) p.x = width;
            if (p.x > width) p.x = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.s, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(255, 255, 255, ${p.alpha.toFixed(2)})`;
            ctx.fill();
          }
        }
      }

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('visibilitychange', handleVisibility);
      cancelAnimationFrame(animId);
    };
  }, [tier, eventMode]);

  return (
    <div
      aria-hidden="true"
      className={`fixed inset-0 pointer-events-none select-none overflow-hidden -z-20 ${className}`}
      style={{ backgroundColor: 'var(--bg-0)' }}
    >
      {/* Layer 1: Subtle vertical vignette */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 50% 30%, transparent 40%, rgba(9, 10, 12, 0.6) 80%, rgba(9, 10, 12, 0.95) 100%)',
        }}
      />

      {/* Layer 2: 3 Large Animated Aurora Blobs using --a1, --a2, --a3 */}
      {tier !== 'low' ? (
        <>
          {/* Blob 1: Upper right */}
          <div
            className="aurora-ambient-glow absolute -top-32 right-[10%] w-[500px] lg:w-[750px] h-[500px] lg:h-[750px] rounded-full opacity-40"
            style={{
              background: 'radial-gradient(circle, var(--a1) 0%, transparent 70%)',
              filter: 'blur(80px)',
            }}
          />

          {/* Blob 2: Mid left */}
          <div
            className="aurora-beam absolute top-[30%] -left-20 w-[450px] lg:w-[650px] h-[450px] lg:h-[650px] rounded-full opacity-30"
            style={{
              background: 'radial-gradient(circle, var(--a2) 0%, transparent 70%)',
              filter: 'blur(85px)',
            }}
          />

          {/* Blob 3: Lower center pool */}
          <div
            className="ember-pool absolute -bottom-32 left-[25%] w-[600px] lg:w-[900px] h-[400px] lg:h-[550px] rounded-full opacity-35"
            style={{
              background: 'radial-gradient(circle, var(--a3) 0%, transparent 75%)',
              filter: 'blur(80px)',
            }}
          />
        </>
      ) : (
        /* Low-tier single static ambient glow */
        <div
          className="absolute top-0 right-1/4 w-[600px] h-[600px] rounded-full opacity-25"
          style={{
            background: 'radial-gradient(circle, var(--a1) 0%, transparent 70%)',
            filter: 'blur(90px)',
          }}
        />
      )}

      {/* Layers 3 & 4: Canvas Line field & Dust particles */}
      {tier !== 'low' && (
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full opacity-40 pointer-events-none"
        />
      )}
    </div>
  );
};

export default AmbientBackground;
