import { afterEach, describe, expect, it, vi } from 'vitest';

import { leaveForPublicPage } from './leave';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('leaveForPublicPage', () => {
  it('loads the public page as a page load that replaces the current entry', () => {
    const replace = vi.fn();
    vi.stubGlobal('location', { replace });
    leaveForPublicPage();
    expect(replace).toHaveBeenCalledExactlyOnceWith('/welcome');
  });
});
