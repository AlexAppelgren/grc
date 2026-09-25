'use client';

import { Suspense } from 'react';

import { MyWorkScreen } from '@/components/work/MyWorkScreen';
import { LoadingState } from '@/components/ui/States';

// /work (design/screens/tenant-my-work.html; HOM-05). Any member may open it:
// the server filters every row by the reader's own read permissions, so there
// is no client gate. A department opened by its address (`?unit=`) is read
// from the URL, which Next serves through a suspense boundary.
export default function MyWorkPage() {
  return (
    <Suspense fallback={<LoadingState rows={3} />}>
      <MyWorkScreen />
    </Suspense>
  );
}
