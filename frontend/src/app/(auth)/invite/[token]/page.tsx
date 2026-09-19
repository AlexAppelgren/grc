import type { Metadata } from 'next';

import { InvitationScreen } from '@/components/auth/InvitationScreen';

// The invitation token sits in the address, so this route sends no Referer at
// all (chunk 1 review, security item 1): nothing downstream — an analytics
// beacon, an image host, a link the person clicks — ever sees the token.
// Next renders this as <meta name="referrer" content="no-referrer">. The
// screen itself replaces the address with /enrol as soon as the code step
// begins, so the token does not linger in history either.
export const metadata: Metadata = { referrer: 'no-referrer' };

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <InvitationScreen token={token} />;
}
