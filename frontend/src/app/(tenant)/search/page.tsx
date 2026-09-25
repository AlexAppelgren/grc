'use client';

import { Suspense } from 'react';

import { SearchScreen } from '@/components/search/SearchScreen';
import { LoadingState } from '@/components/ui/States';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /search (SRC-01, SRC-02). The client gate is the registry's entry for the
// destination (playbook 6.2); the server's structured 403 is the enforcer,
// and the screen renders it as the same Restricted screen. The screen reads
// its filters from the URL, which Next serves through a suspense boundary.
const SEARCH = findDestination('search');

export default function SearchPage() {
  return (
    <RequirePermission anyOf={SEARCH?.anyOfPermissions ?? []}>
      <Suspense fallback={<LoadingState rows={3} />}>
        <SearchScreen />
      </Suspense>
    </RequirePermission>
  );
}
