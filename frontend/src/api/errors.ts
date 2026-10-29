import type { ApiErrorCode, ApiErrorEnvelope } from './types';

/**
 * Custom error class for all VELORA API interactions.
 * Preserves HTTP status, documented backend error code, details dictionary,
 * and network failure status without inventing fake codes.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: ApiErrorCode | string;
  readonly details?: Record<string, unknown>;
  readonly isNetworkError: boolean;

  constructor(params: {
    message: string;
    status: number;
    code?: ApiErrorCode | string;
    details?: Record<string, unknown>;
    isNetworkError?: boolean;
  }) {
    super(params.message);
    this.name = 'ApiError';
    this.status = params.status;
    this.code = params.code;
    this.details = params.details;
    this.isNetworkError = Boolean(params.isNetworkError);

    // Maintain proper prototype chain for instanceof checks
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

/**
 * Type guard for ApiError.
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * Safely parse backend HTTP error response.
 * If the response body conforms to {"error": {"code": "...", "message": "...", "details": {...}}},
 * extracts those fields directly. Otherwise falls back to HTTP status text without inventing codes.
 */
export function parseErrorResponse(response: Response, rawBody: string): ApiError {
  const status = response.status;
  const statusText = response.statusText || `HTTP ${status}`;

  if (!rawBody || rawBody.trim().length === 0) {
    return new ApiError({
      message: statusText,
      status,
    });
  }

  try {
    const parsed = JSON.parse(rawBody) as unknown;

    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'error' in parsed &&
      typeof (parsed as ApiErrorEnvelope).error === 'object' &&
      (parsed as ApiErrorEnvelope).error !== null
    ) {
      const errorObj = (parsed as ApiErrorEnvelope).error;
      const message =
        typeof errorObj.message === 'string' && errorObj.message.trim().length > 0
          ? errorObj.message
          : statusText;
      const code = typeof errorObj.code === 'string' ? errorObj.code : undefined;
      const details =
        typeof errorObj.details === 'object' && errorObj.details !== null
          ? (errorObj.details as Record<string, unknown>)
          : undefined;

      return new ApiError({
        message,
        status,
        code,
        details,
      });
    }

    // JSON was parsed but does not follow the standard envelope
    return new ApiError({
      message: statusText,
      status,
      details: typeof parsed === 'object' && parsed !== null ? (parsed as Record<string, unknown>) : undefined,
    });
  } catch {
    // Non-JSON response (e.g. plain text, HTML error page from proxy)
    return new ApiError({
      message: rawBody.length > 200 ? `${rawBody.slice(0, 200)}...` : rawBody,
      status,
    });
  }
}

/**
 * Convert an unexpected network error (e.g. fetch TypeError) into an ApiError.
 * Crucially, does NOT label client network failures with backend error codes (e.g. INTERNAL or ML_UNAVAILABLE).
 */
export function createNetworkError(error: unknown): ApiError {
  const message =
    error instanceof Error && error.message ? error.message : 'Network request failed';

  return new ApiError({
    message,
    status: 0,
    isNetworkError: true,
  });
}
