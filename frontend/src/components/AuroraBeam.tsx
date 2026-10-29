import React, { useEffect, useRef } from 'react';

interface AuroraBeamProps {
  className?: string;
  scrollProgress?: number;
}

interface Particle {
  x: number;
  y: number;
  size: number;
  speedY: number;
  speedX: number;
  opacity: number;
  baseOpacity: number;
  color: string;
  pulseSpeed: number;
  pulsePhase: number;
}

/**
 * AuroraBeam
 *
 * Upgraded cinematic vertical aurora beam inspired by the Huly reference.
 * Multi-layered optical structure:
 *  1. Deep atmospheric haze & drifting celestial micro-particles (Canvas)
 *  2. Broad radial base ember glow spreading into the product preview
 *  3. Electric Iris (#5683DA) outer bloom blending down into Ember Pulse (#FF8964)
 *  4. Inner focused slit with white-hot core filament and multi-stop bloom
 *  5. Continuous idle motion with responsive scroll-linked intensity modulation
 */
export const AuroraBeam: React.FC<AuroraBeamProps> = ({
  className = '',
  scrollProgress = 0,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Atmospheric micro-particle field (living dust & embers)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Check prefers-reduced-motion safely
    const isReducedMotion =
      typeof window !== 'undefined' && typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false;
    if (isReducedMotion) {
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.parentElement?.clientWidth || 600);
    let height = (canvas.height = canvas.parentElement?.clientHeight || 900);

    const handleResize = () => {
      if (!canvas || !canvas.parentElement) return;
      width = canvas.width = canvas.parentElement.clientWidth;
      height = canvas.height = canvas.parentElement.clientHeight;
    };
    window.addEventListener('resize', handleResize);

    const colors = [
      'rgba(86, 131, 218, ',   // Electric Iris
      'rgba(255, 137, 100, ',  // Ember Pulse
      'rgba(255, 255, 255, ',  // White core spark
    ];

    const particles: Particle[] = Array.from({ length: 42 }, () => ({
      x: width * 0.4 + (Math.random() - 0.5) * width * 0.5,
      y: Math.random() * height,
      size: Math.random() * 1.8 + 0.6,
      speedY: -(Math.random() * 0.4 + 0.15),
      speedX: (Math.random() - 0.5) * 0.2,
      baseOpacity: Math.random() * 0.5 + 0.2,
      opacity: 0.3,
      color: colors[Math.floor(Math.random() * colors.length)],
      pulseSpeed: Math.random() * 0.02 + 0.01,
      pulsePhase: Math.random() * Math.PI * 2,
    }));

    let isVisible = true;
    let observer: IntersectionObserver | null = null;
    if (typeof IntersectionObserver !== 'undefined') {
      observer = new IntersectionObserver(
        ([entry]) => {
          isVisible = entry.isIntersecting;
        },
        { threshold: 0.1 }
      );
      observer.observe(canvas);
    }

    const render = () => {
      if (isVisible) {
        ctx.clearRect(0, 0, width, height);

        for (let i = 0; i < particles.length; i++) {
          const p = particles[i];
          p.y += p.speedY;
          p.x += p.speedX;
          p.pulsePhase += p.pulseSpeed;
          p.opacity = p.baseOpacity * (0.6 + 0.4 * Math.sin(p.pulsePhase));

          // Recycle particle at bottom when it floats off top
          if (p.y < 0) {
            p.y = height + 10;
            p.x = width * 0.4 + (Math.random() - 0.5) * width * 0.5;
          }
          if (p.x < 0) p.x = width;
          if (p.x > width) p.x = 0;

          ctx.beginPath();
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
          ctx.fillStyle = `${p.color}${p.opacity.toFixed(2)})`;
          ctx.fill();
        }
      }
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      if (observer) observer.disconnect();
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  // Subtle scroll response: beam scales down and fades slightly as you scroll past
  const scrollShift = Math.min(scrollProgress * 60, 90);
  const scrollOpacity = Math.max(1 - scrollProgress * 0.65, 0.4);

  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none select-none relative flex items-center justify-center overflow-visible ${className}`}
      style={{
        transform: `translateY(${scrollShift * 0.35}px)`,
        opacity: scrollOpacity,
        transition: 'transform 0.15s ease-out, opacity 0.15s ease-out',
      }}
    >
      {/* 1. Broad Ambient Chromatic Backing Wash */}
      <div
        className="aurora-ambient-glow absolute -top-24 w-[600px] md:w-[900px] h-[700px] md:h-[950px] rounded-full pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 65% 55% at 50% 45%, rgba(86, 131, 218, 0.22) 0%, rgba(255, 137, 100, 0.16) 42%, rgba(90, 37, 10, 0.08) 70%, transparent 85%)',
          filter: 'blur(75px)',
        }}
      />

      {/* 2. Base Radial Warm Ember Glow (pools at bottom behind product preview) */}
      <div
        className="ember-pool absolute bottom-0 w-[500px] sm:w-[700px] lg:w-[920px] h-[340px] sm:h-[460px] rounded-full"
        style={{
          background:
            'radial-gradient(ellipse 75% 60% at 50% 65%, rgba(255, 137, 100, 0.42) 0%, rgba(90, 37, 10, 0.26) 45%, rgba(9, 10, 12, 0) 75%)',
          filter: 'blur(60px)',
        }}
      />

      {/* 3. Outer Atmospheric Haze Column (Slow gentle undulating wave) */}
      <div
        className="aurora-haze absolute top-[-60px] w-[260px] sm:w-[360px] lg:w-[460px] h-[780px] sm:h-[950px] lg:h-[1100px] rounded-full opacity-70"
        style={{
          background:
            'linear-gradient(180deg, rgba(86, 131, 218, 0) 0%, rgba(86, 131, 218, 0.35) 22%, rgba(255, 137, 100, 0.45) 60%, rgba(90, 37, 10, 0.25) 85%, transparent 100%)',
          filter: 'blur(64px)',
        }}
      />

      {/* 4. Secondary Diffuse Aurora Column (Electric Iris to Ember Coral) */}
      <div
        className="aurora-beam absolute top-[-40px] w-[130px] sm:w-[190px] lg:w-[250px] h-[750px] sm:h-[900px] lg:h-[1050px] rounded-full opacity-85"
        style={{
          background:
            'linear-gradient(180deg, rgba(86, 131, 218, 0.05) 0%, rgba(86, 131, 218, 0.75) 28%, rgba(255, 137, 100, 0.88) 65%, rgba(90, 37, 10, 0.45) 90%, transparent 100%)',
          filter: 'blur(42px)',
        }}
      />

      {/* 5. Inner Focused Luminous Column (Electric Iris bloom with coral throat) */}
      <div
        className="aurora-inner-bloom absolute top-[-10px] w-[35px] sm:w-[50px] lg:w-[70px] h-[650px] sm:h-[800px] lg:h-[920px] rounded-full opacity-90"
        style={{
          background:
            'linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(120, 165, 255, 0.85) 30%, rgba(255, 160, 130, 0.95) 65%, rgba(255, 137, 100, 0.6) 88%, transparent 100%)',
          filter: 'blur(18px)',
        }}
      />

      {/* 6. Razor Fine White-Hot Luminous Core Filament */}
      <div
        className="core-filament absolute top-4 w-[3px] sm:w-[4px] lg:w-[5px] h-[520px] sm:h-[680px] lg:h-[800px] bg-white rounded-full"
        style={{
          filter: 'blur(2px)',
        }}
      />

      {/* 7. Canvas Particle Field Layer */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full pointer-events-none z-10"
        style={{ opacity: 0.8 }}
      />
    </div>
  );
};

export default AuroraBeam;
