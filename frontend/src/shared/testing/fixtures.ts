// Test support: the wire shapes many tests answer with, built once. Each
// builder takes the fields a test cares about; the rest are the plain
// defaults every copy of it used.

/** The session `GET /me` answers for a screen test: a bank in Stockholm, the reader's permissions, nothing pending. */
export function session(permissions: readonly string[] = [], timeZone = 'Europe/Stockholm') {
  return { user: { locale: 'en' }, tenant: { timezone: timeZone }, enrolmentPending: false, permissions: [...permissions] };
}
