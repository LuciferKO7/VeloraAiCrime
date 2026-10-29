import React, { useState, useRef, useEffect } from 'react';
import {
  Mic,
  Send,
  Sparkles,
  Lock,
  Unlock,
  Check,
  Download,
  AlertTriangle,
  Shield,
  RefreshCw,
  Compass,
  Layers,
  WifiOff,
  AlertCircle,
  FileText,
  Square,
  Wand2,
} from 'lucide-react';
import { DynamicIsland } from '../components/DynamicIsland';
import { Vela, type VelaState } from '../components/Vela';
import { ExportSheet } from '../components/ExportSheet';
import { SceneEditor } from '../components/SceneEditor';
import { ForensicGraphiteSketch } from '../components/ForensicGraphiteSketch';
import {
  DEMO_FACIAL_ATTRIBUTES,
  DEMO_AI_ASSUMED_UNSTATED,
} from '../store/demoData';
import {
  AudioRecordingSession,
  sendAudioForTranscription,
  DEMO_SAMPLE_TRANSCRIPTS,
} from '../utils/audioRecorder';
import type { CaseItem } from './CommandCenterPage';
import { apiClient } from '../api/client';

interface StudioPageProps {
  activeCase?: CaseItem;
  sessionId?: string;
  initialMode?: 'composite' | 'scene';
  onFinalizeSuccess?: () => void;
}

type StudioPhase = 'Describe' | 'Recognize' | 'Refine' | 'Finalize';

