import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowRight,
  ShieldAlert,
  Fingerprint,
  Scale,
  FileCheck,
  ChevronRight,
  Network,
  Eye,
  FileText,
  Lock,
  CheckCircle2,
} from 'lucide-react';
import { AuroraBeam } from '../components/AuroraBeam';
import { InvestigativeCanvasPreview } from '../components/InvestigativeCanvasPreview';

export const MANDATORY_DISCLAIMER =
  'AI-generated investigative aid — not a photograph, not evidence of identity.';

interface LandingPageProps {
  onEnterWorkspace: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onEnterWorkspace }) => {
  const [scrolled, setScrolled] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);

  // References for scroll reveal sections
  const capabilitiesRef = useRef<HTMLElement | null>(null);
  const responsibleAiRef = useRef<HTMLElement | null>(null);
  const auditabilityRef = useRef<HTMLElement | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);

  // Scroll listener for navigation state and aurora intensity modulation
  useEffect(() => {
    let ticking = false;

    const handleScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const currentScrollY = window.scrollY;
          setScrolled(currentScrollY > 15);

          // Calculate normalized scroll progress through hero (0 to 1)
          const heroHeight = window.innerHeight * 0.9;
          const progress = Math.min(Math.max(currentScrollY / heroHeight, 0), 1);
          setScrollProgress(progress);

          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // IntersectionObserver for continuous section reveals
  useEffect(() => {
    const isReducedMotion =
      typeof window !== 'undefined' && typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
        : false;

    if (isReducedMotion || typeof IntersectionObserver === 'undefined') {
      // In reduced motion mode or unsupported environments, reveal all immediately
      document.querySelectorAll('.reveal-init').forEach((el) => {
        el.classList.add('reveal-visible');
      });
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('reveal-visible');
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );

    const elements = [
      previewRef.current,
      capabilitiesRef.current,
      responsibleAiRef.current,
      auditabilityRef.current,
    ].filter(Boolean) as HTMLElement[];

    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  const scrollToResponsibleAi = (e: React.MouseEvent) => {
    e.preventDefault();
    const element = document.getElementById('responsible-ai');
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="min-h-screen bg-[#090A0C] text-[#E5E5E7] selection:bg-[#FF8964]/30 selection:text-white font-sans overflow-x-hidden">
      {/* ------------------------------------------------------------- */}
      {/* NAVIGATION BAR                                                */}
      {/* ------------------------------------------------------------- */}
      <nav
        aria-label="Main Navigation"
        className={`sticky top-0 z-40 transition-all duration-300 ${
          scrolled
            ? 'bg-[#090A0C]/90 backdrop-blur-md border-b border-[#4A4B50]/40 py-3 shadow-xl'
            : 'bg-[#090A0C]/35 backdrop-blur-sm py-4 border-b border-[#4A4B50]/20'
        }`}
      >
        <div className="max-w-[1240px] mx-auto px-6 flex items-center justify-between">
          {/* Brand Lockup */}
          <a
            href="#overview"
            className="flex items-center gap-2.5 text-white focus:outline-none focus:ring-2 focus:ring-[#5683DA] rounded-lg px-1 py-0.5"
          >
            <div className="relative flex items-center justify-center w-7 h-7 rounded-lg bg-[#111111] border border-[#4A4B50]/60 shadow-inner">
              <span className="w-2.5 h-2.5 rounded-full bg-gradient-to-tr from-[#5683DA] to-[#FF8964]" />
            </div>
            <span className="font-display font-semibold tracking-widest text-base text-white">
              VELORA
            </span>
          </a>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center gap-8 text-sm font-normal text-[#A9A9AA]">
            <a
              href="#overview"
              className="hover:text-white transition-colors py-1 focus:outline-none focus:underline"
            >
              Overview
            </a>
            <a
              href="#capabilities"
              className="hover:text-white transition-colors py-1 focus:outline-none focus:underline"
            >
              Capabilities
            </a>
            <a
              href="#responsible-ai"
              onClick={scrollToResponsibleAi}
              className="hover:text-white transition-colors py-1 focus:outline-none focus:underline"
            >
              Responsible AI
            </a>
            <a
              href="#auditability"
              className="hover:text-white transition-colors py-1 focus:outline-none focus:underline"
            >
              Auditability
            </a>
          </div>

          {/* Action CTA */}
          <div className="flex items-center gap-3">
            <button
              onClick={onEnterWorkspace}
              className="group inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-xs md:text-sm font-medium bg-[#111111] text-white border border-[#4A4B50]/80 hover:border-[#5683DA] hover:bg-[#1A1A1E] transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-[#5683DA]"
            >
              <span>Enter VELORA</span>
              <ArrowRight className="w-3.5 h-3.5 text-[#FF8964] group-hover:translate-x-0.5 transition-transform" />
            </button>
          </div>
        </div>
      </nav>

      {/* ------------------------------------------------------------- */}
      {/* HERO SECTION — LEFT-ALIGNED EDITORIAL + RIGHT AURORA BEAM     */}
      {/* ------------------------------------------------------------- */}
      <section
        id="overview"
        className="relative pt-12 md:pt-16 pb-20 md:pb-28 px-6 overflow-hidden"
      >
        {/* Dominant Vertical Aurora Beam (Positioned center-right beside content) */}
        <div className="absolute right-[5%] sm:right-[12%] lg:right-[22%] -top-10 pointer-events-none z-10">
          <AuroraBeam scrollProgress={scrollProgress} />
        </div>

        {/* Content Container (Constrained ~1240px) */}
        <div className="max-w-[1240px] mx-auto relative z-20">
          {/* Main Asymmetrical Hero Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center min-h-[460px] lg:min-h-[520px]">
            {/* Left Content Column */}
            <div className="lg:col-span-8 xl:col-span-8 text-left">
              {/* Eyebrow Badge */}
              <div className="animate-hero-eyebrow inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#111111]/85 border border-[#4A4B50]/60 mb-6 backdrop-blur-md shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-[#FF8964] animate-pulse" />
                <span className="text-[11px] md:text-xs font-semibold tracking-[0.16em] uppercase text-[#A9A9AA]">
                  INTELLIGENCE, WITH ACCOUNTABILITY.
                </span>
              </div>

              {/* Large Bold Editorial Display Headline (~80px desktop, tight tracking) */}
              <h1 className="animate-hero-title font-display text-4xl sm:text-6xl md:text-7xl lg:text-[76px] xl:text-[84px] font-medium tracking-[-0.035em] text-white leading-[1.06]">
                See the connections.
                <br />
                <span className="text-[#A9A9AA]">Understand the context.</span>
              </h1>

              {/* Supporting Copy */}
              <p className="animate-hero-body mt-6 text-base sm:text-lg md:text-xl text-[#95979E] max-w-xl font-normal leading-relaxed">
                An AI-powered investigative workspace that helps teams organize witness interviews,
                explore scene context, connect observations, and trace every critical action.
              </p>

              {/* CTA Group with Luminous Iris/Coral Glow */}
              <div className="animate-hero-cta mt-9 flex flex-col sm:flex-row items-stretch sm:items-center gap-4">
                {/* Primary CTA with refined luminous glow */}
                <button
                  onClick={onEnterWorkspace}
                  className="group relative inline-flex items-center justify-center gap-2.5 px-8 py-4 rounded-full text-sm md:text-base font-semibold bg-white text-[#090A0C] hover:bg-[#E5E5E7] transition-all duration-300 shadow-[0_0_25px_rgba(86,131,218,0.35),0_0_50px_rgba(255,137,100,0.22)] hover:shadow-[0_0_35px_rgba(86,131,218,0.5),0_0_70px_rgba(255,137,100,0.38)] hover:scale-[1.02] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-[#5683DA] focus:ring-offset-2 focus:ring-offset-[#090A0C]"
                >
                  <span>Enter VELORA</span>
                  <ArrowRight className="w-4 h-4 text-[#FF8964] group-hover:translate-x-1 transition-transform duration-200" />
                </button>

                {/* Secondary CTA */}
                <a
                  href="#responsible-ai"
                  onClick={scrollToResponsibleAi}
                  className="inline-flex items-center justify-center gap-2 px-6 py-4 rounded-full text-sm md:text-base font-normal text-[#A9A9AA] hover:text-white bg-[#111111]/70 hover:bg-[#111111] border border-[#4A4B50]/60 hover:border-[#5683DA]/60 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#5683DA]"
                >
                  <span>Explore responsible AI</span>
                  <ChevronRight className="w-4 h-4 text-[#95979E]" />
                </a>
              </div>
            </div>

            {/* Right Column (Negative space where aurora stream pours through) */}
            <div className="hidden lg:flex lg:col-span-4 xl:col-span-4 justify-end pointer-events-none" />
          </div>

          {/* Product Preview Frame Emerging into Foreground */}
          <div
            ref={previewRef}
            className="reveal-init mt-14 sm:mt-20 lg:mt-24 relative z-30"
          >
            <InvestigativeCanvasPreview />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- */}
      {/* SECTION 2 — CORE CAPABILITIES (CHARCOAL SURFACES)              */}
      {/* ------------------------------------------------------------- */}
      <section
        id="capabilities"
        ref={capabilitiesRef}
        className="reveal-init py-28 px-6 border-t border-[#4A4B50]/30 bg-[#0D0E12] relative"
      >
        <div className="max-w-[1240px] mx-auto">
          {/* Section Header */}
          <div className="max-w-2xl text-left mb-16">
            <span className="text-xs font-mono uppercase tracking-widest text-[#5683DA]">
              // ARCHITECTURAL CAPABILITIES
            </span>
            <h2 className="font-display text-3xl sm:text-4xl md:text-5xl font-medium tracking-tight text-white mt-2 mb-4">
              Structured Context. Forensic Integrity.
            </h2>
            <p className="text-base text-[#95979E] leading-relaxed">
              VELORA replaces fragmented notes and unvalidated assumptions with a multi-layered
              workspace designed for investigative rigor.
            </p>
          </div>

          {/* 3 Modular Charcoal Surface Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Card 1 */}
            <div className="rounded-2xl bg-[#111111] border border-[#4A4B50]/40 p-8 flex flex-col justify-between hover:border-[#5683DA]/60 transition-colors group shadow-lg">
              <div>
                <div className="w-10 h-10 rounded-xl bg-[#5683DA]/10 border border-[#5683DA]/30 flex items-center justify-center mb-6">
                  <Network className="w-5 h-5 text-[#5683DA]" />
                </div>
                <h3 className="text-xl font-display font-medium text-white mb-2">
                  Multi-Witness Synthesis
                </h3>
                <p className="text-sm text-[#95979E] leading-relaxed">
                  Ingest disparate witness audio and statements. Detect viewpoint angles, lighting
                  discrepancies, and perception variances without introducing confirmation bias.
                </p>
              </div>
              <div className="mt-8 pt-4 border-t border-[#4A4B50]/20 flex items-center justify-between text-xs text-[#A9A9AA]">
                <span>Timeline Coherence</span>
                <span className="font-mono text-[#5683DA]">Automated Mapping</span>
              </div>
            </div>

            {/* Card 2 */}
            <div className="rounded-2xl bg-[#111111] border border-[#4A4B50]/40 p-8 flex flex-col justify-between hover:border-[#FF8964]/60 transition-colors group shadow-lg">
              <div>
                <div className="w-10 h-10 rounded-xl bg-[#FF8964]/10 border border-[#FF8964]/30 flex items-center justify-center mb-6">
                  <Eye className="w-5 h-5 text-[#FF8964]" />
                </div>
                <h3 className="text-xl font-display font-medium text-white mb-2">
                  Scene Context & Viewpoints
                </h3>
                <p className="text-sm text-[#95979E] leading-relaxed">
                  Map witness vantage points to physical scene geometry. Validate sightline
                  obstructions, ambient lux levels, and distance thresholds with scientific clarity.
                </p>
              </div>
              <div className="mt-8 pt-4 border-t border-[#4A4B50]/20 flex items-center justify-between text-xs text-[#A9A9AA]">
                <span>Spatial Geometry</span>
                <span className="font-mono text-[#FF8964]">Vector Verification</span>
              </div>
            </div>

            {/* Card 3 */}
            <div className="rounded-2xl bg-[#111111] border border-[#4A4B50]/40 p-8 flex flex-col justify-between hover:border-emerald-400/60 transition-colors group shadow-lg">
              <div>
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-6">
                  <Lock className="w-5 h-5 text-emerald-400" />
                </div>
                <h3 className="text-xl font-display font-medium text-white mb-2">
                  Cryptographic Provenance
                </h3>
                <p className="text-sm text-[#95979E] leading-relaxed">
                  Every operator adjustment, prompt modification, and parameter iteration is bound
                  to an immutable SHA-256 audit log, ensuring complete chain-of-custody compliance.
                </p>
              </div>
              <div className="mt-8 pt-4 border-t border-[#4A4B50]/20 flex items-center justify-between text-xs text-[#A9A9AA]">
                <span>Chain of Custody</span>
                <span className="font-mono text-emerald-400">Verifiable Ledger</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- */}
      {/* SECTION 3 — RESPONSIBLE AI (LIGHT SECTIONS / LINEN SURFACES)   */}
      {/* ------------------------------------------------------------- */}
      <section
        id="responsible-ai"
        ref={responsibleAiRef}
        className="reveal-init py-28 px-6 bg-[#FFFFFF] text-[#111111] relative overflow-hidden"
      >
        <div className="max-w-[1240px] mx-auto">
          {/* Section Header (High Editorial Contrast) */}
          <div className="max-w-3xl mb-16 text-left">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-[#E5E5E7] text-[#111111] uppercase tracking-wider mb-3">
              <Scale className="w-3.5 h-3.5 text-[#FF8964]" />
              Ethical Mandate
            </span>
            <h2 className="font-display text-3xl sm:text-5xl font-medium tracking-tight text-[#111111] mb-4">
              Accountability by design.
              <br />
              Never an afterthought.
            </h2>
            <p className="text-base sm:text-lg text-[#666666] leading-relaxed">
              Investigative AI carries severe constitutional responsibility. VELORA is engineered
              with strict structural boundaries that prevent overreach, bias amplification, and
              unwarranted identity attribution.
            </p>
          </div>

          {/* Standing Notice Callout Banner */}
          <div className="mb-14 p-6 sm:p-7 rounded-2xl bg-[#FFF6F2] border-2 border-[#FF8964]/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
            <div className="flex items-start gap-4">
              <div className="p-2.5 rounded-xl bg-[#FF8964]/15 text-[#FF8964] shrink-0">
                <ShieldAlert className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-semibold text-[#111111]">
                  Mandatory Evidentiary Standard
                </h4>
                <p className="text-sm font-medium text-[#FF5A1F] mt-0.5">
                  &ldquo;{MANDATORY_DISCLAIMER}&rdquo;
                </p>
              </div>
            </div>
            <div className="text-xs font-mono text-[#666666] shrink-0 sm:text-right bg-white px-3 py-1.5 rounded-lg border border-[#E5E5E7]">
              ENFORCED AT RUNTIME
            </div>
          </div>

          {/* 3 Light-Theme Principle Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-8 rounded-2xl bg-[#F5F5F5] border border-[#E5E5E7] space-y-3">
              <div className="w-9 h-9 rounded-lg bg-white border border-[#E5E5E7] flex items-center justify-center text-[#5683DA]">
                <Fingerprint className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold text-[#111111]">
                Non-Biometric Identification
              </h3>
              <p className="text-sm text-[#666666] leading-relaxed">
                VELORA does not match photos against surveillance databases or establish criminal
                identity. Visualizations serve exclusively to jog human recollection during interviews.
              </p>
            </div>

            <div className="p-8 rounded-2xl bg-[#F5F5F5] border border-[#E5E5E7] space-y-3">
              <div className="w-9 h-9 rounded-lg bg-white border border-[#E5E5E7] flex items-center justify-center text-[#FF8964]">
                <FileCheck className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold text-[#111111]">
                Human-in-the-Loop Governance
              </h3>
              <p className="text-sm text-[#666666] leading-relaxed">
                AI never operates autonomously. Every composite, timeline connection, and
                investigative hypothesis requires deliberate investigator validation and review.
              </p>
            </div>

            <div className="p-8 rounded-2xl bg-[#F5F5F5] border border-[#E5E5E7] space-y-3">
              <div className="w-9 h-9 rounded-lg bg-white border border-[#E5E5E7] flex items-center justify-center text-emerald-600">
                <FileText className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-semibold text-[#111111]">
                Defensible in Judicial Review
              </h3>
              <p className="text-sm text-[#666666] leading-relaxed">
                Export comprehensive discovery packets detailing model versions, prompt sequences,
                confidence bounds, and seed values for full courtroom scrutiny.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- */}
      {/* SECTION 4 — AUDITABILITY & CLOSING CALL TO ACTION              */}
      {/* ------------------------------------------------------------- */}
      <section
        id="auditability"
        ref={auditabilityRef}
        className="reveal-init py-28 px-6 bg-[#090A0C] border-t border-[#4A4B50]/30 text-center relative"
      >
        <div className="max-w-[1240px] mx-auto flex flex-col items-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#111111] border border-[#4A4B50]/50 mb-6">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-xs font-mono text-[#A9A9AA]">AUDIT READINESS VERIFIED</span>
          </div>

          <h2 className="font-display text-3xl sm:text-5xl md:text-6xl font-medium tracking-tight text-white max-w-2xl">
            Ready to experience accountable intelligence?
          </h2>

          <p className="mt-5 text-base sm:text-lg text-[#95979E] max-w-xl">
            Step into the VELORA workspace to explore witness synthesis, scene context, and
            transparent provenance.
          </p>

          <div className="mt-8">
            <button
              onClick={onEnterWorkspace}
              className="inline-flex items-center gap-2 px-8 py-4 rounded-full text-base font-semibold bg-white text-[#090A0C] hover:bg-[#E5E5E7] transition-all shadow-[0_0_25px_rgba(86,131,218,0.35),0_0_50px_rgba(255,137,100,0.22)] hover:scale-[1.02] focus:outline-none focus:ring-2 focus:ring-white"
            >
              <span>Enter VELORA</span>
              <ArrowRight className="w-4 h-4 text-[#FF8964]" />
            </button>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- */}
      {/* FOOTER                                                        */}
      {/* ------------------------------------------------------------- */}
      <footer className="py-12 px-6 border-t border-[#4A4B50]/30 bg-[#090A0C] text-xs text-[#95979E]">
        <div className="max-w-[1240px] mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2.5">
            <div className="w-5 h-5 rounded-md bg-[#111111] border border-[#4A4B50]/60 flex items-center justify-center">
              <span className="w-2 h-2 rounded-full bg-gradient-to-tr from-[#5683DA] to-[#FF8964]" />
            </div>
            <span className="font-semibold text-white tracking-wider">VELORA</span>
            <span className="text-[#4A4B50]">•</span>
            <span>Investigative Intelligence Platform</span>
          </div>

          {/* Legal statement & version */}
          <div className="text-center md:text-right space-y-1">
            <p className="text-[#A9A9AA]">
              {MANDATORY_DISCLAIMER}
            </p>
            <p className="text-[11px] text-[#4A4B50]">
              Built strictly for investigative support. Does not replace human judgment.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
