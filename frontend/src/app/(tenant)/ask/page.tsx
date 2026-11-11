'use client';

import { Suspense } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { AskScreen } from '@/components/search/AskScreen';
import { LoadingState } from '@/components/ui/States';

// /ask (SRC-03, D-104). The client gate is the registry's entry for the
// destination (playbook 6.2); the server's structured 403 is the enforcer.
// The screen reads its "as of" date from the URL, which Next serves through
// a suspense boundary.

export default function AskPage() {
  return (
    <AdminGate id="ask">
      <Suspense fallback={<LoadingState rows={3} />}>
        <AskScreen />
      </Suspense>
    </AdminGate>
  );
}
