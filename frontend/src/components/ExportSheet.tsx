import React, { useState, useEffect, useMemo } from 'react';
import {
  X,
  Download,
  FileText,
  Image as ImageIcon,
  Code,
  Layers,
  CheckCircle2,
  AlertTriangle,
  QrCode,
  Copy,
  Check,
  ShieldCheck,
} from 'lucide-react';
import { MANDATORY_DISCLAIMER } from '../pages/LandingPage';
import { apiClient } from '../api/client';
import { generateQRCode } from '../utils/qrCode';
import { generateBinaryPDF } from '../utils/pdfGenerator';
import { generateRasterPNG } from '../utils/imageExport';

export interface ExportSheetProps {
  isOpen: boolean;
  onClose: () => void;
  caseNumber: string;
  sessionId: string;
  attributes: Array<{ region: string; key: string; value: string; confidence: string }>;
  aiAssumed: Array<{ key: string; note: string }>;
}

export const LEGAL_CUSTODY_DISCLOSURE =
  'Notice: Cryptographic SHA-256 digest provides data integrity verification against accidental modification or tampering; it does not constitute an immutable distributed ledger or a statutory digital signature under Section 3 of the Information Technology Act.';

export const CANONICAL_MANIFEST_FIELDS = [
  'disclaimer',
  'case_number',
  'session_id',
  'format',
  'language',
  'include_alternates',
  'attributes',
  'ai_assumed',
  'model_versions',
] as const;

