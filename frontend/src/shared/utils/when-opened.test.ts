import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useWhenOpened } from './when-opened';

describe('useWhenOpened', () => {
  it('waits until the select is reached by focus or by pointer', () => {
    for (const reach of ['onFocus', 'onPointerEnter'] as const) {
      const hook = renderHook(() => useWhenOpened(''));
      expect(hook.result.current[0]).toBe(false);
      act(() => hook.result.current[1][reach]());
      expect(hook.result.current[0]).toBe(true);
    }
  });

  it('reads at once when the address already names a value', () => {
    expect(renderHook(() => useWhenOpened('gap')).result.current[0]).toBe(true);
  });
});
