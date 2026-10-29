import React, { useState } from 'react';
import { Shield, Lock, User, X, Globe, AlertCircle, ArrowRight, RefreshCw, WifiOff } from 'lucide-react';
import type { UserRole } from '../api/types';
import { apiClient } from '../api/client';
import { isApiError } from '../api/errors';

interface LoginSheetProps {
  isOpen: boolean;
  onClose: () => void;
  onLoginSuccess: (user: { username: string; role: UserRole }) => void;
}

export const LoginSheet: React.FC<LoginSheetProps> = ({
  isOpen,
  onClose,
  onLoginSuccess,
}) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isOffline, setIsOffline] = useState(false);
  const [selectedLang, setSelectedLang] = useState('English');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setIsOffline(false);

    if (!username.trim() || !password.trim()) {
      setErrorMsg('Please enter both username and password.');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await apiClient.login({
        username: username.trim(),
        password,
      });

      onLoginSuccess({
        username: response.user?.username || username.trim(),
        role: response.user?.role || 'investigator',
      });
      onClose();
    } catch (err: unknown) {
      const isNet = isApiError(err) ? err.isNetworkError : false;
      const msg = isApiError(err)
        ? err.message
        : err instanceof Error
        ? err.message
        : 'Authentication service request failed.';

      setErrorMsg(msg);
      if (
        isNet ||
        msg.toLowerCase().includes('network') ||
        msg.toLowerCase().includes('failed to fetch') ||
        msg.toLowerCase().includes('refused')
      ) {
        setIsOffline(true);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDevFixtureBypass = () => {
    let role: UserRole = 'investigator';
    const lower = username.toLowerCase();
    if (lower.includes('admin')) role = 'admin';
    else if (lower.includes('supervisor')) role = 'supervisor';
    else if (lower.includes('auditor')) role = 'auditor';
    else if (lower.includes('artist')) role = 'artist';

    onLoginSuccess({
      username: username.trim() || 'investigator_1',
      role,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Dimmed backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Glass Login Sheet */}
      <div className="relative w-full max-w-md rounded-3xl glass-panel-strong p-8 shadow-2xl z-10 text-left border border-[rgba(255,255,255,0.14)] animate-hero-eyebrow">
        {/* Top header */}
        <div className="flex items-center justify-between pb-4 border-b border-[rgba(255,255,255,0.08)] mb-6">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-[#7c8cff]/20 flex items-center justify-center text-[#7c8cff]">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">VELORA Access</h3>
              <p className="text-[10px] text-[#A9A9AA]">Role-Based Forensic Authentication</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setSelectedLang(selectedLang === 'English' ? 'தமிழ்' : 'English')}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-[#A9A9AA] hover:text-white"
            >
              <Globe className="w-3 h-3" />
              <span>{selectedLang}</span>
            </button>
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-[#A9A9AA] hover:text-white hover:bg-[rgba(255,255,255,0.06)]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {errorMsg && (
          <div className="mb-4 p-3 rounded-xl bg-[#ff6b6b]/15 border border-[#ff6b6b]/40 text-[#ff6b6b] text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {isOffline && (
          <div className="mb-4 p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 space-y-2">
            <div className="flex items-center gap-1.5 font-semibold text-amber-300">
              <WifiOff className="w-4 h-4 shrink-0" />
              <span>Authentication Service Offline (:8000)</span>
            </div>
            <p className="text-[11px] text-amber-200/90 leading-relaxed">
              The backend authentication endpoint <code className="px-1 py-0.5 rounded bg-black/40 font-mono text-[10px]">/api/v1/auth/login</code> on port 8000 is currently unreachable.
            </p>
            <div className="pt-1">
              <button
                type="button"
                onClick={handleDevFixtureBypass}
                className="w-full py-2 px-3 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-200 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
              >
                <span>[DEV FIXTURE] Proceed in Offline Evaluation Mode</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#A9A9AA] mb-1">
              Officer / User ID
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-[#A9A9AA] absolute left-3.5 top-3 pointer-events-none" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. investigator_1 or supervisor_1"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white placeholder-[#95979E] focus:outline-none focus:ring-2 focus:ring-[#7c8cff]"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-[#A9A9AA] mb-1">
              Security Token / Password
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-[#A9A9AA] absolute left-3.5 top-3 pointer-events-none" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white placeholder-[#95979E] focus:outline-none focus:ring-2 focus:ring-[#7c8cff]"
                required
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className={`btn-primary-glow w-full py-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 ${
                isSubmitting ? 'opacity-60 cursor-not-allowed' : ''
              }`}
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Connecting to :8000...</span>
                </>
              ) : (
                <>
                  <span>Authenticate into Workspace</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </form>

        <div className="mt-5 pt-4 border-t border-[rgba(255,255,255,0.08)] text-[10px] text-[#95979E] text-center">
          Available roles: investigator, supervisor, auditor, admin.
        </div>
      </div>
    </div>
  );
};

export default LoginSheet;
