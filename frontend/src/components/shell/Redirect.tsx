'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

// Sends the person on once a page knows where they belong (the console's
// landing, Today for platform staff). Replaced, never pushed, so Back does not
// return to a page that only forwards; nothing renders meanwhile.
export function Redirect({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(to);
  }, [router, to]);
  return null;
}
