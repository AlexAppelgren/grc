'use client';

// Demo mode for a component. Kept apart from frame.ts, which the middleware imports and
// which must therefore hold no React hook.

import { useSyncExternalStore } from 'react';

import { isDemoFrame } from './frame';

// A frame's name stays the same for as long as the app runs in it.
const unchanging = () => () => undefined;

/** Demo mode for a component: off while the server renders and the browser hydrates, so the two agree. */
export function useDemoFrame(): boolean {
  return useSyncExternalStore(unchanging, isDemoFrame, () => false);
}
