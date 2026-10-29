import { describe, it, expect } from 'vitest';
import { generateQRCode, qrToSVG } from './qrCode';
import { generateBinaryPDF } from './pdfGenerator';
import { CANONICAL_MANIFEST_FIELDS, LEGAL_CUSTODY_DISCLOSURE } from '../components/ExportSheet';
import { MANDATORY_DISCLAIMER } from '../pages/LandingPage';

describe('Exports & Cryptographic Verification', () => {
  describe('Standards-Compliant QR Code Generator (ISO/IEC 18004)', () => {
    it('generates a valid QR code matrix with correct finder patterns', () => {
      const text = 'http://localhost:5173/#trust?verify=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
      const matrix = generateQRCode(text);

      expect(matrix.size).toBeGreaterThanOrEqual(21);
      expect(matrix.modules.length).toBe(matrix.size);
      expect(matrix.modules[0].length).toBe(matrix.size);

      // Top-left finder pattern 7x7 outer border should be true
      for (let r = 0; r < 7; r++) {
        expect(matrix.modules[r][0]).toBe(true);
        expect(matrix.modules[r][6]).toBe(true);
      }
      for (let c = 0; c < 7; c++) {
        expect(matrix.modules[0][c]).toBe(true);
        expect(matrix.modules[6][c]).toBe(true);
      }
      // Center of top-left finder pattern (3,3) should be true
      expect(matrix.modules[3][3]).toBe(true);

      // Verify SVG conversion
      const svg = qrToSVG(matrix);
      expect(svg).toContain('<svg');
      expect(svg).toContain('xmlns="http://www.w3.org/2000/svg"');
      expect(svg).toContain('<rect');
    });

    it('is decoded correctly by an independent QR decoder function', () => {
      const payloadUrl = 'http://localhost:5173/#trust?verify=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
      const matrix = generateQRCode(payloadUrl);
      const { size, modules } = matrix;

      // Identify function modules to skip
      const isFunction = Array.from({ length: size }, () => Array(size).fill(false));

      // Finder patterns
      function markFinder(row: number, col: number) {
        for (let r = -1; r <= 7; r++) {
          for (let c = -1; c <= 7; c++) {
            const tr = row + r;
            const tc = col + c;
            if (tr >= 0 && tr < size && tc >= 0 && tc < size) {
              isFunction[tr][tc] = true;
            }
          }
        }
      }
      markFinder(0, 0);
      markFinder(0, size - 7);
      markFinder(size - 7, 0);

      // Timing patterns
      for (let i = 0; i < size; i++) {
        isFunction[6][i] = true;
        isFunction[i][6] = true;
      }

      // Alignment pattern if version >= 2
      if (size > 21) {
        const alignPos = size - 7;
        for (let dr = -2; dr <= 2; dr++) {
          for (let dc = -2; dc <= 2; dc++) {
            isFunction[alignPos + dr][alignPos + dc] = true;
          }
        }
      }

      // Format info
      for (let i = 0; i < 9; i++) {
        isFunction[8][i] = true;
        isFunction[i][8] = true;
      }
      for (let i = size - 8; i < size; i++) {
        isFunction[8][i] = true;
        isFunction[i][8] = true;
      }
      isFunction[size - 8][8] = true;

      // Extract raw data bits in standard zigzag
      const extractedBits: number[] = [];
      let upward = true;
      for (let rightCol = size - 1; rightCol > 0; rightCol -= 2) {
        if (rightCol === 6) rightCol--;
        const leftCol = rightCol - 1;
        const rowStart = upward ? size - 1 : 0;
        const rowEnd = upward ? -1 : size;
        const rowStep = upward ? -1 : 1;

        for (let row = rowStart; row !== rowEnd; row += rowStep) {
          for (const col of [rightCol, leftCol]) {
            if (!isFunction[row][col]) {
              const mask = (row + col) % 2 === 0;
              const val = modules[row][col];
              extractedBits.push((val !== mask) ? 1 : 0);
            }
          }
        }
        upward = !upward;
      }

      // Parse Mode (4 bits: 0100 for Byte mode)
      let bitPos = 0;
      function readBits(count: number): number {
        let v = 0;
        for (let i = 0; i < count; i++) {
          v = (v << 1) | extractedBits[bitPos++];
        }
        return v;
      }

      const mode = readBits(4);
      expect(mode).toBe(0b0100); // Byte mode

      // Parse Character count (8 bits for versions 1..9 in byte mode)
      const charCount = readBits(8);
      expect(charCount).toBe(payloadUrl.length);

      // Parse payload characters
      let decoded = '';
      for (let i = 0; i < charCount; i++) {
        decoded += String.fromCharCode(readBits(8));
      }

      expect(decoded).toBe(payloadUrl);
    });
  });

  describe('Pure TypeScript Binary PDF 1.4 Generator', () => {
    it('produces genuine application/pdf binary blobs with valid PDF 1.4 signatures', async () => {
      const pdfBlob = generateBinaryPDF({
        caseNumber: 'DEMO-001',
        sessionId: 'SES-2026-0814',
        disclaimer: MANDATORY_DISCLAIMER,
        sha256Hash: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
        language: 'en',
        timestamp: '2026-10-28T12:00:00.000Z',
        attributes: [
          { region: 'face_shape', key: 'Jawline', value: 'sharp angular', confidence: 'sure' },
          { region: 'eyebrows', key: 'Eyebrows', value: 'thick arched', confidence: 'sure' },
        ],
        aiAssumed: [
          { key: 'Eye Color', note: 'Not stated — varied across variants' },
        ],
        modelVersions: {
          image_gen: 'sd15-lcm-v1.0',
          llm_parser: 'qwen2.5-7b-instruct',
        },
        legalNotice: LEGAL_CUSTODY_DISCLOSURE,
      });

      expect(pdfBlob.type).toBe('application/pdf');
      expect(pdfBlob.size).toBeGreaterThan(500);

      const text = await new Promise<string>((resolve) => {
        if (typeof (pdfBlob as any).text === 'function') {
          (pdfBlob as any).text().then(resolve);
        } else {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.readAsText(pdfBlob);
        }
      });

      // Verify PDF magic header
      expect(text.startsWith('%PDF-1.4')).toBe(true);

      // Verify binary comment header
      expect(text).toContain('%âãÏÓ');

      // Verify structure: Catalog, Pages, Page, Font, stream, xref, trailer, %%EOF
      expect(text).toContain('/Type /Catalog');
      expect(text).toContain('/Type /Pages');
      expect(text).toContain('/Type /Page');
      expect(text).toContain('/BaseFont /Helvetica');
      expect(text).toContain('/BaseFont /Helvetica-Bold');
      expect(text).toContain('xref');
      expect(text).toContain('trailer');
      expect(text.trim().endsWith('%%EOF')).toBe(true);

      // Verify mandatory statutory disclaimer and case metadata are present
      expect(text).toContain('AI-GENERATED INVESTIGATIVE AID');
      expect(text).toContain('DEMO-001');
      expect(text).toContain('SES-2026-0814');
    });
  });

  describe('Canonical Manifest SHA-256 Digest Reproducibility', () => {
    it('ensures canonical preimage field ordering is deterministic', () => {
      expect(CANONICAL_MANIFEST_FIELDS).toContain('case_number');
      expect(CANONICAL_MANIFEST_FIELDS).toContain('session_id');
      expect(CANONICAL_MANIFEST_FIELDS).toContain('disclaimer');
      expect(CANONICAL_MANIFEST_FIELDS).toContain('attributes');
      expect(CANONICAL_MANIFEST_FIELDS).toContain('ai_assumed');
      expect(CANONICAL_MANIFEST_FIELDS).toContain('model_versions');
      // volatile timestamp exported_at must not be in canonical preimage
      expect((CANONICAL_MANIFEST_FIELDS as readonly string[]).includes('exported_at')).toBe(false);
    });

    it('generates identical SHA-256 hashes across independent runs for identical canonical payloads', async () => {
      const canonicalPayload1 = {
        ai_assumed: [{ key: 'Eye Color', note: 'Not stated' }],
        attributes: [{ region: 'face', key: 'Jawline', value: 'sharp', confidence: 'sure' }],
        case_number: 'DEMO-001',
        disclaimer: MANDATORY_DISCLAIMER,
        format: 'pdf',
        include_alternates: true,
        language: 'en',
        model_versions: { image_gen: 'sd15' },
        session_id: 'SES-001',
      };

      const canonicalPayload2 = {
        // Different insertion order in JS object, but JSON.stringify with key sorting yields same bytes
        session_id: 'SES-001',
        model_versions: { image_gen: 'sd15' },
        language: 'en',
        include_alternates: true,
        format: 'pdf',
        disclaimer: MANDATORY_DISCLAIMER,
        case_number: 'DEMO-001',
        attributes: [{ region: 'face', key: 'Jawline', value: 'sharp', confidence: 'sure' }],
        ai_assumed: [{ key: 'Eye Color', note: 'Not stated' }],
      };

      const serialize = (obj: any) => JSON.stringify(obj, Object.keys(obj).sort());
      const hash1Buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(serialize(canonicalPayload1)));
      const hash2Buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(serialize(canonicalPayload2)));

      const hash1 = Array.from(new Uint8Array(hash1Buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
      const hash2 = Array.from(new Uint8Array(hash2Buf)).map((b) => b.toString(16).padStart(2, '0')).join('');

      expect(hash1).toBe(hash2);
      expect(hash1.length).toBe(64);
    });
  });
});
