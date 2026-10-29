/**
 * Pure TypeScript binary PDF 1.4 generator.
 * Emits genuine, standards-compliant Adobe PDF 1.4 binary documents (MIME application/pdf)
 * complete with object dictionary catalog, xref table, and trailer.
 */

export interface PDFPacketData {
  caseNumber: string;
  sessionId: string;
  disclaimer: string;
  sha256Hash: string;
  language: string;
  timestamp: string;
  attributes: Array<{ region: string; key: string; value: string; confidence: string }>;
  aiAssumed: Array<{ key: string; note: string }>;
  modelVersions: Record<string, string>;
  legalNotice: string;
}

function escapePDFText(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

export function generateBinaryPDF(data: PDFPacketData): Blob {
  const objects: string[] = [];
  const offsets: number[] = [];

  // 1. Catalog
  objects.push(`1 0 obj
<<
  /Type /Catalog
  /Pages 2 0 R
>>
endobj`);

  // 2. Pages
  objects.push(`2 0 obj
<<
  /Type /Pages
  /Kids [3 0 R]
  /Count 1
>>
endobj`);

  // 3. Page (A4: 595.28 x 841.89 pt)
  objects.push(`3 0 obj
<<
  /Type /Page
  /Parent 2 0 R
  /MediaBox [0 0 595.28 841.89]
  /Resources <<
    /Font <<
      /F1 4 0 R
      /F2 5 0 R
    >>
  >>
  /Contents 6 0 R
>>
endobj`);

  // 4. Helvetica
  objects.push(`4 0 obj
<<
  /Type /Font
  /Subtype /Type1
  /BaseFont /Helvetica
>>
endobj`);

  // 5. Helvetica-Bold
  objects.push(`5 0 obj
<<
  /Type /Font
  /Subtype /Type1
  /BaseFont /Helvetica-Bold
>>
endobj`);

  // 6. Content Stream
  // Coordinates in PDF start from bottom-left (0,0) to top-right (595.28, 841.89)
  const streamLines: string[] = [];

  // Top header background banner (#5A250A = 0.353 0.145 0.039)
  streamLines.push(`q`);
  streamLines.push(`0.353 0.145 0.039 rg`);
  streamLines.push(`0 800 595.28 41.89 re f`);
  streamLines.push(`Q`);

  // Disclaimer text in banner (white)
  streamLines.push(`BT`);
  streamLines.push(`/F2 9 Tf`);
  streamLines.push(`1 1 1 rg`);
  streamLines.push(`30 818 Td`);
  streamLines.push(`(${escapePDFText(data.disclaimer.toUpperCase())}) Tj`);
  streamLines.push(`ET`);

  // Document Title
  streamLines.push(`BT`);
  streamLines.push(`/F2 18 Tf`);
  streamLines.push(`0.1 0.1 0.15 rg`);
  streamLines.push(`40 760 Td`);
  streamLines.push(`(VELORA INVESTIGATIVE COURT PACKET) Tj`);
  streamLines.push(`ET`);

  // Subtitle & Session
  streamLines.push(`BT`);
  streamLines.push(`/F1 10 Tf`);
  streamLines.push(`0.4 0.4 0.45 rg`);
  streamLines.push(`40 742 Td`);
  streamLines.push(`(Case: ${escapePDFText(data.caseNumber)}   |   Session: ${escapePDFText(data.sessionId)}   |   Docket Lang: ${escapePDFText(data.language)}) Tj`);
  streamLines.push(`ET`);

  // Divider line
  streamLines.push(`q 0.8 0.8 0.8 RG 1 w 40 730 m 555 730 l S Q`);

  // Section 1: Extraction Attributes
  streamLines.push(`BT`);
  streamLines.push(`/F2 12 Tf`);
  streamLines.push(`0.1 0.1 0.2 rg`);
  streamLines.push(`40 705 Td`);
  streamLines.push(`(1. EXTRACTED WITNESS ATTRIBUTES) Tj`);
  streamLines.push(`ET`);

  let currentY = 685;
  for (const attr of data.attributes) {
    streamLines.push(`BT`);
    streamLines.push(`/F2 10 Tf 0.2 0.2 0.2 rg 50 ${currentY} Td (${escapePDFText(attr.key)}:) Tj ET`);
    streamLines.push(`BT`);
    streamLines.push(`/F1 10 Tf 0.1 0.1 0.1 rg 180 ${currentY} Td (${escapePDFText(attr.value)}) Tj ET`);
    streamLines.push(`BT`);
    streamLines.push(`/F1 9 Tf 0.4 0.4 0.4 rg 420 ${currentY} Td ([Confidence: ${escapePDFText(attr.confidence)}]) Tj ET`);
    currentY -= 18;
  }

  currentY -= 10;
  // Section 2: AI Assumed Unstated Features (R11 Invariant)
  streamLines.push(`BT`);
  streamLines.push(`/F2 12 Tf`);
  streamLines.push(`0.7 0.25 0.1 rg`);
  streamLines.push(`40 ${currentY} Td`);
  streamLines.push(`(2. AI-ASSUMED UNSTATED FEATURES [R11 INVARIANT]) Tj`);
  streamLines.push(`ET`);
  currentY -= 20;

  for (const item of data.aiAssumed) {
    streamLines.push(`BT`);
    streamLines.push(`/F2 10 Tf 0.2 0.2 0.2 rg 50 ${currentY} Td (${escapePDFText(item.key)}:) Tj ET`);
    streamLines.push(`BT`);
    streamLines.push(`/F1 9 Tf 0.3 0.3 0.3 rg 160 ${currentY} Td (${escapePDFText(item.note)}) Tj ET`);
    currentY -= 16;
  }

  currentY -= 10;
  // Section 3: Model Provenance
  streamLines.push(`BT`);
  streamLines.push(`/F2 12 Tf`);
  streamLines.push(`0.1 0.1 0.2 rg`);
  streamLines.push(`40 ${currentY} Td`);
  streamLines.push(`(3. FORENSIC MODEL PROVENANCE) Tj`);
  streamLines.push(`ET`);
  currentY -= 20;

  for (const [k, v] of Object.entries(data.modelVersions)) {
    streamLines.push(`BT`);
    streamLines.push(`/F1 9 Tf 0.3 0.3 0.3 rg 50 ${currentY} Td (${escapePDFText(k)}: ${escapePDFText(v)}) Tj ET`);
    currentY -= 14;
  }

  currentY -= 15;
  // Section 4: Cryptographic Verification Seal
  streamLines.push(`q 0.9 0.9 0.95 rg 40 ${currentY - 55} 515 65 re f 0.7 0.7 0.8 RG 1 w 40 ${currentY - 55} 515 65 re S Q`);
  streamLines.push(`BT`);
  streamLines.push(`/F2 11 Tf 0.1 0.1 0.4 rg 50 ${currentY - 5} Td (4. CRYPTOGRAPHIC VERIFICATION SEAL) Tj`);
  streamLines.push(`ET`);
  streamLines.push(`BT`);
  streamLines.push(`/F1 9 Tf 0.2 0.2 0.2 rg 50 ${currentY - 22} Td (SHA-256 Digest: ${escapePDFText(data.sha256Hash)}) Tj`);
  streamLines.push(`ET`);
  streamLines.push(`BT`);
  streamLines.push(`/F1 8 Tf 0.4 0.4 0.4 rg 50 ${currentY - 38} Td (Timestamp UTC: ${escapePDFText(data.timestamp)}) Tj`);
  streamLines.push(`ET`);

  currentY -= 80;
  // Section 5: Statutory & Legal Custody Notice
  streamLines.push(`BT`);
  streamLines.push(`/F2 8 Tf 0.5 0.1 0.1 rg 40 ${currentY} Td (LEGAL & CUSTODIAL NOTICE:) Tj`);
  streamLines.push(`ET`);
  currentY -= 12;
  streamLines.push(`BT`);
  streamLines.push(`/F1 7.5 Tf 0.3 0.3 0.3 rg 40 ${currentY} Td (${escapePDFText(data.legalNotice)}) Tj`);
  streamLines.push(`ET`);

  const streamContent = streamLines.join('\n');
  const streamLength = new TextEncoder().encode(streamContent).length;

  objects.push(`6 0 obj
<<
  /Length ${streamLength}
>>
stream
${streamContent}
endstream
endobj`);

  // Assemble the PDF file
  let pdf = `%PDF-1.4\n%\xE2\xE3\xCF\xD3\n`;

  for (let i = 0; i < objects.length; i++) {
    offsets.push(new TextEncoder().encode(pdf).length);
    pdf += objects[i] + '\n';
  }

  const xrefOffset = new TextEncoder().encode(pdf).length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) {
    pdf += `${off.toString().padStart(10, '0')} 00000 n \n`;
  }

  pdf += `trailer\n<<\n  /Size ${objects.length + 1}\n  /Root 1 0 R\n>>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  const binaryBytes = new TextEncoder().encode(pdf);
  return new Blob([binaryBytes], { type: 'application/pdf' });
}
