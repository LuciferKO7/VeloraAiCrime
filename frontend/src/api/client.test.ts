import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ApiClient } from './client';
import { ApiError, isApiError } from './errors';
import {
  setCasePurpose,
  getCasePurpose,
  clearCasePurposes,
  extractCaseIdFromPath,
} from './purpose';

describe('ApiClient & API Foundation', () => {
  let client: ApiClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    client = new ApiClient('/api/v1');
    clearCasePurposes();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    clearCasePurposes();
  });

  describe('Authentication Header Handling', () => {
    it('attaches Bearer token when a valid token is set', async () => {
      client.setToken('valid.jwt.token');

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({ status: 'ok' })),
      });
      global.fetch = mockFetch;

      await client.get('/cases');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.get('Authorization')).toBe('Bearer valid.jwt.token');
    });

    it('does not attach Bearer token when skipAuth is true', async () => {
      client.setToken('valid.jwt.token');

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({ status: 'ok' })),
      });
      global.fetch = mockFetch;

      await client.get('/health', { skipAuth: true });

      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.has('Authorization')).toBe(false);
    });

    it('does not attach Bearer token when token is null', async () => {
      client.setToken(null);

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({ status: 'ok' })),
      });
      global.fetch = mockFetch;

      await client.get('/cases');

      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.has('Authorization')).toBe(false);
    });
  });

  describe('Purpose-of-Access Header & In-Memory Scoping', () => {
    it('rejects purposes with fewer than 5 characters', () => {
      expect(() => setCasePurpose('case-1', 'four')).toThrow(
        /at least 5 characters/i
      );
      expect(() => setCasePurpose('case-1', '   ')).toThrow(
        /at least 5 characters/i
      );
    });

    it('rejects empty case ID', () => {
      expect(() => setCasePurpose('', 'Valid reason')).toThrow(
        /case id cannot be empty/i
      );
    });

    it('stores and retrieves purpose in memory only without touching web storage', () => {
      const caseId = 'case-uuid-101';
      const purpose = 'Witness interview for case 101';

      setCasePurpose(caseId, purpose);
      expect(getCasePurpose(caseId)).toBe(purpose);

      // Verify no persistence in localStorage or sessionStorage
      expect(window.localStorage.getItem(caseId)).toBeNull();
      expect(window.sessionStorage.getItem(caseId)).toBeNull();
    });

    it('extracts case ID from standard case-scoped paths', () => {
      expect(extractCaseIdFromPath('/cases/550e8400-e29b-41d4-a716-446655440000')).toBe(
        '550e8400-e29b-41d4-a716-446655440000'
      );
      expect(
        extractCaseIdFromPath('/cases/550e8400-e29b-41d4-a716-446655440000/witnesses')
      ).toBe('550e8400-e29b-41d4-a716-446655440000');
      expect(extractCaseIdFromPath('/cases')).toBeNull();
      expect(extractCaseIdFromPath('/health')).toBeNull();
      expect(extractCaseIdFromPath('/auth/login')).toBeNull();
    });

    it('attaches X-Access-Purpose when request path matches a case with an active purpose', async () => {
      const caseId = 'case-alpha';
      setCasePurpose(caseId, 'Reviewing composite progression');

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({ id: caseId })),
      });
      global.fetch = mockFetch;

      await client.get(`/cases/${caseId}/sessions`);

      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.get('X-Access-Purpose')).toBe('Reviewing composite progression');
    });

    it('attaches X-Access-Purpose when explicit caseId option is supplied', async () => {
      const caseId = 'case-beta';
      setCasePurpose(caseId, 'Evaluating forensic statements');

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({ ok: true })),
      });
      global.fetch = mockFetch;

      await client.post('/custom-endpoint', {}, { caseId });

      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.get('X-Access-Purpose')).toBe('Evaluating forensic statements');
    });

    it('does not attach X-Access-Purpose when no purpose has been recorded', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: () => Promise.resolve(JSON.stringify({ id: 'case-unauthorized' })),
      });
      global.fetch = mockFetch;

      await client.get('/cases/case-unauthorized');

      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.has('X-Access-Purpose')).toBe(false);
    });

    it('clears all in-memory purposes when requested', () => {
      setCasePurpose('case-1', 'Valid purpose for case 1');
      clearCasePurposes();
      expect(getCasePurpose('case-1')).toBeNull();
    });
  });

  describe('Error Response Handling', () => {
    it('parses structured backend error envelope (e.g. 400 PURPOSE_REQUIRED)', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        text: () =>
          Promise.resolve(
            JSON.stringify({
              error: {
                code: 'PURPOSE_REQUIRED',
                message: 'Case-scoped requests require X-Access-Purpose header',
                details: { min_length: 5 },
              },
            })
          ),
      });
      global.fetch = mockFetch;

      try {
        await client.get('/cases/case-123');
        expect.unreachable('Should have thrown an ApiError');
      } catch (err: unknown) {
        expect(isApiError(err)).toBe(true);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(400);
        expect(apiErr.code).toBe('PURPOSE_REQUIRED');
        expect(apiErr.message).toBe(
          'Case-scoped requests require X-Access-Purpose header'
        );
        expect(apiErr.details).toEqual({ min_length: 5 });
        expect(apiErr.isNetworkError).toBe(false);
      }
    });

    it('parses structured auth errors (e.g. 401 AUTH_EXPIRED)', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        text: () =>
          Promise.resolve(
            JSON.stringify({
              error: {
                code: 'AUTH_EXPIRED',
                message: 'JWT token expired',
              },
            })
          ),
      });
      global.fetch = mockFetch;

      try {
        await client.get('/cases');
        expect.unreachable('Should have thrown an ApiError');
      } catch (err: unknown) {
        expect(isApiError(err)).toBe(true);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(401);
        expect(apiErr.code).toBe('AUTH_EXPIRED');
        expect(apiErr.isNetworkError).toBe(false);
      }
    });

    it('handles non-JSON or HTML 500 error without inventing backend error codes', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
        text: () => Promise.resolve('<html><body>502 Bad Gateway</body></html>'),
      });
      global.fetch = mockFetch;

      try {
        await client.get('/cases');
        expect.unreachable('Should have thrown an ApiError');
      } catch (err: unknown) {
        expect(isApiError(err)).toBe(true);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(502);
        expect(apiErr.code).toBeUndefined(); // Crucial: no invented code
        expect(apiErr.message).toContain('502 Bad Gateway');
        expect(apiErr.isNetworkError).toBe(false);
      }
    });

    it('handles empty error response gracefully', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        text: () => Promise.resolve(''),
      });
      global.fetch = mockFetch;

      try {
        await client.get('/cases');
        expect.unreachable('Should have thrown an ApiError');
      } catch (err: unknown) {
        expect(isApiError(err)).toBe(true);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(500);
        expect(apiErr.code).toBeUndefined();
        expect(apiErr.message).toBe('Internal Server Error');
      }
    });
  });

  describe('Honest Network Error Handling', () => {
    it('catches network fetch failure without inventing backend error codes', async () => {
      global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

      try {
        await client.get('/health');
        expect.unreachable('Should have thrown an ApiError');
      } catch (err: unknown) {
        expect(isApiError(err)).toBe(true);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(0);
        expect(apiErr.isNetworkError).toBe(true);
        expect(apiErr.code).toBeUndefined(); // Never mislabel as INTERNAL or ML_UNAVAILABLE
        expect(apiErr.message).toBe('Failed to fetch');
      }
    });
  });

  describe('Successful and Empty Response Handling', () => {
    it('returns null on 204 No Content', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        statusText: 'No Content',
        text: () => Promise.resolve(''),
      });
      global.fetch = mockFetch;

      const result = await client.delete('/cases/case-123/access/user-456');
      expect(result).toBeNull();
    });

    it('returns parsed JSON for successful calls', async () => {
      const expectedHealth = {
        status: 'ok',
        db: 'ok',
        ml_service: 'ok',
        speech_service: 'ok',
        llm: { gemini: 'ok', ollama: 'ok' },
        time: '2026-10-28T12:00:00Z',
      };

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: 'OK',
        text: () => Promise.resolve(JSON.stringify(expectedHealth)),
      });
      global.fetch = mockFetch;

      const health = await client.getHealth();
      expect(health).toEqual(expectedHealth);
      expect(mockFetch.mock.calls[0][0]).toBe('/api/v1/health');
    });

    it('login sets auth token and returns typed response', async () => {
      const loginPayload = {
        access_token: 'header.payload.signature',
        token_type: 'Bearer',
        expires_in: 3600,
        user: {
          id: 'u-1',
          username: 'officer1',
          role: 'investigator' as const,
        },
      };

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: 'OK',
        text: () => Promise.resolve(JSON.stringify(loginPayload)),
      });
      global.fetch = mockFetch;

      const res = await client.login({ username: 'officer1', password: 'secretpassword' });
      expect(res).toEqual(loginPayload);
      expect(client.getToken()).toBe('header.payload.signature');
    });
  });

  describe('Local-Only Privacy Invariant Enforcement (R11.4)', () => {
    it('attaches X-Data-Mode: real header when dataMode is real', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: 'OK',
        text: () => Promise.resolve(JSON.stringify({ status: 'ok' })),
      });
      global.fetch = mockFetch;

      await client.post('/sessions/s-1/statements', { text: 'test' }, {
        caseId: 'case-real-001',
        dataMode: 'real',
        purpose: 'Court authorized interview',
      });

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [, init] = mockFetch.mock.calls[0];
      const headers = new Headers(init.headers);
      expect(headers.get('X-Data-Mode')).toBe('real');
    });

    it('blocks and throws error if cloud endpoint is targeted for real cases', async () => {
      const cloudClient = new ApiClient('https://generativelanguage.googleapis.com/v1');
      await expect(
        cloudClient.post('/models/gemini:generateContent', {}, {
          dataMode: 'real',
          purpose: 'Witness transcription',
        })
      ).rejects.toThrow('LLM_UNAVAILABLE_LOCAL');
    });
  });
});
