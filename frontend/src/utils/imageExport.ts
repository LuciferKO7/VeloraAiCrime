/**
 * Client-side genuine raster PNG generator using offscreen Canvas.
 * Produces authentic image/png blobs with valid PNG signature (0x89504E470D0A1A0A).
 */

import { generateQRCode } from './qrCode';

export interface ImageExportData {
  caseNumber: string;
  sessionId: string;
  disclaimer: string;
  sha256Hash: string;
  language: string;
  attributes: Array<{ region: string; key: string; value: string; confidence: string }>;
  aiAssumed: Array<{ key: string; note: string }>;
  legalNotice: string;
}

export function generateRasterPNG(data: ImageExportData): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const width = 1200;
    const height = 1500;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      reject(new Error('Canvas 2D context unavailable'));
      return;
    }

    // 1. Dark canvas background
    ctx.fillStyle = '#090a0c';
    ctx.fillRect(0, 0, width, height);

    // 2. Mandatory statutory banner (#5A250A)
    ctx.fillStyle = '#5A250A';
    ctx.fillRect(0, 0, width, 60);

    ctx.fillStyle = '#FFC1AD';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(data.disclaimer.toUpperCase(), width / 2, 38);

    // 3. Document Header
    ctx.textAlign = 'left';
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 32px sans-serif';
    ctx.fillText('VELORA COURT COMPOSITE PACKET', 60, 130);

    ctx.fillStyle = '#95979E';
    ctx.font = '16px monospace';
    ctx.fillText(`CASE: ${data.caseNumber}  ·  SESSION: ${data.sessionId}  ·  DOCKET: ${data.language.toUpperCase()}`, 60, 165);

    // Divider
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(60, 185);
    ctx.lineTo(width - 60, 185);
    ctx.stroke();

    // 4. Center Composite Sketch Frame
    const sketchBoxX = 60;
    const sketchBoxY = 220;
    const sketchBoxW = 480;
    const sketchBoxH = 580;

    ctx.fillStyle = '#14161a';
    ctx.strokeStyle = 'rgba(124, 140, 255, 0.4)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(sketchBoxX, sketchBoxY, sketchBoxW, sketchBoxH, 16);
    ctx.fill();
    ctx.stroke();

    // Stylized sketch lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    // Head oval
    ctx.ellipse(sketchBoxX + sketchBoxW / 2, sketchBoxY + 280, 160, 210, 0, 0, Math.PI * 2);
    ctx.stroke();

    // Eyes
    ctx.beginPath();
    ctx.ellipse(sketchBoxX + sketchBoxW / 2 - 60, sketchBoxY + 240, 26, 14, 0, 0, Math.PI * 2);
    ctx.ellipse(sketchBoxX + sketchBoxW / 2 + 60, sketchBoxY + 240, 26, 14, 0, 0, Math.PI * 2);
    ctx.stroke();

    // Arched Eyebrows
    ctx.beginPath();
    ctx.arc(sketchBoxX + sketchBoxW / 2 - 60, sketchBoxY + 225, 30, Math.PI * 1.1, Math.PI * 1.9);
    ctx.arc(sketchBoxX + sketchBoxW / 2 + 60, sketchBoxY + 225, 30, Math.PI * 1.1, Math.PI * 1.9);
    ctx.stroke();

    // Nose
    ctx.beginPath();
    ctx.moveTo(sketchBoxX + sketchBoxW / 2, sketchBoxY + 245);
    ctx.lineTo(sketchBoxX + sketchBoxW / 2 - 8, sketchBoxY + 335);
    ctx.lineTo(sketchBoxX + sketchBoxW / 2 + 12, sketchBoxY + 335);
    ctx.stroke();

    // Mouth
    ctx.beginPath();
    ctx.moveTo(sketchBoxX + sketchBoxW / 2 - 40, sketchBoxY + 390);
    ctx.quadraticCurveTo(sketchBoxX + sketchBoxW / 2, sketchBoxY + 410, sketchBoxX + sketchBoxW / 2 + 40, sketchBoxY + 390);
    ctx.stroke();

    // 5. Attributes Panel on Right
    const panelX = 580;
    const panelY = 220;

    ctx.fillStyle = '#5ad1ff';
    ctx.font = 'bold 20px sans-serif';
    ctx.fillText('CONFIRMED WITNESS ATTRIBUTES', panelX, panelY + 25);

    let attrY = panelY + 65;
    for (const attr of data.attributes) {
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 16px sans-serif';
      ctx.fillText(`${attr.key}:`, panelX, attrY);

      ctx.fillStyle = '#f4f5f7';
      ctx.font = '16px sans-serif';
      ctx.fillText(attr.value, panelX + 130, attrY);

      ctx.fillStyle = '#95979E';
      ctx.font = '14px sans-serif';
      ctx.fillText(`[${attr.confidence}]`, panelX + 380, attrY);

      attrY += 34;
    }

    // AI Assumed unstated
    attrY += 20;
    ctx.fillStyle = '#FF8964';
    ctx.font = 'bold 18px sans-serif';
    ctx.fillText('AI-ASSUMED UNSTATED FEATURES (R11)', panelX, attrY);
    attrY += 35;

    for (const item of data.aiAssumed) {
      ctx.fillStyle = '#FFC1AD';
      ctx.font = 'bold 14px sans-serif';
      ctx.fillText(`${item.key}:`, panelX, attrY);

      ctx.fillStyle = '#A9A9AA';
      ctx.font = '13px sans-serif';
      ctx.fillText(item.note, panelX + 110, attrY);
      attrY += 28;
    }

    // 6. Cryptographic Seal with Scannable QR Code Matrix
    const sealY = 850;
    ctx.fillStyle = '#14161a';
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.beginPath();
    ctx.roundRect(60, sealY, width - 120, 240, 16);
    ctx.fill();
    ctx.stroke();

    // Render genuine QR Code inside seal
    const origin = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : 'http://localhost:5173';
    const qrMatrix = generateQRCode(`${origin}/#trust?verify=${data.sha256Hash}`);
    const qrPixelSize = 5;
    const qrDim = qrMatrix.size * qrPixelSize;
    const qrX = 90;
    const qrY = sealY + (240 - qrDim) / 2;

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(qrX - 8, qrY - 8, qrDim + 16, qrDim + 16);

    ctx.fillStyle = '#000000';
    for (let r = 0; r < qrMatrix.size; r++) {
      for (let c = 0; c < qrMatrix.size; c++) {
        if (qrMatrix.modules[r][c]) {
          ctx.fillRect(qrX + c * qrPixelSize, qrY + r * qrPixelSize, qrPixelSize, qrPixelSize);
        }
      }
    }

    // Seal text
    const textX = qrX + qrDim + 40;
    ctx.fillStyle = '#5ad1ff';
    ctx.font = 'bold 18px sans-serif';
    ctx.fillText('CRYPTOGRAPHIC AUDIT SEAL (SHA-256)', textX, sealY + 60);

    ctx.fillStyle = '#ffffff';
    ctx.font = '14px monospace';
    ctx.fillText(`Digest: ${data.sha256Hash}`, textX, sealY + 100);

    ctx.fillStyle = '#95979E';
    ctx.font = '13px sans-serif';
    ctx.fillText('Deterministic manifest hash chained into immutable session audit log.', textX, sealY + 135);
    ctx.fillText('Scan QR code to verify integrity status in VELORA Trust Center.', textX, sealY + 160);

    // 7. Footer legal disclosure
    ctx.fillStyle = '#6E7179';
    ctx.font = '12px sans-serif';
    ctx.fillText(data.legalNotice, 60, height - 50);

    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error('Failed to generate PNG blob'));
      }
    }, 'image/png');
  });
}
