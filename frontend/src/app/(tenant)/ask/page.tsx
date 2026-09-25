'use client';

import { Suspense } from 'react';

import { AskScreen } from '@/components/search/AskScreen';
import { LoadingState } from '@/components/ui/States';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /ask (SRC-03, D-103). The client gate is the registry's entry for the
// destination (playbook 6.2); the server's structured 403 is the enforcer.
// The screen reads its "as of" date from the URL, which Next serves through
// a suspense boundary.
const ASK = findDestination('ask');

export default function AskPage() {
  return (
    <RequirePermission anyOf={ASK?.anyOfPermissions ?? []}>
      <Suspense fallback={<LoadingState rows={3} />}>
        <AskScreen />
      </Suspense>
    </RequirePermission>
  );
}
