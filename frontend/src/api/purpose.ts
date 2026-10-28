/**
 * In-memory purpose-of-access management for VELORA.
 *
 * Strict constraint:
 * Purpose data MUST remain in memory only.
 * NEVER persist to localStorage, sessionStorage, cookies, or any persistent storage.
 * (MASTER_PROMPT.md §6.3 & §13 Step C2)
 */

const casePurposes = new Map<string, string>();

/**
 * Validates and records access purpose for a specific case.
 * Enforces the required minimum 5 character rule.
 */
export function setCasePurpose(caseId: string, purpose: string): void {
  if (!caseId || caseId.trim().length === 0) {
    throw new Error('Case ID cannot be empty');
  }

  const trimmed = purpose ? purpose.trim() : '';
  if (trimmed.length < 5) {
    throw new Error('Access purpose must be at least 5 characters');
  }

  casePurposes.set(caseId.trim(), trimmed);
}

/**
 * Retrieves the in-memory access purpose for a given case.
 * Returns null if no purpose has been set in the current session.
 */
export function getCasePurpose(caseId: string): string | null {
  if (!caseId) return null;
  return casePurposes.get(caseId.trim()) ?? null;
}

/**
 * Removes the in-memory access purpose for a given case.
 */
export function removeCasePurpose(caseId: string): void {
  if (caseId) {
    casePurposes.delete(caseId.trim());
  }
}

/**
 * Clears all in-memory access purposes (e.g. on logout).
 */
export function clearCasePurposes(): void {
  casePurposes.clear();
}

/**
 * Extracts case ID from standard case-scoped endpoint paths.
 * E.g., "/cases/123e4567-e89b-12d3-a456-426614174000/sessions" -> "123e4567-e89b-12d3-a456-426614174000"
 * Returns null for non-case-scoped paths like "/cases", "/health", "/auth/login".
 */
export function extractCaseIdFromPath(path: string): string | null {
  if (!path) return null;

  // Match /cases/{caseId} where caseId is not followed immediately by another resource root
  // e.g. /cases/abc-123 or /cases/abc-123/witnesses
  const match = path.match(/(?:^|\/)cases\/([0-9a-zA-Z_-]+)(?:\/|$|\?)/);
  if (match && match[1] && match[1] !== 'undefined') {
    return match[1];
  }

  return null;
}
