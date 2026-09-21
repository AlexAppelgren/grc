'use client';

import { Suspense } from 'react';

import { RoadmapScreen } from '@/components/home/RoadmapScreen';
import { LoadingState } from '@/components/ui/States';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// /roadmap (design/screens/tenant-roadmap.html; HOM-03, FP-03). The client
// gate is the registry's entry for the destination (playbook 6.2); the
// server's structured 403 is the enforcer. The screen reads its `kind`
// filter from the URL, which Next serves through a suspense boundary.
const ROADMAP = findDestination('roadmap');

export default function RoadmapPage() {
  return (
    <RequirePermission anyOf={ROADMAP?.anyOfPermissions ?? []}>
      <Suspense fallback={<LoadingState rows={3} />}>
        <RoadmapScreen />
      </Suspense>
    </RequirePermission>
  );
}
