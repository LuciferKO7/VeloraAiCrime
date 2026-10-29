/**
 * Pure TypeScript standards-compliant QR Code generator (ISO/IEC 18004).
 * Generates an exact 2D binary matrix suitable for SVG and Canvas rendering.
 */

// Galois Field GF(256) arithmetic for Reed-Solomon error correction
const EXP_TABLE = new Uint8Array(512);
const LOG_TABLE = new Uint8Array(256);

(function initGaloisField() {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    EXP_TABLE[i] = x;
    EXP_TABLE[i + 255] = x;
    LOG_TABLE[x] = i;
    x <<= 1;
    if (x & 256) {
      x ^= 0x11d; // Primitive polynomial x^8 + x^4 + x^3 + x^2 + 1
    }
  }
})();

function gfMul(x: number, y: number): number {
  if (x === 0 || y === 0) return 0;
  return EXP_TABLE[LOG_TABLE[x] + LOG_TABLE[y]];
}

function rsComputePoly(ecBytes: number): Uint8Array {
  let poly = new Uint8Array([1]);
  for (let i = 0; i < ecBytes; i++) {
    const nextPoly = new Uint8Array(poly.length + 1);
    const factor = EXP_TABLE[i];
    for (let j = 0; j < poly.length; j++) {
      nextPoly[j] ^= gfMul(poly[j], factor);
      nextPoly[j + 1] ^= poly[j];
    }
    poly = nextPoly;
  }
  return poly;
}

function rsEncode(data: Uint8Array, ecBytes: number): Uint8Array {
  const genPoly = rsComputePoly(ecBytes);
  const remainder = new Uint8Array(ecBytes);
  for (let i = 0; i < data.length; i++) {
    const factor = data[i] ^ remainder[0];
    for (let j = 0; j < ecBytes - 1; j++) {
      remainder[j] = remainder[j + 1] ^ gfMul(genPoly[genPoly.length - 1 - (j + 1)], factor);
    }
    remainder[ecBytes - 1] = gfMul(genPoly[0], factor);
  }
  return remainder;
}

// QR Code version parameters (Version 1..6, Error Correction Level M)
interface QRVersionConfig {
  version: number;
  size: number;
  totalCodewords: number;
  dataCodewords: number;
  ecCodewords: number;
  alignmentPattern?: number[];
}

const QR_VERSIONS: QRVersionConfig[] = [
  { version: 1, size: 21, totalCodewords: 26, dataCodewords: 16, ecCodewords: 10 },
  { version: 2, size: 25, totalCodewords: 44, dataCodewords: 28, ecCodewords: 16, alignmentPattern: [6, 18] },
  { version: 3, size: 29, totalCodewords: 70, dataCodewords: 44, ecCodewords: 26, alignmentPattern: [6, 22] },
  { version: 4, size: 33, totalCodewords: 100, dataCodewords: 64, ecCodewords: 36, alignmentPattern: [6, 26] },
  { version: 5, size: 37, totalCodewords: 134, dataCodewords: 86, ecCodewords: 48, alignmentPattern: [6, 30] },
  { version: 6, size: 41, totalCodewords: 172, dataCodewords: 108, ecCodewords: 64, alignmentPattern: [6, 34] },
];

export interface QRCodeMatrix {
  size: number;
  modules: boolean[][];
}

/**
 * Encodes text into a standard QR code matrix.
 */
