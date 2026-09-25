import { api } from '@/shared/utils/api-client';

import { installDemoClock } from './clock';
import { isDemoFrame } from './frame';
import meta from './recorded-at.json';
import type { DemoRecordings } from './recordings';
import { createReplayAdapter } from './replay';

/**
 * Inside the demo frame, and only there: every request goes to the replay,
 * whatever adapter the caller asked for (Ask asks for fetch), and the clock
 * reads the recording's date. The recordings are their own chunk, so nobody
 * outside the demo downloads them.
 */
export function installDemoModeWhenFramed(): void {
  if (!isDemoFrame()) return;
  installDemoClock(meta.recordedAt);
  const replay = createReplayAdapter(async () => (await import('./recordings.json')).default as unknown as DemoRecordings);
  api.defaults.adapter = replay;
  api.interceptors.request.use((config) => {
    config.adapter = replay;
    return config;
  });
}
