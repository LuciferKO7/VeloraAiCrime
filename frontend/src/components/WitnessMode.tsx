import React, { useState, useRef, useEffect } from 'react';
import {
  Mic,
  Square,
  Sun,
  Moon,
  ArrowRight,
  LogOut,
  Sparkles,
  AlertCircle,
  FileText,
} from 'lucide-react';
import { Vela, type VelaState } from './Vela';
import { MANDATORY_DISCLAIMER } from '../pages/LandingPage';
import { ForensicGraphiteSketch } from './ForensicGraphiteSketch';
import {
  AudioRecordingSession,
  sendAudioForTranscription,
  DEMO_SAMPLE_TRANSCRIPTS,
} from '../utils/audioRecorder';

interface WitnessModeProps {
  onExitWitnessMode: () => void;
  caseNumber?: string;
  initialLanguage?: string;
}

const REGIONAL_PROMPTS: Record<
  string,
  {
    greeting: string;
    instructions: string;
    micPrompt: string;
    micRecording: string;
    nextStepPrompt: string;
    pick: string;
    reject: string;
  }
> = {
  ta: {
    greeting: 'வணக்கம். நீங்கள் பார்த்த நபரை விவரிக்கவும்.',
    instructions: 'அமைதியாக பேசுங்கள். நீங்கள் கூறுவதைக் கேட்டு வேலா படமாக வரையும்.',
    micPrompt: 'பேச தொடங்குங்கள்',
    micRecording: 'கேட்கிறது... நிறுத்துவதற்கு அழுத்தவும்',
    nextStepPrompt: 'பொருத்தமான உருவத்தை தேர்ந்தெடுக்கவும்',
    pick: 'இது பொருந்துகிறது',
    reject: 'வேறு காட்டுங்கள்',
  },
  hi: {
    greeting: 'नमस्ते। आपने जिस व्यक्ति को देखा, उसका विवरण दें।',
    instructions: 'कृपया स्पष्ट बोलें। आपके शब्दों के आधार पर वेला चित्र बनाएगी।',
    micPrompt: 'बोलना शुरू करें',
    micRecording: 'सुन रही हूँ... रोकने के लिए टैप करें',
    nextStepPrompt: 'कृपया सबसे मिलता-जुलता चेहरा चुनें',
    pick: 'यह सही लगता है',
    reject: 'अन्य दिखाएँ',
  },
  en: {
    greeting: 'Welcome. Please describe the person you witnessed.',
    instructions: 'Speak clearly in your own words. Vela will sketch as you speak.',
    micPrompt: 'Tap to Speak',
    micRecording: 'Listening... Tap to stop',
    nextStepPrompt: 'Select the face that most closely matches',
    pick: 'Looks Like This',
    reject: 'Show Alternates',
  },
};