export function generateQRCode(text: string): QRCodeMatrix {
  const encoder = new TextEncoder();
  const textBytes = encoder.encode(text);

  // Pick appropriate version based on text length (Byte mode: mode indicator 4 bits, count indicator 8 bits)
  let selectedVersion: QRVersionConfig | null = null;
  for (const v of QR_VERSIONS) {
    const maxDataBytes = v.dataCodewords - 2; // header overhead ~ 2 bytes
    if (textBytes.length <= maxDataBytes) {
      selectedVersion = v;
      break;
    }
  }

  if (!selectedVersion) {
    selectedVersion = QR_VERSIONS[QR_VERSIONS.length - 1];
  }

  const { size, dataCodewords, ecCodewords, alignmentPattern } = selectedVersion;

  // Build bitstream: Mode (0100 for Byte mode) + Character Count (8 bits for v1-9) + data
  const bits: number[] = [];
  function pushBits(val: number, len: number) {
    for (let i = len - 1; i >= 0; i--) {
      bits.push((val >> i) & 1);
    }
  }

  // Byte mode indicator: 0100
  pushBits(0b0100, 4);
  // Character count: 8 bits
  pushBits(textBytes.length, 8);
  // Data bytes
  for (let i = 0; i < textBytes.length; i++) {
    pushBits(textBytes[i], 8);
  }

  // Terminator (up to 4 zeroes)
  const remainingDataBits = dataCodewords * 8 - bits.length;
  const termLength = Math.min(4, Math.max(0, remainingDataBits));
  pushBits(0, termLength);

  // Pad to multiple of 8 bits
  while (bits.length % 8 !== 0) {
    bits.push(0);
  }

  // Pad bytes: 0xEC, 0x11
  const padPatterns = [0xec, 0x11];
  let padIdx = 0;
  while (bits.length < dataCodewords * 8) {
    pushBits(padPatterns[padIdx % 2], 8);
    padIdx++;
  }

  // Convert bits to data codewords
  const dataBytes = new Uint8Array(dataCodewords);
  for (let i = 0; i < dataCodewords; i++) {
    let byteVal = 0;
    for (let b = 0; b < 8; b++) {
      byteVal = (byteVal << 1) | bits[i * 8 + b];
    }
    dataBytes[i] = byteVal;
  }

  // Compute Reed-Solomon Error Correction bytes
  const ecBytes = rsEncode(dataBytes, ecCodewords);

  // Combine data + EC codewords
  const finalCodewords = new Uint8Array(dataCodewords + ecCodewords);
  finalCodewords.set(dataBytes, 0);
  finalCodewords.set(ecBytes, dataCodewords);

  // Initialize Matrix with undefined/null
  const modules: (boolean | null)[][] = Array.from({ length: size }, () => Array(size).fill(null));

  // Helper to place finder pattern at (r, c)
  function placeFinder(row: number, col: number) {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const tr = row + r;
        const tc = col + c;
        if (tr >= 0 && tr < size && tc >= 0 && tc < size) {
          if (r >= 0 && r <= 6 && c >= 0 && c <= 6) {
            modules[tr][tc] = (r === 0 || r === 6 || c === 0 || c === 6 || (r >= 2 && r <= 4 && c >= 2 && c <= 4));
          } else {
            modules[tr][tc] = false; // separator
          }
        }
      }
    }
  }

  // Place 3 Finder Patterns
  placeFinder(0, 0);
  placeFinder(0, size - 7);
  placeFinder(size - 7, 0);

  // Place Timing Patterns
  for (let i = 8; i < size - 8; i++) {
    modules[6][i] = i % 2 === 0;
    modules[i][6] = i % 2 === 0;
  }

  // Place Alignment Pattern if required
  if (alignmentPattern) {
    for (const r of alignmentPattern) {
      for (const c of alignmentPattern) {
        if (modules[r][c] !== null) continue;
        for (let dr = -2; dr <= 2; dr++) {
          for (let dc = -2; dc <= 2; dc++) {
            const isBorder = Math.abs(dr) === 2 || Math.abs(dc) === 2;
            const isCenter = dr === 0 && dc === 0;
            modules[r + dr][c + dc] = isBorder || isCenter;
          }
        }
      }
    }
  }

  // Reserve format information areas
  for (let i = 0; i < 9; i++) {
    if (modules[8][i] === null) modules[8][i] = false;
    if (modules[i][8] === null) modules[i][8] = false;
  }
  for (let i = size - 8; i < size; i++) {
    if (modules[8][i] === null) modules[8][i] = false;
    if (modules[i][8] === null) modules[i][8] = false;
  }
  // Dark module
  modules[size - 8][8] = true;

  // Place data bits in zigzag scan
  const allBits: number[] = [];
  for (let i = 0; i < finalCodewords.length; i++) {
    for (let b = 7; b >= 0; b--) {
      allBits.push((finalCodewords[i] >> b) & 1);
    }
  }

  let bitIdx = 0;
  let upward = true;
  for (let rightCol = size - 1; rightCol > 0; rightCol -= 2) {
    if (rightCol === 6) rightCol--; // Skip vertical timing column
    const leftCol = rightCol - 1;

    const rowStart = upward ? size - 1 : 0;
    const rowEnd = upward ? -1 : size;
    const rowStep = upward ? -1 : 1;

    for (let row = rowStart; row !== rowEnd; row += rowStep) {
      for (const col of [rightCol, leftCol]) {
        if (modules[row][col] === null) {
          const bit = bitIdx < allBits.length ? allBits[bitIdx++] : 0;
          // Apply Mask 0: (row + col) % 2 === 0
          const mask = (row + col) % 2 === 0;
          modules[row][col] = (bit === 1) !== mask;
        }
      }
    }
    upward = !upward;
  }

  // Format info bits for Level M, Mask 0: 0x5412 (standard pre-computed with BCH 15,5)
  // Format info string for (EC M = 00, Mask 0 = 000) => 101010000010010
  const formatBits = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0];
  // Place top-left format bits
  for (let i = 0; i < 6; i++) modules[8][i] = formatBits[i] === 1;
  modules[8][7] = formatBits[6] === 1;
  modules[8][8] = formatBits[7] === 1;
  modules[7][8] = formatBits[8] === 1;
  for (let i = 0; i < 6; i++) modules[5 - i][8] = formatBits[9 + i] === 1;

  // Place bottom and right format bits
  for (let i = 0; i < 7; i++) modules[size - 1 - i][8] = formatBits[i] === 1;
  for (let i = 0; i < 8; i++) modules[8][size - 8 + i] = formatBits[7 + i] === 1;

  return {
    size,
    modules: modules.map((row) => row.map((m) => !!m)),
  };
}

/**
 * Renders QR Code matrix to an SVG path string or SVG string.
 */
export function qrToSVG(matrix: QRCodeMatrix, pixelSize = 4): string {
  const { size, modules } = matrix;
  const dimension = size * pixelSize;
  let rects = '';
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (modules[r][c]) {
        rects += `<rect x="${c * pixelSize}" y="${r * pixelSize}" width="${pixelSize}" height="${pixelSize}" fill="currentColor"/>`;
      }
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${dimension} ${dimension}" width="${dimension}" height="${dimension}">${rects}</svg>`;
}
