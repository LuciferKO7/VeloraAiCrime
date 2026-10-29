import React, { useState, useEffect } from 'react';
import { LandingPage, MANDATORY_DISCLAIMER } from './pages/LandingPage';
import { CommandCenterPage, type CaseItem } from './pages/CommandCenterPage';
import { StudioPage } from './pages/StudioPage';
import { TrustCenterPage } from './pages/TrustCenterPage';
import { VelaLabPage } from './pages/VelaLabPage';
import { NavigationHeader, type ShellId } from './components/NavigationHeader';
import { AmbientBackground, type AmbientEventMode } from './components/AmbientBackground';
import { LoginSheet } from './components/LoginSheet';
import { CommandPalette } from './components/CommandPalette';
import { PresenterHUD } from './components/PresenterHUD';
import { WitnessMode } from './components/WitnessMode';
import { AlertTriangle } from 'lucide-react';
import type { UserRole } from './api/types';

export const DISCLAIMER_V1 = MANDATORY_DISCLAIMER;

interface AppProps {
  initialView?: ShellId | 'workspace' | 'vela-lab' | 'witness';
}

export function App({ initialView = 'landing' }: AppProps): React.ReactElement {
  // Normalize initial view
  const initialShell: ShellId | 'vela-lab' | 'witness' =
    initialView === 'workspace' ? 'cases' : initialView;
  const [activeShell, setActiveShell] = useState<ShellId | 'vela-lab' | 'witness'>(initialShell);

  // Authenticated user state
  const [currentUser, setCurrentUser] = useState<{
    username: string;
    role: UserRole;
  }>({
    username: 'investigator_1',
    role: 'investigator',
  });
  const [isLoginSheetOpen, setIsLoginSheetOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isPresenterHUDOpen, setIsPresenterHUDOpen] = useState(false);
  const [isWitnessModeActive, setIsWitnessModeActive] = useState(initialView === 'witness');
  const [studioInitialMode, setStudioInitialMode] = useState<'composite' | 'scene'>('composite');
  const [ambientTier, setAmbientTier] = useState<'high' | 'mid' | 'low'>('high');

  // Active investigation case and session
  const [activeCase, setActiveCase] = useState<CaseItem>({
    id: 'case-demo-001',
    case_number: 'DEMO-001',
    title: 'Commercial District Armed Robbery',
    station: 'Central Division Precinct 4',
    status: 'active',
    data_mode: 'demo',
    default_appearance_group: 'unspecified',
    updated_at: new Date().toISOString(),
  });
  const [activeSessionId, setActiveSessionId] = useState('SES-2026-0814');

  // Ambient mode ('demo' | 'local' | 'alert')
  const [ambientMode, setAmbientMode] = useState<'demo' | 'local' | 'alert'>('demo');
  const [integrityValid, setIntegrityValid] = useState<boolean | null>(null);
  const eventMode: AmbientEventMode = 'idle';

  // Global Shift+P and Ctrl+K shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.shiftKey && e.key.toUpperCase() === 'P') {
        e.preventDefault();
        setIsPresenterHUDOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Sync ambient mode to html data-mode attribute per FRONTEND_DESIGN.md §3.1
  useEffect(() => {
    const htmlEl = document.documentElement;
    if (ambientMode === 'local') {
      htmlEl.setAttribute('data-mode', 'local');
    } else if (ambientMode === 'alert') {
      htmlEl.setAttribute('data-mode', 'alert');
    } else {
      htmlEl.removeAttribute('data-mode');
    }
  }, [ambientMode]);

  const handleOpenStudioSession = (
    sessionId: string,
    caseItem: CaseItem,
    initialMode: 'composite' | 'scene' = 'composite'
  ) => {
    setActiveCase(caseItem);
    setActiveSessionId(sessionId);
    setStudioInitialMode(initialMode);
    setActiveShell('studio');
    setAmbientMode(caseItem.data_mode === 'real' ? 'local' : 'demo');
  };

  const handleSetGlobalDataMode = (mode: 'demo' | 'real' | 'alert') => {
    if (mode === 'real') setAmbientMode('local');
    else if (mode === 'alert') setAmbientMode('alert');
    else setAmbientMode('demo');
  };

  if (isWitnessModeActive || activeShell === 'witness') {
    return (
      <WitnessMode
        caseNumber={activeCase.case_number}
        onExitWitnessMode={() => {
          setIsWitnessModeActive(false);
          setActiveShell('cases');
        }}
      />
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-[#090a0c] text-[#f4f5f7] font-sans antialiased relative selection:bg-[#FF8964]/30 selection:text-white">
      {/* 1. Global Ambient Background System (Mounted once in root per §4) */}
      <AmbientBackground eventMode={eventMode} />

      {/* 2. Persistent Standing Mandatory Disclaimer Banner (Non-overlapping) */}
      <header
        role="banner"
        className="w-full bg-[#5A250A] border-b border-[#FF8964]/40 px-4 py-2 sm:py-2.5 text-center text-[#FFC1AD] text-xs sm:text-sm font-medium tracking-wide shadow-md flex items-center justify-center gap-2 z-50 relative"
      >
        <AlertTriangle className="w-4 h-4 shrink-0 text-[#FF8964]" aria-hidden="true" />
        <span className="leading-snug">{DISCLAIMER_V1}</span>
      </header>

      {/* 3. Global Navigation Header (Across the Four Shells per §2) */}
      <NavigationHeader
        activeShell={activeShell as ShellId}
        onSelectShell={(shell) => setActiveShell(shell)}
        currentUser={currentUser}
        integrityValid={integrityValid}
        onOpenLoginSheet={() => setIsLoginSheetOpen(true)}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
      />

      {/* 4. Four-Shell View Router */}
      <div className="flex-1 flex flex-col">
        {/* Shell 1: Landing Page */}
        {activeShell === 'landing' && (
          <LandingPage
            onEnterWorkspace={() => {
              setActiveShell('cases');
            }}
          />
        )}

        {/* Shell 2: Command Center */}
        {activeShell === 'cases' && (
          <CommandCenterPage
            onOpenStudioSession={handleOpenStudioSession}
            onSetGlobalDataMode={handleSetGlobalDataMode}
          />
        )}

        {/* Shell 3: Studio Core Workflow */}
        {activeShell === 'studio' && (
          <StudioPage
            activeCase={activeCase}
            sessionId={activeSessionId}
            initialMode={studioInitialMode}
          />
        )}

        {/* Shell 4: Trust & Governance Center */}
        {activeShell === 'trust' && (
          <TrustCenterPage
            onSetGlobalDataMode={handleSetGlobalDataMode}
            onIntegrityChange={setIntegrityValid}
          />
        )}

        {/* Dev-Only: Vela State Machine Laboratory (TCD8) */}
        {activeShell === 'vela-lab' && (
          <VelaLabPage
            onBackToApp={() => setActiveShell('landing')}
          />
        )}
      </div>

      {/* 5. Login Sheet Modal (Glass sheet slides up over view per §6.2) */}
      <LoginSheet
        isOpen={isLoginSheetOpen}
        onClose={() => setIsLoginSheetOpen(false)}
        onLoginSuccess={(user) => {
          setCurrentUser(user);
          setActiveShell('cases');
        }}
      />

      {/* 6. Global Command Palette (Cmd+K) */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={(shell) => setActiveShell(shell)}
        onToggleWitnessMode={() => setIsWitnessModeActive((prev) => !prev)}
        onTogglePresenterHUD={() => setIsPresenterHUDOpen((prev) => !prev)}
        onToggleLowPower={() =>
          setAmbientTier((prev) => (prev === 'low' ? 'high' : 'low'))
        }
        onSelectLanguage={(_lang) => {
          // Language change handler
        }}
      />

      {/* 7. Presenter Telemetry HUD (Shift+P) */}
      <PresenterHUD
        isOpen={isPresenterHUDOpen}
        onClose={() => setIsPresenterHUDOpen(false)}
        ambientTier={ambientTier}
      />
    </div>
  );
}

export default App;
