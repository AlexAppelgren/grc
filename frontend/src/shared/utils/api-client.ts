import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';

// The single axios instance (playbook 2.3, 6.1). Never a second one, never
// raw fetch for API calls. Sessions per DECISIONS D-06: the access token lives
// in memory only, the rotating refresh token in an HttpOnly cookie that the
// browser sends to the refresh endpoint with `withCredentials`.

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** Version of the record being written; sent as `If-Match` so a stale write is refused (playbook 4.3). */
    version?: number | string;
    /** Set on the refresh call itself and on session-bootstrap calls: never triggers another refresh. */
    skipAuthRefresh?: boolean;
    /** Internal: the request has already been retried once after a refresh. */
    retriedAfterRefresh?: boolean;
  }
}

export const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_URL ?? '';
export const REFRESH_PATH = '/api/v1/auth/refresh';

// Session bootstrap: the only calls a browser makes before it holds an access
// token. They never carry a bearer, and a 401 from them is an answer, not a
// signal to refresh. Paths are the backend's `identity` routes.
export const SESSION_BOOTSTRAP_PATHS: readonly RegExp[] = [
  /^\/api\/v1\/auth\/refresh$/,
  /^\/api\/v1\/auth\/invitations\/[^/]+(\/.*)?$/,
  /^\/api\/v1\/auth\/code(\/.*)?$/,
  /^\/api\/v1\/auth\/passkeys\/(register|authenticate)\/(begin|finish)$/,
  /^\/api\/v1\/auth\/enrol(\/.*)?$/,
];

interface TokenStore {
  get(): string | null;
  set(token: string): void;
  clear(): void;
}

function createTokenStore(): TokenStore {
  let token: string | null = null;
  return {
    get: () => token,
    set: (value) => {
      token = value;
    },
    clear: () => {
      token = null;
    },
  };
}

export const tokenStore: TokenStore = createTokenStore();

export function pathOf(config: AxiosRequestConfig): string {
  const url = config.url ?? '';
  try {
    return new URL(url, config.baseURL || 'http://request.local').pathname;
  } catch {
    return url;
  }
}

export function isSessionBootstrapPath(path: string): boolean {
  return SESSION_BOOTSTRAP_PATHS.some((pattern) => pattern.test(path));
}

const WRITE_METHODS = new Set(['post', 'put', 'patch', 'delete']);

export function isWrite(method: string | undefined): boolean {
  return WRITE_METHODS.has((method ?? 'get').toLowerCase());
}

export function newRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  // Correlation only, never security: a readable fallback for old runtimes.
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: { Accept: 'application/json' },
});

interface RefreshResponse {
  accessToken: string;
}

let refreshInFlight: Promise<string | null> | null = null;
let coldLoadRefreshDone = false;

// One-flight refresh: concurrent 401s share one call, so the rotating refresh
// token is used exactly once per rotation.
export function refreshSession(): Promise<string | null> {
  if (refreshInFlight === null) {
    refreshInFlight = api
      .post<RefreshResponse>(REFRESH_PATH, null, { skipAuthRefresh: true, withCredentials: true })
      .then((response) => {
        tokenStore.set(response.data.accessToken);
        return response.data.accessToken;
      })
      .catch(() => {
        tokenStore.clear();
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// Tests reset the module-level state between cases.
export function resetApiClientForTests(): void {
  tokenStore.clear();
  refreshInFlight = null;
  coldLoadRefreshDone = false;
}

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const path = pathOf(config);
  const bootstrap = isSessionBootstrapPath(path);

  // Cold load: a fresh tab holds no token but may hold a refresh cookie, so
  // the first real request waits for one refresh attempt. Browser only.
  if (!bootstrap && !coldLoadRefreshDone && typeof window !== 'undefined') {
    coldLoadRefreshDone = true;
    if (tokenStore.get() === null) await refreshSession();
  }

  config.headers.set('X-Request-ID', newRequestId());

  if (bootstrap) {
    config.headers.delete('Authorization');
    config.skipAuthRefresh = true;
  } else {
    const token = tokenStore.get();
    if (token !== null) config.headers.set('Authorization', `Bearer ${token}`);
  }

  if (config.version !== undefined && isWrite(config.method)) {
    config.headers.set('If-Match', `"${String(config.version)}"`);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config;
    if (
      config === undefined ||
      error.response?.status !== 401 ||
      config.skipAuthRefresh === true ||
      config.retriedAfterRefresh === true
    ) {
      throw error;
    }
    const token = await refreshSession();
    if (token === null) throw error;
    config.retriedAfterRefresh = true;
    return api.request(config);
  },
);
