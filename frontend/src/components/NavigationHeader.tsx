import React from 'react';
import {
  FolderKanban,
  Palette,
  ShieldCheck,
  Home,
  User,
  Search,
} from 'lucide-react';
import type { UserRole } from '../api/types';

export type ShellId = 'landing' | 'cases' | 'studio' | 'trust';

interface NavigationHeaderProps {
  activeShell: ShellId;
  onSelectShell: (shell: ShellId) => void;
  currentUser?: {
    username: string;
    role: UserRole;
  };
  healthStatus?: 'healthy' | 'degraded' | 'unreachable';
  integrityValid?: boolean | null;
  onOpenLoginSheet?: () => void;
  onOpenCommandPalette?: () => void;
}

/**
 * NavigationHeader
 *
 * Global navigation across the Four Shells per FRONTEND_DESIGN.md §2.
 * Shells: Landing (/) · Command Center (/cases) · Studio (/studio) · Trust Center (/trust)
 * Role-aware and displays live system health / integrity status.
 */
export const NavigationHeader: React.FC<NavigationHeaderProps> = ({
  activeShell,
  onSelectShell,
  currentUser = { username: 'investigator_1', role: 'investigator' },
  integrityValid = null,
  onOpenLoginSheet,
  onOpenCommandPalette,
}) => {
  return (
    <nav
      aria-label="Application Header"
      className="sticky top-0 z-40 bg-[rgba(14,15,18,0.85)] backdrop-blur-md border-b border-[rgba(255,255,255,0.08)] px-4 sm:px-6 py-2.5 flex items-center justify-between"
    >
      {/* Brand Lockup + Shell Nav */}
      <div className="flex items-center gap-6">
        <button
          onClick={() => onSelectShell('landing')}
          className="flex items-center gap-2.5 text-white focus:outline-none focus:ring-2 focus:ring-[#7c8cff] rounded-lg px-1 py-0.5"
        >
          <div className="w-7 h-7 rounded-lg bg-[#14161a] border border-[rgba(255,255,255,0.12)] flex items-center justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-gradient-to-tr from-[#7c8cff] to-[#5ad1ff]" />
          </div>
          <span className="font-semibold tracking-widest text-sm text-white">
            VELORA
          </span>
        </button>

        {/* 4 Shells Switcher */}
        <div className="hidden md:flex items-center gap-1 p-1 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.06)] text-xs">
          <button
            onClick={() => onSelectShell('landing')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeShell === 'landing'
                ? 'bg-[rgba(255,255,255,0.1)] text-white shadow-sm'
                : 'text-[#A9A9AA] hover:text-white'
            }`}
          >
            <Home className="w-3.5 h-3.5" />
            <span>Landing</span>
          </button>

          <button
            onClick={() => onSelectShell('cases')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeShell === 'cases'
                ? 'bg-[rgba(255,255,255,0.1)] text-white shadow-sm'
                : 'text-[#A9A9AA] hover:text-white'
            }`}
          >
            <FolderKanban className="w-3.5 h-3.5 text-[#5ad1ff]" />
            <span>Command Center</span>
          </button>

          <button
            onClick={() => onSelectShell('studio')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeShell === 'studio'
                ? 'bg-[rgba(255,255,255,0.1)] text-white shadow-sm'
                : 'text-[#A9A9AA] hover:text-white'
            }`}
          >
            <Palette className="w-3.5 h-3.5 text-[#7c8cff]" />
            <span>Studio</span>
          </button>

          {/* Trust Center (Auditor / Supervisor / Admin) */}
          <button
            onClick={() => onSelectShell('trust')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium transition-all ${
              activeShell === 'trust'
                ? 'bg-[rgba(255,255,255,0.1)] text-white shadow-sm'
                : 'text-[#A9A9AA] hover:text-white'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Trust Center</span>
          </button>
        </div>
      </div>

      {/* Right User & System Status Strip */}
      <div className="flex items-center gap-3 text-xs">
        {/* Integrity status dot */}
        <div
          title={
            integrityValid === true
              ? 'Audit Hash Chain Verified via Backend Hub'
              : integrityValid === false
              ? 'Audit Chain Verification Failed'
              : 'Audit Chain Unverified (Verification Pending)'
          }
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[11px]"
        >
          <span
            className={`w-2 h-2 rounded-full ${
              integrityValid === true
                ? 'bg-emerald-400'
                : integrityValid === false
                ? 'bg-[#ff6b6b]'
                : 'bg-[#ffb454]'
            } animate-pulse`}
          />
          <span className="hidden sm:inline text-[#A9A9AA]">
            {integrityValid === true
              ? 'Chain Intact'
              : integrityValid === false
              ? 'Tamper Alert'
              : 'Unverified'}
          </span>
        </div>

        {/* Command Palette Trigger */}
        {onOpenCommandPalette && (
          <button
            onClick={onOpenCommandPalette}
            className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[#A9A9AA] hover:text-white hover:border-white/20 transition-colors"
            title="Open Command Palette (Cmd+K)"
          >
            <Search className="w-3.5 h-3.5 text-[#7c8cff]" />
            <span className="text-[11px]">Search</span>
            <kbd className="px-1 py-0.2 rounded bg-[rgba(255,255,255,0.08)] text-[9px] font-mono">⌘K</kbd>
          </button>
        )}

        {/* User Role Badge */}
        <div className="flex items-center gap-2 pl-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#14161a] border border-[rgba(255,255,255,0.08)]">
            <User className="w-3.5 h-3.5 text-[#5ad1ff]" />
            <span className="font-medium text-white">{currentUser.username}</span>
            <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-[rgba(255,255,255,0.08)] text-[#A9A9AA]">
              {currentUser.role}
            </span>
          </div>

          {onOpenLoginSheet && (
            <button
              onClick={onOpenLoginSheet}
              className="px-2.5 py-1 rounded-lg text-[11px] text-[#A9A9AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)]"
            >
              Switch User
            </button>
          )}
        </div>
      </div>
    </nav>
  );
};

export default NavigationHeader;
