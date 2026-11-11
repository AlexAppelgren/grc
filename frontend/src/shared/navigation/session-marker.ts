import { isDemoFrame } from '@/features/demo/frame';

/**
 * A cookie that says this browser holds a session, and nothing more. The
 * session itself stays where it was (DECISIONS D-06): the access token in
 * memory, the refresh token in an HttpOnly cookie on the API's host, which the
 * web server never sees. So the web server could not tell a signed-in person
 * from a visitor, and the app host's front door had one answer for both: the
 * gate's waiting text. With this hint it answers a visitor with the public page
 * (shared/navigation/hosts.ts). It carries no secret and grants nothing: a
 * forged or stale one shows the gate, which asks the API as before, and a
 * missing one shows the public page, whose Sign in forwards a signed-in person.
 */
export const SESSION_MARKER = 'cw_signed_in';

/** The longest a session may last (SESSION_ABSOLUTE_HOURS_MAX); every refresh renews the hint. */
const MAX_AGE_SECONDS = 24 * 60 * 60;

function write(value: string, maxAge: number): void {
  if (typeof document === 'undefined') return;
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${SESSION_MARKER}=${value}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
}

/** Called whenever the browser is handed an access token. The demo's frame holds no session. */
export function markSignedIn(): void {
  if (!isDemoFrame()) write('1', MAX_AGE_SECONDS);
}

/** Called whenever the token is dropped: a sign-out, or a refresh the server refused. */
export function clearSignedIn(): void {
  if (!isDemoFrame()) write('', 0);
}
