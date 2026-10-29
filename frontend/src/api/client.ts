import { createNetworkError, parseErrorResponse } from './errors';
import { extractCaseIdFromPath, getCasePurpose } from './purpose';
import type { HealthResponse, LoginResponse, RequestOptions } from './types';

/**
 * Genuine request lifecycle telemetry collected by ApiClient.
 */
export interface RequestTelemetryRecord {
  endpoint: string;
  method: string;
  latencyMs: number;
  statusCode: number;
  success: boolean;
  timestamp: string;
  llmInfo?: {
    provider?: string;
    model?: string;
    latency_ms?: number;
    route_reason?: string;
  };
}

/**
 * Default documented backend API base path.
 * In development, Vite dev server proxies /api to http://localhost:8000.
 */
export const DEFAULT_API_BASE = '/api/v1';

export class ApiClient {
  private baseUrl: string;
  private authToken: string | null = null;
  private telemetryHistory: RequestTelemetryRecord[] = [];
  private telemetryListeners: Set<(record: RequestTelemetryRecord) => void> = new Set();

  constructor(baseUrl: string = DEFAULT_API_BASE) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  /**
   * Set or clear the in-memory JWT authentication token.
   */
  public setToken(token: string | null): void {
    this.authToken = token ? token.trim() : null;
  }

  /**
   * Retrieve the current in-memory JWT authentication token.
   */
  public getToken(): string | null {
    return this.authToken;
  }

  /**
   * Core request dispatcher.
   */
  public async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const {
      caseId,
      purpose,
      skipAuth = false,
      headers: userHeaders,
      body,
      ...customConfig
    } = options;

    const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${this.baseUrl}${normalizedEndpoint}`;

    const headers = new Headers(userHeaders);

    // Default Accept header
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }

    // Attach Bearer token when available and not explicitly skipped
    if (!skipAuth && this.authToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${this.authToken}`);
    }

    // Resolve and attach X-Access-Purpose for case-scoped operations
    let resolvedPurpose: string | null = null;
    if (purpose && purpose.trim().length >= 5) {
      resolvedPurpose = purpose.trim();
    } else {
      const resolvedCaseId = caseId || extractCaseIdFromPath(normalizedEndpoint);
      if (resolvedCaseId) {
        resolvedPurpose = getCasePurpose(resolvedCaseId);
      }
    }

    if (resolvedPurpose && !headers.has('X-Access-Purpose')) {
      headers.set('X-Access-Purpose', resolvedPurpose);
    }

    // Attach X-Data-Mode and enforce R11.4 Local-only privacy
    const resolvedDataMode = options.dataMode;
    if (resolvedDataMode) {
      headers.set('X-Data-Mode', resolvedDataMode);
      if (resolvedDataMode === 'real') {
        // Enforce that real cases cannot target external cloud endpoints
        if (url.includes('googleapis.com') || url.includes('openai.com') || url.includes('anthropic.com')) {
          throw new Error('LLM_UNAVAILABLE_LOCAL: Local-only privacy invariant (R11.4) forbids cloud routing for real cases.');
        }
      }
    }

    // Handle JSON body
    let finalBody: BodyInit | null | undefined = body as BodyInit | null | undefined;
    if (body !== undefined && body !== null && !(body instanceof FormData) && typeof body === 'object') {
      if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }
      finalBody = JSON.stringify(body);
    }

    let response: Response;
    const startTime = performance.now();
    const method = customConfig.method || 'GET';

    try {
      response = await fetch(url, {
        ...customConfig,
        headers,
        body: finalBody,
      });
    } catch (networkError: unknown) {
      const elapsed = Math.round(performance.now() - startTime);
      this.recordTelemetry({
        endpoint: normalizedEndpoint,
        method,
        latencyMs: elapsed,
        statusCode: 0,
        success: false,
        timestamp: new Date().toISOString(),
      });
      // Genuine network failure: do not fabricate a backend error code
      throw createNetworkError(networkError);
    }

    const elapsed = Math.round(performance.now() - startTime);
    const rawText = await response.text();

    if (!response.ok) {
      this.recordTelemetry({
        endpoint: normalizedEndpoint,
        method,
        latencyMs: elapsed,
        statusCode: response.status,
        success: false,
        timestamp: new Date().toISOString(),
      });
      throw parseErrorResponse(response, rawText);
    }

    // Handle 204 No Content or empty bodies
    if (response.status === 204 || rawText.trim().length === 0) {
      this.recordTelemetry({
        endpoint: normalizedEndpoint,
        method,
        latencyMs: elapsed,
        statusCode: response.status,
        success: true,
        timestamp: new Date().toISOString(),
      });
      return null as unknown as T;
    }

    try {
      const parsed = JSON.parse(rawText) as T;
      const llmInfo = (parsed && typeof parsed === 'object' && 'llm' in (parsed as Record<string, unknown>))
        ? (parsed as Record<string, unknown>).llm as RequestTelemetryRecord['llmInfo']
        : undefined;

      this.recordTelemetry({
        endpoint: normalizedEndpoint,
        method,
        latencyMs: elapsed,
        statusCode: response.status,
        success: true,
        timestamp: new Date().toISOString(),
        llmInfo,
      });

      return parsed;
    } catch {
      this.recordTelemetry({
        endpoint: normalizedEndpoint,
        method,
        latencyMs: elapsed,
        statusCode: response.status,
        success: true,
        timestamp: new Date().toISOString(),
      });
      // If response was 200 OK but body wasn't JSON, return raw text
      return rawText as unknown as T;
    }
  }

  private recordTelemetry(record: RequestTelemetryRecord): void {
    this.telemetryHistory.push(record);
    if (this.telemetryHistory.length > 50) {
      this.telemetryHistory.shift();
    }
    this.telemetryListeners.forEach((listener) => {
      try {
        listener(record);
      } catch {
        // ignore listener errors
      }
    });
  }

  public getTelemetryHistory(): RequestTelemetryRecord[] {
    return [...this.telemetryHistory];
  }

  public getLatestTelemetry(endpointSubstring?: string): RequestTelemetryRecord | null {
    if (!endpointSubstring) {
      return this.telemetryHistory[this.telemetryHistory.length - 1] || null;
    }
    for (let i = this.telemetryHistory.length - 1; i >= 0; i--) {
      if (this.telemetryHistory[i].endpoint.includes(endpointSubstring)) {
        return this.telemetryHistory[i];
      }
    }
    return null;
  }

  public addTelemetryListener(listener: (rec: RequestTelemetryRecord) => void): () => void {
    this.telemetryListeners.add(listener);
    return () => this.telemetryListeners.delete(listener);
  }

  public get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  public post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'POST', body: body as BodyInit });
  }

  public put<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PUT', body: body as BodyInit });
  }

  public patch<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'PATCH', body: body as BodyInit });
  }

  public delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }

  /**
   * GET /api/v1/health (MASTER_PROMPT.md §7.1)
   */
  public getHealth(options?: RequestOptions): Promise<HealthResponse> {
    return this.get<HealthResponse>('/health', { ...options, skipAuth: true });
  }

  /**
   * POST /api/v1/auth/login (MASTER_PROMPT.md §7.1)
   */
  public async login(
    credentials: { username: string; password: string },
    options?: RequestOptions
  ): Promise<LoginResponse> {
    const response = await this.post<LoginResponse>('/auth/login', credentials, {
      ...options,
      skipAuth: true,
    });
    if (response && response.access_token) {
      this.setToken(response.access_token);
    }
    return response;
  }
}

/**
 * Shared singleton instance for the VELORA application.
 */
export const apiClient = new ApiClient();
