// D-122: a person who already holds a passkey is never sent a code, so the
// invitation's code step offers "Sign in and join", and the token waits in this
// tab's sessionStorage across the sign-in, never in a URL. It is dropped when
// the join succeeds or the invitation answers 410. The only token this app keeps
// in storage (F28 otherwise holds it in memory alone).

const HELD_INVITATION = 'cw.invitation';

/** Keeps the token in this tab across the passkey sign-in (D-122). Storage that refuses leaves the link to be opened again. */
export function holdInvitation(token: string): void {
  try {
    window.sessionStorage.setItem(HELD_INVITATION, token);
  } catch {
    // Blocked storage: after signing in, the person opens the link again.
  }
}

/** The token held across sign-in, or null. */
export function heldInvitation(): string | null {
  try {
    return window.sessionStorage.getItem(HELD_INVITATION);
  } catch {
    return null;
  }
}

export function dropHeldInvitation(): void {
  try {
    window.sessionStorage.removeItem(HELD_INVITATION);
  } catch {
    // Nothing was held where storage is blocked.
  }
}
