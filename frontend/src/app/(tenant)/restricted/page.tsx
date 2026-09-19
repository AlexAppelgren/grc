'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { RestrictedScreen } from '@/shared/navigation/require-permission';

// /restricted: the quiet Restricted screen as a destination, for a link a
// gate or a server 403 sends someone to. `code` and `needs` come along as
// query parameters so the reference and the missing grant still show.
function Restricted() {
  const params = useSearchParams();
  const code = params.get('code') ?? undefined;
  const needs = params.get('needs') ?? undefined;
  return <RestrictedScreen code={code} requiredPermission={needs} />;
}

export default function RestrictedPage() {
  return (
    <Suspense fallback={null}>
      <Restricted />
    </Suspense>
  );
}
