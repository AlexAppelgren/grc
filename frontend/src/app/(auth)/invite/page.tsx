import type { Metadata } from 'next';

import { InvitationScreen } from '@/components/auth/InvitationScreen';

// The emailed link is /invite#<token> (security review F29): a fragment is
// never sent to any server, proxy or Referer header, so no request line holds
// the token. The screen reads it from the address, replaces the address with
// /enrol before any request, and keeps the token in React state alone.
// No Referer at all from this route either (chunk 1 review, security item 1):
// Next renders this as <meta name="referrer" content="no-referrer">.
export const metadata: Metadata = { referrer: 'no-referrer' };

export default function InvitePage() {
  return <InvitationScreen />;
}
