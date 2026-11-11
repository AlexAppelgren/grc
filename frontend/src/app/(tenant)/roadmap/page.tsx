'use client';

import { Suspense } from 'react';

import { AdminGate } from '@/components/admin/AdminGate';
import { RoadmapScreen } from '@/components/home/RoadmapScreen';
import { LoadingState } from '@/components/ui/States';

// /roadmap (design/screens/tenant-roadmap.html; HOM-03, FP-03). The client
// gate is the registry's entry for the destination (playbook 6.2); the
// server's structured 403 is the enforcer. The screen reads its `kind`
// filter from the URL, which Next serves through a suspense boundary.

export default function RoadmapPage() {
  return (
    <AdminGate id="roadmap">
      <Suspense fallback={<LoadingState rows={3} />}>
        <RoadmapScreen />
      </Suspense>
    </AdminGate>
  );
}
