/**
 * VELORA API types and contract definitions.
 * Authoritative source: MASTER_PROMPT.md §6.3 & §7
 */

/**
 * Frozen backend error codes per MASTER_PROMPT.md §6.3.
 */
export type ApiErrorCode =
  | 'AUTH_INVALID'
  | 'AUTH_EXPIRED'
  | 'ACCOUNT_LOCKED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'VALIDATION_ERROR'
  | 'PURPOSE_REQUIRED'
  | 'CONFLICT_VERSION'
  | 'LLM_UNAVAILABLE'
  | 'LLM_UNAVAILABLE_LOCAL'
  | 'LLM_SCHEMA_INVALID'
  | 'ML_UNAVAILABLE'
  | 'ML_BUSY'
  | 'SPEECH_UNAVAILABLE'
  | 'RATE_LIMITED'
  | 'INTERNAL';

/**
 * Standard backend error envelope:
 * {"error": {"code": "STRING", "message": "human readable", "details": {}}}
 */
export interface ApiErrorBody {
  code?: ApiErrorCode | string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

/**
 * Request options extending standard fetch RequestInit.
 */
export interface RequestOptions extends RequestInit {
  /**
   * Explicit case identifier for case-scoped requests.
   * When provided, client looks up in-memory purpose for this case.
   */
  caseId?: string;
  /**
   * Explicit purpose override. Must be at least 5 characters if provided.
   */
  purpose?: string;
  /**
   * If true, bypasses attaching Authorization: Bearer <token>.
   */
  skipAuth?: boolean;
}

/**
 * System health response from GET /api/v1/health (MASTER_PROMPT.md §7.1).
 */
export interface HealthResponse {
  status: string;
  db: string;
  ml_service: string;
  speech_service: string;
  llm: {
    gemini?: string;
    ollama?: string;
    [key: string]: unknown;
  };
  time: string;
}

/**
 * User roles per MASTER_PROMPT.md §6.3 role matrix.
 */
export type UserRole = 'investigator' | 'artist' | 'supervisor' | 'auditor' | 'admin';

/**
 * Authenticated user profile summary.
 */
export interface UserSummary {
  id: string;
  username: string;
  role: UserRole;
  full_name?: string;
}

/**
 * Authentication response from POST /api/v1/auth/login.
 */
export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserSummary;
}
