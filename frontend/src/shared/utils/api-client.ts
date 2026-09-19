import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';

// The single axios instance (playbook 2.3, 6.1). Never a second one, never
// raw fetch for API calls. Sessions per DECISIONS D-06: the access token lives
// in memory only, the rotating refresh token in an HttpOnly cookie that the
// browser sends to the refresh endpoint with `withCredentials`. Step-up per
// playbook 4.2: a 403 `step_up_required` opens the passkey prompt and the
// request is retried once after a fresh assertion.

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** Version of the record being written; sent as `If-Match` so a stale write is refused (playbook 4.3). */
    version?: number | string;
    /** Set on the refresh call itself and on session-bootstrap calls: never triggers another refresh. */
    skipAuthRefresh?: boolean;
    /** Internal: the request has already been retried once after a refresh. */
    retriedAfterRefresh?: boolean;
    /** Internal: the request has already been retried once after a step-up. */
    retriedAfterStepUp?: boolean;
  }
}

export const API_BASE_URL: string = process.env.NEXT_PUBLIC_API_URL ?? '';
export const REFRESH_PATH = '/api/v1/auth/refresh';
export const SIGN_OUT_PATH = '/api/v1/auth/sign-out';
export const STEP_UP_REQUIRED_CODE = 'step_up_required';

// Session bootstrap: the only calls a browser makes before it holds an access
// token. They never carry a bearer, and a 401 from them is an answer, not a
// signal to refresh. Passkey registration is deliberately absent: it runs
// under the enrolment or the full session and carries that token.
export const SESSION_BOOTSTRAP_PATHS: readonly RegExp[] = [
  /^\/api\/v1\/auth\/refresh$/,
  /^\/api\/v1\/auth\/invitations\/(open|verify)$/,
  /^\/api\/v1\/auth\/code\/(request|verify)$/,
  /^\/api\/v1\/auth\/passkeys\/authenticate\/(options|verify)$/,
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

/**
 * What a refresh attempt established. Only `signed-out` is a verdict about the
 * person: `unavailable` says the server did not answer, which is a connection
 * state the caller retries (chunk 1 review, security item 2). Treating it as a
 * sign-out threw people back to /sign-in on a flaky network and lost their work.
 */
export type RefreshOutcome = 'refreshed' | 'signed-out' | 'unavailable';

export interface RefreshResult {
  token: string | null;
  outcome: RefreshOutcome;
  /** The failure behind an `unavailable` outcome, so the screen can render it. */
  error: unknown;
}

let refreshInFlight: Promise<RefreshResult> | null = null;
let coldLoadRefreshDone = false;

// Only a 401 means the rotating refresh cookie is gone and the person is
// signed out. Anything else — no response at all, a 502 from a proxy, a
// gateway timeout — leaves the token in memory alone and is retried.
function refreshFailure(error: unknown): RefreshResult {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    tokenStore.clear();
    return { token: null, outcome: 'signed-out', error: null };
  }
  return { token: tokenStore.get(), outcome: 'unavailable', error };
}

// One-flight refresh: concurrent 401s share one call, so the rotating refresh
// token is used exactly once per rotation.
export function refreshSession(): Promise<RefreshResult> {
  if (refreshInFlight === null) {
    refreshInFlight = api
      .post<RefreshResponse>(REFRESH_PATH, null, { skipAuthRefresh: true, withCredentials: true })
      .then((response): RefreshResult => {
        tokenStore.set(response.data.accessToken);
        return { token: response.data.accessToken, outcome: 'refreshed', error: null };
      })
      .catch(refreshFailure)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

// Cold load: a fresh tab holds no token but may hold a refresh cookie, so the
// first real request waits for one refresh attempt. `useSession` calls this
// too, so an anonymous visitor costs one refresh and no `GET /me`. An
// unreachable server is not an answer, so the attempt is not counted and the
// next call tries again.
export async function ensureColdLoadRefresh(): Promise<RefreshResult> {
  const held = tokenStore.get();
  if (held !== null) return { token: held, outcome: 'refreshed', error: null };
  if (coldLoadRefreshDone) return { token: null, outcome: 'signed-out', error: null };
  coldLoadRefreshDone = true;
  const result = await refreshSession();
  if (result.outcome === 'unavailable') coldLoadRefreshDone = false;
  return result;
}

// Sign-out revokes the session on the server and clears the cookie; the
// client forgets the token and treats the cold load as done, so no refresh
// is attempted against a cookie that is gone.
export async function signOut(): Promise<void> {
  try {
    await api.post(SIGN_OUT_PATH, null, { skipAuthRefresh: true });
  } finally {
    tokenStore.clear();
    coldLoadRefreshDone = true;
  }
}

/** Runs the step-up ceremony; resolves true when a fresh assertion was stored. */
export type StepUpHandler = () => Promise<boolean>;

let stepUpHandler: StepUpHandler | null = null;

export function setStepUpHandler(handler: StepUpHandler | null): void {
  stepUpHandler = handler;
}

export function isStepUpRequired(error: AxiosError): boolean {
  if (error.response?.status !== 403) return false;
  const body: unknown = error.response.data;
  return typeof body === 'object' && body !== null && (body as { code?: unknown }).code === STEP_UP_REQUIRED_CODE;
}

// Tests reset the module-level state between cases.
export function resetApiClientForTests(): void {
  tokenStore.clear();
  refreshInFlight = null;
  coldLoadRefreshDone = false;
  stepUpHandler = null;
}

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const path = pathOf(config);
  const bootstrap = isSessionBootstrapPath(path);

  if (!bootstrap && typeof window !== 'undefined') await ensureColdLoadRefresh();

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
    if (config === undefined) throw error;

    if (error.response?.status === 401 && config.skipAuthRefresh !== true && config.retriedAfterRefresh !== true) {
      // Only a refreshed session is worth retrying on: a refresh that could
      // not reach the server leaves the original 401 as the answer.
      const { outcome, token } = await refreshSession();
      if (outcome !== 'refreshed' || token === null) throw error;
      config.retriedAfterRefresh = true;
      return api.request(config);
    }

    if (isStepUpRequired(error) && config.retriedAfterStepUp !== true && stepUpHandler !== null) {
      const confirmed = await stepUpHandler();
      if (!confirmed) throw error;
      config.retriedAfterStepUp = true;
      return api.request(config);
    }

    throw error;
  },
);