export const ExportSheet: React.FC<ExportSheetProps> = ({
  isOpen,
  onClose,
  caseNumber,
  sessionId,
  attributes,
  aiAssumed,
}) => {
  const [format, setFormat] = useState<'pdf' | 'png' | 'json' | 'svg'>('pdf');
  const [selectedLanguage, setSelectedLanguage] = useState<'en' | 'ta' | 'hi' | 'te' | 'kn' | 'ml' | 'bn'>('en');
  const [includeAlternates, setIncludeAlternates] = useState(true);
  const [sha256Hash, setSha256Hash] = useState<string>('');
  const [copiedHash, setCopiedHash] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportComplete, setExportComplete] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'attempting' | 'backend' | 'client_fallback' | null>(null);

  // Model provenance constant
  const modelVersions = useMemo(
    () => ({
      image_gen: 'sd15-lcm-v1.0 (local fp16)',
      llm_parser: 'qwen2.5-7b-instruct (ollama)',
      preference_model: 'bradley-terry-online-v1',
      verifier: 'insightface-adherence-v1',
    }),
    []
  );

  // Compute live deterministic SHA-256 integrity hash of canonical export manifest fields
  useEffect(() => {
    if (!isOpen) return;

    // Strict canonical payload (excluding volatile timestamps so SHA-256 is reproducible)
    const canonicalPayload = {
      ai_assumed: aiAssumed,
      attributes: attributes,
      case_number: caseNumber,
      disclaimer: MANDATORY_DISCLAIMER,
      format,
      include_alternates: includeAlternates,
      language: selectedLanguage,
      model_versions: modelVersions,
      session_id: sessionId,
    };

    const encoder = new TextEncoder();
    const data = encoder.encode(JSON.stringify(canonicalPayload));
    crypto.subtle.digest('SHA-256', data).then((buf) => {
      const hashArray = Array.from(new Uint8Array(buf));
      const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
      setSha256Hash(hashHex);
    });
  }, [isOpen, caseNumber, sessionId, format, selectedLanguage, includeAlternates, attributes, aiAssumed, modelVersions]);

  // Compute standards-compliant QR Code matrix
  const qrMatrix = useMemo(() => {
    if (!sha256Hash) return null;
    const origin = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : 'http://localhost:5173';
    const verificationUrl = `${origin}/#trust?verify=${sha256Hash}`;
    return generateQRCode(verificationUrl);
  }, [sha256Hash]);

  if (!isOpen) return null;

  const handleCopyHash = () => {
    if (sha256Hash) {
      navigator.clipboard.writeText(sha256Hash);
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2000);
    }
  };

  const handleTriggerDownload = async () => {
    setIsExporting(true);
    setBackendStatus('attempting');

    const filename = `VELORA_${caseNumber}_${sessionId.slice(0, 8)}.${format}`;
    let downloadBlob: Blob | null = null;

    // Try backend endpoint first
    try {
      const backendRes = await apiClient.post<{
        id: string;
        download_url: string;
        sha256: string;
      }>(
        `/cases/${caseNumber}/export`,
        {
          session_id: sessionId,
          format,
          language: selectedLanguage,
          include_alternates: includeAlternates,
          attributes,
          ai_assumed: aiAssumed,
          model_versions: modelVersions,
        },
        { caseId: caseNumber }
      );

      if (backendRes?.download_url) {
        // Backend available and returned download url
        setBackendStatus('backend');
      }
    } catch {
      // Backend is offline on port 8000; gracefully use client-side generator
      setBackendStatus('client_fallback');
    }

    try {
      if (format === 'pdf') {
        downloadBlob = generateBinaryPDF({
          caseNumber,
          sessionId,
          disclaimer: MANDATORY_DISCLAIMER,
          sha256Hash,
          language: selectedLanguage,
          timestamp: new Date().toISOString(),
          attributes,
          aiAssumed,
          modelVersions,
          legalNotice: LEGAL_CUSTODY_DISCLOSURE,
        });
      } else if (format === 'png') {
        downloadBlob = await generateRasterPNG({
          caseNumber,
          sessionId,
          disclaimer: MANDATORY_DISCLAIMER,
          sha256Hash,
          language: selectedLanguage,
          attributes,
          aiAssumed,
          legalNotice: LEGAL_CUSTODY_DISCLOSURE,
        });
      } else if (format === 'json') {
        const canonicalData = {
          demo_notice: 'DEMO DATA — NOT A REAL INCIDENT',
          disclaimer: MANDATORY_DISCLAIMER,
          case_number: caseNumber,
          session_id: sessionId,
          sha256: sha256Hash,
          format: 'json',
          language: selectedLanguage,
          include_alternates: includeAlternates,
          attributes,
          ai_assumed: aiAssumed,
          model_versions: modelVersions,
          canonical_fields: CANONICAL_MANIFEST_FIELDS,
          legal_notice: LEGAL_CUSTODY_DISCLOSURE,
          exported_at: new Date().toISOString(),
        };
        downloadBlob = new Blob([JSON.stringify(canonicalData, null, 2)], {
          type: 'application/json',
        });
      } else if (format === 'svg') {
        const svgContent = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="850" viewBox="0 0 600 850" style="background:#090a0c; font-family:sans-serif;">
  <rect x="0" y="0" width="600" height="40" fill="#5A250A"/>
  <text x="300" y="25" fill="#FFC1AD" font-size="10" font-weight="bold" text-anchor="middle">DEMO DATA — NOT A REAL INCIDENT · ${MANDATORY_DISCLAIMER}</text>
  <text x="40" y="80" fill="#ffffff" font-size="20" font-weight="bold">VELORA COURT COMPOSITE PACKET</text>
  <!-- Forensic Scanned Paper Canvas -->
  <rect x="180" y="145" width="240" height="325" rx="16" fill="#f5f0e6" stroke="#d2cbbe" stroke-width="1.5"/>
  <!-- Head & Jaw Contour (sharp angular jaw) -->
  <path d="M 240,240 C 240,185 360,185 360,240 C 360,310 338,380 300,410 C 262,380 240,310 240,240 Z" fill="#eee7d8" stroke="#4a4235" stroke-width="2.5"/>
  <!-- Hair & Temple Hatching -->
  <path d="M 235,230 C 238,175 362,175 365,230 C 352,205 320,195 300,196 C 275,195 248,206 235,230 Z" fill="#2d2720" stroke="#1f1a14" stroke-width="2"/>
  <!-- Defined Eyebrows -->
  <path d="M 260,265 C 272,258 285,260 292,267" stroke="#332c23" stroke-width="3" stroke-linecap="round" fill="none"/>
  <path d="M 308,267 C 315,260 328,258 340,265" stroke="#332c23" stroke-width="3" stroke-linecap="round" fill="none"/>
  <!-- Deep-Set Almond Eyes -->
  <ellipse cx="276" cy="280" rx="10" ry="5.5" fill="#fdfbf7" stroke="#4a4235" stroke-width="1.5"/>
  <circle cx="276" cy="280" r="3.5" fill="#2d2720"/>
  <ellipse cx="324" cy="280" rx="10" ry="5.5" fill="#fdfbf7" stroke="#4a4235" stroke-width="1.5"/>
  <circle cx="324" cy="280" r="3.5" fill="#2d2720"/>
  <!-- Straight Nose Bridge & Tip -->
  <path d="M 299,268 L 297,318 L 306,322" stroke="#6b5f4f" stroke-width="2" fill="none" stroke-linecap="round"/>
  <!-- Mouth & Lip Philtrum -->
  <path d="M 284,352 Q 300,356 316,352" stroke="#524739" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <path d="M 288,362 Q 300,366 312,362" stroke="#807260" stroke-width="1.5" fill="none" stroke-linecap="round"/>
  <rect x="40" y="500" width="520" height="190" rx="12" fill="#14161a" stroke="rgba(255,255,255,0.1)"/>
  <text x="60" y="530" fill="#5ad1ff" font-size="13" font-weight="bold">CONFIRMED ATTRIBUTES</text>
  ${attributes.map((a, i) => `<text x="60" y="${555 + i * 22}" fill="#f4f5f7" font-size="11">• ${a.key}: ${a.value} (${a.confidence})</text>`).join('\n  ')}
  <text x="40" y="720" fill="#6E7179" font-size="9">${LEGAL_CUSTODY_DISCLOSURE}</text>
</svg>`;
        downloadBlob = new Blob([svgContent], { type: 'image/svg+xml' });
      }

      if (downloadBlob) {
        const url = URL.createObjectURL(downloadBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }

      setExportComplete(true);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-title"
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-end sm:items-center justify-center p-0 sm:p-4 animate-in fade-in duration-200"
    >
      <div className="w-full max-w-2xl bg-[#0e0f12] border border-[rgba(255,255,255,0.12)] rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-[rgba(255,255,255,0.08)] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#7c8cff]/10 border border-[#7c8cff]/30 flex items-center justify-center text-[#7c8cff]">
              <Download className="w-5 h-5" />
            </div>
            <div>
              <h2 id="export-title" className="text-base font-bold text-white">
                Export Court-Admissible Packet
              </h2>
              <p className="text-xs text-[#95979E]">
                {caseNumber} · Session {sessionId.slice(0, 8)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-[#95979E] hover:text-white rounded-lg hover:bg-white/5 transition-colors"
            aria-label="Close export dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content body */}
        <div className="p-6 space-y-6 overflow-y-auto flex-1">
          {/* Statutory disclaimer alert (R11 Invariant) */}
          <div className="p-3 rounded-xl bg-[#5A250A]/40 border border-[#FF8964]/40 flex items-start gap-2.5 text-xs text-[#FFC1AD]">
            <AlertTriangle className="w-4 h-4 shrink-0 text-[#FF8964] mt-0.5" />
            <div>
              <span className="font-semibold block text-[#FF8964]">Mandatory Statutory Notice:</span>
              <span>{MANDATORY_DISCLAIMER}</span>
            </div>
          </div>

          {/* Format selection tiles */}
          <div>
            <label className="text-xs font-semibold text-white block mb-2">Export Format</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { id: 'pdf', label: 'PDF Packet', desc: 'Court docket ready', icon: FileText },
                { id: 'png', label: 'PNG Image', desc: 'Raster composite', icon: ImageIcon },
                { id: 'json', label: 'JSON Data', desc: 'Audit & metadata', icon: Code },
                { id: 'svg', label: 'Vector SVG', desc: 'Scale-independent', icon: Layers },
              ].map((item) => {
                const Icon = item.icon;
                const isSelected = format === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setFormat(item.id as any)}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      isSelected
                        ? 'border-[#7c8cff] bg-[#7c8cff]/10 text-white shadow-lg'
                        : 'border-[rgba(255,255,255,0.08)] bg-[#14161a] text-[#A9A9AA] hover:border-white/20'
                    }`}
                  >
                    <Icon className={`w-5 h-5 mb-2 ${isSelected ? 'text-[#7c8cff]' : 'text-[#95979E]'}`} />
                    <div className="font-semibold text-xs text-white">{item.label}</div>
                    <div className="text-[10px] text-[#95979E]">{item.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Regional language selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-white block mb-1.5">
                Docket Language
              </label>
              <select
                value={selectedLanguage}
                onChange={(e) => setSelectedLanguage(e.target.value as any)}
                className="w-full px-3 py-2 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.12)] text-xs text-white focus:outline-none focus:border-[#7c8cff]"
              >
                <option value="en">English (Official Court Standard)</option>
                <option value="ta">தமிழ் (Tamil)</option>
                <option value="hi">हिन्दी (Hindi)</option>
                <option value="te">తెలుగు (Telugu)</option>
                <option value="kn">ಕನ್ನಡ (Kannada)</option>
                <option value="ml">മലയാളம் (Malayalam)</option>
                <option value="bn">বাংলা (Bengali)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-white block mb-1.5">
                Composite Options
              </label>
              <label className="flex items-center gap-2 p-2 rounded-xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] text-xs text-[#f4f5f7] cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeAlternates}
                  onChange={(e) => setIncludeAlternates(e.target.checked)}
                  className="rounded text-[#7c8cff] focus:ring-0"
                />
                <span>Include rejected round alternates</span>
              </label>
            </div>
          </div>

          {/* Standards-compliant QR Code & SHA-256 seal */}
          <div className="p-4 rounded-2xl bg-[#14161a] border border-[rgba(255,255,255,0.08)] flex flex-col sm:flex-row items-center gap-4">
            {/* Standards-compliant QR Matrix Rendering */}
            <div className="w-24 h-24 p-2 bg-white rounded-xl shrink-0 flex items-center justify-center relative shadow">
              {qrMatrix ? (
                <svg
                  viewBox={`0 0 ${qrMatrix.size} ${qrMatrix.size}`}
                  className="w-full h-full text-black fill-current"
                  shapeRendering="crispEdges"
                >
                  {qrMatrix.modules.map((row, r) =>
                    row.map((active, c) =>
                      active ? <rect key={`${r}-${c}`} x={c} y={r} width={1} height={1} /> : null
                    )
                  )}
                </svg>
              ) : (
                <div className="text-[10px] text-gray-500">Generating QR...</div>
              )}
            </div>

            <div className="flex-1 w-full space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-white flex items-center gap-1.5">
                  <QrCode className="w-3.5 h-3.5 text-[#5ad1ff]" />
                  Cryptographic Seal (SHA-256)
                </span>
                <button
                  onClick={handleCopyHash}
                  className="text-[11px] text-[#7c8cff] hover:text-[#5ad1ff] flex items-center gap-1 font-mono transition-colors"
                >
                  {copiedHash ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <div className="p-2 rounded-lg bg-[#090a0c] font-mono text-[11px] text-[#A9A9AA] break-all select-all border border-[rgba(255,255,255,0.06)]">
                {sha256Hash || 'Computing verification digest...'}
              </div>
              <div className="text-[10px] text-[#95979E] flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                <span>Deterministic manifest SHA-256 with verifiable scannable QR reference.</span>
              </div>
            </div>
          </div>

          {/* Legal custody and evidentiary disclosure */}
          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 text-[10px] text-[#6E7179] space-y-1">
            <div className="font-semibold text-[#A9A9AA]">Canonical Preimage Fields:</div>
            <div className="font-mono text-[#95979E]">
              {CANONICAL_MANIFEST_FIELDS.join(' · ')}
            </div>
            <div className="pt-1 italic">{LEGAL_CUSTODY_DISCLOSURE}</div>
          </div>
        </div>

        {/* Footer actions */}
        <div className="p-5 border-t border-[rgba(255,255,255,0.08)] bg-[#090a0c]/80 flex items-center justify-between">
          <div className="text-xs text-[#95979E]">
            {exportComplete && (
              <span className="text-emerald-400 flex items-center gap-1 font-medium">
                <CheckCircle2 className="w-4 h-4" />
                <span>
                  {format.toUpperCase()} packet ready ({backendStatus === 'backend' ? 'Backend' : 'Client PDF/PNG'})
                </span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-medium text-[#95979E] hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleTriggerDownload}
              disabled={isExporting}
              className="btn-primary-glow px-6 py-2.5 rounded-xl text-xs font-semibold flex items-center gap-2"
            >
              {isExporting ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-[#090a0c] border-t-transparent rounded-full animate-spin" />
                  <span>Generating {format.toUpperCase()}...</span>
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  <span>Download {format.toUpperCase()}</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