export const WitnessMode: React.FC<WitnessModeProps> = ({
  onExitWitnessMode,
  caseNumber = 'DEMO-2026-041',
  initialLanguage = 'ta',
}) => {
  const [lang, setLang] = useState<'ta' | 'hi' | 'en'>(
    initialLanguage === 'hi' ? 'hi' : initialLanguage === 'en' ? 'en' : 'ta'
  );
  const [highContrast, setHighContrast] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [micStatusMessage, setMicStatusMessage] = useState<string | null>(null);
  const [micErrorMessage, setMicErrorMessage] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<string>('');
  const [velaState, setVelaState] = useState<VelaState>('idle');
  const [step, setStep] = useState<'speak' | 'choose'>('speak');
  const [selectedVariant, setSelectedVariant] = useState<number | null>(null);

  const sessionRef = useRef<AudioRecordingSession | null>(null);

  // Clean up microphone tracks on unmount
  useEffect(() => {
    return () => {
      sessionRef.current?.cleanupTracks();
    };
  }, []);

  const t = REGIONAL_PROMPTS[lang] || REGIONAL_PROMPTS.en;

  const handleToggleMic = async () => {
    setMicErrorMessage(null);
    setMicStatusMessage(null);

    if (!isRecording) {
      try {
        const session = new AudioRecordingSession();
        sessionRef.current = session;
        await session.start();
        setIsRecording(true);
        setVelaState('listening');
        setMicStatusMessage('Recording active — speak into your microphone...');
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Microphone initialization failed.';
        setMicErrorMessage(msg);
        setVelaState('wince');
      }
    } else {
      setIsRecording(false);
      setVelaState('thinking');

      try {
        if (!sessionRef.current) throw new Error('No active recording session.');
        const result = await sessionRef.current.stop();
        setMicStatusMessage(
          `Audio captured (${(result.sizeBytes / 1024).toFixed(1)} KB, ${result.durationSec}s). Contacting speech service...`
        );

        try {
          const resp = await sendAudioForTranscription(result.blob, lang);
          setTranscript(resp.text);
          setVelaState('proud');
          setTimeout(() => {
            setStep('choose');
          }, 900);
        } catch {
          // Honest offline speech handling
          const sample = DEMO_SAMPLE_TRANSCRIPTS[lang] || DEMO_SAMPLE_TRANSCRIPTS.en;
          setTranscript(sample.original);
          setMicStatusMessage(
            `Speech Service (:8002) is offline. Captured ${(result.sizeBytes / 1024).toFixed(1)} KB locally. Loaded regional demonstration sample.`
          );
          setVelaState('curious');
          setTimeout(() => {
            setStep('choose');
          }, 1400);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Error stopping recording.';
        setMicErrorMessage(msg);
        setVelaState('idle');
      }
    }
  };

  const handleLoadDemoTranscript = () => {
    const sample = DEMO_SAMPLE_TRANSCRIPTS[lang] || DEMO_SAMPLE_TRANSCRIPTS.en;
    setTranscript(sample.original);
    setMicErrorMessage(null);
    setMicStatusMessage(`Loaded verified [DEMO FIXTURE] ${sample.languageName} statement.`);
    setVelaState('curious');
    setTimeout(() => {
      setStep('choose');
    }, 700);
  };

  return (
    <div
      className={`min-h-screen flex flex-col justify-between p-4 sm:p-8 transition-colors select-none ${
        highContrast ? 'bg-black text-white' : 'bg-[#090a0c] text-[#f4f5f7]'
      }`}
    >
      {/* Top Header: Simple, high-contrast, accessibility toggles */}
      <header className="flex items-center justify-between pb-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-[#7c8cff]/20 border border-[#7c8cff]/40 flex items-center justify-center text-[#7c8cff] font-bold">
            V
          </div>
          <div>
            <h1 className="text-base sm:text-lg font-bold">VELORA Witness Companion</h1>
            <span className="text-xs text-[#95979E] font-mono">Case {caseNumber}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Language selector (≥48px touch target) */}
          <div className="flex items-center bg-white/5 rounded-2xl p-1 border border-white/10">
            {(['ta', 'hi', 'en'] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`min-w-[48px] min-h-[48px] px-3 rounded-xl text-sm font-semibold transition-colors ${
                  lang === l
                    ? 'bg-[#7c8cff] text-[#090a0c]'
                    : 'text-white/70 hover:text-white'
                }`}
              >
                {l === 'ta' ? 'தமிழ்' : l === 'hi' ? 'हिन्दी' : 'EN'}
              </button>
            ))}
          </div>

          {/* High Contrast Toggle (≥48px touch target) */}
          <button
            onClick={() => setHighContrast(!highContrast)}
            className="min-w-[48px] min-h-[48px] p-2.5 rounded-2xl bg-white/5 border border-white/10 text-white hover:bg-white/10 transition-colors flex items-center justify-center"
            title="Toggle high contrast"
            aria-label="Toggle high contrast"
          >
            {highContrast ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5" />}
          </button>

          {/* Exit Witness Mode */}
          <button
            onClick={onExitWitnessMode}
            className="min-w-[48px] min-h-[48px] px-4 rounded-2xl bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 text-xs font-semibold flex items-center gap-2 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Officer Exit</span>
          </button>
        </div>
      </header>

      {/* Main Task Focus (One Task Per Screen per §10) */}
      <main className="flex-1 flex flex-col items-center justify-center py-8 text-center max-w-2xl mx-auto w-full space-y-8">
        {/* Hero Character Companion */}
        <div className="flex flex-col items-center justify-center">
          <Vela
            state={velaState}
            size="hero"
            speechBubble={isRecording ? t.micRecording : t.greeting}
          />
        </div>

        {/* Step 1: Speak Task */}
        {step === 'speak' && (
          <div className="w-full space-y-6">
            <p className="text-base sm:text-lg text-white/90 font-medium px-4">
              {t.instructions}
            </p>

            {/* Mic Error Alert */}
            {micErrorMessage && (
              <div className="p-3 rounded-2xl bg-red-500/15 border border-red-500/30 text-red-300 text-xs flex items-center justify-center gap-2 max-w-md mx-auto">
                <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
                <span>{micErrorMessage}</span>
              </div>
            )}

            {/* Mic Status Banner */}
            {micStatusMessage && !micErrorMessage && (
              <div className="p-3 rounded-2xl bg-[#5ad1ff]/10 border border-[#5ad1ff]/20 text-[#5ad1ff] text-xs flex items-center justify-center gap-2 max-w-md mx-auto">
                <Sparkles className="w-4 h-4 shrink-0" />
                <span>{micStatusMessage}</span>
              </div>
            )}

            {/* Giant Mic Touch Button (≥48px, 120px orb) */}
            <div className="flex flex-col items-center justify-center gap-4">
              <button
                onClick={handleToggleMic}
                className={`w-32 h-32 sm:w-40 sm:h-40 rounded-full flex flex-col items-center justify-center gap-2 transition-all shadow-2xl active:scale-95 ${
                  isRecording
                    ? 'bg-red-500 text-white ring-8 ring-red-500/30 animate-pulse'
                    : 'bg-gradient-to-tr from-[#7c8cff] to-[#5ad1ff] text-[#090a0c] ring-8 ring-[#7c8cff]/20 hover:scale-105'
                }`}
                aria-label={isRecording ? 'Stop recording' : 'Start speaking'}
              >
                {isRecording ? (
                  <>
                    <Square className="w-10 h-10 fill-current" />
                    <span className="text-xs font-bold uppercase tracking-wider">Stop</span>
                  </>
                ) : (
                  <>
                    <Mic className="w-12 h-12" />
                    <span className="text-xs font-bold uppercase tracking-wider">{t.micPrompt}</span>
                  </>
                )}
              </button>

              {/* Explicit Demo Fixture Fallback Button */}
              <button
                onClick={handleLoadDemoTranscript}
                className="px-4 py-2 rounded-xl bg-purple-500/15 border border-purple-500/40 text-purple-300 text-xs font-medium hover:bg-purple-500/25 flex items-center gap-2 transition-all"
              >
                <FileText className="w-3.5 h-3.5 text-purple-400" />
                <span>[DEMO FIXTURE] Load Sample Transcript ({t.pick})</span>
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Choose Face Task */}
        {step === 'choose' && (
          <div className="w-full space-y-6">
            <h2 className="text-lg sm:text-xl font-bold text-white">{t.nextStepPrompt}</h2>

            {/* Transcript preview ribbon */}
            {transcript && (
              <div className="p-3 rounded-2xl bg-[#14161a] border border-white/10 text-xs text-[#A9A9AA] max-w-lg mx-auto">
                <span className="text-[#5ad1ff] font-semibold block mb-0.5">Witness Statement Reference:</span>
                "{transcript}"
              </div>
            )}

            {/* 3 Large Touch Face Cards with Authentic Forensic Graphite Art */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full">
              {[
                { num: 1, view: 'frontal' as const, jawStyle: 'sharp' as const, hasCap: false },
                { num: 2, view: 'profile' as const, jawStyle: 'sharp' as const, hasCap: false },
                { num: 3, view: 'frontal' as const, jawStyle: 'sharp' as const, hasCap: true },
              ].map((variant) => {
                const isSelected = selectedVariant === variant.num;
                return (
                  <button
                    key={variant.num}
                    onClick={() => setSelectedVariant(variant.num)}
                    className={`min-h-[220px] p-3 rounded-3xl border flex flex-col items-center justify-between transition-all active:scale-98 ${
                      isSelected
                        ? 'border-4 border-[#5ad1ff] bg-[#5ad1ff]/15 shadow-2xl scale-102'
                        : 'border-white/20 bg-white/5 hover:border-white/40'
                    }`}
                  >
                    <div className="w-full h-36 rounded-2xl bg-[#f5f0e6] relative overflow-hidden shadow">
                      <ForensicGraphiteSketch
                        view={variant.view}
                        jawStyle={variant.jawStyle}
                        hasCap={variant.hasCap}
                        showMetadata={false}
                        className="w-full h-full border-none"
                      />
                      <span className="absolute bottom-1 inset-x-0 text-[7px] text-[#FF8964] font-mono bg-[#5A250A]/90 py-0.5 text-center">
                        AI AID — NOT EVIDENCE
                      </span>
                    </div>

                    <div className="text-sm font-bold text-white mt-2">
                      Option #{variant.num} {variant.view === 'profile' ? '(Side Profile)' : variant.hasCap ? '(Low-profile Cap)' : '(Frontal View)'}
                    </div>

                    <div
                      className={`min-h-[40px] w-full mt-2 rounded-xl flex items-center justify-center font-bold text-xs ${
                        isSelected ? 'bg-[#5ad1ff] text-[#090a0c]' : 'bg-white/10 text-white'
                      }`}
                    >
                      {isSelected ? t.pick : 'Select'}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-center gap-4 pt-4">
              <button
                onClick={() => setStep('speak')}
                className="min-h-[48px] px-6 rounded-2xl bg-white/10 border border-white/20 text-white text-sm font-semibold hover:bg-white/20 transition-colors"
              >
                ← Speak More Details
              </button>
              <button
                onClick={() => {
                  setVelaState('proud');
                  setTimeout(() => onExitWitnessMode(), 1200);
                }}
                className="btn-primary-glow min-h-[48px] px-8 rounded-2xl text-sm font-bold flex items-center gap-2"
              >
                <span>Save Choice</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Persistent Statutory Banner Footer */}
      <footer className="text-center pt-4 border-t border-white/10 text-xs text-[#FFC1AD] font-mono">
        {MANDATORY_DISCLAIMER}
      </footer>
    </div>
  );
};
