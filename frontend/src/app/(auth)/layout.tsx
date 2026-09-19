import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AuthFrame } from '@/components/auth/AuthFrame';

// The auth route group: sign-in, invitation landing and enrolment, outside
// the tenant shell and its session gate.
//
// `referrer: no-referrer` for the whole group: the invitation route carries a
// single-use secret in its path, so no outbound request from any auth page may
// leak the URL in a Referer header. The invitation page keeps its own copy of
// this metadata, and it drops the token from the address bar with
// history.replaceState before the open request fires.
export const metadata: Metadata = { referrer: 'no-referrer' };

export default function AuthLayout({ children }: { children: ReactNode }) {
  return <AuthFrame>{children}</AuthFrame>;
}