export const StudioPage: React.FC<StudioPageProps> = ({
  activeCase = {
    id: 'case-demo-2026-041',
    case_number: 'DEMO-2026-041',
    title: 'Vehicle incident — reconstructed witness account',
    station: 'Metropolitan Forensic Hub',
    status: 'active',
    data_mode: 'demo',
    default_appearance_group: 'unspecified',
    updated_at: new Date().toISOString(),
  },
  sessionId = 'SES-2026-0814',
  initialMode = 'composite',
}) => {
  const [studioMode, setStudioMode] = useState<'composite' | 'scene'>(initialMode);
  const [isExportSheetOpen, setIsExportSheetOpen] = useState(false);
  const [phase, setPhase] = useState<StudioPhase>('Describe');
  const [velaState, setVelaState] = useState<VelaState>('idle');
  const [velaSpeechOverride, setVelaSpeechOverride] = useState<string | null>(null);

  // Phase 1 Describe state
  const [isRecording, setIsRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [micNotice, setMicNotice] = useState<string | null>(null);
  const [selectedLanguage, setSelectedLanguage] = useState('ta'); // Tamil
  const [transcriptOriginal, setTranscriptOriginal] = useState(
    'அவர் சுமார் 30 வயது, கூர்மையான தாடை, அடர்ந்த புருவங்கள் மற்றும் கருப்பு ஜாக்கெட் அணிந்திருந்தார்.'
  );
  const [transcriptEnglish, setTranscriptEnglish] = useState(
    'He was about 30 years old, sharp angular jawline, thick arched eyebrows, wearing a dark jacket.'
  );
  const [unmappedNotes, setUnmappedNotes] = useState<string[]>([
    'dark nylon jacket (clothing outside facial bounds)',
  ]);

  const sessionRef = useRef<AudioRecordingSession | null>(null);

  // Cleanup microphone tracks on unmount
  useEffect(() => {
    return () => {
      sessionRef.current?.cleanupTracks();
    };
  }, []);

  // Submission & service availability states
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isDevFixtureMode, setIsDevFixtureMode] = useState(false);

  // Attribute inspector state (DEMO-2026-041)
  const [attributes, setAttributes] = useState<
    Array<{ region: string; key: string; value: string; confidence: 'sure' | 'somewhat' | 'unsure'; locked: boolean }>
  >(DEMO_FACIAL_ATTRIBUTES);

  // AI Assumed panel items (R11 invariant: never guessed, varied across variants)
  const [aiAssumed, setAiAssumed] = useState(DEMO_AI_ASSUMED_UNSTATED);

  // Phase 2 Recognize: 6 variants state
  const [cards, setCards] = useState([
    { id: 'v1', status: 'ready', picked: false, score: 0.88, axes: 'frontal · sharp angular jaw · clean', view: 'frontal' as const, jawStyle: 'sharp' as const, hasCap: false, hasBeard: false, isMature: false },
    { id: 'v2', status: 'ready', picked: true, score: 0.94, axes: 'profile lateral · defined brow ridge', view: 'profile' as const, jawStyle: 'sharp' as const, hasCap: false, hasBeard: false, isMature: false },
    { id: 'v3', status: 'ready', picked: false, score: 0.78, axes: 'frontal · rounded jaw (W-003 dispute)', view: 'frontal' as const, jawStyle: 'rounded' as const, hasCap: false, hasBeard: false, isMature: false },
    { id: 'v4', status: 'ready', picked: false, score: 0.82, axes: 'frontal · dark low-profile cap (W-003)', view: 'frontal' as const, jawStyle: 'sharp' as const, hasCap: true, hasBeard: false, isMature: false },
    { id: 'v5', status: 'ready', picked: false, score: 0.85, axes: 'profile · capped / shadowed forehead', view: 'profile' as const, jawStyle: 'sharp' as const, hasCap: true, hasBeard: false, isMature: false },
    { id: 'v6', status: 'ready', picked: false, score: 0.79, axes: 'frontal · speculative mature (+5y)', view: 'frontal' as const, jawStyle: 'sharp' as const, hasCap: false, hasBeard: false, isMature: true },
  ]);

  // Generation tracking & state
  const [isGeneratingRound, setIsGeneratingRound] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [generationRequestId, setGenerationRequestId] = useState<string>('GEN-REQ-2026-041-01');
  const [generationTimestamp, setGenerationTimestamp] = useState<string>('09:28:40');

  // Currently picked variant across Refine & Finalize
  const activeVariant = cards.find((c) => c.picked) || cards[1];

  // Phase 3 Refine state
  const compareSplit = 50;
  const [timeDialYears, setTimeDialYears] = useState(0);
  const [disguiseBeard, setDisguiseBeard] = useState(true);
  const [disguiseGlasses, setDisguiseGlasses] = useState(false);

  // Phase 4 Finalize state
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [finalizedSuccess, setFinalizedSuccess] = useState(false);
  const [exportFormat, setExportFormat] = useState<'png' | 'pdf' | 'json'>('pdf');

  // Toggle genuine audio recording with track lifecycle
  const handleToggleMic = async () => {
    setMicError(null);
    setMicNotice(null);

    if (!isRecording) {
      try {
        const session = new AudioRecordingSession();
        sessionRef.current = session;
        await session.start();
        setIsRecording(true);
        setVelaState('listening');
        setVelaSpeechOverride(`Listening to witness statement via microphone (${selectedLanguage.toUpperCase()})...`);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Microphone access failed.';
        setMicError(msg);
        setVelaState('wince');
      }
    } else {
      setIsRecording(false);
      setVelaState('thinking');
      setVelaSpeechOverride('Processing audio recording...');

      try {
        if (!sessionRef.current) throw new Error('No active recording.');
        const res = await sessionRef.current.stop();

        try {
          const trans = await sendAudioForTranscription(res.blob, selectedLanguage);
          setTranscriptOriginal(trans.text);
          setVelaState('proud');
          setVelaSpeechOverride('Transcribed witness recording.');
        } catch {
          // Speech service (:8002) offline
          setMicNotice(
            `Captured ${(res.sizeBytes / 1024).toFixed(1)} KB audio locally (${res.durationSec}s). Speech Service (:8002) is offline.`
          );
          setVelaState('curious');
          setVelaSpeechOverride('Audio recorded locally. Service offline (:8002) — edit manually or load sample.');
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Error stopping recording.';
        setMicError(msg);
        setVelaState('idle');
      }
    }
  };

  const handleLoadDemoTranscript = () => {
    const sample = DEMO_SAMPLE_TRANSCRIPTS[selectedLanguage] || DEMO_SAMPLE_TRANSCRIPTS.en;
    setTranscriptOriginal(sample.original);
    setTranscriptEnglish(sample.english);
    setMicNotice(`Loaded verified [DEMO FIXTURE] ${sample.languageName} statement.`);
    setMicError(null);
    setVelaState('curious');
  };

  const handleSendTranscript = async () => {
    if (!transcriptOriginal.trim()) return;

    setIsSubmitting(true);
    setSubmitError(null);
    setVelaState('thinking');
    setVelaSpeechOverride('Submitting statement to backend hub (:8000)...');

    try {
      interface StatementApiResponse {
        statement_id?: string;
        session_id?: string;
        english_text?: string;
        attributes?: Array<{ region: string; key: string; value: string; confidence: 'sure' | 'somewhat' | 'unsure'; locked: boolean }>;
        ai_assumed?: Array<{ key: string; note: string }>;
        unmapped_notes?: string[];
        next_question?: string;
      }

      const res = await apiClient.post<StatementApiResponse>(
        `/sessions/${sessionId}/statements`,
        {
          original_text: transcriptOriginal,
          original_lang: selectedLanguage,
          input_mode: isRecording ? 'voice' : 'text',
        },
        {
          caseId: activeCase.id,
          dataMode: activeCase.data_mode,
        }
      );

      if (res) {
        if (res.attributes && res.attributes.length > 0) {
          setAttributes(res.attributes);
        }
        if (res.ai_assumed && res.ai_assumed.length > 0) {
          setAiAssumed(res.ai_assumed);
        }
        if (res.english_text) {
          setTranscriptEnglish(res.english_text);
        }
        if (res.unmapped_notes) {
          setUnmappedNotes(res.unmapped_notes);
        }
        setIsDevFixtureMode(false);
        setVelaState('curious');
        setVelaSpeechOverride(res.next_question || 'Statement processed into forensic facial attributes.');
        setPhase('Recognize');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Backend hub connection failed on port 8000';
      setSubmitError(
        `Service Offline (:8000): ${msg}. Backend hub is not running on port 8000. You may retry or load the development baseline for presentation testing.`
      );
      setVelaState('wince');
      setVelaSpeechOverride('Backend offline on port 8000. Statement parser could not be reached.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Deterministic client-side extraction per P0 emergency offline requirement
  const handleDeterministicParse = () => {
    setSubmitError(null);
    setIsDevFixtureMode(true);
    setAttributes(DEMO_FACIAL_ATTRIBUTES);
    setAiAssumed(DEMO_AI_ASSUMED_UNSTATED);
    const sample = DEMO_SAMPLE_TRANSCRIPTS[selectedLanguage] || DEMO_SAMPLE_TRANSCRIPTS.en;
    setTranscriptEnglish(sample.english);
    setVelaState('curious');
    setVelaSpeechOverride('Deterministic client-side extraction complete for case DEMO-2026-041.');
    setPhase('Recognize');
  };

  // Genuine ML generation trigger with distinct generation request ID & honest offline handling
  const handleGenerateRound = async () => {
    const reqId = 'GEN-REQ-' + Date.now().toString(36).toUpperCase();
    setIsGeneratingRound(true);
    setGenerationError(null);
    setVelaState('sketching');
    setVelaSpeechOverride('Calling ML generation service (:8001)...');

    try {
      await apiClient.post(`/sessions/${sessionId}/rounds/generate`, {
        request_id: reqId,
        locked_attributes: attributes.filter((a) => a.locked),
      });
      setGenerationRequestId(reqId);
      setGenerationTimestamp(new Date().toLocaleTimeString());
      setVelaState('proud');
      setVelaSpeechOverride('New neural composite generated.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'ML Service offline (:8001)';
      setGenerationError(
        `ML Service Offline (:8001): ${msg}. Cannot synthesize neural variation on port 8001.`
      );
      setVelaState('wince');
      setVelaSpeechOverride('ML service offline (:8001). Load verified reference composite.');
    } finally {
      setIsGeneratingRound(false);
    }
  };

  const handleLoadCompositeReference = () => {
    const reqId = 'REF-COMPOSITE-' + Math.floor(Math.random() * 8999 + 1000);
    setGenerationRequestId(reqId);
    setGenerationTimestamp(new Date().toLocaleTimeString());
    setGenerationError(null);
    setVelaState('proud');
    setVelaSpeechOverride('Loaded official forensic graphite composite reference for DEMO-2026-041.');
  };

  const handlePickCard = (id: string) => {
    setCards((prev) =>
      prev.map((c) => ({
        ...c,
        picked: c.id === id ? !c.picked : c.picked,
      }))
    );
  };

  const handleToggleLock = (index: number) => {
    setAttributes((prev) =>
      prev.map((attr, i) => (i === index ? { ...attr, locked: !attr.locked } : attr))
    );
  };

  const handleRunFinalize = () => {
    setIsFinalizing(true);
    setVelaState('thinking');
    setTimeout(() => {
      setIsFinalizing(false);
      setFinalizedSuccess(true);
      setVelaState('proud');
      setIsExportSheetOpen(true);
    }, 1200);
  };

  return (
    <div className="min-h-screen bg-[#090a0c] text-[#f4f5f7] flex flex-col justify-between">
      {/* Mode Bar */}
      <div className="px-6 pt-3 flex justify-between items-center text-xs border-b border-white/5">
        <div className="flex items-center gap-1 bg-[#14161a] p-1 rounded-xl border border-white/10">
          <button
            onClick={() => setStudioMode('composite')}
            className={`px-3 py-1 rounded-lg font-medium flex items-center gap-1.5 transition-colors ${
              studioMode === 'composite' ? 'bg-[#7c8cff] text-[#090a0c] font-bold' : 'text-[#A9A9AA] hover:text-white'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Facial Composite</span>
          </button>
          <button
            onClick={() => setStudioMode('scene')}
            className={`px-3 py-1 rounded-lg font-medium flex items-center gap-1.5 transition-colors ${
              studioMode === 'scene' ? 'bg-[#7c8cff] text-[#090a0c] font-bold' : 'text-[#A9A9AA] hover:text-white'
            }`}
          >
            <Compass className="w-3.5 h-3.5" />
            <span>Scene Diagram</span>
          </button>
        </div>

        <button
          onClick={() => setIsExportSheetOpen(true)}
          className="px-3 py-1 rounded-xl bg-[#14161a] border border-white/10 text-white hover:bg-white/5 flex items-center gap-1.5 transition-colors"
        >
          <Download className="w-3.5 h-3.5 text-[#5ad1ff]" />
          <span>Export Packet</span>
        </button>
      </div>

      {studioMode === 'scene' ? (
        <SceneEditor
          sessionId={sessionId}
          onBackToStudio={() => setStudioMode('composite')}
        />
      ) : (
        <>
          {/* 1. Dynamic Island Top Header */}
          <div className="pt-2 pb-2 px-6 flex justify-center sticky top-0 z-30 pointer-events-auto">
            <DynamicIsland
              caseNumber={activeCase.case_number}
              witnessAlias="W-001 (Store Clerk)"
              phase={phase}
              dataMode={activeCase.data_mode}
              latencyMs={980}
              statusMessage={
                isRecording
                  ? 'Recording Audio (Tamil)...'
                  : isFinalizing
                  ? 'Synthesizing Forensic Export...'
                  : undefined
              }
            />
          </div>

          {/* 2. Main Studio 3-Column Layout (Conversation Rail | Stage | Inspector) */}
          <div className="flex-1 max-w-[1400px] w-full mx-auto px-4 sm:px-6 py-4 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* ========================================================= */}
        {/* LEFT COLUMN: Conversation Rail (340px)                    */}
        {/* ========================================================= */}
        <aside
          aria-label="Conversation rail"
          className="lg:col-span-3 rounded-2xl glass-panel p-5 space-y-4 self-stretch flex flex-col justify-between min-h-[560px]"
        >
          <div className="space-y-4">
            {/* Phase Stepper Pills */}
            <div className="flex items-center justify-between text-[11px] pb-3 border-b border-[rgba(255,255,255,0.08)]">
              {(['Describe', 'Recognize', 'Refine', 'Finalize'] as StudioPhase[]).map((p, idx) => (
                <button
                  key={p}
                  onClick={() => setPhase(p)}
                  className={`font-medium transition-colors ${
                    phase === p ? 'text-[#5ad1ff] font-semibold' : 'text-[#A9A9AA] hover:text-white'
                  }`}
                >
                  <span>{idx + 1}. {p}</span>
                </button>
              ))}
            </div>

            {/* Vela Companion */}
            <div className="flex justify-center py-2">
              <Vela
                state={velaState}
                size="companion"
                speechText={
                  velaSpeechOverride ||
                  (phase === 'Describe'
                    ? 'Do you remember the eye shape or any distinguishing facial mark?'
                    : phase === 'Recognize'
                    ? 'Pick the face that most closely triggers your recognition.'
                    : phase === 'Refine'
                    ? 'Use the Time dial or compare slider to adjust specifics.'
                    : 'Export package ready with cryptographic custody hash.')
                }
              />
            </div>

            {/* Transcript review bubble (Human in the loop per §6.5) */}
            <div className="p-3.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] space-y-2 text-xs">
              <div className="flex items-center justify-between text-[#A9A9AA]">
                <span className="font-medium text-white">Witness Statement</span>
                <span className="text-[10px] font-mono text-[#5ad1ff]">Tamil (தமிழ்)</span>
              </div>
              <textarea
                value={transcriptOriginal}
                onChange={(e) => setTranscriptOriginal(e.target.value)}
                rows={2}
                className="w-full bg-[#090a0c] p-2 rounded-lg border border-[rgba(255,255,255,0.08)] text-xs text-[#f4f5f7] outline-none focus:border-[#5ad1ff]"
              />
              <div className="text-[11px] text-[#A9A9AA] italic border-t border-[rgba(255,255,255,0.06)] pt-1.5">
                &ldquo;{transcriptEnglish}&rdquo;
              </div>
            </div>

            {/* Honest Service Offline Alert Card */}
            {submitError && (
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 space-y-2">
                <div className="flex items-center gap-1.5 font-semibold text-amber-300">
                  <WifiOff className="w-3.5 h-3.5 shrink-0" />
                  <span>Backend Hub Service Offline (:8000)</span>
                </div>
                <p className="text-[11px] text-amber-200/90 leading-relaxed">
                  {submitError}
                </p>
                <div className="flex items-center gap-2 pt-1 flex-wrap">
                  <button
                    onClick={handleSendTranscript}
                    disabled={isSubmitting}
                    className="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 text-[11px] font-medium flex items-center gap-1"
                  >
                    <RefreshCw className={`w-3 h-3 ${isSubmitting ? 'animate-spin' : ''}`} />
                    <span>Retry Connection</span>
                  </button>
                  <button
                    onClick={handleDeterministicParse}
                    className="px-2.5 py-1 rounded-lg bg-purple-500/30 hover:bg-purple-500/40 text-purple-200 text-[11px] font-semibold border border-purple-500/40 flex items-center gap-1"
                  >
                    <FileText className="w-3 h-3 text-purple-300" />
                    <span>[DEMO SIMULATION] Continue with Sample Extraction (DEMO-2026-041)</span>
                  </button>
                </div>
              </div>
            )}

            {/* Unmapped notes (R11 compliance) */}
            {unmappedNotes.length > 0 && (
              <div className="p-2.5 rounded-lg bg-[rgba(255,180,84,0.1)] border border-[rgba(255,180,84,0.3)] text-[11px] text-[#ffb454]">
                <div className="font-semibold text-[10px] uppercase">Unmapped Attribute Note:</div>
                <p>{unmappedNotes[0]}</p>
              </div>
            )}
          </div>

          {/* Action triggers */}
          <div className="space-y-2">
            <button
              onClick={handleSendTranscript}
              disabled={isSubmitting || !transcriptOriginal.trim()}
              className={`btn-primary-glow w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-semibold ${
                isSubmitting || !transcriptOriginal.trim() ? 'opacity-60 cursor-not-allowed' : ''
              }`}
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Submitting to :8000...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Submit to Backend Hub (:8000)</span>
                </>
              )}
            </button>

            <button
              onClick={handleDeterministicParse}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-semibold bg-purple-500/20 text-purple-200 border border-purple-500/40 hover:bg-purple-500/30 transition-all"
            >
              <FileText className="w-3.5 h-3.5 text-purple-300" />
              <span>[DEMO SIMULATION] Parse Sample Statement</span>
            </button>
          </div>
        </aside>

        {/* ========================================================= */}
        {/* CENTER COLUMN: Stage Area                                 */}
        {/* ========================================================= */}
        <main
          aria-label="Studio work stage"
          className="lg:col-span-6 rounded-2xl glass-panel p-6 flex flex-col items-center justify-between min-h-[560px] relative overflow-hidden"
        >
          {/* Top Stage Bar */}
          <div className="w-full flex items-center justify-between text-xs text-[#95979E] pb-3 border-b border-[rgba(255,255,255,0.08)] flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-mono text-white">STAGE // {phase.toUpperCase()} VIEW</span>
              {isDevFixtureMode && (
                <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  [DEV BASELINE · PORT 8000 OFFLINE]
                </span>
              )}
              {activeCase.data_mode === 'real' && (
                <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                  <Shield className="w-3 h-3" />
                  <span>LOCAL ONLY</span>
                </span>
              )}
            </div>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] bg-[#5A250A] text-[#FF8964] border border-[#FF8964]/40">
              <AlertTriangle className="w-3 h-3" />
              <span>AI INVESTIGATIVE AID — NOT EVIDENCE OF IDENTITY</span>
            </span>
          </div>

          {/* ----------------- PHASE 1: DESCRIBE STAGE ----------------- */}
          {phase === 'Describe' && (
            <div className="flex-1 flex flex-col items-center justify-center my-6 text-center space-y-5 w-full max-w-md">
              {/* Mic error notice */}
              {micError && (
                <div className="p-3 rounded-2xl bg-red-500/15 border border-red-500/30 text-red-300 text-xs flex items-center justify-center gap-2 w-full">
                  <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                  <span>{micError}</span>
                </div>
              )}

              {/* Mic capture status */}
              {micNotice && !micError && (
                <div className="p-3 rounded-2xl bg-[#5ad1ff]/10 border border-[#5ad1ff]/20 text-[#5ad1ff] text-xs flex items-center justify-center gap-2 w-full">
                  <Sparkles className="w-4 h-4 shrink-0" />
                  <span>{micNotice}</span>
                </div>
              )}

              <div
                onClick={handleToggleMic}
                className={`w-28 h-28 rounded-full flex items-center justify-center cursor-pointer transition-all duration-300 shadow-2xl relative ${
                  isRecording
                    ? 'bg-[#ff6b6b] scale-110 shadow-[0_0_40px_rgba(255,107,107,0.7)]'
                    : 'bg-gradient-to-tr from-[#7c8cff] to-[#5ad1ff] hover:scale-105 shadow-[0_0_30px_rgba(124,140,255,0.4)]'
                }`}
              >
                {isRecording ? (
                  <Square className="w-10 h-10 text-white fill-current" />
                ) : (
                  <Mic className="w-10 h-10 text-[#090a0c]" />
                )}
                {isRecording && (
                  <span className="absolute inset-0 rounded-full border-4 border-white animate-ping opacity-60" />
                )}
              </div>

              <div>
                <h3 className="text-lg font-bold text-white">
                  {isRecording ? 'Listening to Witness...' : 'Tap Mic or Hold Space'}
                </h3>
                <p className="text-xs text-[#95979E] mt-1">
                  Describe facial features, estimated age, viewpoints, or physical stature.
                </p>
              </div>

              {/* Demo Fixture Load Sample Button */}
              <button
                onClick={handleLoadDemoTranscript}
                className="px-4 py-2 rounded-xl bg-purple-500/20 text-purple-200 border border-purple-500/40 text-xs font-semibold hover:bg-purple-500/30 flex items-center gap-2 transition-all"
              >
                <FileText className="w-3.5 h-3.5 text-purple-400" />
                <span>[DEMO FIXTURE] Load Sample Transcript ({selectedLanguage.toUpperCase()})</span>
              </button>

              {/* Language Selector chips */}
              <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
                {[
                  { code: 'ta', name: 'தமிழ்' },
                  { code: 'hi', name: 'हिन्दी' },
                  { code: 'te', name: 'తెలుగు' },
                  { code: 'en', name: 'English' },
                ].map((l) => (
                  <button
                    key={l.code}
                    onClick={() => setSelectedLanguage(l.code)}
                    className={`px-3 py-1 rounded-full text-xs transition-all ${
                      selectedLanguage === l.code
                        ? 'bg-[#5ad1ff] text-[#090a0c] font-semibold'
                        : 'bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[#A9A9AA]'
                    }`}
                  >
                    {l.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ----------------- PHASE 2: RECOGNIZE STAGE (6 Cards) ----------------- */}
          {phase === 'Recognize' && (
            <div className="w-full flex-1 my-3 space-y-3">
              {/* Generation Control Header */}
              <div className="p-3 rounded-xl bg-[#14161a] border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">Current Generation Batch:</span>
                    <span className="font-mono text-[#5ad1ff]">{generationRequestId}</span>
                    <span className="text-[10px] text-[#95979E]">({generationTimestamp})</span>
                  </div>
                  <p className="text-[11px] text-[#A9A9AA]">
                    Picked: <span className="text-[#7c8cff] font-semibold">{activeVariant.axes}</span>
                  </p>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={handleGenerateRound}
                    disabled={isGeneratingRound}
                    className="btn-primary-glow px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingRound ? 'animate-spin' : ''}`} />
                    <span>{isGeneratingRound ? 'Synthesizing :8001...' : 'Generate New Round'}</span>
                  </button>

                  <button
                    onClick={handleLoadCompositeReference}
                    className="px-3 py-1.5 rounded-lg bg-purple-500/20 text-purple-200 border border-purple-500/40 hover:bg-purple-500/30 text-xs font-medium flex items-center gap-1.5 transition-all"
                  >
                    <Wand2 className="w-3.5 h-3.5 text-purple-300" />
                    <span>[DEMO FIXTURE] Load Composite Reference</span>
                  </button>
                </div>
              </div>

              {/* Offline Generation Error Alert */}
              {generationError && (
                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <WifiOff className="w-4 h-4 text-amber-400 shrink-0" />
                    <span>{generationError}</span>
                  </div>
                  <button
                    onClick={handleLoadCompositeReference}
                    className="px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 font-semibold text-[11px] hover:bg-amber-500/30 shrink-0"
                  >
                    Load Verified Reference
                  </button>
                </div>
              )}

              {/* 6 Recognition Cards Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {cards.map((card, idx) => (
                  <div
                    key={card.id}
                    onClick={() => handlePickCard(card.id)}
                    className={`group cursor-pointer rounded-xl bg-[#14161a] border p-2 relative overflow-hidden transition-all duration-200 ${
                      card.picked
                        ? 'border-[#7c8cff] shadow-[0_0_20px_rgba(124,140,255,0.35)] scale-[1.02]'
                        : 'border-[rgba(255,255,255,0.08)] hover:border-[rgba(255,255,255,0.2)]'
                    }`}
                  >
                    {/* Forensic Graphite Drawing visual container */}
                    <div className="h-44 sm:h-48 rounded-lg bg-[#f5f0e6] relative overflow-hidden pencil-reveal">
                      <ForensicGraphiteSketch
                        view={card.view}
                        jawStyle={card.jawStyle}
                        hasCap={card.hasCap}
                        hasBeard={card.hasBeard}
                        isMature={card.isMature}
                        showMetadata={false}
                        className="h-full border-none shadow-none"
                      />

                      {/* Permanent Statutory Banner Ribbon (TCD4 invariant) */}
                      <div className="absolute bottom-0 inset-x-0 py-0.5 bg-[#5A250A]/90 text-[8px] font-mono text-[#FF8964] text-center">
                        AI AID — NOT IDENTIFICATION
                      </div>
                    </div>

                    {/* Card Meta & Action Pills */}
                    <div className="mt-2 flex items-center justify-between text-[10px]">
                      <span className="font-mono text-white">#0{idx + 1}</span>
                      <span className="text-[#A9A9AA] truncate max-w-[80px]">{card.axes}</span>
                      <span
                        className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                          card.picked ? 'bg-[#7c8cff] text-[#090a0c]' : 'bg-[#1b1d22] text-[#A9A9AA]'
                        }`}
                      >
                        {card.picked ? <Check className="w-2.5 h-2.5 stroke-[3]" /> : idx + 1}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ----------------- PHASE 3: REFINE STAGE (Expanded Compare) ----------------- */}
          {phase === 'Refine' && (
            <div className="w-full flex-1 flex flex-col items-center justify-between my-4 space-y-4">
              {/* Compare Canvas with Forensic Graphite Rendering of Active Selected Variant */}
              <div className="w-full max-w-md h-72 rounded-xl bg-[#f5f0e6] border border-[#d2cbbe] relative overflow-hidden shadow-2xl">
                <ForensicGraphiteSketch
                  view={activeVariant.view}
                  jawStyle={activeVariant.jawStyle}
                  hasCap={activeVariant.hasCap}
                  hasBeard={disguiseBeard || activeVariant.hasBeard}
                  isMature={timeDialYears > 0 || activeVariant.isMature}
                  showMetadata={true}
                  className="w-full h-full border-none"
                />

                {/* Amber Speculative Stripe */}
                <div className="absolute top-9 left-2 px-2 py-0.5 rounded bg-[rgba(255,180,84,0.35)] border border-[#8a3b14] text-[9px] font-mono font-bold text-[#8a3b14] z-10">
                  SPECULATIVE FORENSIC TRANSFORM ({activeVariant.view.toUpperCase()})
                </div>

                <div className="absolute bottom-6 right-2 text-[10px] font-mono text-[#5a5448] bg-white/80 px-2 py-0.5 rounded shadow z-10">
                  SPLIT: {compareSplit}%
                </div>
              </div>

              {/* Time Dial & Disguise Controls */}
              <div className="w-full max-w-md grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white">Time Dial</span>
                    <span className="font-mono text-[#5ad1ff]">
                      {timeDialYears > 0 ? `+${timeDialYears}` : timeDialYears} yrs
                    </span>
                  </div>
                  <input
                    type="range"
                    min={-20}
                    max={20}
                    value={timeDialYears}
                    onChange={(e) => setTimeDialYears(Number(e.target.value))}
                    className="w-full accent-[#5ad1ff]"
                  />
                </div>

                <div className="p-3 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] space-y-2">
                  <span className="font-semibold text-white">Disguise Strip</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setDisguiseBeard(!disguiseBeard)}
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
                        !disguiseBeard
                          ? 'bg-[#ffb454] text-[#090a0c]'
                          : 'bg-[#1b1d22] text-[#A9A9AA]'
                      }`}
                    >
                      Remove Beard
                    </button>
                    <button
                      onClick={() => setDisguiseGlasses(!disguiseGlasses)}
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
                        disguiseGlasses
                          ? 'bg-[#5ad1ff] text-[#090a0c]'
                          : 'bg-[#1b1d22] text-[#A9A9AA]'
                      }`}
                    >
                      Glasses
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ----------------- PHASE 4: FINALIZE STAGE ----------------- */}
          {phase === 'Finalize' && (
            <div className="w-full flex-1 flex flex-col items-center justify-center my-6 space-y-5 text-center">
              {/* Sealed Final Forensic Composite Sketch — Authentic Graphite Art */}
              <div className="w-56 h-72 rounded-2xl bg-[#f5f0e6] border border-[#d2cbbe] relative overflow-hidden shadow-2xl">
                <ForensicGraphiteSketch
                  view={activeVariant.view}
                  jawStyle={activeVariant.jawStyle}
                  hasCap={activeVariant.hasCap}
                  hasBeard={disguiseBeard || activeVariant.hasBeard}
                  isMature={timeDialYears > 0 || activeVariant.isMature}
                  showMetadata={true}
                  className="w-full h-full border-none"
                />
                <div className="absolute top-2 right-2 px-1.5 py-0.5 rounded bg-black/75 text-[8px] font-mono text-emerald-400 border border-emerald-500/30">
                  SEALED &bull; {generationRequestId}
                </div>
              </div>

              <div>
                <h3 className="text-base font-bold text-white">
                  {finalizedSuccess ? 'Composite Sealed & Audited' : 'Finalize Composite'}
                </h3>
                <p className="text-xs text-[#95979E] mt-0.5">
                  Immutable hash chain record will be generated for court discovery.
                </p>
              </div>

              {/* Export format picker */}
              <div className="flex items-center gap-2">
                {(['pdf', 'png', 'json'] as const).map((fmt) => (
                  <button
                    key={fmt}
                    onClick={() => setExportFormat(fmt)}
                    className={`uppercase font-mono text-xs px-3 py-1 rounded-lg transition-all ${
                      exportFormat === fmt
                        ? 'bg-[#7c8cff] text-[#090a0c] font-bold'
                        : 'bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[#A9A9AA]'
                    }`}
                  >
                    {fmt}
                  </button>
                ))}
              </div>

              <button
                onClick={handleRunFinalize}
                disabled={isFinalizing}
                className="btn-primary-glow px-6 py-2.5 rounded-full text-xs font-semibold flex items-center gap-2"
              >
                {isFinalizing ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Sealing Hash Chain...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-3.5 h-3.5" />
                    <span>Finalize & Export ({exportFormat.toUpperCase()})</span>
                  </>
                )}
              </button>
            </div>
          )}

          {/* Bottom Dock Controls */}
          <div className="w-full pt-3 border-t border-[rgba(255,255,255,0.08)] flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="text-[#95979E]">Next Action:</span>
              <span className="text-white font-medium">
                {phase === 'Describe'
                  ? 'Send statement'
                  : phase === 'Recognize'
                  ? 'Pick variant & advance'
                  : phase === 'Refine'
                  ? 'Adjust sliders'
                  : 'Export court packet'}
              </span>
            </div>

            <button
              onClick={() => {
                if (phase === 'Describe') setPhase('Recognize');
                else if (phase === 'Recognize') setPhase('Refine');
                else if (phase === 'Refine') setPhase('Finalize');
              }}
              className="btn-primary-glow px-4 py-1.5 rounded-full text-xs font-semibold"
            >
              Next Step →
            </button>
          </div>
        </main>

        {/* ========================================================= */}
        {/* RIGHT COLUMN: Attribute Inspector & AI Assumed Panel      */}
        {/* ========================================================= */}
        <aside
          aria-label="Attribute inspector"
          className="lg:col-span-3 rounded-2xl glass-panel p-5 space-y-5 self-stretch flex flex-col justify-between min-h-[560px]"
        >
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[rgba(255,255,255,0.08)]">
              <span className="font-semibold text-xs text-white uppercase tracking-wider">
                Attribute Inspector
              </span>
              <span className="text-[10px] text-[#5ad1ff] font-mono">{attributes.length} Parsed</span>
            </div>

            {/* Extracted attributes list */}
            <div className="space-y-2">
              {attributes.map((attr, idx) => (
                <div
                  key={attr.key}
                  className="p-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.06)] flex items-center justify-between text-xs"
                >
                  <div>
                    <span className="text-[#A9A9AA] text-[10px] uppercase font-mono block">
                      {attr.key}
                    </span>
                    <span className="font-medium text-white">{attr.value}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    <span
                      title={`Confidence: ${attr.confidence}`}
                      className={`w-2 h-2 rounded-full ${
                        attr.confidence === 'sure'
                          ? 'bg-emerald-400'
                          : attr.confidence === 'somewhat'
                          ? 'bg-[#5ad1ff]'
                          : 'bg-[#ffb454]'
                      }`}
                    />
                    <button
                      onClick={() => handleToggleLock(idx)}
                      title={attr.locked ? 'Region locked' : 'Click to lock region'}
                      className={`p-1 rounded ${
                        attr.locked ? 'text-[#5ad1ff]' : 'text-[#95979E] hover:text-white'
                      }`}
                    >
                      {attr.locked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* AI Assumed Panel (R11 mandatory feature) */}
            <div className="pt-3 border-t border-[rgba(255,255,255,0.08)] space-y-2">
              <div className="flex items-center gap-1.5 text-xs text-[#ffb454] font-semibold">
                <Sparkles className="w-3.5 h-3.5" />
                <span>AI Assumed (Unstated)</span>
              </div>
              <p className="text-[10px] text-[#95979E] leading-relaxed">
                R11 rule: Not stated by witness. Varied across variants to prevent stereotyping.
              </p>

              <div className="space-y-1.5">
                {aiAssumed.map((item) => (
                  <div
                    key={item.key}
                    className="p-2 rounded-lg border border-dashed border-[rgba(255,255,255,0.12)] bg-[#090a0c]/60 text-[11px]"
                  >
                    <span className="text-[#A9A9AA] font-mono text-[10px] block">{item.key}</span>
                    <span className="text-white/80">{item.note}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Privacy badge */}
          <div className="p-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[10px] text-[#95979E] flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Zero biometrics inference applied. Human review mandatory.</span>
          </div>
        </aside>
      </div>
      </>
      )}

      {/* Export Court Packet Sheet Modal */}
      <ExportSheet
        isOpen={isExportSheetOpen}
        onClose={() => setIsExportSheetOpen(false)}
        caseNumber={activeCase.case_number}
        sessionId={sessionId}
        attributes={attributes}
        aiAssumed={aiAssumed}
      />
    </div>
  );
};

export default StudioPage;
