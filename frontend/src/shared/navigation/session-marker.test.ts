import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DEMO_FRAME_NAME } from '@/features/demo/frame';
import { tokenStore } from '@/shared/utils/api-client';

import { clearSignedIn, markSignedIn, SESSION_MARKER } from './session-marker';

// The hint the web server reads to choose the app host's front door
// (shared/navigation/hosts.ts). jsdom keeps a real cookie jar, so the tests
// read what a browser would send.

function marker(): string | undefined {
  return document.cookie
    .split('; ')
    .find((pair) => pair.startsWith(`${SESSION_MARKER}=`))
    ?.split('=')[1];
}

beforeEach(() => {
  clearSignedIn();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.name = '';
  tokenStore.clear();
});

describe('the session marker', () => {
  it('is set and cleared, and holds no secret', () => {
    expect(marker()).toBeUndefined();
    markSignedIn();
    expect(marker()).toBe('1');
    clearSignedIn();
    expect(marker()).toBeUndefined();
  });

  it('is written for the whole host, for a day, and never sent across sites', () => {
    const written = vi.spyOn(document, 'cookie', 'set');
    markSignedIn();
    expect(written).toHaveBeenLastCalledWith(`${SESSION_MARKER}=1; Path=/; Max-Age=86400; SameSite=Lax`);
    clearSignedIn();
    expect(written).toHaveBeenLastCalledWith(`${SESSION_MARKER}=; Path=/; Max-Age=0; SameSite=Lax`);
  });

  it('follows the access token: gaining one sets it, dropping it clears it', () => {
    tokenStore.set('tok');
    expect(marker()).toBe('1');
    tokenStore.clear();
    expect(marker()).toBeUndefined();
  });

  it('is left alone in the demo frame, which holds no session', () => {
    // The public page frames the app under this name, with itself as the parent.
    window.name = DEMO_FRAME_NAME;
    vi.spyOn(window, 'top', 'get').mockReturnValue({} as Window);
    markSignedIn();
    expect(marker()).toBeUndefined();
  });
});
