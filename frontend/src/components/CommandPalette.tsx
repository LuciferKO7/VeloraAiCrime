import React, { useState, useEffect } from 'react';
import {
  Search,
  FolderOpen,
  Mic,
  Compass,
  Eye,
  Languages,
  ShieldCheck,
  Activity,
  Zap,
} from 'lucide-react';
import type { ShellId } from './NavigationHeader';

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (shell: ShellId) => void;
  onToggleWitnessMode: () => void;
  onTogglePresenterHUD: () => void;
  onToggleLowPower: () => void;
  onSelectLanguage: (lang: string) => void;
}

interface CommandAction {
  id: string;
  category: string;
  title: string;
  shortcut?: string;
  icon: React.ComponentType<{ className?: string }>;
  handler: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onNavigate,
  onToggleWitnessMode,
  onTogglePresenterHUD,
  onToggleLowPower,
  onSelectLanguage,
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Global Ctrl+K / Cmd+K keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else setQuery('');
      } else if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const actions: CommandAction[] = [
    {
      id: 'cmd-cases',
      category: 'Navigation',
      title: 'Open Command Center (Cases)',
      shortcut: 'G C',
      icon: FolderOpen,
      handler: () => {
        onNavigate('cases');
        onClose();
      },
    },
    {
      id: 'cmd-studio',
      category: 'Navigation',
      title: 'Start Composite Session (Studio)',
      shortcut: 'G S',
      icon: Mic,
      handler: () => {
        onNavigate('studio');
        onClose();
      },
    },
    {
      id: 'cmd-scene',
      category: 'Investigation',
      title: 'Open Crime Scene Diagram Editor',
      shortcut: 'G D',
      icon: Compass,
      handler: () => {
        onNavigate('studio');
        onClose();
      },
    },
    {
      id: 'cmd-witness',
      category: 'Mode',
      title: 'Toggle Large-Touch Witness Mode',
      shortcut: 'W',
      icon: Eye,
      handler: () => {
        onToggleWitnessMode();
        onClose();
      },
    },
    {
      id: 'cmd-trust',
      category: 'Governance',
      title: 'Verify Audit Trail & Trust Center',
      shortcut: 'G T',
      icon: ShieldCheck,
      handler: () => {
        onNavigate('trust');
        onClose();
      },
    },
    {
      id: 'cmd-hud',
      category: 'Telemetry',
      title: 'Toggle Presenter HUD (Live Latency)',
      shortcut: '⇧ P',
      icon: Activity,
      handler: () => {
        onTogglePresenterHUD();
        onClose();
      },
    },
    {
      id: 'cmd-low-power',
      category: 'Performance',
      title: 'Toggle Low-Power Visuals Tier',
      shortcut: 'L',
      icon: Zap,
      handler: () => {
        onToggleLowPower();
        onClose();
      },
    },
    {
      id: 'cmd-lang-ta',
      category: 'Regional Language',
      title: 'Switch Interface to Tamil (தமிழ்)',
      icon: Languages,
      handler: () => {
        onSelectLanguage('ta');
        onClose();
      },
    },
    {
      id: 'cmd-lang-hi',
      category: 'Regional Language',
      title: 'Switch Interface to Hindi (हिन्दी)',
      icon: Languages,
      handler: () => {
        onSelectLanguage('hi');
        onClose();
      },
    },
    {
      id: 'cmd-lang-en',
      category: 'Regional Language',
      title: 'Switch Interface to English',
      icon: Languages,
      handler: () => {
        onSelectLanguage('en');
        onClose();
      },
    },
  ];

  const filteredActions = actions.filter((act) =>
    act.title.toLowerCase().includes(query.toLowerCase()) ||
    act.category.toLowerCase().includes(query.toLowerCase())
  );

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cmd-palette-title"
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-md flex items-start justify-center pt-20 px-4 animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl bg-[#0e0f12] border border-[rgba(255,255,255,0.16)] rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="p-4 border-b border-[rgba(255,255,255,0.08)] flex items-center gap-3">
          <Search className="w-5 h-5 text-[#7c8cff] shrink-0" />
          <input
            id="cmd-palette-title"
            autoFocus
            type="text"
            placeholder="Type a command or jump anywhere... (Cmd+K)"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            className="w-full bg-transparent text-sm text-white placeholder-[#95979E] focus:outline-none"
          />
          <kbd className="px-2 py-0.5 rounded bg-[#14161a] border border-[rgba(255,255,255,0.1)] text-[10px] text-[#A9A9AA] font-mono">
            ESC
          </kbd>
        </div>

        {/* Command list */}
        <div className="max-h-80 overflow-y-auto p-2 divide-y divide-[rgba(255,255,255,0.02)]">
          {filteredActions.length === 0 ? (
            <div className="py-8 text-center text-xs text-[#95979E]">
              No matching commands found.
            </div>
          ) : (
            filteredActions.map((act, idx) => {
              const Icon = act.icon;
              const isSelected = idx === selectedIndex;
              return (
                <button
                  key={act.id}
                  onClick={act.handler}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`w-full p-2.5 rounded-xl flex items-center justify-between text-left transition-colors ${
                    isSelected ? 'bg-[#7c8cff]/15 text-white' : 'text-[#f4f5f7]/80 hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`w-4 h-4 ${isSelected ? 'text-[#7c8cff]' : 'text-[#95979E]'}`} />
                    <div>
                      <div className="text-xs font-medium text-white">{act.title}</div>
                      <div className="text-[10px] text-[#95979E] font-mono">{act.category}</div>
                    </div>
                  </div>
                  {act.shortcut && (
                    <kbd className="px-1.5 py-0.5 rounded bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[10px] text-[#A9A9AA] font-mono">
                      {act.shortcut}
                    </kbd>
                  )}
                </button>
              );
            })
          )}
        </div>

        {/* Footer shortcuts hint */}
        <div className="p-3 border-t border-[rgba(255,255,255,0.08)] bg-[#090a0c] flex items-center justify-between text-[11px] text-[#95979E]">
          <span className="flex items-center gap-2">
            <span>Navigation:</span>
            <kbd className="px-1 py-0.5 rounded bg-[#14161a] text-[10px] font-mono">↑</kbd>
            <kbd className="px-1 py-0.5 rounded bg-[#14161a] text-[10px] font-mono">↓</kbd>
            <span>to navigate</span>
            <kbd className="px-1 py-0.5 rounded bg-[#14161a] text-[10px] font-mono">↵</kbd>
            <span>to select</span>
          </span>
          <span className="font-mono text-[10px]">VELORA v1.1</span>
        </div>
      </div>
    </div>
  );
};
