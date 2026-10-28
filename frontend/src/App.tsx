import React from 'react';

export const DISCLAIMER_V1 = 'AI-generated investigative aid — not a photograph, not evidence of identity.';

export function App(): React.ReactElement {
  return (
    <div className="flex flex-col min-h-screen">
      {/* Standing Disclaimer Banner */}
      <header
        role="banner"
        className="bg-amber-950/80 border-b border-amber-600/50 px-4 py-2.5 text-center text-amber-200 text-xs md:text-sm font-medium tracking-wide"
      >
        <span>{DISCLAIMER_V1}</span>
      </header>

      {/* Main Product Shell */}
      <main className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-2xl mx-auto">
        <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-8 shadow-xl backdrop-blur-sm w-full">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white mb-3">
            AI Witness-to-Face & Scene Platform
          </h1>
          <p className="text-slate-400 text-sm md:text-base leading-relaxed">
            VELORA Investigation Platform
          </p>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-3 text-center text-xs text-slate-500">
        VELORA Platform
      </footer>
    </div>
  );
}

export default App;
